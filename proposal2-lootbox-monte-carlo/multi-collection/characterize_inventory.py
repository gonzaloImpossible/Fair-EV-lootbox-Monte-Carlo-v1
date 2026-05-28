"""
Characterize the lent-inventory pool.

Joins live floor prices from inventory_raw.csv with the agreed lend counts
per partner, then computes per-collection contribution, share metrics, and
tier classification. Outputs inventory.csv + a printed summary.

Step 1 of Proposal 3.
"""

import csv
from pathlib import Path


HERE = Path(__file__).parent
RAW_CSV = HERE / "inventory_raw.csv"
OUT_CSV = HERE / "inventory.csv"


# Agreed lend counts (NFTs per partner). Per user 2026-05-25.
LEND_COUNTS = {
    "mayc":            3,   # BAYC ecosystem stand-in
    "lil_pudgys":      5,   # Pudgy ecosystem stand-in
    "moonbirds":       2,
    "quirkies":        2,
    "azuki":           4,
    "good_vibes_club": 4,
    "doodles":         5,
    "rekt":            10,
    "sappy_seals":     20,
    "normies":         20,
}

# Display-friendly partner names (override matched_name where useful).
DISPLAY_NAME = {
    "mayc":       "Mutant Ape Yacht Club (BAYC eco.)",
    "lil_pudgys": "Lil Pudgys (Pudgy eco.)",
}


def tier_for_floor(floor_usd: float) -> str:
    """Bucket collections by floor price for gacha-tier mapping."""
    if floor_usd >= 5000:
        return "headline"   # 1-of-1-ish, ultra-rare pull
    if floor_usd >= 1500:
        return "high"
    if floor_usd >= 500:
        return "mid"
    return "low"


def main() -> None:
    with RAW_CSV.open() as f:
        raw = list(csv.DictReader(f))
    raw_by_slug = {r["slug"]: r for r in raw}

    rows = []
    for slug, count in LEND_COUNTS.items():
        if slug not in raw_by_slug:
            print(f"  [WARN] {slug} missing from {RAW_CSV.name}; skipping")
            continue
        r = raw_by_slug[slug]
        if r.get("status") != "ok":
            print(f"  [WARN] {slug} status={r.get('status')}; skipping")
            continue
        floor_eth = float(r["floor_eth"])
        floor_usd = float(r["floor_usd"])
        eth_usd = float(r["eth_usd_rate"])
        lent_value_usd = floor_usd * count
        lent_value_eth = floor_eth * count
        rows.append({
            "slug": slug,
            "display_name": DISPLAY_NAME.get(slug, r.get("matched_name") or slug),
            "collection_id": r.get("collection_id"),
            "floor_eth": floor_eth,
            "floor_usd": floor_usd,
            "count_lent": count,
            "lent_value_usd": lent_value_usd,
            "lent_value_eth": lent_value_eth,
            "tier": tier_for_floor(floor_usd),
            "eth_usd_rate": eth_usd,
            "source": r.get("source"),
            "fetched_at": r.get("fetched_at"),
        })

    total_usd = sum(r["lent_value_usd"] for r in rows)
    total_eth = sum(r["lent_value_eth"] for r in rows)
    total_count = sum(r["count_lent"] for r in rows)

    for r in rows:
        r["share_value_pct"] = 100 * r["lent_value_usd"] / total_usd if total_usd else 0
        r["share_count_pct"] = 100 * r["count_lent"] / total_count if total_count else 0

    rows.sort(key=lambda x: -x["lent_value_usd"])

    fieldnames = ["slug", "display_name", "collection_id", "floor_eth", "floor_usd",
                  "count_lent", "lent_value_usd", "lent_value_eth",
                  "share_value_pct", "share_count_pct",
                  "tier", "eth_usd_rate", "source", "fetched_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- Printed summary ----
    print()
    print("=" * 96)
    print(f"{'INVENTORY POOL — characterization':^96s}")
    print("=" * 96)
    print(f"{'Partner':<35s} {'Floor $':>10s} {'NFTs':>5s} {'Value $':>12s} "
          f"{'%val':>6s} {'%cnt':>6s} {'Tier':>9s}")
    print("-" * 96)
    for r in rows:
        print(f"{r['display_name']:<35s} {r['floor_usd']:>10,.0f} "
              f"{r['count_lent']:>5d} {r['lent_value_usd']:>12,.0f} "
              f"{r['share_value_pct']:>5.1f}% {r['share_count_pct']:>5.1f}% "
              f"{r['tier']:>9s}")
    print("-" * 96)
    print(f"{'TOTAL':<35s} {'':>10s} {total_count:>5d} {total_usd:>12,.0f} "
          f"{'100.0%':>6s} {'100.0%':>6s}")
    print(f"{'TOTAL (ETH)':<35s} {'':>10s} {'':>5s} {total_eth:>12,.3f}")

    # Tier rollup
    print()
    print(f"{'Tier rollup':^96s}")
    print("-" * 96)
    tier_agg: dict[str, dict] = {}
    for r in rows:
        t = tier_agg.setdefault(r["tier"],
                                {"count": 0, "value": 0.0, "collections": 0})
        t["count"] += r["count_lent"]
        t["value"] += r["lent_value_usd"]
        t["collections"] += 1
    for tier in ["headline", "high", "mid", "low"]:
        if tier not in tier_agg:
            continue
        t = tier_agg[tier]
        print(f"  {tier:<9s}  collections={t['collections']:>2d}  "
              f"NFTs={t['count']:>3d}  value=${t['value']:>10,.0f}  "
              f"({100 * t['value'] / total_usd:>4.1f}% of pool)")

    print()
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
