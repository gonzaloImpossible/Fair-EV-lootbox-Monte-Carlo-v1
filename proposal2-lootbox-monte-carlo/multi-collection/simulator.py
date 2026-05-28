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
    """In-campaign state at a given pull count, plus hypothetical settlement
    if the campaign ended right at this snapshot."""
    pull_idx: int
    cashbox: float
    debt_open: float                    # current $ owed to lenders (net of restocks)
    inventory_total: int                # NFTs currently in pool
    nfts_consumed_total: int            # cumulative consumed (lifetime)
    nfts_restocked_total: int           # cumulative restocked (lifetime)
    restock_events: int                 # cumulative count of restock triggers
    # If-settled-here metrics (waterfall applied to this snapshot's state)
    if_settled_operator_take: float     # Rarible's share if settled now
    if_settled_operator_total: float    # capital_returned + operator_take
    if_settled_operator_roi: float      # (total - initial) / initial
    if_settled_lender_pool_cash: float
    if_settled_capital_loss: float


@dataclass
class CampaignResult:
    """Outcome of a single simulated campaign (n_pulls_per_campaign pulls)."""

    # Headline cash flows (at end of campaign)
    n_pulls: int
    initial_cashbox: float              # operator's upfront capital
    cashbox: float                      # net cash AFTER payouts + restock + consol
    debt: float                         # $ value of NFTs still owed (net of restocks)
    debt_repaid: float                  # min(cashbox, debt)
    debt_shortfall: float               # max(0, debt - cashbox)
    capital_returned: float             # operator capital returned (capped at initial)
    capital_loss: float                 # max(0, initial - capital_returned)
    profit: float                       # cashbox - debt - capital_returned
    operator_take: float                # profit * operator_share (above capital)
    operator_total: float               # capital_returned + operator_take
    operator_roi: float                 # (operator_total - initial) / initial
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

    # Consolation activity
    consolation_pulls: int                      # pulls that returned a non-NFT prize
    consolation_cost_total: float               # $ paid for consolation rewards

    # State flags
    inventory_exhausted: bool                   # campaign ended early (depletion)
    pulls_by_tier: dict[str, int]               # for diagnostics
    accepts_by_tier: dict[str, int]


# =============================================================================
# CORE SIMULATION
# =============================================================================

TIER_NAMES = ("headline", "high", "mid", "low")


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
    """Sample a tier from Categorical(p_tier_*), CONDITIONAL on the pull
    being an NFT pull (i.e. probabilities renormalised across the three NFT
    tiers, ignoring p_consolation). Applies the depletion policy if the
    chosen tier has no remaining inventory. Returns None when no tier can
    satisfy the pull."""
    nft_prob_sum = (cfg.p_tier_headline + cfg.p_tier_high
                    + cfg.p_tier_mid + cfg.p_tier_low)
    if nft_prob_sum <= 0:
        return None
    base_probs = {
        "headline": cfg.p_tier_headline / nft_prob_sum,
        "high":     cfg.p_tier_high     / nft_prob_sum,
        "mid":      cfg.p_tier_mid      / nft_prob_sum,
        "low":      cfg.p_tier_low      / nft_prob_sum,
    }

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
        # Order: low → mid → high → headline, search upward then downward
        order = ["headline", "high", "mid", "low"]
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


def _settle(cashbox: float, debt: float, initial_cashbox: float,
            op_share: float) -> dict:
    """Apply the waterfall and return the headline numbers. Used at both
    end-of-campaign and at each snapshot (for the demand-shortfall view)."""
    debt_end          = max(0.0, debt)
    debt_repaid       = min(cashbox, debt_end)
    debt_shortfall    = max(0.0, debt_end - cashbox)
    cashbox_post_debt = cashbox - debt_repaid
    capital_returned  = min(cashbox_post_debt, initial_cashbox)
    capital_loss      = max(0.0, initial_cashbox - capital_returned)
    cashbox_post_cap  = cashbox_post_debt - capital_returned
    profit            = max(0.0, cashbox_post_cap)
    operator_take     = profit * op_share
    operator_total    = capital_returned + operator_take
    operator_roi      = ((operator_total - initial_cashbox) / initial_cashbox
                        if initial_cashbox > 0 else 0.0)
    lender_pool_cash  = debt_repaid + profit * (1 - op_share)
    return {
        "debt_repaid": debt_repaid,
        "debt_shortfall": debt_shortfall,
        "capital_returned": capital_returned,
        "capital_loss": capital_loss,
        "profit": profit,
        "operator_take": operator_take,
        "operator_total": operator_total,
        "operator_roi": operator_roi,
        "lender_pool_cash": lender_pool_cash,
    }


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
    headline_slugs     = {c.slug for c in INVENTORY if c.tier == "headline"}

    # Operator seeds the cashbox with their working-capital buffer.
    initial_cashbox = cfg.initial_cashbox_usd
    cashbox = initial_cashbox
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
    consolation_pulls = 0
    consolation_cost_total = 0.0

    n_pulls = 0
    exhausted = False

    # Parse optional floor shock
    shock_pull, shock_slug, shock_mult = (None, None, None)
    if cfg.floor_shock is not None:
        shock_pull, shock_slug, shock_mult = cfg.floor_shock

    for pull_idx in range(cfg.n_pulls_per_campaign):
        # ---- Apply floor shock at the configured pull (one-shot) ----
        if shock_pull is not None and pull_idx == shock_pull:
            old_floor = slug_floor[shock_slug]
            new_floor = old_floor * shock_mult
            # Outstanding-debt adjustment: existing net-consumed of this slug
            # is now owed at the new floor.
            net_consumed = nfts_consumed[shock_slug] - nfts_restocked[shock_slug]
            debt += net_consumed * (new_floor - old_floor)
            slug_floor[shock_slug] = new_floor
            shock_pull = None  # consume the shock

        # Box price (pre-sale rate for the first `presale_pulls`, regular after).
        box_price_now = (cfg.presale_box_price_usd
                         if cfg.presale_pulls > 0 and pull_idx < cfg.presale_pulls
                         else cfg.box_price_usd)
        cashbox += box_price_now

        # First branch: is this a consolation pull?
        if cfg.p_consolation > 0 and rng.random() < cfg.p_consolation:
            cashbox -= cfg.consolation_cost_usd
            consolation_pulls += 1
            consolation_cost_total += cfg.consolation_cost_usd
            n_pulls += 1
            # No inventory consumed, no auto-buyback offered.
        else:
            # Otherwise an NFT pull (existing two-stage mechanic).
            tier = _sample_tier(rng, cfg, inv)
            if tier is None:
                exhausted = True
                # Undo the box-price collection since the pull failed
                cashbox -= cfg.box_price_usd
                break
            slug = _sample_nft(rng, inv[tier])
            nft_floor = slug_floor[slug]

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
        # Triggers: (a) total inventory < threshold, OR
        #          (b) headline tier empty (and headline_empty_triggers_restock).
        headline_empty = (cfg.headline_empty_triggers_restock
                          and sum(inv["headline"].values()) == 0
                          and len(headline_slugs) > 0)
        if cfg.restock_enabled and (current_total < restock_threshold or headline_empty):
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

        # ---- Snapshot (with hypothetical settlement at this point) ----
        if (pull_idx + 1) % cfg.snapshot_interval == 0:
            settled = _settle(cashbox, debt, initial_cashbox,
                              cfg.effective_operator_share)
            snapshots.append(Snapshot(
                pull_idx=pull_idx + 1,
                cashbox=cashbox,
                debt_open=debt,
                inventory_total=current_total,
                nfts_consumed_total=sum(nfts_consumed.values()),
                nfts_restocked_total=sum(nfts_restocked.values()),
                restock_events=restock_events,
                if_settled_operator_take=settled["operator_take"],
                if_settled_operator_total=settled["operator_total"],
                if_settled_operator_roi=settled["operator_roi"],
                if_settled_lender_pool_cash=settled["lender_pool_cash"],
                if_settled_capital_loss=settled["capital_loss"],
            ))

    # ---- Settlement waterfall (end of campaign) ----
    # Order: 1) lenders senior on debt, 2) operator gets capital back, 3) split profit.
    debt_end = max(0.0, debt)  # clamp negative debt (over-restock guard)

    debt_repaid       = min(cashbox, debt_end)
    debt_shortfall    = max(0.0, debt_end - cashbox)
    cashbox_post_debt = cashbox - debt_repaid

    # Return operator's initial capital next (capped at what's left in cashbox).
    capital_returned = min(cashbox_post_debt, initial_cashbox)
    capital_loss     = max(0.0, initial_cashbox - capital_returned)
    cashbox_post_cap = cashbox_post_debt - capital_returned

    # Whatever remains is true profit, split 50/50.
    profit             = max(0.0, cashbox_post_cap)
    operator_take      = profit * cfg.effective_operator_share
    operator_total     = capital_returned + operator_take
    operator_roi       = ((operator_total - initial_cashbox) / initial_cashbox
                          if initial_cashbox > 0 else 0.0)
    lender_pool_cash   = debt_repaid + profit * (1 - cfg.effective_operator_share)

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
    lender_profit_pool = profit * (1 - cfg.effective_operator_share)
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
        initial_cashbox=initial_cashbox,
        cashbox=cashbox,
        debt=debt_end,
        debt_repaid=debt_repaid,
        debt_shortfall=debt_shortfall,
        capital_returned=capital_returned,
        capital_loss=capital_loss,
        profit=profit,
        operator_take=operator_take,
        operator_total=operator_total,
        operator_roi=operator_roi,
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
        consolation_pulls=consolation_pulls,
        consolation_cost_total=consolation_cost_total,
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
    n_pulls         = np.array([r.n_pulls for r in results])
    cashbox         = np.array([r.cashbox for r in results])
    debt            = np.array([r.debt for r in results])
    profit          = np.array([r.profit for r in results])
    op_take         = np.array([r.operator_take for r in results])
    op_total        = np.array([r.operator_total for r in results])
    op_roi          = np.array([r.operator_roi for r in results])
    capital_loss    = np.array([r.capital_loss for r in results])
    initial_cash    = np.array([r.initial_cashbox for r in results])
    lender_cash     = np.array([r.lender_pool_cash for r in results])
    debt_shortfall  = np.array([r.debt_shortfall for r in results])
    exhausted       = np.array([r.inventory_exhausted for r in results])

    # Consolation activity
    consol_pulls = np.array([r.consolation_pulls for r in results])
    consol_cost  = np.array([r.consolation_cost_total for r in results])

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
        snap_cashbox     = _snap_arr("cashbox")
        snap_debt_open   = _snap_arr("debt_open")
        snap_inv_total   = _snap_arr("inventory_total")
        snap_cons_total  = _snap_arr("nfts_consumed_total")
        snap_rest_total  = _snap_arr("nfts_restocked_total")
        snap_rest_evts   = _snap_arr("restock_events")
        snap_op_take     = _snap_arr("if_settled_operator_take")
        snap_op_total    = _snap_arr("if_settled_operator_total")
        snap_op_roi      = _snap_arr("if_settled_operator_roi")
        snap_lender_cash = _snap_arr("if_settled_lender_pool_cash")
        snap_cap_loss    = _snap_arr("if_settled_capital_loss")
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
                # If-settled-here aggregates
                "op_take_mean":   float(snap_op_take[:, i].mean()),
                "op_take_p5":     _pct(snap_op_take[:, i], 5),
                "op_total_mean":  float(snap_op_total[:, i].mean()),
                "op_roi_mean":    float(snap_op_roi[:, i].mean()),
                "op_roi_p5":      _pct(snap_op_roi[:, i], 5),
                "op_roi_p95":     _pct(snap_op_roi[:, i], 95),
                "lender_cash_mean": float(snap_lender_cash[:, i].mean()),
                "cap_loss_rate":  float((snap_cap_loss[:, i] > 0).mean()),
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
        "operator_total":{"mean": float(op_total.mean()), "p5": _pct(op_total, 5), "p95": _pct(op_total, 95)},
        "operator_roi":  {"mean": float(op_roi.mean()),   "p5": _pct(op_roi, 5),   "p95": _pct(op_roi, 95)},
        "initial_cashbox_mean": float(initial_cash.mean()),
        "capital_loss":  {"mean": float(capital_loss.mean()), "p_any": float((capital_loss > 0).mean())},
        "lender_cash":   {"mean": float(lender_cash.mean()), "p5": _pct(lender_cash, 5), "p95": _pct(lender_cash, 95)},
        "shortfall_rate": float((debt_shortfall > 0).mean()),
        "exhausted_rate": float(exhausted.mean()),
        "consolation": {
            "pulls_mean":     float(consol_pulls.mean()),
            "pulls_p5":       _pct(consol_pulls, 5),
            "pulls_p95":      _pct(consol_pulls, 95),
            "cost_total_mean": float(consol_cost.mean()),
            "share_of_pulls": float(consol_pulls.mean() / n_pulls.mean()) if n_pulls.mean() > 0 else 0.0,
        },
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
    print(f"  {'Initial cashbox (op cap)':<26s}        ${agg['initial_cashbox_mean']:>10,.0f}")
    row("Cashbox (end)",        "cashbox")
    row("Debt (end, owed)",     "debt")
    row("Profit",               "profit")
    row("Operator take (50%)",  "operator_take")
    row("Operator total back",  "operator_total")
    roi = agg["operator_roi"]
    print(f"  {'Operator ROI':<26s}  mean  {roi['mean']:>10.1%}    "
          f"p5  {roi['p5']:>10.1%}    p95  {roi['p95']:>10.1%}")
    cl = agg["capital_loss"]
    print(f"  {'Capital loss paths':<26s}  {cl['p_any']:.1%}   "
          f"(mean loss when it happens: ${cl['mean']:,.0f})")
    row("Lender pool cash",     "lender_cash")
    print(f"  {'Shortfall path rate':<26s}  {agg['shortfall_rate']:.1%}   "
          f"(end-of-campaign cashbox < debt)")
    print(f"  {'Inventory-exhaust rate':<26s}  {agg['exhausted_rate']:.1%}   "
          f"(campaign ended before reaching pull cap)")

    # ---- Consolation activity ----
    c = agg["consolation"]
    print(f"\n  Consolation pulls:")
    print(f"    {'count per campaign':<24s}  mean {c['pulls_mean']:>5.0f}   "
          f"p5 {c['pulls_p5']:>5.0f}   p95 {c['pulls_p95']:>5.0f}   "
          f"({c['share_of_pulls']:.1%} of pulls)")
    print(f"    {'$ paid in consolation':<24s}  mean ${c['cost_total_mean']:>10,.0f}")

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

        # ---- DEMAND SHORTFALL view — "if campaign ended at pull X" ----
        print(f"\n  DEMAND SHORTFALL — if campaign ended at this pull, settlement:")
        print(f"    {'pull':>5s}  {'OpTake':>9s}  {'OpTotal':>9s}  "
              f"{'OpROI mean':>10s}  ({'p5':>6s} {'p95':>6s})  "
              f"{'LendCash':>10s}  {'cap-loss %':>10s}")
        for t in agg["timeline"]:
            print(f"    {t['pull_idx']:>5d}  ${t['op_take_mean']:>7,.0f}  "
                  f"${t['op_total_mean']:>7,.0f}  "
                  f"{t['op_roi_mean']:>9.1%}  ({t['op_roi_p5']:>5.1%} {t['op_roi_p95']:>5.1%})  "
                  f"${t['lender_cash_mean']:>8,.0f}  "
                  f"{t['cap_loss_rate']:>9.1%}")

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
    from dataclasses import replace

    N_PATHS = 1000

    print(f"Inventory: {sum(c.count_lent for c in INVENTORY)} NFTs across "
          f"{len(INVENTORY)} collections, ${TOTAL_VALUE_USD:,.0f} principal.")
    print(f"Restock: enabled at <50% of pool (38 NFTs).  "
          f"Pulls per campaign: 1000.  Snapshots every 200 pulls.\n")

    base = VARIANTS["industry_calibrated"]

    # ---- Scenarios to run ----
    SCENARIOS: list[tuple[str, dict]] = [
        ("BASELINE (no shock)", {}),
        ("STRESS: Pudgy floor +50% at pull 500",
         {"floor_shock": (500, "pudgy_penguins", 1.50)}),
        ("STRESS: Pudgy floor +100% at pull 500",
         {"floor_shock": (500, "pudgy_penguins", 2.00)}),
        ("STRESS: Pudgy floor -50% at pull 500",
         {"floor_shock": (500, "pudgy_penguins", 0.50)}),
    ]

    for label, overrides in SCENARIOS:
        cfg = replace(base, **overrides) if overrides else base
        t0 = time.time()
        results = run_monte_carlo(cfg, n_paths=N_PATHS)
        elapsed = time.time() - t0
        agg = aggregate(results)
        _report(f"{label}  (box ${cfg.box_price_usd:,.0f}, "
                f"{cfg.n_pulls_per_campaign} pulls/campaign)", agg)
        print(f"\n  [sim took {elapsed:.2f}s]")
