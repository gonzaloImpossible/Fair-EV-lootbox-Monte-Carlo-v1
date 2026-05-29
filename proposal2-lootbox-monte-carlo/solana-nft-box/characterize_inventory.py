"""
Characterize the lent-inventory pool for the Solana gacha campaign.

Joins live floor prices from inventory_raw.csv with the agreed lend counts
per partner, then computes per-collection contribution, share metrics, and
tier classification. Outputs inventory.csv + a printed summary.

Tier cutoffs are Solana-specific (floors are lower than the ETH proposal):
    high  ≥ $900   →  SMB, Claynosaurz
    mid   $300-$900 → Mad Lads, Galactic Geckos
    low   < $300   →  Okay Bears
"""

import csv
from pathlib import Path


HERE = Path(__file__).parent
RAW_CSV = HERE / "inventory_raw.csv"
OUT_CSV = HERE / "inventory.csv"


# Agreed lend counts (NFTs per partner). Sized to ~$5-10k principal each
# at floor and to give a clean 13/33/54% high/mid/low split by NFT count.
LEND_COUNTS = {
    "smb":             5,
    "claynosaurz":     7,
    "mad_lads":        15,
    "galactic_geckos": 15,
    "okay_bears":      50,
}


# Display-friendly partner names.
DISPLAY_NAME = {
    "smb":             "Solana Monkey Business",
    "claynosaurz":     "Claynosaurz",
    "mad_lads":        "Mad Lads",
    "galactic_geckos": "Galactic Gecko Space Garage",
    "okay_bears":      "Okay Bears",
}


def tier_for_floor(floor_usd: float) -> str:
    """Bucket collections by floor for gacha-tier mapping (Solana cutoffs)."""
    if floor_usd >= 900:
        return "high"
    if floor_usd >= 300:
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
        floor_sol = float(r["floor_sol"])
        floor_usd = float(r["floor_usd"])
        sol_usd = float(r["sol_usd_rate"])
        lent_value_usd = floor_usd * count
        lent_value_sol = floor_sol * count
        rows.append({
            "slug": slug,
            "display_name": DISPLAY_NAME.get(slug, r.get("matched_name") or slug),
            "symbol": r.get("symbol"),
            "floor_sol": floor_sol,
            "floor_usd": floor_usd,
            "count_lent": count,
            "lent_value_usd": lent_value_usd,
            "lent_value_sol": lent_value_sol,
            "tier": tier_for_floor(floor_usd),
            "sol_usd_rate": sol_usd,
            "source": r.get("source"),
            "fetched_at": r.get("fetched_at"),
        })

    total_usd = sum(r["lent_value_usd"] for r in rows)
    total_sol = sum(r["lent_value_sol"] for r in rows)
    total_count = sum(r["count_lent"] for r in rows)

    for r in rows:
        r["share_value_pct"] = 100 * r["lent_value_usd"] / total_usd if total_usd else 0
        r["share_count_pct"] = 100 * r["count_lent"] / total_count if total_count else 0

    rows.sort(key=lambda x: -x["lent_value_usd"])

    fieldnames = ["slug", "display_name", "symbol", "floor_sol", "floor_usd",
                  "count_lent", "lent_value_usd", "lent_value_sol",
                  "share_value_pct", "share_count_pct",
                  "tier", "sol_usd_rate", "source", "fetched_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- Printed summary ----
    print()
    print("=" * 96)
    print(f"{'SOLANA INVENTORY POOL — characterization':^96s}")
    print("=" * 96)
    print(f"{'Partner':<32s} {'Floor $':>10s} {'NFTs':>5s} {'Value $':>12s} "
          f"{'%val':>6s} {'%cnt':>6s} {'Tier':>9s}")
    print("-" * 96)
    for r in rows:
        print(f"{r['display_name']:<32s} {r['floor_usd']:>10,.0f} "
              f"{r['count_lent']:>5d} {r['lent_value_usd']:>12,.0f} "
              f"{r['share_value_pct']:>5.1f}% {r['share_count_pct']:>5.1f}% "
              f"{r['tier']:>9s}")
    print("-" * 96)
    print(f"{'TOTAL':<32s} {'':>10s} {total_count:>5d} {total_usd:>12,.0f} "
          f"{'100.0%':>6s} {'100.0%':>6s}")
    print(f"{'TOTAL (SOL)':<32s} {'':>10s} {'':>5s} {total_sol:>12,.3f}")

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
    for tier in ["high", "mid", "low"]:
        if tier not in tier_agg:
            continue
        t = tier_agg[tier]
        print(f"  {tier:<5s}  collections={t['collections']:>2d}  "
              f"NFTs={t['count']:>3d}  value=${t['value']:>10,.0f}  "
              f"({100 * t['value'] / total_usd:>4.1f}% of pool)")

    print()
    print(f"Wrote {OUT_CSV}")


if __name__ == "__main__":
    main()
