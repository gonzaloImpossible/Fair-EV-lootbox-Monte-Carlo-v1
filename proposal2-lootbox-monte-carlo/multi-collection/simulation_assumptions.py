"""
SIMULATION ASSUMPTIONS — Proposal 3 Multi-Collection Gacha
===========================================================

Canonical reference for every assumption and configuration value used by the
simulator. Two categories:

    A. STRUCTURAL ASSUMPTIONS — modeling choices baked into the code.
       Adjusting these requires changing simulator.py / gacha_config.py logic.

    B. NUMERICAL PARAMETERS — concrete values set in config files.
       Adjusting these requires only editing the relevant config.

Run this file directly (`python3 simulation_assumptions.py`) to print a full
declarative dump of both categories.

Sources of truth:
    - inventory_static.py  → inventory pool, floor prices, lender NFT counts
    - gacha_config.py      → box prices, tier odds, auto-buyback, settlement
    - simulator.py         → core sim engine, allocation rules
"""

from __future__ import annotations

from inventory_static import (
    INVENTORY, TIER_ROLLUP, TOTAL_NFTS, TOTAL_VALUE_USD,
    SNAPSHOT_DATE, ETH_USD_RATE,
)
from gacha_config import VARIANTS


# =============================================================================
# A. STRUCTURAL ASSUMPTIONS (require code changes to alter)
# =============================================================================

STRUCTURAL_ASSUMPTIONS = [
    # ---- Campaign & time ----
    ("Campaign duration",
     "Exactly 1 week. Each simulation path = one weekly campaign."),
    ("Settlement frequency",
     "Once per week, at end of campaign."),
    ("Multi-week dynamics",
     "Each campaign is INDEPENDENT. No carryover of inventory, cash, or "
     "user behavior between weeks."),

    # ---- Prices ----
    ("Floor price stability",
     "Floor prices are CONSTANT throughout the week. No within-week drift."),
    ("FX",
     "ETH/USD rate is locked to the snapshot value. No FX volatility."),
    ("Snapshot freshness",
     f"All prices snapshotted on {SNAPSHOT_DATE} via Rarible BFF. "
     "Re-run fetch_inventory.py + characterize_inventory.py to refresh."),

    # ---- Pull mechanic ----
    ("Pull outcomes (4-way)",
     "Each pull resolves to ONE of: tier_high / tier_mid / tier_low / "
     "consolation. The four probabilities sum to 1.0."),
    ("Pull stage 1 — outcome sampling",
     "Categorical over the four outcomes. If consolation drawn: no NFT "
     "consumed, no auto-buyback offered, operator pays consolation_cost_usd."),
    ("Pull stage 2 — NFT",
     "Conditional on an NFT-tier outcome: uniform sampling over remaining "
     "inventory in that tier. All NFTs in a tier are interchangeable."),
    ("Consolation user-side value",
     "consolation_perceived_value_usd is a USER metric used only in EV / "
     "edge math. It does not flow through cashbox. Operator's actual cost "
     "(consolation_cost_usd) can be much smaller (points, gas for free mint)."),
    ("Tier-empty policy",
     "Configurable: reroll (default) / promote / end_campaign. "
     "Currently set to 'reroll' for all variants."),

    # ---- Auto-buyback ----
    ("Auto-buyback offer",
     "Triggered after EVERY pull. Payout = floor × (1 − auto_buyback_discount)."),
    ("Acceptance model",
     "Bernoulli(p_accept_tier). INDEPENDENT across pulls. No user memory "
     "or learning. No correlation between users."),
    ("Buyback effect on inventory",
     "Accepted buyback → NFT returns to lender pool (free to be pulled "
     "again). Rejected → NFT permanently consumed; lender's pool shrinks."),

    # ---- Inventory dynamics ----
    ("Restock during the campaign",
     "ENABLED by default. When TOTAL pool count drops below "
     "`restock_threshold` × initial (default 50% × 75 = 37 NFTs), buy back "
     "every missing slug at floor from the open market. Cost flows out of "
     "cashbox; debt is reduced by the same amount."),
    ("Restock affordability",
     "If cashbox < total restock cost when triggered, the restock is "
     "skipped that round (all-or-nothing). Debt continues to accrue."),
    ("Restock threshold target",
     "After a successful restock, every slug is restored to its ORIGINAL "
     "lent count. Pool returns to 75 NFTs."),
    ("Restock & per-tier exhaustion",
     "Restock checks TOTAL count, not per-tier. A specific tier (e.g. high) "
     "can still empty out before the total threshold trips, in which case "
     "the depleted_tier_policy applies."),
    ("Inventory at campaign-end",
     "Surviving NFTs (original + restocked) return IN-KIND to lenders at "
     "floor value, up to each lender's original lent count. Any shortage "
     "becomes settlement debt."),
    ("Inventory accounting",
     "Per-tier-per-slug NFT counts maintained. Consumed and restocked "
     "counts tracked separately per slug for per-lender reporting."),

    # ---- Demand ----
    ("Campaign horizon",
     "DETERMINISTIC. n_pulls_per_campaign pulls per path (default 1000). "
     "Inventory exhaustion (under depleted_tier_policy) can end a campaign "
     "early, but restock makes this rare."),
    ("Demand source",
     "Exogenous. No price elasticity, no time-of-week effects, no churn."),
    ("Snapshot reporting",
     "In-campaign state is snapshotted every `snapshot_interval` pulls "
     "(default 200). Cashbox, debt, inventory, consumed/restocked counts, "
     "and restock-event count are captured for timeline analysis."),

    # ---- Settlement waterfall ----
    ("Settlement order",
     "1) cashbox = gross_box_revenue − auto_buyback_payouts.  "
     "2) debt = $ value of consumed NFTs.  "
     "3) debt_repaid = min(cashbox, debt) → LENDERS SENIOR.  "
     "4) profit = max(0, cashbox − debt).  "
     "5) operator_take = profit × operator_revenue_share.  "
     "6) lender_pool_cash = debt_repaid + profit × (1 − operator_revenue_share)."),
    ("Loss absorption",
     "Cashbox shortfall (cashbox < debt) leaves lenders short on debt "
     "repayment. Operator absorbs zero loss in this case (just earns 0 profit)."),
    ("Per-lender debt allocation",
     "debt_repaid is split pro-rata by each lender's $-share of the TOTAL "
     "consumed value in that campaign."),
    ("Per-lender profit allocation",
     "profit_share is split pro-rata by each lender's INITIAL $-principal "
     "(i.e. their share of the original $53,906 lent value)."),

    # ---- What's not modeled ----
    ("Friction & costs (not modeled)",
     "No gas fees. No platform fees beyond the configured haircut. "
     "No marketing/CAC. No operator opex."),
    ("Bad actors (not modeled)",
     "No Sybil resistance modeling. No insider behavior. No front-running. "
     "Each user pull is treated as an independent rational agent decision."),
    ("Secondary-market dynamics (not modeled)",
     "Operator cannot buy/sell NFTs from the secondary market during the "
     "campaign. The lent pool is the only source of inventory."),
    ("Lender heterogeneity (not modeled)",
     "All lenders treated symmetrically — same waterfall, same terms. "
     "No senior/junior tiers between lending collections."),
]


# =============================================================================
# B. NUMERICAL PARAMETERS (live in config files)
# =============================================================================

# Pulled at runtime — see source modules for editable values.

INVENTORY_PARAMS = {
    "snapshot_date": SNAPSHOT_DATE,
    "eth_usd_rate":  ETH_USD_RATE,
    "total_nfts":    TOTAL_NFTS,
    "total_value_usd": TOTAL_VALUE_USD,
    "n_partner_collections": len(INVENTORY),
    "tier_thresholds_usd": {
        "headline":  ">= 5000",
        "high":      "1500 – 5000",
        "mid":       "500 – 1500",
        "low":       "< 500",
    },
    "ecosystem_swaps": {
        "bayc_main_to_mayc":
            "BAYC main ($20k floor) exceeds the $5–10k lend cap; "
            "ecosystem represented by MAYC (~$2.1k floor).",
        "pudgy_main_to_lil_pudgys":
            "Pudgy Penguins main ($10k floor) too thin at 1 NFT lent; "
            "ecosystem represented by Lil Pudgys (~$1.2k floor).",
    },
    "lend_size_band_usd": (5000, 10000),
    "lend_size_band_notes":
        "Each partner was meant to lend $5k–$10k worth of NFTs. "
        "Per-partner counts (NFT count × floor) cluster in this band; "
        "MAYC and Lil Pudgys exceed it slightly due to discrete NFT sizing.",
}

SIMULATION_PARAMS = {
    "n_paths_default":            1000,
    "n_paths_override_in_main":   1000,
    "n_pulls_per_campaign":       1000,
    "snapshot_interval":          200,
    "seed_default":               42,
    "restock_enabled":            True,
    "restock_threshold":          0.50,   # restock when total inv < 50% of start
    "depleted_tier_policy":       "reroll",
    "operator_revenue_share":     0.50,
    "auto_buyback_discount":      0.06,
}


# =============================================================================
# REPORT — run as script to dump everything
# =============================================================================

def _section(title: str) -> None:
    print()
    print("=" * 96)
    print(f"  {title}")
    print("=" * 96)


def _kv(key: str, value, indent: int = 2) -> None:
    print(f"{' ' * indent}{key:<32s} {value}")


def main() -> None:
    print("\n" + "#" * 96)
    print(f"#  SIMULATION ASSUMPTIONS — Proposal 3 Multi-Collection Gacha")
    print(f"#  Snapshot: {SNAPSHOT_DATE}   ETH/USD: ${ETH_USD_RATE:,.0f}")
    print("#" * 96)

    _section("A. STRUCTURAL ASSUMPTIONS")
    for i, (k, v) in enumerate(STRUCTURAL_ASSUMPTIONS, 1):
        print(f"\n  {i:>2d}. {k}")
        # Naive wrap at ~80 cols
        words = v.split()
        line = "      "
        for w in words:
            if len(line) + len(w) > 86:
                print(line.rstrip())
                line = "      "
            line += w + " "
        if line.strip():
            print(line.rstrip())

    _section("B. NUMERICAL PARAMETERS")

    print("\n  Inventory (from inventory_static.py):")
    _kv("snapshot date",         INVENTORY_PARAMS["snapshot_date"])
    _kv("ETH/USD",               f"${INVENTORY_PARAMS['eth_usd_rate']:,.0f}")
    _kv("total NFTs lent",       INVENTORY_PARAMS["total_nfts"])
    _kv("total principal",       f"${INVENTORY_PARAMS['total_value_usd']:,.0f}")
    _kv("partner collections",   INVENTORY_PARAMS["n_partner_collections"])
    _kv("lend size band",        f"${INVENTORY_PARAMS['lend_size_band_usd'][0]:,}"
                                 f"–${INVENTORY_PARAMS['lend_size_band_usd'][1]:,}")
    print("\n  Tier thresholds (floor USD):")
    for tier, rng in INVENTORY_PARAMS["tier_thresholds_usd"].items():
        _kv(tier, rng, indent=4)
    print("\n  Ecosystem substitutions:")
    for k, v in INVENTORY_PARAMS["ecosystem_swaps"].items():
        print(f"    {k}:")
        print(f"        {v}")

    print("\n  Per-collection lent inventory:")
    print(f"    {'collection':<32s} {'tier':>5s} {'count':>6s} "
          f"{'floor$':>9s} {'lent$':>9s}")
    for c in INVENTORY:
        print(f"    {c.display_name:<32s} {c.tier:>5s} {c.count_lent:>6d} "
              f"${c.floor_usd:>7,.0f} ${c.lent_value_usd:>7,.0f}")
    print(f"    {'TOTAL':<32s} {'':>5s} {TOTAL_NFTS:>6d} "
          f"{'':>9s} ${TOTAL_VALUE_USD:>7,.0f}")

    print("\n  Gacha variant parameters (from gacha_config.py):")
    hdr = (f"    {'variant':<12s} {'box$':>7s} {'pulls':>6s} "
           f"{'p(h/m/l)':<18s} {'accept(h/m/l)':<18s} "
           f"{'disc':>5s} {'opShr':>6s} {'restock':>9s}")
    print(hdr)
    for v in VARIANTS.values():
        tiers_str  = f"({v.p_tier_high:.2f}/{v.p_tier_mid:.2f}/{v.p_tier_low:.2f})"
        accept_str = (f"({v.p_accept_buyback_high:.2f}/"
                      f"{v.p_accept_buyback_mid:.2f}/"
                      f"{v.p_accept_buyback_low:.2f})")
        rest_str   = (f"<{v.restock_threshold:.0%}" if v.restock_enabled else "off")
        print(f"    {v.name:<12s} {v.box_price_usd:>7,.0f} "
              f"{v.n_pulls_per_campaign:>6d} {tiers_str:<18s} {accept_str:<18s} "
              f"{v.auto_buyback_discount:>4.1%} {v.operator_revenue_share:>5.1%} "
              f"{rest_str:>9s}")

    print("\n  Simulation runtime parameters (from simulator.py / gacha_config.py):")
    for k, v in SIMULATION_PARAMS.items():
        _kv(k, v)


if __name__ == "__main__":
    main()
