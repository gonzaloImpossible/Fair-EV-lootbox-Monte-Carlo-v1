"""
Frozen inventory snapshot for Proposal 3 multi-collection gacha.

Source: Rarible BFF API (collections/search + floor-price-change fallback),
fetched 2026-05-25 via fetch_inventory.py and curated via
characterize_inventory.py.

This is the canonical static reference for all downstream analysis. Re-run
the fetcher only on explicit refresh — do not regenerate silently.
"""

from dataclasses import dataclass


SNAPSHOT_DATE = "2026-05-25"
ETH_USD_RATE = 2106.0  # mean across the 10 fetches; tiny dispersion across rows


@dataclass(frozen=True)
class Collection:
    slug: str
    display_name: str
    contract_id: str             # "ETHEREUM:0x..."
    floor_eth: float
    floor_usd: float
    count_lent: int              # NFTs lent by this partner
    tier: str                    # "headline" | "high" | "mid" | "low"

    @property
    def lent_value_usd(self) -> float:
        return self.floor_usd * self.count_lent

    @property
    def lent_value_eth(self) -> float:
        return self.floor_eth * self.count_lent


INVENTORY: tuple[Collection, ...] = (
    # ---- headline tier (jackpot — 1-of-a-kind pulls; restock empties trigger refill) ----
    Collection("pudgy_penguins",  "Pudgy Penguins (headline)",          "ETHEREUM:0xbd3531da5cf5857e7cfaa92426877b022e612cf8",   4.864, 10191.0,  2, "headline"),
    # ---- high tier ($1.5k–$2.5k floor) ----
    Collection("azuki",           "Azuki",                              "ETHEREUM:0xed5af388653567af2f388e6224dc7c4b3241c544",   0.848,  1786.0,  4, "high"),
    Collection("mayc",            "Mutant Ape Yacht Club (BAYC eco.)",  "ETHEREUM:0x60e4d786628fea6478f785a6d7e704777c86a7c6",   1.000,  2106.0,  3, "high"),
    Collection("quirkies",        "Quirkies",                           "ETHEREUM:0xd4b7d9bb20fa20ddada9ecef8a7355ca983cccb1",   1.110,  2338.0,  2, "high"),
    Collection("moonbirds",       "Moonbirds",                          "ETHEREUM:0x23581767a106ae21c074b2276d25e5c3e136a68b",   0.970,  2043.0,  2, "high"),
    # ---- mid tier ($500–$1.5k floor) ----
    Collection("lil_pudgys",      "Lil Pudgys (Pudgy eco.)",            "ETHEREUM:0x524cab2ec69124574082676e6f654a18df49a048",   0.587,  1236.0,  5, "mid"),
    Collection("good_vibes_club", "Good Vibes Club",                    "ETHEREUM:0xb8ea78fcacef50d41375e44e6814ebba36bb33c4",   0.690,  1453.0,  4, "mid"),
    Collection("doodles",         "Doodles",                            "ETHEREUM:0x8a90cab2b38dba80c64b7734e58ee1db38b8992e",   0.550,  1158.0,  5, "mid"),
    Collection("rekt",            "Rektguy",                            "ETHEREUM:0xb852c6b5892256c264cc2c888ea462189154d8d7",   0.267,   562.0, 10, "mid"),
    # ---- low tier (<$500 floor) ----
    Collection("sappy_seals",     "Sappy Seals",                        "ETHEREUM:0x364c828ee171616a39897688a831c2499ad972ec",   0.138,   290.0, 20, "low"),
    Collection("normies",         "Normies",                            "ETHEREUM:0x9eb6e2025b64f340691e424b7fe7022ffde12438",   0.059,   124.0, 20, "low"),
)


# ----- Aggregate metrics (derived but pre-computed for convenience) -----

TOTAL_NFTS = sum(c.count_lent for c in INVENTORY)
TOTAL_VALUE_USD = sum(c.lent_value_usd for c in INVENTORY)
TOTAL_VALUE_ETH = sum(c.lent_value_eth for c in INVENTORY)

BY_SLUG = {c.slug: c for c in INVENTORY}

TIER_ROLLUP = {
    "headline": [c for c in INVENTORY if c.tier == "headline"],
    "high":     [c for c in INVENTORY if c.tier == "high"],
    "mid":      [c for c in INVENTORY if c.tier == "mid"],
    "low":      [c for c in INVENTORY if c.tier == "low"],
}


if __name__ == "__main__":
    print(f"Snapshot date: {SNAPSHOT_DATE}   ETH/USD: ${ETH_USD_RATE:,.0f}")
    print(f"Total: {TOTAL_NFTS} NFTs, "
          f"${TOTAL_VALUE_USD:,.0f}  ({TOTAL_VALUE_ETH:.2f} ETH)")
    print()
    for tier, items in TIER_ROLLUP.items():
        if not items:
            continue
        sub_val = sum(c.lent_value_usd for c in items)
        sub_cnt = sum(c.count_lent for c in items)
        print(f"[{tier:>4s}] {len(items)} collections, {sub_cnt} NFTs, "
              f"${sub_val:,.0f}  ({100 * sub_val / TOTAL_VALUE_USD:.1f}% of pool)")
        for c in items:
            print(f"    {c.display_name:<38s} ${c.floor_usd:>7,.0f}  x{c.count_lent:>3d}  "
                  f"= ${c.lent_value_usd:>8,.0f}")
