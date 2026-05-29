"""
Gacha pricing & pull-probability configuration (Proposal 3).

BUSINESS-MODEL CONTEXT (load-bearing):
    Inventory is LENT, not owned. Lenders take equity-like exposure: their
    return comes from their share of revenue, and their principal is the
    USD value of NFTs they contributed at campaign start.

    The operator does NOT optimize per-pull margin. The goal is to:
        (a) maximise total volume (number of boxes sold), and
        (b) maximise auto-buyback acceptance rate.
    Each NFT a user keeps is a debt to the lender at settlement, *and*
    shortens the campaign (depleting inventory). Each NFT a user sells
    back returns to the pool free to be pulled again — the flywheel.

CAMPAIGN & SETTLEMENT (load-bearing):
    A campaign is a fixed-length simulation horizon of `n_pulls_per_campaign`
    pulls (default 1000). Floor prices are held constant. Restock from the
    open market keeps inventory replenished while cashbox can afford it.
    At end of campaign, settle via this waterfall:

        cashbox = Σ(box_price - auto_buyback_payout)   over all pulls
        debt    = Σ(floor_usd of consumed NFTs)         (users kept them)

        debt_repaid     = min(cashbox, debt)            ← lenders SENIOR here
        profit          = max(0, cashbox - debt)
        operator_take   = profit × operator_revenue_share
        lender_cash     = debt_repaid + profit × (1 - operator_revenue_share)

    Surviving inventory returns in-kind to lenders at week-end.
        lender_recovery = lender_cash + value_of_remaining_NFTs

    Senior debt repayment is the structural fix that aligns incentives:
    operator only earns when lenders have been made whole on the NFTs
    that left the pool.

PULL MECHANIC — TWO-STAGE sampling:
    1. Draw tier ∈ {high, mid, low} from Categorical(p_tier_high, p_tier_mid, p_tier_low)
    2. Draw NFT uniformly from the lender pool's remaining inventory in that tier
    3. Decrement inventory IF the user does NOT accept the auto-buyback (below)

AUTO-BUYBACK OFFER (key feature):
    After every pull, the gacha makes an instant offer to buy the NFT back
    from the user at a discount to its current floor price:

        offered_payout_usd = nft_floor_usd * (1 - auto_buyback_discount)

    With default `auto_buyback_discount = 0.06`, the user is offered 94% of
    the NFT's floor price in stablecoin. The user accepts with probability
    `p_accept_buyback_<tier>` (tier-dependent; floor pulls dumped more often).

    Sensitivity lever:
        buyback_acceptance_scale ∈ [0, ~1.5]
        Scales all three per-tier rates uniformly; clipped to [0, 1].
        Use this single variable for "how many users sell back" sweeps.

RESTOCK (market repurchase):
    When the TOTAL count of NFTs in the pool drops below
    `restock_threshold` × initial_total (default 50% × 75 = 37 NFTs),
    the operator buys back every missing NFT at floor price from the open
    market. Cost flows out of cashbox; debt to lenders is reduced by the
    same amount. If cashbox is insufficient, the restock is skipped for
    that round (debt continues to grow until cashbox catches up).

INVENTORY EXHAUSTION:
    If a sampled tier is empty when its turn comes up (can still happen
    even with restock if a specific tier drains faster than the total
    threshold triggers):
        - "reroll":       redraw tier from remaining non-empty tiers
        - "promote":      shift one tier up (low→mid→high); if all gone, end
        - "end_campaign": stop the campaign immediately

This module is *config only* — no simulation logic. Imported by the
simulator (Step 3).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GachaConfig:
    """A single pricing/probability configuration for the gacha."""

    name: str
    box_price_usd: float

    # Tier pull probabilities (must sum to 1.0)
    p_tier_high: float
    p_tier_mid: float
    p_tier_low: float

    # Auto-buyback economics — operator offers to buy the NFT back from the
    # user immediately after the pull at floor * (1 - auto_buyback_discount).
    auto_buyback_discount: float = 0.06   # 6% discount → user gets 94% of floor

    # Per-tier probability the user ACCEPTS the auto-buyback offer.
    # (1 - p_accept) is the probability the user keeps the NFT.
    p_accept_buyback_high: float = 0.15   # premium pulls held more often
    p_accept_buyback_mid:  float = 0.40
    p_accept_buyback_low:  float = 0.75   # floor pulls dumped more often

    # SENSITIVITY LEVER — single multiplier on all three p_accept rates,
    # clipped to [0,1] when applied. Sweep this for "how many users sell back".
    buyback_acceptance_scale: float = 1.0

    # Revenue share — applied to profit ONLY (after debt repayment to lenders).
    operator_revenue_share: float = 0.50

    # Campaign horizon — number of pulls (= boxes sold) per simulated campaign.
    # With restock enabled, this can run much longer than naive inventory cap.
    n_pulls_per_campaign: int = 1000

    # Restock mechanic — when total inventory drops below this fraction of
    # the original pool size, repurchase missing NFTs from the open market
    # at floor price. Cost is debited from cashbox.
    restock_enabled:   bool  = True
    restock_threshold: float = 0.50      # restock when total_inv < 50% of start

    # Snapshot stats every N pulls within a campaign.
    snapshot_interval: int = 200

    # Inventory depletion policy (relevant only if a specific tier empties)
    depleted_tier_policy: str = "reroll"  # "reroll" | "promote" | "end_campaign"

    # Simulation
    n_paths: int = 1000
    seed: int = 42

    def __post_init__(self) -> None:
        s = self.p_tier_high + self.p_tier_mid + self.p_tier_low
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                f"Tier probabilities must sum to 1.0, got {s} "
                f"({self.p_tier_high} + {self.p_tier_mid} + {self.p_tier_low})"
            )
        if self.depleted_tier_policy not in ("reroll", "promote", "end_campaign"):
            raise ValueError(f"Invalid depleted_tier_policy: {self.depleted_tier_policy}")
        if not (0.0 <= self.operator_revenue_share <= 1.0):
            raise ValueError(f"operator_revenue_share out of [0,1]: {self.operator_revenue_share}")
        if self.buyback_acceptance_scale < 0:
            raise ValueError(f"buyback_acceptance_scale must be >= 0: {self.buyback_acceptance_scale}")
        if not (0.0 < self.restock_threshold <= 1.0):
            raise ValueError(f"restock_threshold must be in (0,1]: {self.restock_threshold}")
        if self.snapshot_interval < 1:
            raise ValueError(f"snapshot_interval must be >= 1: {self.snapshot_interval}")

    # ----- Derived quantities -----

    def p_accept_buyback(self, tier: str) -> float:
        """Effective per-tier acceptance rate after applying the sensitivity scale."""
        base = {
            "high": self.p_accept_buyback_high,
            "mid":  self.p_accept_buyback_mid,
            "low":  self.p_accept_buyback_low,
        }[tier]
        return min(1.0, max(0.0, base * self.buyback_acceptance_scale))


# =============================================================================
# PRE-DEFINED VARIANTS
# =============================================================================
# Three variants for sensitivity / pitching.  Each is paired with a box price
# chosen to leave a modest operator edge over the expected pull value implied
# by the tier weights, given the locked inventory snapshot
# (see inventory_static.py — avg floors: high $2,020 / mid $975 / low $207).
#
# Headline metric — implied EV per pull (computed from locked snapshot):
#     EV = p_high·$2,068 + p_mid·$1,102 + p_low·$207
#
# Box prices below target ~10% implied edge (box_price ≈ EV / 0.90).
# All numbers are starting points — sensitivity sweeps will refine.

VARIANTS: dict[str, GachaConfig] = {

    # ---------- A. "Balanced" ----------
    # Pulls roughly match unit-share of the pool (~53% low, ~32% mid, ~15% high).
    # Closest to "what comes out is what's in there".
    "balanced": GachaConfig(
        name="balanced",
        box_price_usd=850.0,           # EV ≈ $773 → ~9% edge
        p_tier_high=0.15,
        p_tier_mid=0.32,
        p_tier_low=0.53,
        auto_buyback_discount=0.06,
        p_accept_buyback_high=0.15,
        p_accept_buyback_mid=0.40,
        p_accept_buyback_low=0.75,
        n_pulls_per_campaign=1000,
    ),

    # ---------- B. "Premium" ----------
    # Higher chance at the good stuff; box priced for whales.
    "premium": GachaConfig(
        name="premium",
        box_price_usd=1150.0,          # EV ≈ $1,030 → ~10% edge
        p_tier_high=0.25,
        p_tier_mid=0.40,
        p_tier_low=0.35,
        auto_buyback_discount=0.06,
        p_accept_buyback_high=0.10,    # whales hold high pulls harder
        p_accept_buyback_mid=0.35,
        p_accept_buyback_low=0.70,
        n_pulls_per_campaign=1000,
    ),

    # ---------- C. "Floor-spam" ----------
    # Cheap-and-cheerful entry; mostly low pulls. Volume play.
    "floor_spam": GachaConfig(
        name="floor_spam",
        box_price_usd=475.0,           # EV ≈ $415 → ~13% edge
        p_tier_high=0.03,
        p_tier_mid=0.17,
        p_tier_low=0.80,
        auto_buyback_discount=0.06,
        p_accept_buyback_high=0.20,    # rare high pulls more likely to be flipped
        p_accept_buyback_mid=0.50,
        p_accept_buyback_low=0.80,
        n_pulls_per_campaign=1000,
    ),
}


DEFAULT = VARIANTS["balanced"]


# =============================================================================
# HELPERS
# =============================================================================

def expected_pull_value_usd(cfg: GachaConfig, inventory) -> float:
    """Expected USD value of a single pull, given tier probs + current
    inventory composition.

    Assumes uniform sampling within tier — so EV of a tier is the mean floor
    of NFTs in that tier (weighted by tier counts is *not* needed; uniform).
    """
    from inventory_static import TIER_ROLLUP  # local import to avoid cycle
    rollup = inventory if inventory is not None else TIER_ROLLUP
    ev_tier: dict[str, float] = {}
    for tier_name, items in rollup.items():
        if not items:
            ev_tier[tier_name] = 0.0
            continue
        ev_tier[tier_name] = sum(c.floor_usd for c in items) / len(items)
    return (cfg.p_tier_high * ev_tier.get("high", 0.0)
            + cfg.p_tier_mid * ev_tier.get("mid", 0.0)
            + cfg.p_tier_low * ev_tier.get("low", 0.0))


def implied_edge_pct(cfg: GachaConfig, inventory=None) -> float:
    """House edge as a percentage of box price."""
    ev = expected_pull_value_usd(cfg, inventory)
    if cfg.box_price_usd <= 0:
        return 0.0
    return 100 * (cfg.box_price_usd - ev) / cfg.box_price_usd


def implied_overall_buyback_rate(cfg: GachaConfig) -> float:
    """Probability a single pull ends in an auto-buyback acceptance, given
    tier weights and per-tier acceptance rates (after scale).

        E[accept] = Σ p_tier · p_accept(tier)
    """
    return (cfg.p_tier_high * cfg.p_accept_buyback(  "high")
            + cfg.p_tier_mid  * cfg.p_accept_buyback("mid")
            + cfg.p_tier_low  * cfg.p_accept_buyback("low"))


def expected_auto_buyback_payout_usd(cfg: GachaConfig, inventory=None) -> float:
    """Expected $ paid out via auto-buyback per pull. Conditional on acceptance,
    payout = floor * (1 - discount); marginal across tier and acceptance gives:

        E[payout] = Σ p_tier · p_accept(tier) · mean_floor(tier) · (1 - discount)
    """
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    total = 0.0
    for tier in ("high", "mid", "low"):
        items = rollup.get(tier, [])
        if not items:
            continue
        mean_floor = sum(c.floor_usd for c in items) / len(items)
        p_tier = getattr(cfg, f"p_tier_{tier}")
        total += p_tier * cfg.p_accept_buyback(tier) * mean_floor
    return total * (1 - cfg.auto_buyback_discount)


def expected_net_revenue_per_pull(cfg: GachaConfig, inventory=None) -> float:
    """Expected NET revenue per pull — the thing that gets split 50/50:

        E[net_rev] = box_price - E[auto-buyback payout]
    """
    return cfg.box_price_usd - expected_auto_buyback_payout_usd(cfg, inventory)


def expected_operator_cash_per_pull(cfg: GachaConfig, inventory=None) -> float:
    """Operator's per-pull cash AFTER applying the 50/50 revenue split."""
    return expected_net_revenue_per_pull(cfg, inventory) * cfg.operator_revenue_share


def expected_lender_cash_per_pull(cfg: GachaConfig, inventory=None) -> float:
    """Lender pool's per-pull cash AFTER applying the 50/50 revenue split.
    This is split across lenders by their share of consumed-NFT value (or by
    initial lent value — Step 4 decision)."""
    return expected_net_revenue_per_pull(cfg, inventory) * (1 - cfg.operator_revenue_share)


def expected_consumption_rate_per_pull(cfg: GachaConfig) -> float:
    """Probability a pull permanently removes an NFT from inventory:

        E[consume_count] = Σ p_tier · (1 - p_accept(tier))
    """
    return (cfg.p_tier_high * (1 - cfg.p_accept_buyback("high"))
            + cfg.p_tier_mid  * (1 - cfg.p_accept_buyback("mid"))
            + cfg.p_tier_low  * (1 - cfg.p_accept_buyback("low")))


def expected_consumed_value_usd_per_pull(cfg: GachaConfig, inventory=None) -> float:
    """Expected USD value of inventory permanently consumed per pull — the
    debt that accrues to lenders for NFTs users decide to keep:

        E[consumed_value] = Σ p_tier · (1 - p_accept(tier)) · mean_floor(tier)
    """
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    total = 0.0
    for tier in ("high", "mid", "low"):
        items = rollup.get(tier, [])
        if not items:
            continue
        mean_floor = sum(c.floor_usd for c in items) / len(items)
        p_tier = getattr(cfg, f"p_tier_{tier}")
        total += p_tier * (1 - cfg.p_accept_buyback(tier)) * mean_floor
    return total


def expected_campaign_length_boxes(cfg: GachaConfig, inventory=None) -> int:
    """First-tier-depletion estimate of campaign length, accounting for buybacks.
    Returns whichever tier exhausts first under expected consumption."""
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    caps: list[int] = []
    for tier in ("high", "mid", "low"):
        items = rollup.get(tier, [])
        count = sum(c.count_lent for c in items)
        p_tier = getattr(cfg, f"p_tier_{tier}")
        p_accept = cfg.p_accept_buyback(tier)
        eff = p_tier * (1 - p_accept)
        if eff > 0:
            caps.append(int(count / eff))
    return min(caps) if caps else 0


def expected_campaign_aggregates(cfg: GachaConfig, inventory=None) -> dict:
    """Expected weekly-campaign view with the senior-debt settlement waterfall:

        cashbox       = gross_box_revenue - auto_buyback_payout
        debt          = $ value of NFTs consumed
        debt_repaid   = min(cashbox, debt)                    ← lenders SENIOR
        profit        = max(0, cashbox - debt)
        operator_take = profit × operator_revenue_share
        lender_cash   = debt_repaid + profit × (1 − operator_revenue_share)

    Actual boxes sold this campaign = min(demand, inventory capacity).
    If demand > capacity, the campaign is flagged inventory_constrained.
    NOTE: this naive expected-value calc ignores restock — under
    `restock_enabled=True` the simulator extends well past these caps.
    """
    from inventory_static import TOTAL_VALUE_USD

    capacity      = expected_campaign_length_boxes(cfg, inventory)
    demand        = cfg.n_pulls_per_campaign
    n             = min(demand, capacity)
    inv_constrained = demand > capacity

    gross_box_revenue   = n * cfg.box_price_usd
    auto_buyback_payout = n * expected_auto_buyback_payout_usd(cfg, inventory)
    cashbox             = gross_box_revenue - auto_buyback_payout

    nfts_consumed_count = n * expected_consumption_rate_per_pull(cfg)
    debt                = n * expected_consumed_value_usd_per_pull(cfg, inventory)

    debt_repaid   = min(cashbox, debt)
    debt_shortfall = max(0.0, debt - cashbox)             # >0 → lenders short on cash
    profit        = max(0.0, cashbox - debt)
    operator_take = profit * cfg.operator_revenue_share
    lender_cash   = debt_repaid + profit * (1 - cfg.operator_revenue_share)

    initial_principal         = TOTAL_VALUE_USD
    remaining_inventory_value = max(0.0, initial_principal - debt)
    lender_recovery_total     = lender_cash + remaining_inventory_value
    lender_recovery_ratio     = (lender_recovery_total / initial_principal
                                 if initial_principal > 0 else 0.0)

    return {
        "n_boxes": n,
        "demand": demand,
        "capacity": capacity,
        "inventory_constrained": inv_constrained,
        "gross_box_revenue": gross_box_revenue,
        "auto_buyback_payout": auto_buyback_payout,
        "cashbox": cashbox,
        "debt": debt,
        "debt_repaid": debt_repaid,
        "debt_shortfall": debt_shortfall,
        "profit": profit,
        "operator_take": operator_take,
        "lender_cash": lender_cash,
        "nfts_consumed_count": nfts_consumed_count,
        "remaining_inventory_value": remaining_inventory_value,
        "lender_recovery_total": lender_recovery_total,
        "lender_recovery_ratio": lender_recovery_ratio,
    }


# =============================================================================
# SELF-TEST / VARIANT COMPARISON
# =============================================================================

if __name__ == "__main__":
    from dataclasses import replace
    from inventory_static import TIER_ROLLUP, TOTAL_NFTS, TOTAL_VALUE_USD

    # ----- Inventory context -----
    print("Inventory tier composition (locked snapshot):")
    for tier in ("high", "mid", "low"):
        items = TIER_ROLLUP[tier]
        mean = sum(c.floor_usd for c in items) / len(items) if items else 0
        tier_value = sum(c.lent_value_usd for c in items)
        print(f"  {tier:>4s}  {len(items)} collections / "
              f"{sum(c.count_lent for c in items):>3d} NFTs / "
              f"mean floor ${mean:>6,.0f} / "
              f"tier value ${tier_value:>7,.0f}")
    print(f"  TOTAL: {TOTAL_NFTS} NFTs, ${TOTAL_VALUE_USD:,.0f} lent principal")

    # ----- 1. Per-pull cash flow view -----
    print()
    print("=" * 96)
    print(f"{'1. PER-PULL CASH FLOW (expected values)':^96s}")
    print("=" * 96)
    hdr = (f"{'Variant':<12s} {'Box$':>6s} {'Pull$':>6s} {'P(acc)':>7s} "
           f"{'Payout':>8s} {'NetRev':>8s} {'Op50%':>7s} {'Lend50%':>8s} "
           f"{'ConsVal':>8s}")
    print(hdr)
    print("-" * len(hdr))
    for v in VARIANTS.values():
        ev    = expected_pull_value_usd(v, TIER_ROLLUP)
        pbb   = implied_overall_buyback_rate(v)
        pay   = expected_auto_buyback_payout_usd(v, TIER_ROLLUP)
        net   = expected_net_revenue_per_pull(v, TIER_ROLLUP)
        op    = expected_operator_cash_per_pull(v, TIER_ROLLUP)
        lend  = expected_lender_cash_per_pull(v, TIER_ROLLUP)
        cval  = expected_consumed_value_usd_per_pull(v, TIER_ROLLUP)
        print(f"{v.name:<12s} {v.box_price_usd:>6,.0f} {ev:>6,.0f} "
              f"{pbb:>6.1%} ${pay:>6,.0f} ${net:>6,.0f} ${op:>5,.0f} "
              f"${lend:>6,.0f} ${cval:>6,.0f}")
    print("(ConsVal = USD value of NFTs leaving inventory per pull → debt to lenders)")

    # ----- 2. Weekly campaign with waterfall settlement -----
    print()
    print("=" * 96)
    print(f"{'2. WEEKLY CAMPAIGN (1 wk, waterfall: debt FIRST, then 50/50 profit)':^96s}")
    print("=" * 96)
    hdr = (f"{'Variant':<12s} {'Boxes':>5s} {'Cashbox':>9s} {'Debt':>8s} "
           f"{'Repaid':>8s} {'Profit':>8s} {'OpTake':>8s} {'LendCash':>9s} "
           f"{'RemNFT$':>9s} {'Recovery':>9s}")
    print(hdr)
    print("-" * len(hdr))
    for v in VARIANTS.values():
        a = expected_campaign_aggregates(v, TIER_ROLLUP)
        constrained = " *" if a["inventory_constrained"] else ""
        print(f"{v.name:<12s} {a['n_boxes']:>4d}{constrained:<1s} "
              f"${a['cashbox']:>7,.0f} ${a['debt']:>6,.0f} "
              f"${a['debt_repaid']:>6,.0f} ${a['profit']:>6,.0f} "
              f"${a['operator_take']:>6,.0f} ${a['lender_cash']:>7,.0f} "
              f"${a['remaining_inventory_value']:>7,.0f} "
              f"{a['lender_recovery_ratio']:>8.1%}")
    print(f"(Recovery = (lender_cash + remaining_NFT_value) / ${TOTAL_VALUE_USD:,.0f} principal)")
    print(f"(* = demand exceeded inventory capacity; actual boxes capped)")

    # ----- 3. Buyback-acceptance sensitivity on balanced -----
    print()
    print("=" * 96)
    print(f"{'3. SENSITIVITY: buyback_acceptance_scale on balanced (waterfall view)':^96s}")
    print("=" * 96)
    print(f"  {'scale':>6s}  {'P(acc)':>7s}  {'Boxes':>5s}  {'Cashbox':>9s}  "
          f"{'Debt':>8s}  {'OpTake':>8s}  {'LendCash':>9s}  {'Recovery':>9s}")
    print("-" * 96)
    for s in [0.0, 0.5, 1.0, 1.25, 1.5]:
        v = replace(VARIANTS["balanced"], buyback_acceptance_scale=s)
        pbb = implied_overall_buyback_rate(v)
        a = expected_campaign_aggregates(v, TIER_ROLLUP)
        print(f"  {s:>6.2f}  {pbb:>6.1%}   {a['n_boxes']:>4d}   "
              f"${a['cashbox']:>7,.0f}  ${a['debt']:>6,.0f}  "
              f"${a['operator_take']:>6,.0f}  ${a['lender_cash']:>7,.0f}  "
              f"{a['lender_recovery_ratio']:>8.1%}")
    print("Senior-debt waterfall means lender cash ≥ debt (when cashbox suffices);")
    print("operator only earns once lenders are made whole on consumed NFTs.")
