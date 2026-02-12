#!/usr/bin/env python3
"""
Phase 4 Figure Generation
==========================
MNL 재순위 분석 결과를 논문용 Figure로 생성한다.

산출물:
  - fig11_mnl_reranking_by_usertype.png
  - fig12_mnl_improvement_by_nalts.png
  - fig13_otp_mnl_disagreement.png
  - fig14_mnl_probability_distribution.png
  - fig15_route_characteristics_comparison.png

스타일: step8_model_comparison.py와 동일 (Times New Roman, 300dpi)
데이터: results/mnl_reranking_analysis.json
"""

import json
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ================================================================
# Paths
# ================================================================
ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

# ================================================================
# Publication Style
# ================================================================
COLORS = {
    'otp':   '#0072B2',   # dark blue
    'mnl':   '#D55E00',   # orange-red
    'best':  '#009E73',   # teal green
    'gray':  '#999999',
    'win':   '#D55E00',
    'lose':  '#0072B2',
    'tie':   '#CCCCCC',
    'walk':  '#E69F00',   # amber
    'trans': '#CC79A7',   # mauve
    'sub':   '#56B4E9',   # light blue
    'ride':  '#0072B2',   # dark blue
}


def set_pub_style():
    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 14,
        'axes.linewidth': 1.2,
        'xtick.major.width': 1.2,
        'ytick.major.width': 1.2,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.facecolor': 'white',
    })


def add_value_labels(ax, bars, values, fmt='{:.1f}%', offset=0.3,
                     fontsize=11, bold=True):
    for bar, v in zip(bars, values):
        y = bar.get_height()
        va = 'bottom' if y >= 0 else 'top'
        dy = offset if y >= 0 else -offset
        ax.text(bar.get_x() + bar.get_width() / 2., y + dy,
                fmt.format(v), ha='center', va=va,
                fontsize=fontsize,
                fontweight='bold' if bold else 'normal')


# ================================================================
# Load Data
# ================================================================
def load_data():
    with open(RESULTS_DIR / "mnl_reranking_analysis.json") as f:
        return json.load(f)


# ================================================================
# Figure 11: MNL Re-ranking by User Type
# ================================================================
def fig11_by_usertype(data):
    set_pub_style()

    types = ['GENERAL', 'ELDERLY', 'YOUTH', 'CHILDREN', 'DISABLED']
    labels = ['General\n(n=1.04M)', 'Elderly\n(n=177K)', 'Youth\n(n=50K)',
              'Children\n(n=11K)', 'Disabled\n(n=38K)']

    otp_vals = [data['by_user_type'][t]['otp_exact'] * 100 for t in types]
    mnl_vals = [data['by_user_type'][t]['mnl_exact'] * 100 for t in types]
    best_vals = [data['by_user_type'][t]['best_exact'] * 100 for t in types]

    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
    x = np.arange(len(types))
    width = 0.25

    b1 = ax.bar(x - width, otp_vals, width, label='OTP 1st Choice',
                color=COLORS['otp'], edgecolor='black', linewidth=1.0, alpha=0.85)
    b2 = ax.bar(x, mnl_vals, width, label='MNL 1st Choice',
                color=COLORS['mnl'], edgecolor='black', linewidth=1.0, alpha=0.85)
    b3 = ax.bar(x + width, best_vals, width, label='Best Match (Upper Bound)',
                color=COLORS['best'], edgecolor='black', linewidth=1.0, alpha=0.85)

    # Highlight MNL bars
    for bar in b2:
        bar.set_hatch('///')
        bar.set_alpha(1.0)

    add_value_labels(ax, b1, otp_vals, fontsize=10, offset=0.4)
    add_value_labels(ax, b2, mnl_vals, fontsize=10, offset=0.4)
    add_value_labels(ax, b3, best_vals, fontsize=10, offset=0.4)

    # Delta annotations between OTP and MNL
    for i in range(len(types)):
        delta = mnl_vals[i] - otp_vals[i]
        mid_y = (otp_vals[i] + mnl_vals[i]) / 2
        ax.annotate(f'+{delta:.1f}%p',
                    xy=(x[i], mid_y), fontsize=9,
                    ha='center', va='center', color='#C00000',
                    fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.2', fc='white',
                              ec='#C00000', alpha=0.9, lw=0.8))

    ax.set_ylabel('Exact Match Rate (%)', fontsize=16, fontweight='bold')
    ax.set_title('MNL Re-ranking Improvement by User Type\n'
                 '(1,320,030 Trip Chains, Phase 2 Baseline)',
                 fontsize=16, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylim(0, max(best_vals) + 6)
    ax.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc='upper left', fontsize=12, framealpha=0.9)

    plt.tight_layout()
    path = FIGURES_DIR / "fig11_mnl_reranking_by_usertype.png"
    plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Saved: {path.name}")
    return path


# ================================================================
# Figure 12: MNL Improvement by Number of Alternatives
# ================================================================
def fig12_by_nalts(data):
    set_pub_style()

    alts_data = data['by_n_alts']
    cats = ['1', '2', '3-4', '5+']
    ns = [alts_data[c]['n'] for c in cats]
    otp = [alts_data[c]['otp_exact'] * 100 for c in cats]
    mnl = [alts_data[c]['mnl_exact'] * 100 for c in cats]
    delta = [alts_data[c]['delta_exact'] * 100 for c in cats]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), dpi=300,
                                    gridspec_kw={'width_ratios': [3, 2]})

    # --- Left: Grouped bars ---
    x = np.arange(len(cats))
    width = 0.35
    b1 = ax1.bar(x - width/2, otp, width, label='OTP 1st Choice',
                 color=COLORS['otp'], edgecolor='black', linewidth=1.0, alpha=0.85)
    b2 = ax1.bar(x + width/2, mnl, width, label='MNL 1st Choice',
                 color=COLORS['mnl'], edgecolor='black', linewidth=1.0, alpha=0.85,
                 hatch='///')

    add_value_labels(ax1, b1, otp, fontsize=10, offset=0.4)
    add_value_labels(ax1, b2, mnl, fontsize=10, offset=0.4)

    labels_left = [f'{c} alt\n(n={ns[i]:,})' for i, c in enumerate(cats)]
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels_left, fontsize=11)
    ax1.set_ylabel('Exact Match Rate (%)', fontsize=14, fontweight='bold')
    ax1.set_title('(a) Exact Match by Number of Alternatives',
                  fontsize=14, fontweight='bold')
    ax1.set_ylim(0, max(otp) + 6)
    ax1.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax1.set_axisbelow(True)
    ax1.legend(fontsize=11)

    # --- Right: Delta bars (monotonic increase) ---
    colors_delta = ['#CCCCCC' if d == 0 else COLORS['mnl'] for d in delta]
    b3 = ax2.bar(x, delta, 0.6, color=colors_delta,
                 edgecolor='black', linewidth=1.0, alpha=0.85)

    for bar in b3:
        if bar.get_height() > 0:
            bar.set_hatch('///')

    for i, (bar, d) in enumerate(zip(b3, delta)):
        y = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., y + 0.08,
                 f'+{d:.2f}%p' if d > 0 else '0.00%p',
                 ha='center', va='bottom', fontsize=12, fontweight='bold',
                 color='#C00000' if d > 0 else '#666666')

    # Trend arrow
    ax2.annotate('', xy=(3.3, delta[-1] - 0.1), xytext=(0.3, 0.1),
                 arrowprops=dict(arrowstyle='->', color='#C00000',
                                 lw=2.5, connectionstyle='arc3,rad=0.15'))
    ax2.text(1.8, delta[-1] * 0.85, 'More alternatives\n→ more MNL benefit',
             fontsize=11, ha='center', style='italic', color='#C00000')

    labels_right = [f'{c} alt' for c in cats]
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels_right, fontsize=11)
    ax2.set_ylabel('MNL Improvement (Δ%p)', fontsize=14, fontweight='bold')
    ax2.set_title('(b) MNL − OTP Improvement (Monotonic)',
                  fontsize=14, fontweight='bold')
    ax2.set_ylim(-0.3, max(delta) + 1.0)
    ax2.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax2.set_axisbelow(True)

    fig.suptitle('MNL Re-ranking Effect by Choice Set Size',
                 fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    path = FIGURES_DIR / "fig12_mnl_improvement_by_nalts.png"
    plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Saved: {path.name}")
    return path


# ================================================================
# Figure 13: OTP vs MNL Disagreement Analysis
# ================================================================
def fig13_disagreement(data):
    set_pub_style()

    agree = data['agreement']
    disagree = data['disagreement']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), dpi=300,
                                    gridspec_kw={'width_ratios': [1, 1.3]})

    # --- Left: Agreement pie ---
    same_pct = agree['same_pct']
    diff_pct = 100 - same_pct

    wedges, texts, autotexts = ax1.pie(
        [same_pct, diff_pct],
        labels=['Same Choice\n(OTP = MNL)', 'Different Choice\n(OTP ≠ MNL)'],
        autopct='%1.1f%%',
        colors=[COLORS['gray'], '#F0E442'],
        startangle=90,
        explode=(0, 0.05),
        textprops={'fontsize': 13},
        wedgeprops={'edgecolor': 'black', 'linewidth': 1.2},
    )
    for at in autotexts:
        at.set_fontweight('bold')
        at.set_fontsize(14)

    ax1.set_title('(a) OTP vs MNL Agreement\n(1,320,030 Chains)',
                  fontsize=14, fontweight='bold', pad=10)

    # Add chain counts
    ax1.text(0, -1.35,
             f'Same: {agree["same_choice"]:,}  |  Different: {agree["diff_choice"]:,}',
             ha='center', fontsize=11, color='#555555')

    # --- Right: Win/Loss comparison when they disagree ---
    exact = disagree['exact_match']
    sim = disagree['sim_total']

    categories = ['Exact Match\n(Binary)', 'Sim Total\n(Continuous)']
    mnl_wins = [exact['mnl_wins'], sim['mnl_wins']]
    otp_wins = [exact['otp_wins'], sim['otp_wins']]
    ties = [exact['tie'], sim.get('tie', 0)]
    totals = [sum(x) for x in zip(mnl_wins, otp_wins, ties)]

    mnl_pcts = [m / t * 100 for m, t in zip(mnl_wins, totals)]
    otp_pcts = [o / t * 100 for o, t in zip(otp_wins, totals)]
    tie_pcts = [ti / t * 100 for ti, t in zip(ties, totals)]

    x = np.arange(len(categories))
    width = 0.55

    b_mnl = ax2.barh(x, mnl_pcts, width, label='MNL Wins',
                     color=COLORS['mnl'], edgecolor='black', linewidth=1.0)
    b_tie = ax2.barh(x, tie_pcts, width, left=mnl_pcts, label='Tie (both wrong)',
                     color=COLORS['tie'], edgecolor='black', linewidth=1.0)
    lefts = [m + t for m, t in zip(mnl_pcts, tie_pcts)]
    b_otp = ax2.barh(x, otp_pcts, width, left=lefts, label='OTP Wins',
                     color=COLORS['otp'], edgecolor='black', linewidth=1.0)

    # Labels inside bars
    for i in range(len(categories)):
        # MNL
        if mnl_pcts[i] > 5:
            ax2.text(mnl_pcts[i] / 2, x[i],
                     f'{mnl_wins[i]:,}\n({mnl_pcts[i]:.1f}%)',
                     ha='center', va='center', fontsize=10,
                     fontweight='bold', color='white')
        # Tie
        if tie_pcts[i] > 10:
            ax2.text(mnl_pcts[i] + tie_pcts[i] / 2, x[i],
                     f'{ties[i]:,}',
                     ha='center', va='center', fontsize=9, color='#555555')
        # OTP
        if otp_pcts[i] > 3:
            ax2.text(lefts[i] + otp_pcts[i] / 2, x[i],
                     f'{otp_wins[i]:,}\n({otp_pcts[i]:.1f}%)',
                     ha='center', va='center', fontsize=10,
                     fontweight='bold', color='white')

    # Win ratio annotations (centered above each bar)
    ratios_text = [
        f'MNL:OTP = {mnl_wins[0]:,}:{otp_wins[0]:,} = {mnl_wins[0]/max(otp_wins[0],1):.1f}:1',
        f'MNL:OTP = {mnl_wins[1]:,}:{otp_wins[1]:,} = {mnl_wins[1]/max(otp_wins[1],1):.1f}:1'
    ]
    for i, r in enumerate(ratios_text):
        ax2.text(50, x[i] + 0.35, r, ha='center', va='bottom', fontsize=10,
                 fontweight='bold', color='#C00000')

    ax2.set_yticks(x)
    ax2.set_yticklabels(categories, fontsize=13)
    ax2.set_xlabel('Share (%)', fontsize=14, fontweight='bold')
    ax2.set_xlim(0, 100)
    ax2.set_title(f'(b) When OTP ≠ MNL: Who Wins?\n({disagree["n_disagree"]:,} Disagreement Cases)',
                  fontsize=14, fontweight='bold', pad=10)
    ax2.legend(loc='lower right', fontsize=11, framealpha=0.9)
    ax2.xaxis.grid(True, linestyle='--', alpha=0.3)
    ax2.set_axisbelow(True)

    fig.suptitle('OTP vs MNL Ranking Disagreement Analysis',
                 fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    path = FIGURES_DIR / "fig13_otp_mnl_disagreement.png"
    plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Saved: {path.name}")
    return path


# ================================================================
# Figure 14: MNL Probability Distribution
# ================================================================
def fig14_probability_dist(data):
    set_pub_style()

    prob = data['mnl_probability']
    dist = prob['distribution']
    bins = ['0.0-0.3', '0.3-0.5', '0.5-0.7', '0.7-0.9', '0.9-1.0']
    ns = [dist[b]['n'] for b in bins]
    pcts = [dist[b]['pct'] for b in bins]

    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)

    # Color gradient: light → dark orange-red
    gradient = ['#FED976', '#FEB24C', '#FD8D3C', '#FC4E2A', '#BD0026']

    x = np.arange(len(bins))
    bars = ax.bar(x, pcts, width=0.7, color=gradient,
                  edgecolor='black', linewidth=1.2)

    # Highlight the dominant bin
    bars[-1].set_hatch('///')
    bars[-1].set_edgecolor('#8B0000')
    bars[-1].set_linewidth(2.5)

    for bar, pct, n in zip(bars, pcts, ns):
        y = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., y + 0.8,
                f'{pct:.1f}%\n({n:,})',
                ha='center', va='bottom', fontsize=11, fontweight='bold')

    # Mean/Median lines
    ax.axhline(y=0, color='black', linewidth=0.8)

    # Annotation box with stats (top-left)
    stats_text = (f'Mean = {prob["mean"]:.3f}\n'
                  f'Median = {prob["median"]:.3f}\n'
                  f'Std = {prob["std"]:.3f}')
    ax.text(0.02, 0.97, stats_text, transform=ax.transAxes,
            fontsize=12, va='top', ha='left',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='lightyellow',
                      edgecolor='gray', alpha=0.9, linewidth=0.8))

    # Interpretation annotation — above the dominant bar, outside plot area
    dominant_pct = pcts[-1]
    ax.annotate(
        f'{dominant_pct:.1f}% of chains:\nMNL assigns P > 0.9\n'
        r'$\rightarrow$ near-deterministic',
        xy=(x[-1], dominant_pct), xytext=(x[-1] - 1.2, dominant_pct + 14),
        fontsize=11, ha='center', va='bottom',
        style='italic', color='#8B0000',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor='#8B0000', alpha=0.95, linewidth=1.0),
        arrowprops=dict(arrowstyle='->', color='#8B0000', lw=1.5))

    bin_labels = ['0.0 – 0.3\n(Uncertain)', '0.3 – 0.5', '0.5 – 0.7',
                  '0.7 – 0.9', '0.9 – 1.0\n(Dominant)']
    ax.set_xticks(x)
    ax.set_xticklabels(bin_labels, fontsize=11)
    ax.set_xlabel('MNL 1st Choice Probability', fontsize=14, fontweight='bold')
    ax.set_ylabel('Share of Trip Chains (%)', fontsize=14, fontweight='bold')
    ax.set_title('Distribution of MNL Choice Probability\n'
                 '(1,320,030 Trip Chains)',
                 fontsize=16, fontweight='bold', pad=15)
    ax.set_ylim(0, max(pcts) + 22)
    ax.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    path = FIGURES_DIR / "fig14_mnl_probability_distribution.png"
    plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Saved: {path.name}")
    return path


# ================================================================
# Figure 15: Route Characteristics Comparison
# ================================================================
def fig15_route_characteristics(data):
    set_pub_style()

    rc = data['route_characteristics']
    otp_rc = rc['otp_choice']
    mnl_rc = rc['mnl_choice']

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=300)
    axes = axes.flatten()

    metrics = [
        ('avg_walk_min', 'Walk Time (min)', COLORS['walk']),
        ('avg_transfers', 'Transfers (count)', COLORS['trans']),
        ('subway_pct', 'Subway Share (%)', COLORS['sub']),
        ('avg_ride_min', 'Ride Time (min)', COLORS['ride']),
    ]

    for ax, (key, label, color) in zip(axes, metrics):
        otp_v = otp_rc[key]
        mnl_v = mnl_rc[key]
        diff = mnl_v - otp_v

        x_pos = np.array([0, 1])
        vals = [otp_v, mnl_v]
        bar_colors = [COLORS['otp'], COLORS['mnl']]

        bars = ax.bar(x_pos, vals, width=0.55, color=bar_colors,
                      edgecolor='black', linewidth=1.2, alpha=0.85)
        bars[1].set_hatch('///')

        # Value labels on top
        for bar, v in zip(bars, vals):
            if key == 'subway_pct':
                fmt_str = f'{v:.1f}%'
            elif key == 'avg_transfers':
                fmt_str = f'{v:.2f}'
            else:
                fmt_str = f'{v:.1f}'
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                    fmt_str, ha='center', va='bottom',
                    fontsize=14, fontweight='bold',
                    verticalalignment='bottom')

        # Delta annotation with arrow between bars
        sign = '+' if diff > 0 else ''
        if key == 'subway_pct':
            fmt_d = f'{sign}{diff:.1f}%p'
        elif key == 'avg_transfers':
            fmt_d = f'{sign}{diff:.2f}'
        else:
            fmt_d = f'{sign}{diff:.1f}'

        mid_y = max(vals) * 0.5
        ax.annotate(fmt_d,
                    xy=(0.5, mid_y), fontsize=16,
                    ha='center', va='center',
                    fontweight='bold', color='#C00000',
                    bbox=dict(boxstyle='round,pad=0.4', fc='white',
                              ec='#C00000', alpha=0.95, lw=1.5))

        # Arrow from OTP bar to MNL bar
        arrow_y = max(vals) * 0.75
        ax.annotate('', xy=(0.85, arrow_y), xytext=(0.15, arrow_y),
                    arrowprops=dict(arrowstyle='->', color='#C00000',
                                    lw=2.0, connectionstyle='arc3,rad=0'))

        ax.set_xticks(x_pos)
        ax.set_xticklabels(['OTP\n1st Choice', 'MNL\n1st Choice'], fontsize=12)
        ax.set_title(label, fontsize=14, fontweight='bold', pad=10)
        ax.set_ylim(0, max(vals) * 1.25)
        ax.yaxis.grid(True, linestyle='--', alpha=0.3)
        ax.set_axisbelow(True)
        # Remove top and right spines
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    fig.suptitle('Route Characteristics: OTP vs MNL Selected Routes\n'
                 'MNL prefers: less walking, fewer transfers, more subway',
                 fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    path = FIGURES_DIR / "fig15_route_characteristics_comparison.png"
    plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Saved: {path.name}")
    return path


# ================================================================
# Main
# ================================================================
def main():
    print("=" * 60)
    print("  Phase 4 Figure Generation")
    print("=" * 60)

    data = load_data()
    print(f"  Data loaded: {data['overall']['n_chains']:,} chains\n")

    fig11_by_usertype(data)
    fig12_by_nalts(data)
    fig13_disagreement(data)
    fig14_probability_dist(data)
    fig15_route_characteristics(data)

    print(f"\n  All figures saved to: {FIGURES_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
