"""
NFT Lootbox Pricing — Monte Carlo Simulation (Proposal 2)
==========================================================
Authors: Daniel + Adam (Impossible Finance / Rarible-Sappy collab)
Version: v1.0

Purpose
-------
Price a fair-EV NFT lootbox where revenue comes ONLY from the buyback
spread (haircut), not from the box itself. Models four discrete pull
tiers with no within-tier dispersion. Tests whether a "no house edge"
positioning can be profitable purely on flip-spread economics.

Key difference vs Proposal 1 (Gacha):
- Proposal 1: Box has positive house edge, revenue from edge + spread
- Proposal 2: Box is EV-neutral (or near-neutral), revenue ONLY from
  spread on user-initiated buybacks. This is a pawn-shop / market-maker
  business, not a casino business.

Model
-----
Each box pull:
    Tier ~ Categorical(p_floor, p_mid_low, p_mid_high, p_grand)
    NFT value = deterministic per tier ($30 / $50 / $80 / $220)
    Buyback ~ Bernoulli(p_buyback | tier)

P&L per box:
    if buyback:
        margin = haircut * NFT_value
        (Box price collected, then (1-haircut) returned. NFT goes back
         to inventory. Only spread is realized cash.)
    else:
        margin = box_price - cost_basis * NFT_value
        (User keeps NFT. House ate the inventory acquisition cost.)

Critical sensitivity: with EV ≈ box price and no edge, the entire
profitability of the business depends on (a) buyback rate, (b) haircut,
(c) inventory cost basis.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict


# ============================================================================
# PARAMETERS
# ============================================================================

@dataclass
class LootboxParams:
    # --- Box pricing (USD) ---
    box_price: float = 55.0             # USDT per box (recommended; sweep shows break-even at ~$50)

    # --- Tier outcomes (USD value) ---
    val_floor: float = 30.0
    val_mid_low: float = 50.0
    val_mid_high: float = 80.0
    val_grand: float = 220.0

    # --- Tier probabilities ---
    # Default 60/25/10/5 → EV = $49.50 ≈ box price
    p_floor: float = 0.60
    p_mid_low: float = 0.25
    p_mid_high: float = 0.10
    # p_grand = 1 - others

    # --- Buyback economics ---
    haircut: float = 0.06               # 6% spread — user gets 94% of FMV
    p_buyback_floor: float = 0.70       # Floor pulls — most users dump
    p_buyback_mid_low: float = 0.50     # Mid-low — break-even, mixed
    p_buyback_mid_high: float = 0.30    # Mid-high — keep more often
    p_buyback_grand: float = 0.15       # Grand — keep the Sappy

    # --- Inventory cost ---
    cost_basis: float = 0.85            # 85% of FMV (treasury discount)

    # --- Simulation ---
    n_boxes_per_campaign: int = 1000
    n_paths: int = 500
    n_per_box_sims: int = 50000
    seed: int = 42

    @property
    def p_grand(self) -> float:
        return max(0.0, 1.0 - self.p_floor - self.p_mid_low - self.p_mid_high)

    @property
    def expected_pull_value(self) -> float:
        return (self.val_floor * self.p_floor
                + self.val_mid_low * self.p_mid_low
                + self.val_mid_high * self.p_mid_high
                + self.val_grand * self.p_grand)


PARAMS = LootboxParams()


# ============================================================================
# CORE SIMULATION
# ============================================================================

def simulate_boxes(p: LootboxParams, n: int, rng: np.random.Generator) -> Dict[str, np.ndarray]:
    """Simulate n independent box outcomes."""
    u = rng.random(n)
    cum = np.array([p.p_floor,
                    p.p_floor + p.p_mid_low,
                    p.p_floor + p.p_mid_low + p.p_mid_high])
    tier = np.where(u < cum[0], 0,
            np.where(u < cum[1], 1,
              np.where(u < cum[2], 2, 3)))

    tier_values = np.array([p.val_floor, p.val_mid_low, p.val_mid_high, p.val_grand])
    nft_values = tier_values[tier]

    p_buybacks = np.array([p.p_buyback_floor, p.p_buyback_mid_low,
                           p.p_buyback_mid_high, p.p_buyback_grand])[tier]
    buyback = rng.random(n) < p_buybacks

    # Margin
    margin_buyback = p.haircut * nft_values
    margin_hold = p.box_price - p.cost_basis * nft_values
    margin = np.where(buyback, margin_buyback, margin_hold)

    # User realized value
    user_value = np.where(buyback, (1 - p.haircut) * nft_values, nft_values)

    return {
        'tier': tier,
        'nft_value': nft_values,
        'buyback': buyback,
        'margin': margin,
        'user_value': user_value,
    }


def simulate_campaigns(p: LootboxParams, rng: np.random.Generator) -> Dict[str, np.ndarray]:
    """Simulate n_paths full campaigns of n_boxes_per_campaign each."""
    n_paths, n_boxes = p.n_paths, p.n_boxes_per_campaign
    out = simulate_boxes(p, n_paths * n_boxes, rng)
    margins = out['margin'].reshape(n_paths, n_boxes)
    cum = np.cumsum(margins, axis=1)
    return {
        'cumulative_margins': cum,
        'final_margins': cum[:, -1],
        'min_margins': cum.min(axis=1),
    }


# ============================================================================
# ANALYSIS
# ============================================================================

def summary_stats(p: LootboxParams, boxes: Dict, campaigns: Dict) -> pd.DataFrame:
    margins = boxes['margin']
    finals = campaigns['final_margins']

    stats = {
        'box_price (USDT)': p.box_price,
        'expected_pull_value (USDT)': p.expected_pull_value,
        'implied_house_edge (%)': (p.box_price - p.expected_pull_value) / p.box_price * 100,
        '— margin per box —': '',
        'mean_margin (USDT)': margins.mean(),
        'mean_margin_pct': margins.mean() / p.box_price * 100,
        'p5_margin (USDT)': np.percentile(margins, 5),
        'p50_margin (USDT)': np.percentile(margins, 50),
        'p95_margin (USDT)': np.percentile(margins, 95),
        '— user side —': '',
        'mean_user_value (USDT)': boxes['user_value'].mean(),
        'user_to_box_ratio': boxes['user_value'].mean() / p.box_price,
        'p_user_profitable_pull': (boxes['user_value'] >= p.box_price).mean(),
        '— campaign —': '',
        'p_campaign_ruin (final < 0)': (finals < 0).mean(),
        'p_intra_drawdown': (campaigns['min_margins'] < 0).mean(),
        'mean_campaign_margin (USDT)': finals.mean(),
        'p5_campaign_margin (USDT)': np.percentile(finals, 5),
        'p95_campaign_margin (USDT)': np.percentile(finals, 95),
        '— tier mix observed —': '',
        'pct_floor_pulls': (boxes['tier'] == 0).mean() * 100,
        'pct_mid_low_pulls': (boxes['tier'] == 1).mean() * 100,
        'pct_mid_high_pulls': (boxes['tier'] == 2).mean() * 100,
        'pct_grand_pulls': (boxes['tier'] == 3).mean() * 100,
        'pct_buyback_overall': boxes['buyback'].mean() * 100,
    }
    return pd.DataFrame.from_dict(stats, orient='index', columns=['value'])


# ============================================================================
# SWEEPS
# ============================================================================

def haircut_sweep(base_p: LootboxParams, haircuts: np.ndarray,
                  rng: np.random.Generator) -> pd.DataFrame:
    """How sensitive is margin to the haircut?"""
    rows = []
    for h in haircuts:
        p = LootboxParams(**{**asdict(base_p), 'haircut': float(h)})
        out = simulate_boxes(p, 20000, rng)
        rows.append({
            'haircut': h,
            'mean_margin': out['margin'].mean(),
            'margin_pct': out['margin'].mean() / p.box_price * 100,
            'p_user_profitable': (out['user_value'] >= p.box_price).mean(),
        })
    return pd.DataFrame(rows)


def box_price_sweep(base_p: LootboxParams, prices: np.ndarray,
                    rng: np.random.Generator) -> pd.DataFrame:
    """Sweep box price with all other parameters held fixed.

    NFT values are exogenous (real-world prices don't move because we changed
    box price), so EV stays at $49.50 — only the box revenue leg moves.
    Find the price where mean_margin >= 0 AND P(user value >= box price) is
    still acceptable.
    """
    rows = []
    for price in prices:
        p = LootboxParams(**{**asdict(base_p), 'box_price': float(price)})
        out = simulate_boxes(p, 30000, rng)
        rows.append({
            'box_price': price,
            'expected_pull_value': p.expected_pull_value,
            'implied_house_edge_pct': (price - p.expected_pull_value) / price * 100,
            'mean_margin': out['margin'].mean(),
            'margin_pct_of_box': out['margin'].mean() / price * 100,
            'p_user_profitable': (out['user_value'] >= price).mean(),
            'p_negative_box': (out['margin'] < 0).mean(),
        })
    return pd.DataFrame(rows)


def buyback_rate_sweep(base_p: LootboxParams, scales: np.ndarray,
                       rng: np.random.Generator) -> pd.DataFrame:
    """Scale all buyback probabilities up/down to test sensitivity to user behavior."""
    rows = []
    for s in scales:
        kwargs = asdict(base_p)
        kwargs['p_buyback_floor'] = min(1.0, base_p.p_buyback_floor * s)
        kwargs['p_buyback_mid_low'] = min(1.0, base_p.p_buyback_mid_low * s)
        kwargs['p_buyback_mid_high'] = min(1.0, base_p.p_buyback_mid_high * s)
        kwargs['p_buyback_grand'] = min(1.0, base_p.p_buyback_grand * s)
        p = LootboxParams(**kwargs)
        out = simulate_boxes(p, 20000, rng)
        rows.append({
            'buyback_scale': s,
            'effective_buyback_rate': out['buyback'].mean(),
            'mean_margin': out['margin'].mean(),
            'margin_pct': out['margin'].mean() / p.box_price * 100,
        })
    return pd.DataFrame(rows)


def sensitivity_tornado(base_p: LootboxParams, rng: np.random.Generator,
                        delta_pct: float = 0.20) -> pd.DataFrame:
    """±20% on each lever, measure ∆ mean margin."""
    base_margin = simulate_boxes(base_p, 20000, rng)['margin'].mean()

    levers = {
        'box_price': base_p.box_price,
        'haircut': base_p.haircut,
        'cost_basis': base_p.cost_basis,
        'p_buyback_floor': base_p.p_buyback_floor,
        'p_buyback_mid_low': base_p.p_buyback_mid_low,
        'p_buyback_mid_high': base_p.p_buyback_mid_high,
        'p_buyback_grand': base_p.p_buyback_grand,
        'val_grand': base_p.val_grand,
    }
    rows = []
    for name, base_val in levers.items():
        up_kwargs = {**asdict(base_p), name: min(1.0, base_val * (1 + delta_pct)) if 'p_' in name else base_val * (1 + delta_pct)}
        dn_kwargs = {**asdict(base_p), name: base_val * (1 - delta_pct)}
        up_margin = simulate_boxes(LootboxParams(**up_kwargs), 20000, rng)['margin'].mean()
        dn_margin = simulate_boxes(LootboxParams(**dn_kwargs), 20000, rng)['margin'].mean()
        rows.append({
            'lever': name,
            'down_margin': dn_margin,
            'up_margin': up_margin,
            'delta': up_margin - dn_margin,
            'abs_delta': abs(up_margin - dn_margin),
        })
    df = pd.DataFrame(rows).sort_values('abs_delta', ascending=True)
    df['base_margin'] = base_margin
    return df


# ============================================================================
# PLOTS
# ============================================================================

def plot_margin_distribution(boxes: Dict, p: LootboxParams, outpath: Path):
    margins = boxes['margin']
    fig, ax = plt.subplots(figsize=(10, 5))
    counts, bins, patches = ax.hist(margins, bins=60, edgecolor='white', linewidth=0.3)
    for patch, bin_left in zip(patches, bins[:-1]):
        patch.set_facecolor('#E24B4A' if bin_left < 0 else '#1D9E75')

    ax.axvline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)
    ax.axvline(margins.mean(), color='#185FA5', linestyle='-', linewidth=1.5,
               label=f'Mean: ${margins.mean():.2f}')
    ax.axvline(np.percentile(margins, 5), color='#888', linestyle=':', linewidth=1,
               label=f'P5: ${np.percentile(margins, 5):.2f}')
    ax.axvline(np.percentile(margins, 95), color='#888', linestyle=':', linewidth=1,
               label=f'P95: ${np.percentile(margins, 95):.2f}')
    ax.set_xlabel('House margin per box (USDT)')
    ax.set_ylabel('Frequency')
    ax.set_title(f'Margin distribution per box (N={len(margins):,} sims, box ${p.box_price})')
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def plot_cumulative_paths(campaigns: Dict, p: LootboxParams, outpath: Path):
    cum = campaigns['cumulative_margins']
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(1, p.n_boxes_per_campaign + 1)

    idx = np.random.choice(cum.shape[0], min(100, cum.shape[0]), replace=False)
    for i in idx:
        ax.plot(x, cum[i], color='#888', alpha=0.10, linewidth=0.5)

    p5 = np.percentile(cum, 5, axis=0)
    p50 = np.percentile(cum, 50, axis=0)
    p95 = np.percentile(cum, 95, axis=0)
    ax.fill_between(x, p5, p95, color='#378ADD', alpha=0.20, label='P5–P95')
    ax.plot(x, p50, color='#185FA5', linewidth=2, label='Median')
    ax.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)

    ax.set_xlabel('Boxes sold')
    ax.set_ylabel('Cumulative house margin (USDT)')
    ax.set_title(f'Campaign trajectories (N={cum.shape[0]} × {p.n_boxes_per_campaign} boxes)')
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def plot_box_price_sweep(df: pd.DataFrame, outpath: Path):
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()

    ax1.plot(df['box_price'], df['mean_margin'], color='#1D9E75', linewidth=2,
             marker='o', label='Mean margin')
    ax1.axhline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.5)
    ax1.set_xlabel('Box price (USDT)')
    ax1.set_ylabel('Mean margin per box (USDT)', color='#1D9E75')
    ax1.tick_params(axis='y', labelcolor='#1D9E75')

    ax2.plot(df['box_price'], df['p_user_profitable'] * 100, color='#D85A30',
             linewidth=2, marker='s', label='P(user profitable)')
    ax2.axhline(35, color='#D85A30', linestyle=':', linewidth=0.8, alpha=0.5,
                label='35% threshold')
    ax2.set_ylabel('P(user-profitable pull) %', color='#D85A30')
    ax2.tick_params(axis='y', labelcolor='#D85A30')

    ax1.set_title('Box price sweep — break-even and user UX')
    ax1.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def plot_haircut_sweep(df: pd.DataFrame, outpath: Path):
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(df['haircut'] * 100, df['mean_margin'], color='#1D9E75', linewidth=2, marker='o')
    ax1.axhline(0, color='black', linestyle='--', linewidth=0.6, alpha=0.4)
    ax1.set_xlabel('Buyback haircut (%)')
    ax1.set_ylabel('Mean margin per box (USDT)', color='#1D9E75')
    ax1.tick_params(axis='y', labelcolor='#1D9E75')
    ax1.set_title('Margin vs buyback haircut')
    ax1.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def plot_buyback_sweep(df: pd.DataFrame, outpath: Path):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df['effective_buyback_rate'] * 100, df['mean_margin'],
            color='#185FA5', linewidth=2, marker='o')
    ax.axhline(0, color='black', linestyle='--', linewidth=0.6, alpha=0.4)
    ax.set_xlabel('Effective buyback rate (%)')
    ax.set_ylabel('Mean margin per box (USDT)')
    ax.set_title('Margin vs user buyback rate')
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def plot_tornado(df: pd.DataFrame, outpath: Path):
    fig, ax = plt.subplots(figsize=(10, 5))
    base = df['base_margin'].iloc[0]
    y = np.arange(len(df))
    ax.barh(y, df['up_margin'] - base, left=base, color='#1D9E75', alpha=0.7, label='+20% input')
    ax.barh(y, df['down_margin'] - base, left=base, color='#E24B4A', alpha=0.7, label='-20% input')
    ax.axvline(base, color='black', linestyle='--', linewidth=0.8, alpha=0.6,
               label=f'Base: ${base:.2f}')
    ax.set_yticks(y)
    ax.set_yticklabels(df['lever'])
    ax.set_xlabel('Mean margin per box (USDT)')
    ax.set_title('Sensitivity tornado')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.2, axis='x')
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


# ============================================================================
# MAIN
# ============================================================================

def main():
    out_dir = Path('./outputs')
    out_dir.mkdir(exist_ok=True)
    rng = np.random.default_rng(PARAMS.seed)

    print("=" * 72)
    print("NFT Lootbox Monte Carlo — Proposal 2 (Fair-EV) v1.0")
    print("=" * 72)
    print(f"Box price:       ${PARAMS.box_price}")
    print(f"Tier values:     ${PARAMS.val_floor} / ${PARAMS.val_mid_low} / ${PARAMS.val_mid_high} / ${PARAMS.val_grand}")
    print(f"Tier odds:       {PARAMS.p_floor:.0%} / {PARAMS.p_mid_low:.0%} / {PARAMS.p_mid_high:.0%} / {PARAMS.p_grand:.0%}")
    print(f"Expected pull:   ${PARAMS.expected_pull_value:.2f}")
    print(f"Implied edge:    {(PARAMS.box_price - PARAMS.expected_pull_value)/PARAMS.box_price*100:.1f}%")
    print(f"Haircut:         {PARAMS.haircut:.0%}")
    print(f"Cost basis:      {PARAMS.cost_basis:.0%} of FMV")
    print()

    print("[1/4] Per-box sims...")
    boxes = simulate_boxes(PARAMS, PARAMS.n_per_box_sims, rng)

    print("[2/4] Campaign sims...")
    campaigns = simulate_campaigns(PARAMS, rng)

    stats = summary_stats(PARAMS, boxes, campaigns)
    stats.to_csv(out_dir / 'summary_stats.csv')
    print("\nSummary:")
    print(stats.to_string())
    print()

    print("[3/4] Plots...")
    plot_margin_distribution(boxes, PARAMS, out_dir / 'margin_distribution.png')
    plot_cumulative_paths(campaigns, PARAMS, out_dir / 'cumulative_paths.png')

    print("[4/5] Sweeps + sensitivity...")
    haircuts = np.linspace(0.01, 0.20, 20)
    h_df = haircut_sweep(PARAMS, haircuts, rng)
    h_df.to_csv(out_dir / 'haircut_sweep.csv', index=False)
    plot_haircut_sweep(h_df, out_dir / 'haircut_sweep.png')

    print("[5/5] Box price sweep (finding break-even)...")
    prices = np.linspace(45, 70, 26)
    bp_df = box_price_sweep(PARAMS, prices, rng)
    bp_df.to_csv(out_dir / 'box_price_sweep.csv', index=False)
    plot_box_price_sweep(bp_df, out_dir / 'box_price_sweep.png')

    # Find break-even
    profitable = bp_df[bp_df['mean_margin'] > 0]
    if len(profitable) > 0:
        be_price = profitable['box_price'].min()
        be_row = bp_df[bp_df['box_price'] == be_price].iloc[0]
        print(f"\n>>> Break-even box price: ${be_price:.2f}")
        print(f"    Implied house edge: {be_row['implied_house_edge_pct']:.1f}%")
        print(f"    P(user profitable): {be_row['p_user_profitable']:.1%}")

    scales = np.linspace(0.3, 2.0, 18)
    b_df = buyback_rate_sweep(PARAMS, scales, rng)
    b_df.to_csv(out_dir / 'buyback_sweep.csv', index=False)
    plot_buyback_sweep(b_df, out_dir / 'buyback_sweep.png')

    t_df = sensitivity_tornado(PARAMS, rng)
    t_df.to_csv(out_dir / 'sensitivity_tornado.csv', index=False)
    plot_tornado(t_df, out_dir / 'sensitivity_tornado.png')

    print(f"\nDone. Outputs → {out_dir.resolve()}")


if __name__ == '__main__':
    main()
