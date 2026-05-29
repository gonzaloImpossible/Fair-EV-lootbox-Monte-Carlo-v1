"""
Probe a shortlist of well-known Solana NFT collections for current floors.
Goal: identify 1-2 low-floor (sub-$150) partners to anchor the gacha's
"low" tier, since the four base partners (Mad Lads, Claynosaurz, SMB,
Galactic Geckos) all floor above $500.

Run: python3 probe_low_floor.py
"""

import json
import time
import urllib.error
import urllib.request


ME_STATS_URL = "https://api-mainnet.magiceden.dev/v2/collections/{symbol}/stats"
CG_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
LAMPORTS_PER_SOL = 1_000_000_000

HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
}

# Candidate Solana collections to probe. These were historically prominent
# Solana NFT projects whose floors have likely compressed below $150.
CANDIDATES = [
    "famous_fox_federation",
    "okay_bears",
    "degods",                  # may have migrated off-chain, included for probe
    "y00ts",                   # likewise
    "abc",
    "cets_on_creck",
    "aurory",
    "thugbirdz",
    "trippin_ape_tribe",
    "frogana",
    "tensorians",
    "banx",
    "cyber_frogs",
    "bears_reloaded",
    "solpunks",
    "shadowy_super_coder_dao",
    "bonkz",
    "lifinity_flares",
    "the_heimer",
    "boryoku_dragonz",
    "aurorians",
    "stoned_ape_crew",
    "skeleton_crew_skull",
    "primates",
    "blocksmith_labs",
    "communi3",
    "froganas",
    "retardio_cousins",
    "the_remnants_",
    "transdimensional_fox_federation",
]


def fetch_sol_usd() -> float:
    req = urllib.request.Request(CG_PRICE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return float(json.loads(resp.read())["solana"]["usd"])


def fetch_stats(symbol: str) -> dict | None:
    url = ME_STATS_URL.format(symbol=symbol)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"_error": str(e)}


def main() -> None:
    sol_usd = fetch_sol_usd()
    print(f"SOL/USD = ${sol_usd:,.2f}\n")
    print(f"{'symbol':<35s} {'floor SOL':>10s} {'floor USD':>10s} {'listed':>8s}")
    print("-" * 70)

    results: list[tuple[str, float, float, int]] = []
    errors: list[tuple[str, str]] = []
    for sym in CANDIDATES:
        stats = fetch_stats(sym)
        if stats is None or "_error" in (stats or {}):
            errors.append((sym, (stats or {}).get("_error", "no data")))
            time.sleep(0.3)
            continue
        floor_lamports = stats.get("floorPrice")
        if floor_lamports is None:
            errors.append((sym, "no floor"))
            time.sleep(0.3)
            continue
        floor_sol = float(floor_lamports) / LAMPORTS_PER_SOL
        floor_usd = floor_sol * sol_usd
        listed = int(stats.get("listedCount") or 0)
        results.append((sym, floor_sol, floor_usd, listed))
        time.sleep(0.3)

    # Sort by floor USD ascending — cheap first.
    results.sort(key=lambda r: r[2])
    for sym, sol, usd, listed in results:
        flag = "  ← low-tier candidate" if usd < 150 else ""
        print(f"{sym:<35s} {sol:>10.3f} {usd:>10,.0f} {listed:>8d}{flag}")

    if errors:
        print("\nProbe errors:")
        for sym, err in errors:
            print(f"  {sym:<35s}  {err}")


if __name__ == "__main__":
    main()
