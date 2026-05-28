"""
Low-volume risk analysis for the Proposal 3 multi-collection gacha.

Question: what happens to operator economics + risk if a campaign only
sells 25 / 50 / 100 boxes instead of the modeled 1,000?

This is the most realistic risk to a real launch: marketing acquires fewer
users than expected, the campaign settles after a small number of pulls,
and the cashbox may not have accumulated enough to absorb early Pudgy holds.

We answer this by running independent Monte Carlo passes at each volume
level (rather than mid-campaign snapshots), so every metric reflects the
actual settled-at-N-pulls distribution.
"""

from __future__ import annotations

from dataclasses import replace
import numpy as np

from gacha_config import VARIANTS
from simulator import run_monte_carlo, aggregate


BASELINE = VARIANTS["industry_calibrated"]
N_PATHS = 2000          # larger than usual — we want tight percentiles on rare events
VOLUMES = [25, 50, 100, 200, 500, 1000]


def _row(label: str, agg: dict) -> None:
    op_roi  = agg["operator_roi"]
    op_take = agg["operator_take"]
    cap     = agg["capital_loss"]
    pr      = agg["pool_recovery"]
    rk      = agg["restock"]
    print(f"  {label:<10s}  "
          f"ROI mean {op_roi['mean']:>7.1%}   p5 {op_roi['p5']:>7.1%}   p50 (median below) "
          f"p95 {op_roi['p95']:>7.1%}  "
          f"|  op_take ${op_take['mean']:>8,.0f}  "
          f"cap-loss {cap['p_any']:>5.1%}  "
          f"pool {pr['mean']:>6.1%}")


def main() -> None:
    print(f"Low-volume risk analysis — variant: {BASELINE.name}")
    print(f"  Box ${BASELINE.box_price_usd:,.0f}, initial cashbox ${BASELINE.initial_cashbox_usd:,.0f}")
    print(f"  Pro-rata operator share: {BASELINE.operator_pro_rata_lender_share:.2%}"
          f", total Rarible profit share: {BASELINE.effective_operator_share:.2%}")
    print(f"  Paths per sim: {N_PATHS:,}")
    print()

    # Run each volume level
    results_by_vol: dict[int, dict] = {}
    for n in VOLUMES:
        cfg = replace(BASELINE, n_pulls_per_campaign=n,
                      snapshot_interval=max(n, 1))
        rs = run_monte_carlo(cfg, n_paths=N_PATHS, seed=BASELINE.seed)
        results_by_vol[n] = (rs, aggregate(rs))

    # ---- 1. Operator headline economics by volume ----
    print("=" * 110)
    print(f"  {'1. OPERATOR ECONOMICS BY VOLUME':^104s}")
    print("=" * 110)
    print(f"  {'volume':>7s}  {'op_take mean':>13s}  {'p5':>10s}  {'p50':>10s}  {'p95':>10s}"
          f"  {'ROI mean':>9s}  {'ROI p5':>8s}  {'ROI p95':>8s}")
    for n, (rs, agg) in results_by_vol.items():
        take = np.array([r.operator_take for r in rs])
        roi  = np.array([r.operator_roi  for r in rs])
        print(f"  {n:>7d}  ${take.mean():>11,.0f}  "
              f"${np.percentile(take, 5):>8,.0f}  "
              f"${np.percentile(take, 50):>8,.0f}  "
              f"${np.percentile(take, 95):>8,.0f}  "
              f"{roi.mean():>8.1%}  "
              f"{np.percentile(roi, 5):>7.1%}  "
              f"{np.percentile(roi, 95):>7.1%}")

    # ---- 2. Risk metrics ----
    print()
    print("=" * 110)
    print(f"  {'2. RISK METRICS BY VOLUME':^104s}")
    print("=" * 110)
    print(f"  {'volume':>7s}  {'P(cap-loss)':>11s}  {'P(loss>0)':>10s}  "
          f"{'mean loss|loss':>15s}  {'p95 loss':>10s}  "
          f"{'P(ROI<0)':>9s}  {'P(ROI<50%)':>11s}")
    for n, (rs, agg) in results_by_vol.items():
        caploss = np.array([r.capital_loss for r in rs])
        op_take = np.array([r.operator_take for r in rs])
        roi     = np.array([r.operator_roi  for r in rs])
        any_loss = caploss > 0
        net_op_position = np.array([r.operator_total - r.initial_cashbox for r in rs])
        print(f"  {n:>7d}  "
              f"{any_loss.mean():>10.1%}  "
              f"{(net_op_position < 0).mean():>9.1%}  "
              f"${caploss[any_loss].mean() if any_loss.any() else 0:>13,.0f}  "
              f"${np.percentile(caploss, 95):>8,.0f}  "
              f"{(roi < 0).mean():>8.1%}  "
              f"{(roi < 0.5).mean():>10.1%}")

    # ---- 3. Inventory dynamics ----
    print()
    print("=" * 110)
    print(f"  {'3. INVENTORY & RESTOCK DYNAMICS BY VOLUME':^104s}")
    print("=" * 110)
    print(f"  {'volume':>7s}  {'P(any restock)':>14s}  {'mean restocks':>14s}  "
          f"{'Pudgy holds mean':>17s}  {'P(Pudgy held)':>14s}  {'P(both Pudgies held)':>20s}")
    for n, (rs, agg) in results_by_vol.items():
        nrestocks = np.array([r.restock_events for r in rs])
        pudgy_cons = np.array([r.nfts_consumed["pudgy_penguins"] for r in rs])
        pudgy_held_net = np.array([
            r.nfts_consumed["pudgy_penguins"] - r.nfts_restocked["pudgy_penguins"]
            for r in rs
        ])
        print(f"  {n:>7d}  "
              f"{(nrestocks > 0).mean():>13.1%}  "
              f"{nrestocks.mean():>13.2f}  "
              f"{pudgy_cons.mean():>16.2f}  "
              f"{(pudgy_cons >= 1).mean():>13.1%}  "
              f"{(pudgy_held_net >= 2).mean():>19.1%}")

    # ---- 4. External lender recovery by volume ----
    print()
    print("=" * 110)
    print(f"  {'4. EXTERNAL LENDER RECOVERY BY VOLUME':^104s}")
    print("=" * 110)
    print(f"  {'volume':>7s}  {'pool recovery':>14s}  {'p5':>7s}  {'p50':>7s}  "
          f"{'p95':>7s}  {'P(< par)':>9s}  {'lender cash mean':>17s}")
    for n, (rs, agg) in results_by_vol.items():
        pr = agg["pool_recovery"]
        lc = np.array([r.lender_pool_cash for r in rs])
        print(f"  {n:>7d}  "
              f"{pr['mean']:>13.1%}  "
              f"{pr['p5']:>6.1%}  "
              f"{pr['p50']:>6.1%}  "
              f"{pr['p95']:>6.1%}  "
              f"{pr['p_below_par']:>8.1%}  "
              f"${lc.mean():>15,.0f}")

    # ---- 5. Summary recommendation ----
    print()
    print("=" * 110)
    print("  5. SUMMARY")
    print("=" * 110)
    take_mean = {n: np.mean([r.operator_take for r in rs]) for n, (rs, _) in results_by_vol.items()}
    caploss_p = {n: float(np.mean([r.capital_loss > 0 for r in rs])) for n, (rs, _) in results_by_vol.items()}
    for n in VOLUMES:
        print(f"    @ {n:>4d} pulls:  op take ${take_mean[n]:>9,.0f}   "
              f"cap-loss P {caploss_p[n]:>5.1%}   "
              f"break-even multiple {take_mean[n] / BASELINE.initial_cashbox_usd + 1:>5.2f}x")


if __name__ == "__main__":
    main()
