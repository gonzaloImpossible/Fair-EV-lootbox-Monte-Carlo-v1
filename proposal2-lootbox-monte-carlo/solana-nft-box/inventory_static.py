"""
Frozen inventory snapshot for the Solana gacha campaign.

Source: Magic Eden public stats API (`/v2/collections/{symbol}/stats`),
fetched 2026-05-28 via fetch_inventory.py. SOL/USD spot from CoinGecko.

This is the canonical static reference for all downstream analysis. Re-run
the fetcher only on explicit refresh — do not regenerate silently.
"""

from dataclasses import dataclass


SNAPSHOT_DATE = "2026-05-28"
SOL_USD_RATE = 81.03  # CoinGecko spot at snapshot


@dataclass(frozen=True)
class Collection:
    slug: str
    display_name: str
    symbol: str                  # Magic Eden collection symbol
    floor_sol: float
    floor_usd: float
    count_lent: int              # NFTs lent by this partner
    tier: str                    # "high" | "mid" | "low"

    @property
    def lent_value_usd(self) -> float:
        return self.floor_usd * self.count_lent

    @property
    def lent_value_sol(self) -> float:
        return self.floor_sol * self.count_lent


INVENTORY: tuple[Collection, ...] = (
    # ---- headline tier (rare-trait specific NFTs, ≥ $4k floor) ----
    # Two high-trait Mad Lads sourced from the partner inventory.  Floor here
    # is the rarity-conditioned floor, not the collection floor.  Placeholder
    # at $6,000 each — refine once specific token IDs are picked.
    Collection("mad_lads_rare",   "Mad Lads (rare-trait)",        "mad_lads",               74.05,  6000.0,  2, "headline"),
    # ---- high tier (≥ $900 floor) ----
    Collection("smb",             "Solana Monkey Business",       "solana_monkey_business", 17.586, 1425.0,  5, "high"),
    Collection("claynosaurz",     "Claynosaurz",                  "claynosaurz",            12.049,  976.0,  7, "high"),
    # ---- mid tier ($300-$900 floor) ----
    Collection("galactic_geckos", "Galactic Gecko Space Garage",  "galactic_geckos",         6.753,  547.0, 15, "mid"),
    Collection("mad_lads",        "Mad Lads",                     "mad_lads",                6.100,  494.0, 15, "mid"),
    # ---- low tier (< $300 floor) ----
    Collection("okay_bears",      "Okay Bears",                   "okay_bears",              1.825,  148.0, 50, "low"),
)


# ----- Aggregate metrics (derived but pre-computed for convenience) -----

TOTAL_NFTS = sum(c.count_lent for c in INVENTORY)
TOTAL_VALUE_USD = sum(c.lent_value_usd for c in INVENTORY)
TOTAL_VALUE_SOL = sum(c.lent_value_sol for c in INVENTORY)

BY_SLUG = {c.slug: c for c in INVENTORY}

TIER_ROLLUP = {
    "headline": [c for c in INVENTORY if c.tier == "headline"],
    "high":     [c for c in INVENTORY if c.tier == "high"],
    "mid":      [c for c in INVENTORY if c.tier == "mid"],
    "low":      [c for c in INVENTORY if c.tier == "low"],
}


if __name__ == "__main__":
    print(f"Snapshot date: {SNAPSHOT_DATE}   SOL/USD: ${SOL_USD_RATE:,.2f}")
    print(f"Total: {TOTAL_NFTS} NFTs, "
          f"${TOTAL_VALUE_USD:,.0f}  ({TOTAL_VALUE_SOL:.2f} SOL)")
    print()
    for tier, items in TIER_ROLLUP.items():
        sub_val = sum(c.lent_value_usd for c in items)
        sub_cnt = sum(c.count_lent for c in items)
        print(f"[{tier:>4s}] {len(items)} collections, {sub_cnt} NFTs, "
              f"${sub_val:,.0f}  ({100 * sub_val / TOTAL_VALUE_USD:.1f}% of pool)")
        for c in items:
            print(f"    {c.display_name:<32s} ${c.floor_usd:>7,.0f}  x{c.count_lent:>3d}  "
                  f"= ${c.lent_value_usd:>8,.0f}")
