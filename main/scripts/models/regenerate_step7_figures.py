#!/usr/bin/env python3
"""
Regenerate Step 7 figures with Times New Roman font.
Produces publication-quality versions of:
  - model_comparison.png
  - shap_summary_core.png
  - shap_summary_full.png
  - shap_by_usertype_core.png
  - shap_by_usertype_full.png
"""

import json
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "results"
FIGURE_DIR = RESULT_DIR / "figures"

USER_TYPE_MAP = {1: 'General', 2: 'Children', 3: 'Youth',
                 4: 'Elderly', 5: 'Disabled'}


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


def load_results():
    with open(RESULT_DIR / 'lightgbm_results.json') as f:
        lgb = json.load(f)
    with open(RESULT_DIR / 'mnl_results.json') as f:
        mnl = json.load(f)
    with open(RESULT_DIR / 'mixed_logit_results.json') as f:
        ml = json.load(f)
    with open(RESULT_DIR / 'latent_class_results.json') as f:
        lc = json.load(f)
    return lgb, mnl, ml, lc


def fig_model_comparison(lgb, mnl, ml, lc):
    """Recreate model_comparison.png with Times New Roman."""
    set_pub_style()

    comparison = lgb.get('comparison', {})
    if not comparison:
        # Build from individual results
        comparison = {}
        pm = mnl['pooled']['metrics']
        comparison['MNL'] = {'hit_rate': pm.get('hit_rate', 0)}
        pred = ml.get('prediction', {})
        comparison['Mixed_Logit'] = {'hit_rate': pred.get('hit_rate', 0)}
        met = lc['best_model']['metrics']
        comparison['Latent_Class'] = {'hit_rate': met.get('hit_rate_test', 0)}
        comparison['LightGBM_Core'] = {'hit_rate': lgb['core_model']['hit_rate_test']}
        comparison['LightGBM_Full'] = {'hit_rate': lgb['full_model']['hit_rate_test']}

    models = list(comparison.keys())
    hit_rates = [comparison[m].get('hit_rate', 0) or 0 for m in models]

    colors = []
    for m in models:
        if 'LightGBM' in m:
            colors.append('#882255' if 'Full' in m else '#CC79A7')
        elif 'Latent' in m:
            colors.append('#D55E00')
        elif 'Mixed' in m:
            colors.append('#56B4E9')
        else:
            colors.append('#0072B2')

    display_names = {
        'MNL': 'MNL (Pooled)',
        'Mixed_Logit': 'Mixed Logit',
        'Latent_Class': 'Latent Class (K=3)',
        'LightGBM_Core': 'LightGBM (Core 4var)',
        'LightGBM_Full': 'LightGBM (Full 7var)'
    }
    labels = [display_names.get(m, m) for m in models]

    _fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(range(len(models)), hit_rates, color=colors,
                   edgecolor='black', linewidth=1.2, alpha=0.85)

    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(labels, fontsize=13)
    ax.set_xlabel('Choice-Set Level Hit Rate', fontsize=16,
                  fontweight='bold', labelpad=10)
    ax.set_title('Model Comparison: Transit Route Choice Prediction',
                 fontsize=16, fontweight='bold', pad=15)

    x_min = min(hr for hr in hit_rates if hr > 0) * 0.95
    x_max = max(hit_rates) * 1.02
    ax.set_xlim(x_min, x_max)

    for bar, hr in zip(bars, hit_rates):
        if hr > 0:
            ax.text(hr + (x_max - x_min) * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f'{hr:.1%}', va='center', fontsize=12, fontweight='bold')

    n_econ = sum(1 for m in models if 'LightGBM' not in m)
    if 0 < n_econ < len(models):
        ax.axhline(y=n_econ - 0.5, color='gray', linestyle='--',
                   linewidth=0.8, alpha=0.5)
        ax.text(x_min + (x_max - x_min) * 0.02, n_econ - 0.7,
                'Econometric \u2191  |  ML \u2193', fontsize=10, color='gray',
                style='italic')

    ax.xaxis.grid(True, linestyle='--', alpha=0.3, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.invert_yaxis()
    plt.tight_layout()
    path = FIGURE_DIR / "model_comparison.png"
    plt.savefig(path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  -> {path.name}")


def fig_shap_bar(lgb, model_key, label, suffix):
    """Create SHAP global importance bar chart (replaces summary_plot)."""
    set_pub_style()

    shap_data = lgb[model_key]['shap']['global_importance']
    features = list(shap_data.keys())
    values = [shap_data[f] for f in features]

    # Sort by importance (descending)
    pairs = sorted(zip(features, values), key=lambda x: x[1], reverse=True)
    features = [p[0] for p in pairs]
    values = [p[1] for p in pairs]

    feat_display = {
        'T_walk': 'Walking Time',
        'N_transfer': 'Transfer Count',
        'T_ride': 'In-vehicle Time',
        'D_subway': 'Subway Included',
        'D_peak': 'Peak Hour',
        'user_type': 'User Type',
        'n_alternatives': 'N Alternatives',
    }
    labels = [feat_display.get(f, f) for f in features]

    colors = ['#D55E00' if i == 0 else '#0072B2' for i in range(len(features))]

    _fig, ax = plt.subplots(figsize=(10, max(5, len(features) * 0.8)))
    bars = ax.barh(range(len(features)), values, color=colors,
                   edgecolor='black', linewidth=1.2, alpha=0.85)

    ax.set_yticks(range(len(features)))
    ax.set_yticklabels(labels, fontsize=13)
    ax.set_xlabel('Mean |SHAP Value|', fontsize=16,
                  fontweight='bold', labelpad=10)
    ax.set_title(f'SHAP Feature Importance ({label})',
                 fontsize=16, fontweight='bold', pad=15)

    x_max = max(values) * 1.2
    for bar, v in zip(bars, values):
        ax.text(v + x_max * 0.02,
                bar.get_y() + bar.get_height() / 2,
                f'{v:.4f}', va='center', fontsize=12, fontweight='bold')

    ax.set_xlim(0, x_max)
    ax.xaxis.grid(True, linestyle='--', alpha=0.3, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.invert_yaxis()
    plt.tight_layout()
    path = FIGURE_DIR / f"shap_summary_{suffix}.png"
    plt.savefig(path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  -> {path.name}")


def fig_shap_heatmap(lgb, model_key, label, suffix):
    """Create SHAP by user type heatmap."""
    set_pub_style()

    shap_by_type = lgb[model_key]['shap']['by_user_type']
    if not shap_by_type:
        print(f"  -> shap_by_usertype_{suffix}.png (skipped, no data)")
        return

    types_list = [t for t in USER_TYPE_MAP.values() if t in shap_by_type]
    feature_cols = list(next(iter(shap_by_type.values())).keys())

    feat_display = {
        'T_walk': 'Walking\nTime',
        'N_transfer': 'Transfer\nCount',
        'T_ride': 'In-vehicle\nTime',
        'D_subway': 'Subway\nIncluded',
        'D_peak': 'Peak\nHour',
        'user_type': 'User\nType',
        'n_alternatives': 'N Alts',
    }
    feat_labels = [feat_display.get(f, f) for f in feature_cols]

    matrix = np.array([
        [shap_by_type[t].get(f, 0) for f in feature_cols]
        for t in types_list
    ])

    _fig, ax = plt.subplots(figsize=(max(8, len(feature_cols) * 1.5),
                                      max(4, len(types_list) * 1.0)))
    im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
    ax.set_xticks(range(len(feature_cols)))
    ax.set_xticklabels(feat_labels, fontsize=12)
    ax.set_yticks(range(len(types_list)))
    ax.set_yticklabels(types_list, fontsize=13)

    vmax = matrix.max()
    for i in range(len(types_list)):
        for j in range(len(feature_cols)):
            color = 'white' if matrix[i, j] > vmax * 0.6 else 'black'
            ax.text(j, i, f'{matrix[i, j]:.3f}',
                    ha='center', va='center', fontsize=11,
                    fontweight='bold', color=color)

    cbar = plt.colorbar(im, label='Mean |SHAP Value|')
    cbar.ax.tick_params(labelsize=11)
    ax.set_title(f'SHAP Feature Importance by User Type ({label})',
                 fontsize=16, fontweight='bold', pad=15)
    plt.tight_layout()
    path = FIGURE_DIR / f"shap_by_usertype_{suffix}.png"
    plt.savefig(path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  -> {path.name}")


def main():
    print("=" * 50)
    print("  Regenerating Step 7 Figures (Times New Roman)")
    print("=" * 50)

    lgb, mnl, ml, lc = load_results()

    print("\n  [1/5] model_comparison.png")
    fig_model_comparison(lgb, mnl, ml, lc)

    print("  [2/5] shap_summary_core.png")
    fig_shap_bar(lgb, 'core_model', 'Core 4var', 'core')

    print("  [3/5] shap_summary_full.png")
    fig_shap_bar(lgb, 'full_model', 'Full 7var', 'full')

    print("  [4/5] shap_by_usertype_core.png")
    fig_shap_heatmap(lgb, 'core_model', 'Core 4var', 'core')

    print("  [5/5] shap_by_usertype_full.png")
    fig_shap_heatmap(lgb, 'full_model', 'Full 7var', 'full')

    print("\n  Done! All figures regenerated with Times New Roman.")


if __name__ == '__main__':
    main()
