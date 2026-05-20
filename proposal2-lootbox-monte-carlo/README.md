# Fair-EV NFT Lootbox — Monte Carlo Simulator (Proposal 2)

> Stochastic pricing model for a USDT-denominated NFT lootbox with discrete tier outcomes and instant-buyback secondary mechanic. Tests whether a "no house edge" positioning can be profitable purely on flip-spread economics. Built for the Rarible × Sappy Seals partnership.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-v1-orange)](#)

## Companion to Proposal 1

This is the **fair-EV lootbox** variant of the Sappy pricing work. Companion model:

- **Proposal 1 (Gacha)**: Continuous-tier ETH-denominated pack with positive house edge. Revenue from pack edge + buyback spread.
- **Proposal 2 (this repo)**: Four-outcome USDT lootbox with near-zero edge. Revenue from buyback spread only — pawn-shop / market-maker business, not a casino business.

## What this does

Models a lootbox where every box has 4 possible outcomes ($30 / $50 / $80 / $220), priced just above expected pull value, with a 6% spread on instant buybacks. Tests:

1. Whether the spread alone is enough to absorb tail risk from grand-prize hold-throughs
2. Where the break-even box price sits
3. How sensitive margin is to user buyback behavior, inventory cost, and grand-prize value drift

## Headline finding

**A true zero-edge box at $50 doesn't work.** Grand-prize hold-throughs cost more than buyback fees can recoup.

| Box price | Mean margin | P(ruin) | Verdict |
|---|---|---|---|
| $50 (zero edge) | **−$0.38** | 62% | Structurally broken |
| **$55 (recommended)** | **+$1.71 (3.1%)** | 4% | Viable |
| $60 | +$3.86 (6.4%) | <1% | Profitable but starts feeling like a casino |

Box price needs ~10% implied edge to survive the tail. The 6% haircut is necessary but not sufficient on its own.

## Quick start

```bash
git clone <your-repo-url>
cd proposal2-lootbox-monte-carlo
pip install -r requirements.txt
python lootbox_monte_carlo.py
```

Outputs land in `./outputs/`:

```
outputs/
├── summary_stats.csv          # Headline metrics
├── margin_distribution.png    # Per-box margin histogram
├── cumulative_paths.png       # Campaign trajectory
├── box_price_sweep.png        # Break-even analysis
├── box_price_sweep.csv
├── haircut_sweep.png          # Margin vs haircut size
├── haircut_sweep.csv
├── buyback_sweep.png          # Margin vs user buyback rate
├── buyback_sweep.csv
├── sensitivity_tornado.png    # Which inputs move margin most
└── sensitivity_tornado.csv
```

## Configuration

All inputs live in the `LootboxParams` dataclass at the top of `lootbox_monte_carlo.py`.

```python
@dataclass
class LootboxParams:
    # Box pricing (USDT)
    box_price: float = 55.0             # Revised from $50 — see findings

    # Tier outcomes (USDT)
    val_floor: float = 30.0
    val_mid_low: float = 50.0
    val_mid_high: float = 80.0
    val_grand: float = 220.0             # Sappy Seal floor

    # Tier probabilities (sum to 1.0, p_grand = 1 − others)
    p_floor: float = 0.60
    p_mid_low: float = 0.25
    p_mid_high: float = 0.10

    # Buyback economics
    haircut: float = 0.06                # Anchored to industry comp
    p_buyback_floor: float = 0.70
    p_buyback_mid_low: float = 0.50
    p_buyback_mid_high: float = 0.30
    p_buyback_grand: float = 0.15

    # Inventory cost basis
    cost_basis: float = 0.85

    # Simulation
    n_boxes_per_campaign: int = 1000
    n_paths: int = 500
    n_per_box_sims: int = 50000
    seed: int = 42
```

## Model

For each simulated box:

```
1. Draw tier ~ Categorical(p_floor, p_mid_low, p_mid_high, p_grand)
2. NFT value = deterministic per tier ($30 / $50 / $80 / $220)
3. Draw buyback ~ Bernoulli(p_buyback | tier)
4. Compute margin:
     if buyback: margin = haircut × NFT_value
                 (Box rev collected, 94% returned, NFT to inventory)
     else:       margin = box_price − cost_basis × NFT_value
                 (User keeps NFT, house ate the inventory)
```

### The buyback-only revenue insight

When a user buys back, the NFT returns to inventory — it's not a P&L event. The only realized cash flow is the spread (`haircut × NFT_value`). When a user holds, they walk away with the NFT and the inventory cost crystallizes against box revenue.

This asymmetry is the entire model. The hold case for the grand prize ($55 box revenue − $187 inventory cost = **−$132 per Sappy held**) is what kills the zero-edge configuration. With 5% grand-prize odds and 85% of grand winners keeping the Sappy, the hold tail dominates 95 buyback fees at $1.80 each.

### Why discrete tiers (vs Proposal 1's lognormal)

1. Product positioning: "4 clear outcomes" — simpler user comms
2. Inventory can be hand-picked at exact target values (treasury sourcing)
3. Strips second-moment effects to isolate first-moment economics

Within-tier dispersion can be added back in V2 if needed for realism.

## Three insights for the Sappy pitch

1. **"Fair box, fair flip" needs a 10% box markup to survive.** The marketing line is honest only if the 10% is framed as "operations fee" rather than house edge. 6% spread alone cannot absorb grand-prize tail.

2. **Sappy floor price is a counterparty risk.** If Sappy rallies from 0.11 → 0.15 ETH mid-campaign, grand-prize hold tail eats the margin. Mitigation: price boxes as a % of current Sappy floor, or quarterly re-price.

3. **Cost basis is the #1 lever — same as Proposal 1.** Every percentage point of treasury discount is worth more than the entire 6% haircut. Sappy negotiation = "give us better inventory access," not "let us increase the fee."

## Roadmap

- [ ] **Inventory depletion** — currently assumes infinite pool. Need Rolling Jackpot mechanic.
- [ ] **Floor price drift** — grand-prize value treated as static. Add geometric Brownian motion on tier values.
- [ ] **Within-tier dispersion** — currently discrete. Add lognormal if real inventory has spread.
- [ ] **Multi-collection pools** — single-collection model. Real product spans multiple IPs.
- [ ] **Stochastic buyback rates** — currently deterministic. Could model market-condition dependence.
- [ ] **Real Sappy minthub calibration** — buyback rates are educated guesses pending Adam's data.

## Repo structure

```
proposal2-lootbox-monte-carlo/
├── lootbox_monte_carlo.py     # Main script
├── requirements.txt           # numpy, pandas, matplotlib
├── README.md                  # You are here
├── LICENSE                    # MIT
├── .gitignore                 # Standard Python
└── outputs/                   # Generated artifacts (gitignored)
```

## Requirements

- Python 3.9+
- `numpy`, `pandas`, `matplotlib`

```bash
pip install -r requirements.txt
```

## License

MIT — see [LICENSE](LICENSE).

## Context

Built for the Rarible × Sappy Seals partnership exploration. Companion methodology doc (private): Notion → Sappy Seals Proposal → Proposal 2: Fair-EV Lootbox v1.
