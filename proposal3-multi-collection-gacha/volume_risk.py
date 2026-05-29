"""
VOLUME RISK — what happens at small pull counts?
================================================

The default campaign assumes ~1,000 pulls per week. Variance dominates at low
N: the operator can run a 50-pull or 100-pull window and end up with no
profit if a few unbuy-backed high-tier draws land early. This script
quantifies that risk.

Risk framing (not just losses):
    1. Operator zero-profit probability  — P(cashbox <= debt at horizon)
    2. Lender shortfall probability      — P(debt > cashbox at horizon)
    3. Distribution of operator take     — mean / p5 / p25 / p50 / p95 / stdev
    4. Realized vs. expected per-pull    — variance penalty quantified
    5. Worst-case lender recovery        — p5 of lender_recovery_ratio (all slugs)

Run:
    python3 volume_risk.py

No CLI flags. Two horizons (50, 100) × three variants (balanced, premium,
floor_spam) × 20,000 paths each.
"""

from __future__ import annotations

import dataclasses
import math
from collections import Counter

import numpy as np

from gacha_config import (
    VARIANTS,
    expected_operator_cash_per_pull,
    expected_net_revenue_per_pull,
)
from simulator import run_monte_carlo


HORIZONS = (50, 100)
N_PATHS = 20_000


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def pct(arr: np.ndarray, p: float) -> float:
    return float(np.percentile(arr, p))


def fmt_usd(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


# -----------------------------------------------------------------------------
# Per-(variant, horizon) risk profile
# -----------------------------------------------------------------------------

def profile(variant_name: str, n_pulls: int) -> dict:
    base = VARIANTS[variant_name]
    # Clone the frozen config with the desired horizon. Restock threshold is
    # left at default — at 50/100 pulls inventory is nowhere near depleted so
    # it never fires anyway, which is what we want (we're isolating volume
    # variance, not restock dynamics).
    cfg = dataclasses.replace(base, n_pulls_per_campaign=n_pulls, seed=42)

    results = run_monte_carlo(cfg, n_paths=N_PATHS, seed=42)

    cashbox        = np.array([r.cashbox        for r in results])
    debt           = np.array([r.debt           for r in results])
    profit         = np.array([r.profit         for r in results])
    op_take        = np.array([r.operator_take  for r in results])
    shortfall      = np.array([r.debt_shortfall for r in results])

    # Operator P&L is the per-pull comparable to the steady-state expectation.
    op_per_pull = op_take / n_pulls
    expected_per_pull = expected_operator_cash_per_pull(base)

    # Lender recovery — worst slug recovery ratio in each path.
    # (A pool-wide blended recovery hides single-lender impairment.)
    worst_recovery = np.array([
        min(r.lender_recovery_ratio.values()) if r.lender_recovery_ratio else 1.0
        for r in results
    ])

    # Probability of operator getting nothing (cashbox <= debt → profit = 0).
    p_zero_profit = float((profit <= 0).mean())
    # Probability lenders aren't made whole from cash (debt > cashbox).
    # Equivalent to debt_shortfall > 0.
    p_lender_short = float((shortfall > 0).mean())

    # Closed-form sanity check: probability of at least one non-buybacked
    # high-tier draw in N pulls. p_consume_high = p_high × (1 − p_accept_high)
    p_consume_high = base.p_tier_high * (1 - base.p_accept_buyback_high)
    p_at_least_one_consumed_high = 1 - (1 - p_consume_high) ** n_pulls

    return {
        "variant": variant_name,
        "n_pulls": n_pulls,
        "box_price": base.box_price_usd,
        "expected_op_per_pull": expected_per_pull,
        "expected_total_revenue": expected_per_pull * n_pulls,
        # Cashbox (pre-settlement)
        "cash_mean": float(cashbox.mean()),
        "cash_p5": pct(cashbox, 5),
        "cash_p50": pct(cashbox, 50),
        # Operator take
        "op_mean": float(op_take.mean()),
        "op_stdev": float(op_take.std()),
        "op_cv": float(op_take.std() / op_take.mean()) if op_take.mean() > 0 else float("inf"),
        "op_p5": pct(op_take, 5),
        "op_p25": pct(op_take, 25),
        "op_p50": pct(op_take, 50),
        "op_p95": pct(op_take, 95),
        "op_per_pull_mean": float(op_per_pull.mean()),
        "op_per_pull_p5": pct(op_per_pull, 5),
        # Risk events
        "p_zero_profit": p_zero_profit,
        "p_lender_short": p_lender_short,
        "shortfall_mean_when_positive": float(shortfall[shortfall > 0].mean()) if (shortfall > 0).any() else 0.0,
        "shortfall_p95_when_positive": pct(shortfall[shortfall > 0], 95) if (shortfall > 0).any() else 0.0,
        "shortfall_max": float(shortfall.max()),
        # Lender recovery (worst slug per path)
        "worst_recovery_p5": pct(worst_recovery, 5),
        "worst_recovery_p50": pct(worst_recovery, 50),
        # Closed-form sanity check
        "p_one_plus_consumed_high_closed_form": p_at_least_one_consumed_high,
    }


# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------

def main() -> None:
    rows: list[dict] = []
    for v in ("balanced", "premium", "floor_spam"):
        for h in HORIZONS:
            rows.append(profile(v, h))

    bar = "═" * 78
    print()
    print(bar)
    print(f"  VOLUME RISK — proposal 3 gacha at {' / '.join(map(str, HORIZONS))} pulls")
    print(f"  {N_PATHS:,} Monte Carlo paths per (variant, horizon)")
    print(bar)

    # ---- Headline: variance vs. expectation ----
    for r in rows:
        print()
        print(f"  ── {r['variant'].upper()} · {r['n_pulls']} pulls "
              f"(box ${r['box_price']:.0f}) ─────────────────────")
        print(f"     Expected operator take @ steady state:  "
              f"{fmt_usd(r['expected_op_per_pull'])}/pull × {r['n_pulls']}  "
              f"= {fmt_usd(r['expected_total_revenue'])}")
        print(f"     Realized operator take (Monte Carlo):")
        print(f"       mean      {fmt_usd(r['op_mean']):>10s}   "
              f"stdev   {fmt_usd(r['op_stdev']):>10s}   "
              f"cv  {r['op_cv']:>5.2f}")
        print(f"       p5        {fmt_usd(r['op_p5']):>10s}   "
              f"p25     {fmt_usd(r['op_p25']):>10s}   "
              f"p50  {fmt_usd(r['op_p50']):>10s}   "
              f"p95  {fmt_usd(r['op_p95']):>10s}")
        print(f"       per-pull  {fmt_usd(r['op_per_pull_mean']):>10s} mean   "
              f"{fmt_usd(r['op_per_pull_p5']):>10s} p5")
        print()
        print(f"     Volume-risk events:")
        print(f"       P(operator take = 0)              {fmt_pct(r['p_zero_profit']):>8s}")
        print(f"       P(lender shortfall > 0)           {fmt_pct(r['p_lender_short']):>8s}")
        if r['p_lender_short'] > 0:
            print(f"       Shortfall when it happens         "
                  f"mean {fmt_usd(r['shortfall_mean_when_positive'])},  "
                  f"p95 {fmt_usd(r['shortfall_p95_when_positive'])},  "
                  f"max {fmt_usd(r['shortfall_max'])}")
        else:
            print(f"       Shortfall when it happens         —")
        print(f"       Worst lender recovery ratio       "
              f"p5 {fmt_pct(r['worst_recovery_p5'])},  "
              f"p50 {fmt_pct(r['worst_recovery_p50'])}")
        print(f"       P(≥1 unbuy-backed HIGH-tier pull) "
              f"{fmt_pct(r['p_one_plus_consumed_high_closed_form']):>8s} (closed-form)")

    # ---- Summary contrast: 50 vs 100 ----
    print()
    print(bar)
    print(f"  CONTRAST — going from 50 pulls to 100 pulls")
    print(bar)
    print(f"  {'variant':<12} {'metric':<32} {'50 pulls':>14} {'100 pulls':>14} {'Δ':>10}")
    print(f"  {'-'*12} {'-'*32} {'-'*14} {'-'*14} {'-'*10}")
    for v in ("balanced", "premium", "floor_spam"):
        r50  = next(x for x in rows if x['variant'] == v and x['n_pulls'] == 50)
        r100 = next(x for x in rows if x['variant'] == v and x['n_pulls'] == 100)
        def line(label: str, k: str, fmt):
            a, b = r50[k], r100[k]
            d = b - a
            print(f"  {v:<12} {label:<32} {fmt(a):>14} {fmt(b):>14} {fmt(d):>10}")
        line("operator take mean",       "op_mean",                       fmt_usd)
        line("operator take p5",          "op_p5",                         fmt_usd)
        line("operator take stdev",       "op_stdev",                      fmt_usd)
        line("operator CV",               "op_cv",                          lambda x: f"{x:.2f}")
        line("P(operator take = 0)",      "p_zero_profit",                  fmt_pct)
        line("P(lender shortfall > 0)",   "p_lender_short",                 fmt_pct)
        line("worst recovery p5",         "worst_recovery_p5",              fmt_pct)
        print()


if __name__ == "__main__":
    main()
