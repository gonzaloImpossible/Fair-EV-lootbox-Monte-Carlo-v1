"""
Monte Carlo simulator — Proposal 3 multi-collection gacha (Step 3).

One simulation path = one weekly campaign. Each campaign:
    1. starts with the locked inventory from inventory_static.INVENTORY,
    2. sells up to `n_boxes_per_week` boxes,
    3. each box: two-stage pull → auto-buyback offer → inventory update,
    4. ends after the demand cap OR when inventory is exhausted, whichever
       comes first,
    5. settles via the waterfall: cashbox → repay consumed-NFT debt to
       lenders SENIOR → split remaining profit 50/50.

Output is a list of CampaignResult records, one per path. Aggregation +
percentile reporting happen in `_report()` at the bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from inventory_static import (
    INVENTORY, BY_SLUG, TIER_ROLLUP, TOTAL_VALUE_USD,
)
from gacha_config import GachaConfig, VARIANTS


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Snapshot:
    """In-campaign state at a given pull count."""
    pull_idx: int
    cashbox: float
    debt_open: float                    # current $ owed to lenders (net of restocks)
    inventory_total: int                # NFTs currently in pool
    nfts_consumed_total: int            # cumulative consumed (lifetime)
    nfts_restocked_total: int           # cumulative restocked (lifetime)
    restock_events: int                 # cumulative count of restock triggers


@dataclass
class CampaignResult:
    """Outcome of a single simulated campaign (n_pulls_per_campaign pulls)."""

    # Headline cash flows (at end of campaign)
    n_pulls: int
    cashbox: float                      # net cash after payouts + restock costs
    debt: float                         # $ value of NFTs still owed (net of restocks)
    debt_repaid: float                  # min(cashbox, debt)
    debt_shortfall: float               # max(0, debt - cashbox)
    profit: float                       # max(0, cashbox - debt)
    operator_take: float                # profit * operator_share
    lender_pool_cash: float             # debt_repaid + profit * (1 - op_share)

    # Restock activity
    restock_events: int                 # times threshold triggered
    pulls_to_first_restock: Optional[int]   # None if no restock occurred
    pulls_between_restocks: list[int]   # gap between consecutive restocks
    total_restock_cost: float           # $ spent buying NFTs back from market
    nfts_restocked: dict[str, int]      # per-slug count restocked

    # Per-collection tracking (lender-level, cumulative over campaign)
    nfts_consumed: dict[str, int]               # slug → count consumed (lifetime)
    value_consumed: dict[str, float]            # slug → $ floor consumed (lifetime)
    remaining_inventory: dict[str, int]         # slug → count in pool at end
    lender_recovery: dict[str, float]           # slug → total $ recovered
    lender_recovery_ratio: dict[str, float]     # slug → ratio vs initial principal

    # Snapshots taken every cfg.snapshot_interval pulls
    snapshots: list[Snapshot]

    # State flags
    inventory_exhausted: bool                   # campaign ended early (depletion)
    pulls_by_tier: dict[str, int]               # for diagnostics
    accepts_by_tier: dict[str, int]


# =============================================================================
# CORE SIMULATION
# =============================================================================

TIER_NAMES = ("high", "mid", "low")


def _initial_inventory_state() -> dict[str, dict[str, int]]:
    """Fresh per-tier-per-slug NFT counts at the start of a campaign."""
    return {
        tier: {c.slug: c.count_lent for c in TIER_ROLLUP[tier]}
        for tier in TIER_NAMES
    }


def _initial_lent_value_by_slug() -> dict[str, float]:
    return {c.slug: c.lent_value_usd for c in INVENTORY}


def _sample_tier(
    rng: np.random.Generator,
    cfg: GachaConfig,
    inv: dict[str, dict[str, int]],
) -> Optional[str]:
    """Sample a tier from Categorical(p_tier_*), applying the depletion policy
    if the chosen tier has no remaining inventory. Returns None when no tier
    can satisfy the pull (campaign should end)."""
    base_probs = {"high": cfg.p_tier_high, "mid": cfg.p_tier_mid, "low": cfg.p_tier_low}

    # Initial draw
    r = rng.random()
    cum = 0.0
    chosen = None
    for t in TIER_NAMES:
        cum += base_probs[t]
        if r < cum:
            chosen = t
            break
    if chosen is None:
        chosen = TIER_NAMES[-1]

    # Quick path: chosen tier still has inventory
    if sum(inv[chosen].values()) > 0:
        return chosen

    policy = cfg.depleted_tier_policy

    if policy == "end_campaign":
        return None

    if policy == "reroll":
        # Renormalise base_probs over non-empty tiers and resample
        active = [t for t in TIER_NAMES if sum(inv[t].values()) > 0]
        if not active:
            return None
        total = sum(base_probs[t] for t in active)
        r2 = rng.random() * total
        cum2 = 0.0
        for t in active:
            cum2 += base_probs[t]
            if r2 < cum2:
                return t
        return active[-1]

    if policy == "promote":
        # Order: low → mid → high → mid → low
        order = ["high", "mid", "low"]
        idx = order.index(chosen)
        # Try upward first (toward high)
        for j in range(idx - 1, -1, -1):
            if sum(inv[order[j]].values()) > 0:
                return order[j]
        # Then downward
        for j in range(idx + 1, len(order)):
            if sum(inv[order[j]].values()) > 0:
                return order[j]
        return None

    return None  # unreachable


def _sample_nft(
    rng: np.random.Generator,
    tier_inv: dict[str, int],
) -> str:
    """Uniformly sample one NFT slug from a tier's remaining inventory."""
    slugs = list(tier_inv.keys())
    counts = np.array([tier_inv[s] for s in slugs], dtype=np.int64)
    total = counts.sum()
    if total == 0:
        raise RuntimeError("Empty tier passed to _sample_nft (should never happen)")
    r = rng.integers(0, total)
    cum = 0
    for s, c in zip(slugs, counts.tolist()):
        cum += c
        if r < cum:
            return s
    return slugs[-1]


def _try_restock(
    cfg: GachaConfig,
    inv: dict[str, dict[str, int]],
    cashbox: float,
    target_per_slug: dict[str, int],
    slug_to_tier: dict[str, str],
    slug_floor: dict[str, float],
    nfts_restocked: dict[str, int],
) -> tuple[float, int, float]:
    """Attempt to restore every slug back to its target count. Returns the
    (new_cashbox, total_units_restocked, total_cost). If cashbox cannot
    cover the full restock, skips entirely this round."""
    # Total cost to restore everything
    total_cost = 0.0
    shortages: dict[str, int] = {}
    for s, target in target_per_slug.items():
        cur = inv[slug_to_tier[s]][s]
        sh = target - cur
        if sh > 0:
            shortages[s] = sh
            total_cost += sh * slug_floor[s]

    if total_cost == 0:
        return cashbox, 0, 0.0
    if cashbox < total_cost:
        # Can't afford full restock — skip this round
        return cashbox, 0, 0.0

    # Execute
    units = 0
    for s, sh in shortages.items():
        inv[slug_to_tier[s]][s] += sh
        nfts_restocked[s] += sh
        units += sh
    return cashbox - total_cost, units, total_cost


def simulate_campaign(cfg: GachaConfig, rng: np.random.Generator) -> CampaignResult:
    """Run one campaign of `n_pulls_per_campaign` pulls with optional restock."""
    inv = _initial_inventory_state()
    lent_value = _initial_lent_value_by_slug()
    target_per_slug = {c.slug: c.count_lent for c in INVENTORY}
    slug_to_tier    = {c.slug: c.tier for c in INVENTORY}
    slug_floor      = {c.slug: c.floor_usd for c in INVENTORY}

    initial_total      = sum(target_per_slug.values())
    restock_threshold  = initial_total * cfg.restock_threshold

    cashbox = 0.0
    debt    = 0.0  # current outstanding debt (declines on restock)
    nfts_consumed:  dict[str, int]   = {s: 0 for s in lent_value}
    value_consumed: dict[str, float] = {s: 0.0 for s in lent_value}
    nfts_restocked: dict[str, int]   = {s: 0 for s in lent_value}
    pulls_by_tier:  dict[str, int]   = {t: 0 for t in TIER_NAMES}
    accepts_by_tier: dict[str, int]  = {t: 0 for t in TIER_NAMES}

    current_total = initial_total
    restock_events = 0
    total_restock_cost = 0.0
    pulls_at_restocks: list[int] = []
    snapshots: list[Snapshot] = []

    n_pulls = 0
    exhausted = False

    for pull_idx in range(cfg.n_pulls_per_campaign):
        tier = _sample_tier(rng, cfg, inv)
        if tier is None:
            exhausted = True
            break
        slug = _sample_nft(rng, inv[tier])
        nft_floor = slug_floor[slug]

        cashbox += cfg.box_price_usd

        if rng.random() < cfg.p_accept_buyback(tier):
            cashbox -= nft_floor * (1 - cfg.auto_buyback_discount)
            accepts_by_tier[tier] += 1
        else:
            inv[tier][slug]      -= 1
            current_total        -= 1
            nfts_consumed[slug]  += 1
            value_consumed[slug] += nft_floor
            debt                 += nft_floor

        pulls_by_tier[tier] += 1
        n_pulls += 1

        # ---- Restock check ----
        if cfg.restock_enabled and current_total < restock_threshold:
            cashbox, units, cost = _try_restock(
                cfg, inv, cashbox, target_per_slug,
                slug_to_tier, slug_floor, nfts_restocked,
            )
            if units > 0:
                current_total      += units
                total_restock_cost += cost
                debt               -= cost          # restocked NFTs cancel debt
                restock_events     += 1
                pulls_at_restocks.append(pull_idx + 1)

        # ---- Snapshot ----
        if (pull_idx + 1) % cfg.snapshot_interval == 0:
            snapshots.append(Snapshot(
                pull_idx=pull_idx + 1,
                cashbox=cashbox,
                debt_open=debt,
                inventory_total=current_total,
                nfts_consumed_total=sum(nfts_consumed.values()),
                nfts_restocked_total=sum(nfts_restocked.values()),
                restock_events=restock_events,
            ))

    # ---- Settlement waterfall (end of campaign) ----
    # Defensive: debt can go slightly negative if rounding (or if we'd ever
    # over-restock). Clamp to zero before waterfall.
    debt_end = max(0.0, debt)

    debt_repaid      = min(cashbox, debt_end)
    debt_shortfall   = max(0.0, debt_end - cashbox)
    profit           = max(0.0, cashbox - debt_end)
    operator_take    = profit * cfg.operator_revenue_share
    lender_pool_cash = debt_repaid + profit * (1 - cfg.operator_revenue_share)

    # ---- Per-lender recovery ----
    # Per-slug remaining = target − consumed + restocked  (clamped at >=0)
    remaining_inventory = {
        s: max(0, target_per_slug[s] - nfts_consumed[s] + nfts_restocked[s])
        for s in lent_value
    }
    # Per-slug debt at settlement = (target − remaining) × floor
    debt_by_slug = {
        s: max(0, target_per_slug[s] - remaining_inventory[s]) * slug_floor[s]
        for s in lent_value
    }
    total_debt_check = sum(debt_by_slug.values())

    # Debt repayment leg: pro-rata by this lender's $-share of total settlement debt.
    debt_repay_per_slug: dict[str, float] = {}
    for s in lent_value:
        share = debt_by_slug[s] / total_debt_check if total_debt_check > 0 else 0.0
        debt_repay_per_slug[s] = debt_repaid * share

    # Profit-share leg: pro-rata by initial principal.
    lender_profit_pool = profit * (1 - cfg.operator_revenue_share)
    profit_share_per_slug = {
        s: lender_profit_pool * (lent_value[s] / TOTAL_VALUE_USD)
        for s in lent_value
    }

    remaining_value_per_slug = {
        s: remaining_inventory[s] * slug_floor[s] for s in lent_value
    }

    lender_recovery: dict[str, float] = {}
    lender_recovery_ratio: dict[str, float] = {}
    for s in lent_value:
        rec = (debt_repay_per_slug[s]
               + profit_share_per_slug[s]
               + remaining_value_per_slug[s])
        lender_recovery[s] = rec
        lender_recovery_ratio[s] = rec / lent_value[s] if lent_value[s] > 0 else 0.0

    pulls_to_first_restock = pulls_at_restocks[0] if pulls_at_restocks else None
    pulls_between = [
        b - a for a, b in zip(pulls_at_restocks, pulls_at_restocks[1:])
    ]

    return CampaignResult(
        n_pulls=n_pulls,
        cashbox=cashbox,
        debt=debt_end,
        debt_repaid=debt_repaid,
        debt_shortfall=debt_shortfall,
        profit=profit,
        operator_take=operator_take,
        lender_pool_cash=lender_pool_cash,
        restock_events=restock_events,
        pulls_to_first_restock=pulls_to_first_restock,
        pulls_between_restocks=pulls_between,
        total_restock_cost=total_restock_cost,
        nfts_restocked=nfts_restocked,
        nfts_consumed=nfts_consumed,
        value_consumed=value_consumed,
        remaining_inventory=remaining_inventory,
        lender_recovery=lender_recovery,
        lender_recovery_ratio=lender_recovery_ratio,
        snapshots=snapshots,
        inventory_exhausted=exhausted,
        pulls_by_tier=pulls_by_tier,
        accepts_by_tier=accepts_by_tier,
    )


def run_monte_carlo(
    cfg: GachaConfig,
    n_paths: Optional[int] = None,
    seed: Optional[int] = None,
) -> list[CampaignResult]:
    """Run `n_paths` independent campaign simulations under `cfg`."""
    n = n_paths if n_paths is not None else cfg.n_paths
    rng = np.random.default_rng(seed if seed is not None else cfg.seed)
    return [simulate_campaign(cfg, rng) for _ in range(n)]


# =============================================================================
# AGGREGATION / REPORTING
# =============================================================================

def _pct(arr: np.ndarray, p: float) -> float:
    return float(np.percentile(arr, p))


def aggregate(results: list[CampaignResult]) -> dict:
    """Distribution stats across paths."""
    n_pulls        = np.array([r.n_pulls for r in results])
    cashbox        = np.array([r.cashbox for r in results])
    debt           = np.array([r.debt for r in results])
    profit         = np.array([r.profit for r in results])
    op_take        = np.array([r.operator_take for r in results])
    lender_cash    = np.array([r.lender_pool_cash for r in results])
    debt_shortfall = np.array([r.debt_shortfall for r in results])
    exhausted      = np.array([r.inventory_exhausted for r in results])

    # Restock activity
    restock_events     = np.array([r.restock_events for r in results])
    restock_cost       = np.array([r.total_restock_cost for r in results])
    first_restock_pull = np.array([
        r.pulls_to_first_restock if r.pulls_to_first_restock is not None else -1
        for r in results
    ])
    had_restock = first_restock_pull >= 0
    first_restock_pull_obs = first_restock_pull[had_restock]
    all_gaps = np.concatenate([
        np.array(r.pulls_between_restocks, dtype=np.int64)
        for r in results if r.pulls_between_restocks
    ]) if any(r.pulls_between_restocks for r in results) else np.array([], dtype=np.int64)

    slugs = [c.slug for c in INVENTORY]
    cons_count_by_slug = {s: np.array([r.nfts_consumed[s] for r in results]) for s in slugs}
    rest_count_by_slug = {s: np.array([r.nfts_restocked[s] for r in results]) for s in slugs}
    cons_value_by_slug = {s: np.array([r.value_consumed[s] for r in results]) for s in slugs}
    rec_by_slug        = {s: np.array([r.lender_recovery[s] for r in results]) for s in slugs}
    rec_ratio_by_slug  = {s: np.array([r.lender_recovery_ratio[s] for r in results]) for s in slugs}

    pool_recovery = np.array([
        sum(r.lender_recovery.values()) / TOTAL_VALUE_USD for r in results
    ])

    # ---- Snapshot timeline (mean / p5 / p95 across paths, indexed by snapshot index) ----
    # Assumes all paths recorded the same number of snapshots; if some paths
    # ended early there may be fewer — we align on min length.
    if results and results[0].snapshots:
        min_snaps = min(len(r.snapshots) for r in results)
        snap_pull_idx = [results[0].snapshots[i].pull_idx for i in range(min_snaps)]
        def _snap_arr(attr):
            return np.array([[getattr(r.snapshots[i], attr) for i in range(min_snaps)]
                             for r in results])
        snap_cashbox    = _snap_arr("cashbox")
        snap_debt_open  = _snap_arr("debt_open")
        snap_inv_total  = _snap_arr("inventory_total")
        snap_cons_total = _snap_arr("nfts_consumed_total")
        snap_rest_total = _snap_arr("nfts_restocked_total")
        snap_rest_evts  = _snap_arr("restock_events")
        timeline = []
        for i, p in enumerate(snap_pull_idx):
            timeline.append({
                "pull_idx": p,
                "cashbox_mean":   float(snap_cashbox[:, i].mean()),
                "debt_open_mean": float(snap_debt_open[:, i].mean()),
                "inv_total_mean": float(snap_inv_total[:, i].mean()),
                "cons_total_mean":float(snap_cons_total[:, i].mean()),
                "rest_total_mean":float(snap_rest_total[:, i].mean()),
                "restock_evts_mean":float(snap_rest_evts[:, i].mean()),
            })
    else:
        timeline = []

    return {
        "n_paths": len(results),
        "n_pulls":       {"mean": float(n_pulls.mean()),  "p5": _pct(n_pulls, 5),  "p95": _pct(n_pulls, 95)},
        "cashbox":       {"mean": float(cashbox.mean()),  "p5": _pct(cashbox, 5),  "p95": _pct(cashbox, 95)},
        "debt":          {"mean": float(debt.mean()),     "p5": _pct(debt, 5),     "p95": _pct(debt, 95)},
        "profit":        {"mean": float(profit.mean()),   "p5": _pct(profit, 5),   "p95": _pct(profit, 95)},
        "operator_take": {"mean": float(op_take.mean()),  "p5": _pct(op_take, 5),  "p95": _pct(op_take, 95)},
        "lender_cash":   {"mean": float(lender_cash.mean()), "p5": _pct(lender_cash, 5), "p95": _pct(lender_cash, 95)},
        "shortfall_rate": float((debt_shortfall > 0).mean()),
        "exhausted_rate": float(exhausted.mean()),
        "restock": {
            "p_any_restock":       float(had_restock.mean()),
            "events_mean":         float(restock_events.mean()),
            "events_p95":          _pct(restock_events, 95),
            "cost_mean":           float(restock_cost.mean()),
            "first_pull_mean":     float(first_restock_pull_obs.mean()) if first_restock_pull_obs.size else None,
            "first_pull_p5":       _pct(first_restock_pull_obs, 5) if first_restock_pull_obs.size else None,
            "first_pull_p95":      _pct(first_restock_pull_obs, 95) if first_restock_pull_obs.size else None,
            "gap_mean":            float(all_gaps.mean()) if all_gaps.size else None,
            "gap_p5":              _pct(all_gaps, 5) if all_gaps.size else None,
            "gap_p95":             _pct(all_gaps, 95) if all_gaps.size else None,
        },
        "pool_recovery": {
            "mean": float(pool_recovery.mean()),
            "p5":   _pct(pool_recovery, 5),
            "p50":  _pct(pool_recovery, 50),
            "p95":  _pct(pool_recovery, 95),
            "p_below_par": float((pool_recovery < 1.0).mean()),
        },
        "lender_by_slug": {
            s: {
                "cons_count_mean": float(cons_count_by_slug[s].mean()),
                "rest_count_mean": float(rest_count_by_slug[s].mean()),
                "cons_value_mean": float(cons_value_by_slug[s].mean()),
                "p_any_consumed":  float((cons_count_by_slug[s] > 0).mean()),
                "recovery_mean":   float(rec_by_slug[s].mean()),
                "ratio_mean":      float(rec_ratio_by_slug[s].mean()),
                "ratio_p5":        _pct(rec_ratio_by_slug[s], 5),
                "p_below_par":     float((rec_ratio_by_slug[s] < 1.0).mean()),
            }
            for s in slugs
        },
        "timeline": timeline,
    }


def _report(name: str, agg: dict) -> None:
    print(f"\n{'='*100}\n  {name}  (N = {agg['n_paths']:,} paths)\n{'='*100}")

    def row(label, key):
        d = agg[key]
        print(f"  {label:<26s}  mean ${d['mean']:>11,.0f}   "
              f"p5 ${d['p5']:>11,.0f}   p95 ${d['p95']:>11,.0f}")

    print(f"  {'Pulls per campaign':<26s}  mean  {agg['n_pulls']['mean']:>11.0f}   "
          f"p5  {agg['n_pulls']['p5']:>11.0f}   p95  {agg['n_pulls']['p95']:>11.0f}")
    row("Cashbox (end)",        "cashbox")
    row("Debt (end, owed)",     "debt")
    row("Profit",               "profit")
    row("Operator take",        "operator_take")
    row("Lender pool cash",     "lender_cash")
    print(f"  {'Shortfall path rate':<26s}  {agg['shortfall_rate']:.1%}   "
          f"(end-of-campaign cashbox < debt)")
    print(f"  {'Inventory-exhaust rate':<26s}  {agg['exhausted_rate']:.1%}   "
          f"(campaign ended before reaching pull cap)")

    # ---- Restock activity ----
    r = agg["restock"]
    print(f"\n  Restock:")
    print(f"    {'P(any restock)':<24s}  {r['p_any_restock']:.1%}")
    print(f"    {'restock events':<24s}  mean {r['events_mean']:>5.2f}   "
          f"p95 {int(r['events_p95']):>4d}")
    print(f"    {'$ spent on restock':<24s}  mean ${r['cost_mean']:>10,.0f}")
    if r["first_pull_mean"] is not None:
        print(f"    {'pulls→1st restock':<24s}  mean {r['first_pull_mean']:>5.0f}   "
              f"p5 {r['first_pull_p5']:>4.0f}   p95 {r['first_pull_p95']:>4.0f}")
    if r["gap_mean"] is not None:
        print(f"    {'pulls between restocks':<24s}  mean {r['gap_mean']:>5.0f}   "
              f"p5 {r['gap_p5']:>4.0f}   p95 {r['gap_p95']:>4.0f}")

    # ---- Recovery ----
    pr = agg["pool_recovery"]
    print(f"\n  Pool lender recovery ratio:  mean {pr['mean']:.1%}   "
          f"p5 {pr['p5']:.1%}   p50 {pr['p50']:.1%}   p95 {pr['p95']:.1%}   "
          f"P(< par) {pr['p_below_par']:.1%}")

    # ---- Snapshot timeline ----
    if agg["timeline"]:
        print(f"\n  Snapshot timeline (mean across paths):")
        print(f"    {'pull':>5s}  {'inv':>5s}  {'consumed':>9s}  "
              f"{'restocked':>10s}  {'restocks':>9s}  {'cashbox':>10s}  "
              f"{'debt_open':>10s}")
        for t in agg["timeline"]:
            print(f"    {t['pull_idx']:>5d}  {t['inv_total_mean']:>5.1f}  "
                  f"{t['cons_total_mean']:>9.1f}  {t['rest_total_mean']:>10.1f}  "
                  f"{t['restock_evts_mean']:>9.2f}  ${t['cashbox_mean']:>8,.0f}  "
                  f"${t['debt_open_mean']:>8,.0f}")

    # ---- Per-lender ----
    print(f"\n  Per-lender outcomes (cumulative over the campaign):")
    print(f"    {'collection':<28s} {'lent':>4s}  {'cons':>5s}  {'rest':>5s}  "
          f"{'$cons':>8s}  {'rcvr$':>8s}  {'ratio':>6s} {'P<1':>5s}")
    for c in INVENTORY:
        d = agg["lender_by_slug"][c.slug]
        print(f"    {c.display_name:<28s} {c.count_lent:>4d}  "
              f"{d['cons_count_mean']:>5.1f}  {d['rest_count_mean']:>5.1f}  "
              f"${d['cons_value_mean']:>6,.0f}  ${d['recovery_mean']:>6,.0f}  "
              f"{d['ratio_mean']:>5.1%} {d['p_below_par']:>4.1%}")
    print("    (cons = NFTs consumed; rest = NFTs restocked from market;")
    print("     rcvr$ = mean $ recovered at settlement; ratio = recovery / lent$)")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import time

    N_PATHS_OVERRIDE = 1000   # 1k paths × 1k pulls = 1M events/variant

    print(f"Inventory: {sum(c.count_lent for c in INVENTORY)} NFTs across "
          f"{len(INVENTORY)} collections, ${TOTAL_VALUE_USD:,.0f} principal.")
    print(f"Restock: enabled at <50% of pool (37 NFTs).  "
          f"Pulls per campaign: 1000.  Snapshots every 200 pulls.\n")

    for name, cfg in VARIANTS.items():
        t0 = time.time()
        results = run_monte_carlo(cfg, n_paths=N_PATHS_OVERRIDE)
        elapsed = time.time() - t0
        agg = aggregate(results)
        _report(f"VARIANT: {name}  (box ${cfg.box_price_usd:,.0f}, "
                f"{cfg.n_pulls_per_campaign} pulls/campaign, "
                f"buyback_scale {cfg.buyback_acceptance_scale:.2f})", agg)
        print(f"\n  [sim took {elapsed:.2f}s]")
