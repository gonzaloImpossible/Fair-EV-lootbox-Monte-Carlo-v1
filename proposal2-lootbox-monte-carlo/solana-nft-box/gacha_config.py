"""
Gacha pricing & pull-probability configuration — Solana campaign.

Mirrors the structure of `multi-collection/gacha_config.py` (the ETH
`industry_calibrated` reference) so the simulator and analysis scripts
can be ported with only an inventory_static import swap.

Differences from the ETH multi-collection:
    - Solana floors are lower (mean high ~$1,200 vs ETH ~$2,000)
    - Headline tier is two rare-trait Mad Lads at ~$6k each (vs Pudgy)
    - Three variants (value / balanced / whale) priced for a sub-$700
      box range vs the ETH $990 single variant

BUSINESS-MODEL CONTEXT (load-bearing — same as proposal3 / ETH):
    Inventory is LENT. Lenders take equity-like exposure.
    Operator does NOT optimise per-pull margin — goal is volume × auto-
    buyback acceptance.  Each consumed NFT is debt to the lender.

PULL OUTCOMES — five categories drawn from a Categorical that sums to 1:
    headline / high / mid / low / consolation
    Consolation pulls return a shard (1/N of a future box); 5 shards
    redeem for one free pull.  Operator's per-shard cost accrued at
    `consolation_cost_usd = box_price/shards_per_box × shard_redemption_rate`.

SETTLEMENT WATERFALL (operator wears two hats: fee + pro-rata lender):
    cashbox       = Σ(box_price − auto-buyback payout − consolation cost)
    debt          = $ value of NFTs consumed (declines on restock)
    debt_repaid   = min(cashbox, debt)                          ← lenders SENIOR
    cap_returned  = min(cashbox − debt_repaid, initial_cashbox) ← op cap back
    profit        = max(0, cashbox − debt_repaid − cap_returned)
    operator_take = profit × effective_operator_share
    lender_cash   = debt_repaid + profit × (1 − effective_operator_share)

    effective_operator_share = operator_fee_share
                             + (1 − operator_fee_share) × operator_pro_rata_lender_share

RESTOCK (market repurchase):
    Two triggers (either fires it):
        (a) total inventory < restock_threshold × initial_total
        (b) headline tier hits 0  AND  headline_empty_triggers_restock
    Restock is all-or-nothing: tries to top up every slug to its original
    count; if cashbox cannot cover the full bill, skips entirely this round.
    Cost is debited from cashbox; debt is reduced by the same amount.

INVENTORY EXHAUSTION (a specific tier drains before total threshold):
    - "reroll":       redraw tier from remaining non-empty tiers (default)
    - "promote":      shift one tier; if all gone, end
    - "end_campaign": stop immediately
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GachaConfig:
    """A single pricing/probability configuration for the gacha."""

    name: str
    box_price_usd: float

    # Outcome probabilities — must sum to 1.0 INCLUDING headline + consolation.
    p_tier_headline: float = 0.0
    p_tier_high:     float = 0.0
    p_tier_mid:      float = 0.0
    p_tier_low:      float = 0.0
    p_consolation:   float = 0.0

    # Consolation = "1 shard" per consolation pull. shards_per_box shards
    # redeem for one free pull.  Derived:
    #     perceived_value = box_price / shards_per_box     (1/5 of a box by default)
    #     cost            = perceived_value × shard_redemption_rate
    shards_per_box:        int   = 5
    shard_redemption_rate: float = 1.0     # 1.0 = worst case (every shard redeems)

    # Auto-buyback economics — instant offer at floor * (1 - discount).
    auto_buyback_discount: float = 0.08    # user gets 92% of floor on instant-sell

    # Per-tier acceptance probabilities (calibrated to ETH industry_calibrated).
    p_accept_buyback_headline: float = 0.05   # $6k Mad Lads → almost always kept
    p_accept_buyback_high:     float = 0.25
    p_accept_buyback_mid:      float = 0.60
    p_accept_buyback_low:      float = 0.85

    buyback_acceptance_scale: float = 1.0

    # Operator dual role:
    #   (1) OPERATOR — runs the gacha, takes operator_fee_share off the top
    #   (2) LENDER   — contributes initial_cashbox_usd to the capital pool,
    #                  earns pro-rata share of post-fee profit
    # Effective share = fee + (1 - fee) × pro_rata_weight (see property).
    operator_fee_share:         float = 0.50
    operator_revenue_share:     float = 0.50   # legacy knob; ignored if pro_rata=True
    use_pro_rata_capital_split: bool  = True

    # Campaign horizon
    n_pulls_per_campaign: int = 1000

    # Restock — pool-wide, all-or-nothing, two triggers.
    restock_enabled:                 bool  = True
    restock_threshold:               float = 0.50
    headline_empty_triggers_restock: bool  = True

    # Operator working-capital buffer at start of campaign.  Returned at
    # settlement BEFORE the 50/50 profit split; operator ROI is computed
    # against this.  Must absorb early restock spikes.
    initial_cashbox_usd: float = 10000.0

    # Snapshot every N pulls
    snapshot_interval: int = 200

    # Optional floor-shock stress test: (pull_idx, slug, multiplier).
    floor_shock: tuple | None = None

    # Pre-sale pricing — first N pulls at presale rate, rest at regular.
    presale_pulls:         int   = 0
    presale_box_price_usd: float = 0.0

    # Tier depletion policy
    depleted_tier_policy: str = "reroll"   # "reroll" | "promote" | "end_campaign"

    # Simulation
    n_paths: int = 1000
    seed:    int = 42

    def __post_init__(self) -> None:
        s = (self.p_tier_headline + self.p_tier_high + self.p_tier_mid
             + self.p_tier_low + self.p_consolation)
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                f"Outcome probabilities must sum to 1.0, got {s} "
                f"(headline {self.p_tier_headline} + high {self.p_tier_high}"
                f" + mid {self.p_tier_mid} + low {self.p_tier_low}"
                f" + consolation {self.p_consolation})"
            )
        if not (0.0 <= self.p_consolation <= 1.0):
            raise ValueError(f"p_consolation must be in [0,1]: {self.p_consolation}")
        if self.shards_per_box < 1:
            raise ValueError(f"shards_per_box must be >= 1: {self.shards_per_box}")
        if not (0.0 <= self.shard_redemption_rate <= 1.0):
            raise ValueError(f"shard_redemption_rate must be in [0,1]: {self.shard_redemption_rate}")
        if self.depleted_tier_policy not in ("reroll", "promote", "end_campaign"):
            raise ValueError(f"Invalid depleted_tier_policy: {self.depleted_tier_policy}")
        if not (0.0 <= self.operator_fee_share <= 1.0):
            raise ValueError(f"operator_fee_share out of [0,1]: {self.operator_fee_share}")
        if not (0.0 <= self.operator_revenue_share <= 1.0):
            raise ValueError(f"operator_revenue_share out of [0,1]: {self.operator_revenue_share}")
        if self.buyback_acceptance_scale < 0:
            raise ValueError(f"buyback_acceptance_scale must be >= 0: {self.buyback_acceptance_scale}")
        if not (0.0 < self.restock_threshold <= 1.0):
            raise ValueError(f"restock_threshold must be in (0,1]: {self.restock_threshold}")
        if self.snapshot_interval < 1:
            raise ValueError(f"snapshot_interval must be >= 1: {self.snapshot_interval}")

    # ----- Derived properties -----

    @property
    def operator_pro_rata_lender_share(self) -> float:
        """Operator's weight as a lender in the capital pool:
            initial_cashbox / (initial_cashbox + total_NFT_principal)"""
        from inventory_static import TOTAL_VALUE_USD
        total_cap = self.initial_cashbox_usd + TOTAL_VALUE_USD
        return self.initial_cashbox_usd / total_cap if total_cap > 0 else 0.0

    @property
    def effective_operator_share(self) -> float:
        """Total share of profit accruing to the operator (fee + lender slice)."""
        post_fee = 1.0 - self.operator_fee_share
        if self.use_pro_rata_capital_split:
            return self.operator_fee_share + post_fee * self.operator_pro_rata_lender_share
        return self.operator_fee_share + post_fee * self.operator_revenue_share

    @property
    def consolation_perceived_value_usd(self) -> float:
        """User-side value of one shard = 1/shards_per_box of a box."""
        return self.box_price_usd / self.shards_per_box

    @property
    def consolation_cost_usd(self) -> float:
        """Operator's accrued cost per shard issued, scaled by redemption rate."""
        return self.consolation_perceived_value_usd * self.shard_redemption_rate

    # ----- Derived quantities -----

    def p_accept_buyback(self, tier: str) -> float:
        base = {
            "headline": self.p_accept_buyback_headline,
            "high":     self.p_accept_buyback_high,
            "mid":      self.p_accept_buyback_mid,
            "low":      self.p_accept_buyback_low,
        }[tier]
        return min(1.0, max(0.0, base * self.buyback_acceptance_scale))


# =============================================================================
# PRE-DEFINED VARIANTS
# =============================================================================
# Inventory tier mean floors (inventory_static.py):
#     headline ≈ $6,000  (rare-trait Mad Lads × 2)
#     high     ≈ $1,200  (SMB $1,425, Claynosaurz $976)
#     mid      ≈ $520    (Galactic Geckos $547, Mad Lads $494)
#     low      ≈ $148    (Okay Bears)
#
# All variants use:
#   - shards_per_box=5, shard_redemption_rate=1.0 (conservative)
#   - auto_buyback_discount=0.08 (user gets 92% of floor)
#   - acceptance rates calibrated to multi-collection industry_calibrated
#   - headline_empty_triggers_restock=True (protects the 2-NFT headline tier)
#   - initial_cashbox $10k (covers worst-case $12k headline restock + buffer)
#
# Box prices target ~10-12% edge over expected pull value.

VARIANTS: dict[str, GachaConfig] = {

    # ---------- A. "value" — mass adoption ----------
    "value": GachaConfig(
        name="value",
        box_price_usd=220.0,
        presale_pulls=200,
        presale_box_price_usd=200.0,
        p_tier_headline=0.005,         # 1 in 200 pulls
        p_tier_high=0.025,
        p_tier_mid=0.080,
        p_tier_low=0.590,
        p_consolation=0.300,           # 30% shards
        shards_per_box=5,
        shard_redemption_rate=1.0,
        auto_buyback_discount=0.08,
        operator_fee_share=0.50,
        use_pro_rata_capital_split=True,
        initial_cashbox_usd=10000.0,
        n_pulls_per_campaign=1000,
    ),

    # ---------- B. "balanced" — industry-calibrated reference ----------
    # Headline at 1%, shards at 20% — mirrors the ETH industry_calibrated mix.
    "balanced": GachaConfig(
        name="balanced",
        box_price_usd=440.0,
        presale_pulls=200,
        presale_box_price_usd=400.0,
        p_tier_headline=0.010,
        p_tier_high=0.100,
        p_tier_mid=0.250,
        p_tier_low=0.440,
        p_consolation=0.200,
        shards_per_box=5,
        shard_redemption_rate=1.0,
        auto_buyback_discount=0.08,
        operator_fee_share=0.50,
        use_pro_rata_capital_split=True,
        initial_cashbox_usd=10000.0,
        n_pulls_per_campaign=1000,
    ),

    # ---------- C. "whale" — premium ----------
    "whale": GachaConfig(
        name="whale",
        box_price_usd=650.0,
        presale_pulls=200,
        presale_box_price_usd=600.0,
        p_tier_headline=0.015,         # 1 in 67 pulls
        p_tier_high=0.200,
        p_tier_mid=0.350,
        p_tier_low=0.335,
        p_consolation=0.100,
        shards_per_box=5,
        shard_redemption_rate=1.0,
        auto_buyback_discount=0.08,
        p_accept_buyback_high=0.20,    # whales hold high pulls harder
        p_accept_buyback_mid=0.50,
        p_accept_buyback_low=0.80,
        operator_fee_share=0.50,
        use_pro_rata_capital_split=True,
        initial_cashbox_usd=10000.0,
        n_pulls_per_campaign=1000,
    ),
}


DEFAULT = VARIANTS["balanced"]


# =============================================================================
# HELPERS  (signatures identical to multi-collection/gacha_config.py)
# =============================================================================

NFT_TIERS = ("headline", "high", "mid", "low")


def _tier_mean_floor(rollup, tier: str) -> float:
    items = rollup.get(tier, [])
    if not items:
        return 0.0
    return sum(c.floor_usd for c in items) / len(items)


def expected_pull_value_usd(cfg: GachaConfig, inventory=None) -> float:
    """Expected USD value of a single pull (user perspective)."""
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    total = cfg.p_consolation * cfg.consolation_perceived_value_usd
    for tier in NFT_TIERS:
        total += getattr(cfg, f"p_tier_{tier}") * _tier_mean_floor(rollup, tier)
    return total


def implied_edge_pct(cfg: GachaConfig, inventory=None) -> float:
    ev = expected_pull_value_usd(cfg, inventory)
    if cfg.box_price_usd <= 0:
        return 0.0
    return 100 * (cfg.box_price_usd - ev) / cfg.box_price_usd


def implied_overall_buyback_rate(cfg: GachaConfig) -> float:
    return sum(
        getattr(cfg, f"p_tier_{t}") * cfg.p_accept_buyback(t) for t in NFT_TIERS
    )


def expected_auto_buyback_payout_usd(cfg: GachaConfig, inventory=None) -> float:
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    total = 0.0
    for tier in NFT_TIERS:
        mean_floor = _tier_mean_floor(rollup, tier)
        if mean_floor == 0:
            continue
        p_tier = getattr(cfg, f"p_tier_{tier}")
        total += p_tier * cfg.p_accept_buyback(tier) * mean_floor
    return total * (1 - cfg.auto_buyback_discount)


def expected_consolation_cost_per_pull(cfg: GachaConfig) -> float:
    return cfg.p_consolation * cfg.consolation_cost_usd


def expected_net_revenue_per_pull(cfg: GachaConfig, inventory=None) -> float:
    return (cfg.box_price_usd
            - expected_auto_buyback_payout_usd(cfg, inventory)
            - expected_consolation_cost_per_pull(cfg))


def expected_operator_cash_per_pull(cfg: GachaConfig, inventory=None) -> float:
    return expected_net_revenue_per_pull(cfg, inventory) * cfg.effective_operator_share


def expected_lender_cash_per_pull(cfg: GachaConfig, inventory=None) -> float:
    return expected_net_revenue_per_pull(cfg, inventory) * (1 - cfg.effective_operator_share)


def expected_consumption_rate_per_pull(cfg: GachaConfig) -> float:
    return sum(
        getattr(cfg, f"p_tier_{t}") * (1 - cfg.p_accept_buyback(t)) for t in NFT_TIERS
    )


def expected_consumed_value_usd_per_pull(cfg: GachaConfig, inventory=None) -> float:
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    total = 0.0
    for tier in NFT_TIERS:
        mean_floor = _tier_mean_floor(rollup, tier)
        if mean_floor == 0:
            continue
        p_tier = getattr(cfg, f"p_tier_{tier}")
        total += p_tier * (1 - cfg.p_accept_buyback(tier)) * mean_floor
    return total


def expected_campaign_length_boxes(cfg: GachaConfig, inventory=None) -> int:
    from inventory_static import TIER_ROLLUP
    rollup = inventory if inventory is not None else TIER_ROLLUP
    caps: list[int] = []
    for tier in NFT_TIERS:
        items = rollup.get(tier, [])
        count = sum(c.count_lent for c in items)
        if count == 0:
            continue
        p_tier = getattr(cfg, f"p_tier_{tier}")
        eff = p_tier * (1 - cfg.p_accept_buyback(tier))
        if eff > 0:
            caps.append(int(count / eff))
    return min(caps) if caps else 0


def expected_campaign_aggregates(cfg: GachaConfig, inventory=None) -> dict:
    """Naive expected-value campaign view — ignores restock dynamics."""
    from inventory_static import TOTAL_VALUE_USD

    capacity        = expected_campaign_length_boxes(cfg, inventory)
    demand          = cfg.n_pulls_per_campaign
    n               = min(demand, capacity)
    inv_constrained = demand > capacity

    gross_box_revenue   = n * cfg.box_price_usd
    auto_buyback_payout = n * expected_auto_buyback_payout_usd(cfg, inventory)
    consolation_cost    = n * expected_consolation_cost_per_pull(cfg)
    cashbox             = gross_box_revenue - auto_buyback_payout - consolation_cost

    nfts_consumed_count = n * expected_consumption_rate_per_pull(cfg)
    debt                = n * expected_consumed_value_usd_per_pull(cfg, inventory)
    consolation_pulls   = n * cfg.p_consolation
    shards_issued       = consolation_pulls
    free_pulls_owed     = shards_issued / cfg.shards_per_box

    debt_repaid    = min(cashbox, debt)
    debt_shortfall = max(0.0, debt - cashbox)
    profit         = max(0.0, cashbox - debt)
    operator_take  = profit * cfg.effective_operator_share
    lender_cash    = debt_repaid + profit * (1 - cfg.effective_operator_share)

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
        "consolation_cost": consolation_cost,
        "shards_issued": shards_issued,
        "free_pulls_owed": free_pulls_owed,
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
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    from dataclasses import replace
    from inventory_static import (
        TIER_ROLLUP, TOTAL_NFTS, TOTAL_VALUE_USD, SOL_USD_RATE,
    )

    print("Solana inventory tier composition (locked snapshot):")
    for tier in ("headline", "high", "mid", "low"):
        items = TIER_ROLLUP[tier]
        mean = sum(c.floor_usd for c in items) / len(items) if items else 0
        tier_value = sum(c.lent_value_usd for c in items)
        tier_count = sum(c.count_lent for c in items)
        print(f"  {tier:>8s}  {len(items)} collections / "
              f"{tier_count:>3d} NFTs / "
              f"mean floor ${mean:>6,.0f} / "
              f"tier value ${tier_value:>7,.0f}")
    print(f"  TOTAL: {TOTAL_NFTS} NFTs, ${TOTAL_VALUE_USD:,.0f} lent principal  "
          f"(SOL/USD ${SOL_USD_RATE:,.2f})")

    # ----- 1. Per-pull cash flow view -----
    print()
    print("=" * 104)
    print(f"{'1. PER-PULL CASH FLOW (expected values)':^104s}")
    print("=" * 104)
    hdr = (f"{'Variant':<10s} {'Box$':>5s} {'EV':>5s} {'Edge':>6s} {'P(cnsl)':>7s} "
           f"{'P(acc)':>7s} {'Payout':>7s} {'CnslC':>6s} {'NetRev':>7s} "
           f"{'OpEff%':>7s} {'OpCash':>7s} {'LendC':>6s} {'ConsVal':>7s}")
    print(hdr)
    print("-" * len(hdr))
    for v in VARIANTS.values():
        ev   = expected_pull_value_usd(v, TIER_ROLLUP)
        edge = implied_edge_pct(v, TIER_ROLLUP)
        pbb  = implied_overall_buyback_rate(v)
        pay  = expected_auto_buyback_payout_usd(v, TIER_ROLLUP)
        cns  = expected_consolation_cost_per_pull(v)
        net  = expected_net_revenue_per_pull(v, TIER_ROLLUP)
        op   = expected_operator_cash_per_pull(v, TIER_ROLLUP)
        lend = expected_lender_cash_per_pull(v, TIER_ROLLUP)
        cval = expected_consumed_value_usd_per_pull(v, TIER_ROLLUP)
        op_share = v.effective_operator_share
        print(f"{v.name:<10s} {v.box_price_usd:>5,.0f} {ev:>5,.0f} {edge:>5.1f}% "
              f"{v.p_consolation:>6.1%} {pbb:>6.1%} ${pay:>5,.0f} ${cns:>4,.0f} "
              f"${net:>5,.0f} {op_share:>6.1%} ${op:>5,.0f} ${lend:>4,.0f} "
              f"${cval:>5,.0f}")
    print("(CnslC = consolation cost per pull; OpEff% = effective operator share")
    print(" after fee + pro-rata lender slice; ConsVal = NFT debt per pull)")

    # ----- 2. Weekly campaign with waterfall settlement -----
    print()
    print("=" * 104)
    print(f"{'2. WEEKLY CAMPAIGN (1 wk, waterfall: debt FIRST, then 50/50 profit)':^104s}")
    print("=" * 104)
    hdr = (f"{'Variant':<10s} {'Boxes':>5s} {'Cashbox':>9s} {'Debt':>8s} "
           f"{'Repaid':>8s} {'Profit':>8s} {'OpTake':>8s} {'LendCash':>9s} "
           f"{'Shards':>7s} {'FreePul':>8s} {'Recovery':>9s}")
    print(hdr)
    print("-" * len(hdr))
    for v in VARIANTS.values():
        a = expected_campaign_aggregates(v, TIER_ROLLUP)
        constrained = " *" if a["inventory_constrained"] else ""
        print(f"{v.name:<10s} {a['n_boxes']:>4d}{constrained:<1s} "
              f"${a['cashbox']:>7,.0f} ${a['debt']:>6,.0f} "
              f"${a['debt_repaid']:>6,.0f} ${a['profit']:>6,.0f} "
              f"${a['operator_take']:>6,.0f} ${a['lender_cash']:>7,.0f} "
              f"{a['shards_issued']:>7,.0f} {a['free_pulls_owed']:>8,.1f} "
              f"{a['lender_recovery_ratio']:>8.1%}")
    print(f"(Recovery = (lender_cash + remaining_NFT_value) / ${TOTAL_VALUE_USD:,.0f} principal)")
    print(f"(* = demand exceeded inventory capacity; naive view ignores restock)")

    # ----- 3. Buyback-acceptance sensitivity on balanced -----
    print()
    print("=" * 104)
    print(f"{'3. SENSITIVITY: buyback_acceptance_scale on balanced variant':^104s}")
    print("=" * 104)
    print(f"  {'scale':>6s}  {'P(acc)':>7s}  {'Boxes':>5s}  {'Cashbox':>9s}  "
          f"{'Debt':>8s}  {'OpTake':>8s}  {'LendCash':>9s}  {'Recovery':>9s}")
    print("-" * 104)
    for s in [0.0, 0.5, 1.0, 1.25, 1.5]:
        v = replace(VARIANTS["balanced"], buyback_acceptance_scale=s)
        pbb = implied_overall_buyback_rate(v)
        a = expected_campaign_aggregates(v, TIER_ROLLUP)
        print(f"  {s:>6.2f}  {pbb:>6.1%}   {a['n_boxes']:>4d}   "
              f"${a['cashbox']:>7,.0f}  ${a['debt']:>6,.0f}  "
              f"${a['operator_take']:>6,.0f}  ${a['lender_cash']:>7,.0f}  "
              f"{a['lender_recovery_ratio']:>8.1%}")
