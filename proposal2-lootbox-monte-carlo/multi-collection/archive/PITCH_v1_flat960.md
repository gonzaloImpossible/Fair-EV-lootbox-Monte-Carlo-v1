# Rarible Multi-Collection NFT Gacha — Internal Approval

*Pitch document for internal review. Numbers from Monte Carlo simulation
(1,000 paths × 1,000 pulls per campaign, inventory snapshot 2026-05-25.)*

---

## 1. Executive summary

A **capital-light**, **inventory-lent** NFT gacha that lets Rarible run a
recurring weekly campaign across 11 partner collections without buying any
inventory. Rarible plays two roles — operator and small co-lender — and
walks away with **~520% ROI on $25k of working capital** per weekly campaign
in expectation, with **zero observed capital-loss paths** across 1,000
simulations.

| | |
|---|---:|
| Rarible's capital at risk | **$25,000** |
| Expected operator return per week | **$155,000** ($130k profit + $25k capital) |
| Expected operator ROI | **520%** (p5 357%, p95 672%) |
| Capital-loss probability | **0%** (over 1,000 simulated weeks) |
| External lender recovery ratio | **205%** (2× principal) |
| Headline max user ROI per pull | **+961%** (10.6× on a Pudgy hit) |

---

## 2. The model in one paragraph

11 partner collections lend **$74,288 of NFTs** as inventory. Rarible adds
**$25,000 cash** as a working-capital buffer. Users buy **$960 boxes**,
each resolving to one of four outcomes (headline / high / mid / low NFT, or
"1 shard"). After each NFT pull, the gacha offers to buy the NFT back
instantly at **94% of its floor price** — most users accept (~63% blended
acceptance). When inventory drops below 50% (or the headline tier empties),
the operator buys missing NFTs back from the open market, paid from the
cashbox. At end of the weekly campaign, debt is repaid to lenders first,
then Rarible takes its capital back, then the remaining profit is split.

---

## 3. The inventory pool

Eleven partner collections contribute **77 NFTs worth $74,288** total
principal. Locked floor prices from Rarible BFF (2026-05-25 snapshot).

| Collection | Tier | Floor | Count lent | Lent value | Share |
|---|---|---:|---:|---:|---:|
| **Pudgy Penguins (headline)** | headline | $10,191 | 2 | $20,382 | 27.4% |
| Azuki | high | $1,786 | 4 | $7,144 | 9.6% |
| MAYC (BAYC ecosystem) | high | $2,106 | 3 | $6,318 | 8.5% |
| Quirkies | high | $2,338 | 2 | $4,676 | 6.3% |
| Moonbirds | high | $2,043 | 2 | $4,086 | 5.5% |
| Lil Pudgys (Pudgy eco) | mid | $1,236 | 5 | $6,180 | 8.3% |
| Good Vibes Club | mid | $1,453 | 4 | $5,812 | 7.8% |
| Doodles | mid | $1,158 | 5 | $5,790 | 7.8% |
| Rektguy | mid | $562 | 10 | $5,620 | 7.6% |
| Sappy Seals | low | $290 | 20 | $5,800 | 7.8% |
| Normies | low | $124 | 20 | $2,480 | 3.3% |
| **TOTAL** | | | **77** | **$74,288** | **100%** |

**Two design decisions worth noting:**

1. **BAYC ($20,302 floor) was swapped for MAYC** ($2,106 floor) because BAYC's
   floor exceeds the $5–10k partner lend band. The Yuga ecosystem is still
   represented at a feasible inventory size.
2. **Pudgy Penguins is the only headline-tier collection.** Two Pudgies are
   the entire jackpot — that's what gives users a 10× max-ROI outcome and is
   the structural reason restocks fire.

---

## 4. The mechanics

### 4a. Pull flow per box

```
                          $960 BOX
                              │
              ┌───────────────┼───────────────────────────┐
              │               │               │           │
           1% Pudgy        15% High        32% Mid     32% Low
        ($10,191)       ($1,786–2,338)   ($562–1,453) ($124–290)
              │               │               │           │
              ▼               ▼               ▼           ▼
        Auto-buyback offer at 94% of floor
              │               │               │           │
        accept 5% │     accept 25%   │   accept 60%   accept 85%
              │               │               │           │
        keep NFT or take cash; NFT returns to pool on accept
                              │
                              └────► (separate branch)
                          20% Consolation
                          (1 shard; 5 shards → 1 free box)
```

### 4b. Auto-buyback flywheel

- User pulls → operator offers buyback at 94% of floor
- **If accepted**: NFT returns to pool (free to be pulled again), operator
  pays the 94% out of cashbox, pockets the 6% spread
- **If kept**: NFT permanently leaves the pool; lender is owed its value
  at settlement
- ~63% blended acceptance means most pulls cycle through the pool multiple
  times during the week

### 4c. Restock

- Triggered when total inventory < 50% (38 NFTs) OR when the headline tier
  is empty
- Operator buys missing NFTs from the open market at floor, paid from cashbox
- Reduces lender debt accordingly
- Expected: ~8 restocks per 1,000-pull campaign

### 4d. End-of-campaign settlement (waterfall)

```
1. CASHBOX (at end of campaign)
       = Σ box revenue − Σ auto-buyback payouts − Σ restock costs − Σ consolation costs

2. SENIOR LENDER DEBT REPAID
       = min(cashbox, remaining lender debt)
       Lenders made whole on NFTs that left the pool and weren't restocked.

3. OPERATOR CAPITAL RETURNED
       = min(cashbox-post-debt, $25,000)
       Rarible gets its working-capital buffer back.

4. PROFIT = remaining cashbox
       Split as follows:
       ┌─────────────────────────────────────────────────────────────┐
       │  OPERATOR FEE                        = 50% × profit         │ → Rarible
       │  ┌──────────────────────────────────────────────────────┐   │
       │  │ POST-FEE PROFIT  = 50% × profit                      │   │
       │  │   ├─ pro-rata to capital  →  25.18% to Rarible       │ → Rarible (as lender)
       │  │   └─ pro-rata to capital  →  74.82% to external      │ → NFT lenders
       │  └──────────────────────────────────────────────────────┘   │
       └─────────────────────────────────────────────────────────────┘

       Rarible total share        = 50%  +  50%×25.18%  =  62.6% of profit
       External lender total      = 50%  ×  74.82%      =  37.4% of profit
```

---

## 5. Headline economics (1,000-path simulation)

### 5a. Per campaign

| Cashflow item | Mean | p5 | p95 |
|---|---:|---:|---:|
| Cashbox at end | $258,102 | $191,354 | $320,987 |
| Lender debt (consumed-NFT $ value) | $25,558 | $1,236 | $49,595 |
| Profit (post-debt, post-capital-return) | $207,544 | $142,461 | $268,265 |
| **Rarible take (62.6% of profit)** | **$129,901** | $89,166 | $167,906 |
| External lender pool cash | $103,201 | $69,394 | $135,724 |
| Restock spend | $387,852 | — | — |
| Consolation/shard liability | $38,530 | — | — |

### 5b. Rarible's $25k → expected outcomes

| Component | $ |
|---|---:|
| Initial capital | $25,000 |
| Capital returned at settlement | $25,000 |
| Operator fee (50% × profit) | ~$103,800 |
| Lender pro-rata share (12.6% × profit) | ~$26,100 |
| **Total back to Rarible** | **$154,900** |
| **Net profit** | **$129,900** |
| **ROI on capital** | **~520%** |

### 5c. External lender recovery (per partner collection)

All 10 NFT-contributing partners earn the same recovery ratio under the
pro-rata structure (any variation is in absolute $ proportional to their
contribution). **Recovery ratio: ~205%** — every partner walks away with
≈2× their principal contribution per week.

| Partner | Lent | Mean recovery |
|---|---:|---:|
| Pudgy Penguins (headline) | $20,382 | $41,684 |
| Azuki | $7,144 | $14,611 |
| MAYC | $6,318 | $12,921 |
| Quirkies | $4,676 | $9,563 |
| Moonbirds | $4,086 | $8,357 |
| Lil Pudgys | $6,180 | $12,639 |
| Good Vibes Club | $5,812 | $11,886 |
| Doodles | $5,790 | $11,841 |
| Rektguy | $5,620 | $11,494 |
| Sappy Seals | $5,800 | $11,862 |
| Normies | $2,480 | $5,072 |

---

## 6. User experience

- **Max ROI per box: +961% (10.6×)** if user pulls a Pudgy and keeps it.
- **Worst outcome: 1 shard** (worth 1/5 of a future box = $192 perceived value).
  Critically, the "you got nothing" scenario doesn't exist — every pull
  delivers something the user can keep or sell.
- **Mid-tier "consolation prize" feel**: ~52% of pulls produce a mid- or
  low-tier NFT, where the auto-buyback offer typically becomes the better
  choice (instant cash at 94% of floor).
- **Per-pull expected value: ~$865**, on a $960 box → **~10% implied edge.**
  Comparable to industry — Beezie/Courtyard run wider edges (12-15%).

---

## 7. Industry benchmarks

| Platform | Blended auto-buyback acceptance | Discount on instant-sell |
|---|---:|---:|
| Courtyard | ~60-75% | 10-15% |
| Beezie | ~65-85% | 10-20% |
| **Rarible (this design)** | **~63%** | **6%** |

Rarible's design is **friendlier to users on the haircut (6% vs ~12%)**
while preserving an industry-comparable acceptance rate. That's the
marketing differentiator.

---

## 8. Sensitivity findings

Seven-lever sweep (each tested across 5 values, 500 paths each, holding
others at baseline):

| Lever | Direction of risk | Recommendation |
|---|---|---|
| `p_tier_headline` | Above 2% → **capital-loss paths appear** | Hold at 1% |
| `restock_threshold` | Higher = more restock churn = worse ROI | 25-50% (current 50% OK) |
| `buyback_acceptance_scale` | Higher = better for all parties | Invest in UX nudges |
| `initial_cashbox_usd` | Trade-off: ROI% ↓ but absolute $ ↑ | $25k is the sweet spot |
| `p_consolation` | Above 30% → ROI tanks (shard liability) | 10-20% range OK |
| `auto_buyback_discount` | Modest lever (+10 pp ROI per 2x widening) | Hold at 6% for UX |
| `shard_redemption_rate` | Low redemption = better op ROI | Assume 100% for safety |

**Three things must NOT happen**:
1. Headline pull rate above 2% (capital-loss risk)
2. Consolation rate above 30% (shard liability too high)
3. Operator capital below $20k (loses Pudgy double-pull safety margin)

---

## 9. Risks

1. **NFT floor volatility (not modeled)** — A sudden +50% floor jump on a
   heavily-consumed collection would inflate momentary debt and restock cost
   by ~50%. Mitigation: bigger cashbox buffer, or a per-campaign floor
   re-pricing trigger above a threshold move.

2. **Open-market liquidity for restock** — ~$388k of NFT purchases per
   campaign. Concentrated on Pudgies, Lil Pudgys, Doodles, Rektguy. On
   thinner markets (Quirkies, Moonbirds) the operator's buying could move
   floors against itself. Mitigation: split restocks into multiple smaller
   buys, or use Reservoir aggregator for slippage management.

3. **Cold-start demand risk** — Model assumes 1,000 box pulls of demand
   per week (~$960k of paid demand). Below that run-rate, the model still
   works mechanically but operator ROI scales down linearly. Mitigation:
   start with smaller campaign size (250-500 boxes) and verify acceptance
   rates before scaling up.

4. **Pudgy floor dependence** — Pudgy Penguins is 27% of pool value AND the
   sole headline tier. If Pudgy floor drops 50% mid-campaign, restock cost
   halves (good for operator) but lender recovery for Pudgy team specifically
   gets worse. Worth a side-letter agreement on settlement valuation.

5. **Partnership concentration** — All 11 partners must agree to lend on
   the same terms. If one drops late, the variant's tier mix changes and
   the box price needs recomputation.

6. **Regulatory / lootbox classification** — Not addressed here. Legal needs
   to confirm the auto-buyback mechanic doesn't reclassify the product
   under gambling regulations in EU/UK/US markets.

---

## 10. Recommendation

**Approve $25,000 of Rarible treasury capital** for a one-week pilot using
the `industry_calibrated` configuration above.

Expected outcomes (single week):
- Rarible profit: **$130k (520% ROI)**
- 11 partners recover **2× their lent value** in cash + returned NFTs
- Capital-loss probability: **0%** (within model assumptions)

Pilot-week unlocks the data we need to verify the two most uncertain
assumptions: real user acceptance rate (modeled at 63%) and effective
shard redemption rate (modeled at 100%, likely 30-60% in practice).

---

## 11. Next steps

1. **Partnership commitments**: confirm written intent from each of the
   11 collections to lend the specified NFT counts under the waterfall
   terms outlined in §4d.
2. **Settlement infrastructure**: design and deploy the multi-sig /
   on-chain settlement contract that automates the waterfall.
3. **UX prototype**: build the pull → auto-buyback flow with default-to-
   instant-sell behaviour and friction-on-keep for low-tier pulls.
4. **Legal review**: confirm regulatory classification per market.
5. **Stress tests**: run floor-shock and demand-shortfall sims before live
   launch. (Sim infrastructure ready; ~30 min of work.)
6. **Pilot**: launch a single-week campaign with full instrumentation, then
   re-calibrate model parameters from observed user behaviour.

---

## Appendix A — Model assumptions

See [simulation_assumptions.py](simulation_assumptions.py) for the full
declarative list. Highlights:

- Floor prices held constant within the campaign
- Demand deterministic at 1,000 pulls (no stochastic demand modeling yet)
- User acceptance Bernoulli, independent across pulls
- No gas fees / opex / CAC costs modeled
- Inventory restock is instantaneous at floor (no slippage)
- Single-campaign analysis only (no multi-week carryover)

## Appendix B — How to reproduce these numbers

```bash
cd proposal2-lootbox-monte-carlo/multi-collection
python3 inventory_static.py         # inventory snapshot
python3 gacha_config.py             # variant + per-pull EV math
python3 simulator.py                # full Monte Carlo (1000 paths)
python3 sensitivity.py              # 7-lever sweeps
python3 simulation_assumptions.py   # full declarative model dump
```

All inputs are in `inventory_static.py` (fixed snapshot) and `gacha_config.py`
(the one production variant `industry_calibrated`).
