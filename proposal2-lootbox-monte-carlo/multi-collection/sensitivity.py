"""
Sensitivity sweeps for the Proposal 3 multi-collection gacha.

For each lever, holds everything else at the baseline (premium variant) and
sweeps a small set of values. Reports the key outcome metrics so we can see
which inputs the model is most sensitive to.

Baseline: premium variant.
Paths per sweep point: 500 (tight enough for sensible percentiles, fast).
Pulls per campaign: 1000.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import numpy as np

from gacha_config import VARIANTS
from simulator import run_monte_carlo, aggregate


BASELINE = VARIANTS["industry_calibrated"]
N_PATHS = 500


def _sweep(label: str, fields_values: list[dict], header: str) -> None:
    print()
    print("=" * 100)
    print(f"  SENSITIVITY: {label}")
    print("=" * 100)
    print(f"  {header}")
    print("  " + "-" * 96)
    for kv in fields_values:
        cfg = replace(BASELINE, **kv)
        results = run_monte_carlo(cfg, n_paths=N_PATHS, seed=BASELINE.seed)
        agg = aggregate(results)
        op_roi   = agg["operator_roi"]["mean"]
        pool_rec = agg["pool_recovery"]["mean"]
        rest_evs = agg["restock"]["events_mean"]
        rest_usd = agg["restock"]["cost_mean"]
        cons_usd = agg["consolation"]["cost_total_mean"]
        cap_loss_p = agg["capital_loss"]["p_any"]
        op_share = cfg.effective_operator_share
        params = ", ".join(f"{k}={v}" for k, v in kv.items())
        print(f"  {params:<42s}  op_share {op_share:>5.1%}  "
              f"ROI {op_roi:>6.1%}  pool {pool_rec:>5.1%}  "
              f"restocks {rest_evs:>4.1f}  ${rest_usd:>7,.0f}  "
              f"cons ${cons_usd:>6,.0f}  cap_loss {cap_loss_p:>4.1%}")


def main() -> None:
    # ---- Heading ----
    print(f"Baseline: {BASELINE.name}  box ${BASELINE.box_price_usd:,.0f}  "
          f"initial_cashbox ${BASELINE.initial_cashbox_usd:,.0f}  "
          f"pulls {BASELINE.n_pulls_per_campaign}  paths {N_PATHS}")
    print(f"Pro-rata operator share at baseline: {BASELINE.effective_operator_share:.2%}")

    hdr = (f"{'param':<42s}  {'opshr':>6s}  {'ROI':>6s}  {'poolR':>6s}  "
           f"{'rsk#':>5s}  {'rsk$':>8s}  {'cons$':>7s}  {'caploss':>7s}")

    # ---- 1) buyback acceptance scale ----
    _sweep("buyback_acceptance_scale",
           [{"buyback_acceptance_scale": s} for s in (0.5, 0.75, 1.0, 1.25, 1.5)],
           hdr)

    # ---- 2) p_consolation (with low-tier rebalancing to keep sum=1) ----
    # Start from baseline 10% consolation; sweep, shifting δ to/from p_tier_low.
    base = BASELINE
    cons_sweep = []
    for p_cons in (0.0, 0.05, 0.10, 0.20, 0.30):
        delta = p_cons - base.p_consolation
        cons_sweep.append({
            "p_consolation": p_cons,
            "p_tier_low":    base.p_tier_low - delta,
        })
    _sweep("p_consolation  (low-tier rebalances)", cons_sweep, hdr)

    # ---- 3) shard_redemption_rate ----
    _sweep("shard_redemption_rate",
           [{"shard_redemption_rate": r} for r in (0.25, 0.50, 0.75, 1.0)],
           hdr)

    # ---- 4) initial_cashbox_usd (also changes effective_operator_share!) ----
    _sweep("initial_cashbox_usd  (also moves pro-rata split)",
           [{"initial_cashbox_usd": b} for b in (10000, 25000, 50000, 75000, 100000)],
           hdr)

    # ---- 5) p_tier_headline (with low-tier rebalancing) ----
    head_sweep = []
    base_low = base.p_tier_low
    base_head = base.p_tier_headline
    for p_head in (0.005, 0.010, 0.015, 0.020, 0.030):
        delta = p_head - base_head
        head_sweep.append({
            "p_tier_headline": p_head,
            "p_tier_low":      base_low - delta,
        })
    _sweep("p_tier_headline  (low-tier rebalances)", head_sweep, hdr)

    # ---- 6) auto_buyback_discount ----
    _sweep("auto_buyback_discount",
           [{"auto_buyback_discount": d} for d in (0.02, 0.04, 0.06, 0.09, 0.12)],
           hdr)

    # ---- 7) restock_threshold ----
    _sweep("restock_threshold",
           [{"restock_threshold": r} for r in (0.25, 0.40, 0.50, 0.65, 0.80)],
           hdr)


if __name__ == "__main__":
    main()
