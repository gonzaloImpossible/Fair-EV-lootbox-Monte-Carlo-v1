"""
Fetch live floor prices for the 10 partner collections via Rarible BFF API.

Output: inventory.csv with one row per partner collection.

Step 1 of Proposal 3 (multi-collection lent-inventory gacha):
characterize and price the lent inventory pool.
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SEARCH_URL = "https://bff.rarible.com/api/market/collections/search"
FLOOR_CHANGE_URL = "https://bff.rarible.com/api/market/collections/{cid}/floor-price-change?period=D1"

# Partner collections.
#   query / expected_name → used by the search-based path.
#   contract → optional fallback; if search fails or yields no floor, fetch via
#              /collections/:id/floor-price-change. Required for Normies because
#              the Rarible BFF errors on any "normie*" search text.
PARTNERS = [
    {"slug": "sappy_seals",      "query": "Sappy Seals",            "expected_name": "Sappy Seals",         "contract": None},
    # Pudgy Penguins main floor (~$10k) is too thin a buffer at 1 NFT lent;
    # Pudgy ecosystem represented by Lil Pudgys instead.
    {"slug": "lil_pudgys",       "query": "Lil Pudgys",             "expected_name": "Lil Pudgys",          "contract": None},
    {"slug": "normies",          "query": "Normies",                "expected_name": "Normies",             "contract": "0x9eb6e2025b64f340691e424b7fe7022ffde12438"},
    {"slug": "quirkies",         "query": "Quirkies",               "expected_name": "Quirkies",            "contract": None},
    {"slug": "moonbirds",        "query": "Moonbirds",              "expected_name": "Moonbirds",           "contract": None},
    # BAYC's main collection floor (~$20k) exceeds the $5-10k lend cap, so the
    # Yuga ecosystem is represented by MAYC instead.
    {"slug": "mayc",             "query": "Mutant Ape Yacht Club",  "expected_name": "MutantApeYachtClub", "contract": None},
    {"slug": "azuki",            "query": "Azuki",                  "expected_name": "Azuki",               "contract": None},
    {"slug": "doodles",          "query": "Doodles",                "expected_name": "Doodles",             "contract": None},
    {"slug": "good_vibes_club",  "query": "Good Vibes Club",        "expected_name": "Good Vibes Club",     "contract": None},
    {"slug": "rekt",             "query": "Rektguy",                "expected_name": "rektguy",             "contract": None},
]


COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Origin": "https://rarible.com",
    "Referer": "https://rarible.com/",
}


def search_collection(query: str, size: int = 5) -> list[dict]:
    body = json.dumps({
        "text": query,
        "size": size,
        "blockchains": ["ETHEREUM"],
    }).encode("utf-8")
    req = urllib.request.Request(SEARCH_URL, data=body, headers=COMMON_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_floor_by_contract(contract: str) -> tuple[float | None, float | None, str]:
    """Fallback path: use /collections/:id/floor-price-change which returns a
    time-series of floors. Take the most recent point.

    Returns (floor_eth, eth_usd_rate, collection_id).
    """
    cid = f"ETHEREUM:{contract}"
    url = FLOOR_CHANGE_URL.format(cid=cid)
    req = urllib.request.Request(url, headers=COMMON_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    series = payload.get("priceChange") or []
    if not series:
        return None, None, cid
    floor_eth = float(series[-1].get("value"))
    currency = payload.get("currency") or {}
    rate = currency.get("usdExchangeRate")
    eth_usd = float(rate) if rate is not None else None
    return floor_eth, eth_usd, cid


def pick_best_match(results: list[dict], expected_name: str) -> dict | None:
    if not results:
        return None
    # Prefer exact (case-insensitive) name match, then prefix match, else first.
    expected = expected_name.strip().lower()
    for r in results:
        if r.get("name", "").strip().lower() == expected:
            return r
    for r in results:
        if r.get("name", "").strip().lower().startswith(expected):
            return r
    return results[0]


def extract_floor(record: dict) -> tuple[float | None, float | None]:
    """Return (floor_eth, eth_usd_rate) from a search result record."""
    fp = record.get("floorPrice") or {}
    amount = fp.get("amount")
    currency = fp.get("currency") or {}
    rate = currency.get("usdExchangeRate")
    floor_eth = float(amount) if amount is not None else None
    eth_usd = float(rate) if rate is not None else None
    return floor_eth, eth_usd


def main() -> None:
    out_dir = Path(__file__).parent
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    rows = []
    for p in PARTNERS:
        row = {
            "slug": p["slug"],
            "query": p["query"],
            "matched_name": None,
            "collection_id": None,
            "floor_eth": None,
            "eth_usd_rate": None,
            "floor_usd": None,
            "source": None,
            "status": "no_match",
            "fetched_at": fetched_at,
        }

        # Path 1: search.
        try:
            results = search_collection(p["query"], size=5)
            match = pick_best_match(results, p["expected_name"])
            if match is not None:
                floor_eth, eth_usd = extract_floor(match)
                row["matched_name"] = match.get("name")
                row["collection_id"] = match.get("id")
                if floor_eth and eth_usd:
                    row["floor_eth"] = floor_eth
                    row["eth_usd_rate"] = eth_usd
                    row["floor_usd"] = floor_eth * eth_usd
                    row["source"] = "search"
                    row["status"] = "ok"
        except urllib.error.URLError as e:
            row["error"] = f"search: {e}"

        # Path 2: floor-price-change fallback (uses contract).
        if row["status"] != "ok" and p.get("contract"):
            try:
                floor_eth, eth_usd, cid = fetch_floor_by_contract(p["contract"])
                if floor_eth and eth_usd:
                    row["collection_id"] = cid
                    row["matched_name"] = row["matched_name"] or p["expected_name"]
                    row["floor_eth"] = floor_eth
                    row["eth_usd_rate"] = eth_usd
                    row["floor_usd"] = floor_eth * eth_usd
                    row["source"] = "floor-price-change"
                    row["status"] = "ok"
            except urllib.error.URLError as e:
                row["error"] = (row.get("error") or "") + f" | floor-change: {e}"

        if row["status"] == "ok":
            print(f"  {p['slug']:18s}  {row['matched_name']:30s}  "
                  f"{row['floor_eth']:>8}  ${row['floor_usd']:,.0f}   ({row['source']})")
        else:
            print(f"  [WARN] {p['slug']:18s}  status={row['status']}")

        rows.append(row)
        time.sleep(0.3)  # be polite to the public BFF

    csv_path = out_dir / "inventory_raw.csv"
    fieldnames = ["slug", "query", "matched_name", "collection_id",
                  "floor_eth", "eth_usd_rate", "floor_usd",
                  "source", "status", "fetched_at", "error"]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {csv_path}")

    bad = [r for r in rows if r.get("status") != "ok"]
    if bad:
        print(f"\n[WARN] {len(bad)} collection(s) need manual review:")
        for r in bad:
            print(f"  {r['slug']:18s}  query='{r['query']}'  status={r.get('status')}")


if __name__ == "__main__":
    main()
