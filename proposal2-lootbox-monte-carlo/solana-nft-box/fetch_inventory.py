"""
Fetch live floor prices for the 4 Solana partner collections via Magic Eden.

Output: inventory_raw.csv with one row per partner collection.

Magic Eden endpoints (public, no auth):
    GET /v2/collections/{symbol}/stats
        → {symbol, floorPrice (lamports), listedCount, avgPrice24hr, volumeAll}

SOL/USD spot:
    CoinGecko /api/v3/simple/price?ids=solana&vs_currencies=usd
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ME_STATS_URL = "https://api-mainnet.magiceden.dev/v2/collections/{symbol}/stats"
CG_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
LAMPORTS_PER_SOL = 1_000_000_000


# Magic Eden collection symbols.  These are the slugs used in
# https://magiceden.io/marketplace/<symbol>.
PARTNERS = [
    {"slug": "mad_lads",         "symbol": "mad_lads",                "expected_name": "Mad Lads"},
    {"slug": "claynosaurz",      "symbol": "claynosaurz",             "expected_name": "Claynosaurz"},
    {"slug": "smb",              "symbol": "solana_monkey_business",  "expected_name": "Solana Monkey Business"},
    {"slug": "galactic_geckos",  "symbol": "galactic_geckos",         "expected_name": "Galactic Gecko Space Garage"},
    # Low-floor anchor added so the gacha has a real "low" tier and the box
    # price can be sub-$300 without going EV-negative on every pull.
    {"slug": "okay_bears",       "symbol": "okay_bears",              "expected_name": "Okay Bears"},
]


COMMON_HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
}


def fetch_sol_usd() -> float:
    req = urllib.request.Request(CG_PRICE_URL, headers=COMMON_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return float(data["solana"]["usd"])


def fetch_collection_stats(symbol: str) -> dict:
    url = ME_STATS_URL.format(symbol=symbol)
    req = urllib.request.Request(url, headers=COMMON_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    out_dir = Path(__file__).parent
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        sol_usd = fetch_sol_usd()
        print(f"SOL/USD = ${sol_usd:,.2f}  (CoinGecko)")
    except urllib.error.URLError as e:
        print(f"[FATAL] could not fetch SOL/USD: {e}")
        sys.exit(1)

    rows = []
    for p in PARTNERS:
        row = {
            "slug": p["slug"],
            "symbol": p["symbol"],
            "matched_name": None,
            "floor_sol": None,
            "sol_usd_rate": sol_usd,
            "floor_usd": None,
            "listed_count": None,
            "source": None,
            "status": "no_match",
            "fetched_at": fetched_at,
            "error": "",
        }

        try:
            stats = fetch_collection_stats(p["symbol"])
            floor_lamports = stats.get("floorPrice")
            if floor_lamports is not None:
                floor_sol = float(floor_lamports) / LAMPORTS_PER_SOL
                row["matched_name"] = stats.get("symbol") or p["expected_name"]
                row["floor_sol"] = floor_sol
                row["floor_usd"] = floor_sol * sol_usd
                row["listed_count"] = stats.get("listedCount")
                row["source"] = "magic-eden-stats"
                row["status"] = "ok"
        except urllib.error.URLError as e:
            row["error"] = f"me-stats: {e}"
        except (KeyError, ValueError) as e:
            row["error"] = f"me-stats parse: {e}"

        if row["status"] == "ok":
            print(f"  {p['slug']:18s}  {row['matched_name']:32s}  "
                  f"{row['floor_sol']:>7.3f} SOL  ${row['floor_usd']:>7,.0f}  "
                  f"listed={row['listed_count']}")
        else:
            print(f"  [WARN] {p['slug']:18s}  status={row['status']}  "
                  f"err={row.get('error')}")

        rows.append(row)
        time.sleep(0.5)

    csv_path = out_dir / "inventory_raw.csv"
    fieldnames = ["slug", "symbol", "matched_name",
                  "floor_sol", "sol_usd_rate", "floor_usd",
                  "listed_count", "source", "status",
                  "fetched_at", "error"]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {csv_path}")

    bad = [r for r in rows if r.get("status") != "ok"]
    if bad:
        print(f"\n[WARN] {len(bad)} collection(s) need manual review:")
        for r in bad:
            print(f"  {r['slug']:18s}  symbol='{r['symbol']}'  status={r.get('status')}")


if __name__ == "__main__":
    main()
