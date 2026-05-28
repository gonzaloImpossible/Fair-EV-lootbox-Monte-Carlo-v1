# Campaign v1 — flat $960 pricing (archived 2026-05-27)

This document preserves the headline parameters and results of the original
`industry_calibrated` campaign design before the pre-sale price-discrimination
change introduced in v2.

## v1 configuration (frozen reference)

| Parameter | Value |
|---|---|
| Variant name | `industry_calibrated` |
| Box price | **$960** (single flat price) |
| Pre-sale | none |
| Tier probabilities | headline 1%, high 15%, mid 32%, low 32%, consolation 20% |
| Auto-buyback acceptance (h/m/l + headline) | 5% / 25% / 60% / 85% |
| Auto-buyback discount | 6% |
| Operator fee | 50% off the top |
| Operator pro-rata lender share | 25.18% |
| Total Rarible profit share | **62.59%** |
| Operator initial cashbox | $25,000 |
| Restock threshold | < 50% of pool OR headline tier empty |
| Pulls per campaign | 1,000 |
| Shards per box | 5 (1 shard = 1/5 of a future box) |
| Shard redemption rate | 100% (conservative) |

## v1 inventory (frozen 2026-05-25 snapshot)

77 NFTs across 11 collections, $74,288 total principal:

- 2× Pudgy Penguins (headline, $10,191)
- 4× Azuki, 3× MAYC, 2× Quirkies, 2× Moonbirds (high tier)
- 5× Lil Pudgys, 4× Good Vibes Club, 5× Doodles, 10× Rektguy (mid tier)
- 20× Sappy Seals, 20× Normies (low tier)

## v1 headline results (1,000 paths × 1,000 pulls)

| Metric | Value |
|---|---:|
| Operator ROI | 520% (p5 357%, p95 672%) |
| Operator total return | $155k on $25k capital |
| External lender pool recovery | 205% (2× principal) |
| Per-pull max user ROI | +961% (Pudgy hit kept) |
| Restock events / campaign | 8 |
| $ spent on restock | $388k |
| Capital-loss paths | 0% (at full 1,000 pulls) |

## v1 low-volume risk

| Pulls completed | Op ROI | P(cap-loss) |
|---:|---:|---:|
| 25 | 8.1% | 22.3% |
| 50 | 18.4% | 14.8% |
| 100 | 43.3% | 7.8% |
| 200 | 97.9% | 1.9% |
| 500 | 257% | 0.1% |
| 1000 | 520% | 0% |

## Why v1 was superseded

The flat-price design exposed Rarible to a 22% cap-loss probability at the
worst-case 25-pull volume scenario. v2 introduces a pre-sale price tier to
secure ≥200 commits before the campaign opens, eliminating the cold-start
demand risk.

## Full v1 artefacts

- [pitch_v1_flat960.html](pitch_v1_flat960.html) — internal approval memo
- [PITCH_v1_flat960.md](PITCH_v1_flat960.md) — markdown source

Re-running v1 numbers requires reverting `industry_calibrated` to
`box_price_usd=960.0`, `presale_pulls=0` in `gacha_config.py`.
