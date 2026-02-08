#!/usr/bin/env python3
"""
Create Route Jaccard Distribution chart for SCI paper
"""

import matplotlib.pyplot as plt
import numpy as np

# Set publication-quality style with larger fonts
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman', 'DejaVu Serif']
plt.rcParams['font.size'] = 14
plt.rcParams['axes.linewidth'] = 1.2
plt.rcParams['xtick.major.width'] = 1.2
plt.rcParams['ytick.major.width'] = 1.2

# Data from analysis
categories = ['Exact Match\n(=1.0)', 'Partial Match\n(0<x<1)', 'No Match\n(=0)']
best_jaccard = [38.1, 48.6, 13.3]
gc_optimal = [30.4, 30.0, 39.6]

# Set up the figure
fig, ax = plt.subplots(figsize=(10, 5), dpi=300)

# X-axis positions
x = np.arange(len(categories))
width = 0.35

# Create bars
bars1 = ax.bar(x - width/2, best_jaccard, width,
               label='Best Jaccard Method',
               color='#2E86AB', edgecolor='black', linewidth=1.2, alpha=0.85)

bars2 = ax.bar(x + width/2, gc_optimal, width,
               label='GC Optimal Method',
               color='#A23B72', edgecolor='black', linewidth=1.2, alpha=0.85)

# Add value labels on top of bars
def add_value_labels(bars, values):
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{value:.1f}%',
                ha='center', va='bottom', fontsize=12, fontweight='bold')

add_value_labels(bars1, best_jaccard)
add_value_labels(bars2, gc_optimal)

# Customize the plot
ax.set_xlabel('Route Jaccard Category', fontsize=16, fontweight='bold', labelpad=10)
ax.set_ylabel('Percentage of Trips (%)', fontsize=16, fontweight='bold', labelpad=10)
ax.set_title('Route Jaccard Similarity Distribution (N=886,769)', fontsize=18, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(categories, fontsize=13)
ax.set_ylim(0, 60)

# Grid
ax.yaxis.grid(True, linestyle='--', alpha=0.3, linewidth=0.8)
ax.set_axisbelow(True)

# Legend
legend = ax.legend(loc='upper right', frameon=True, fontsize=13,
                   edgecolor='black', fancybox=False, framealpha=1.0)
legend.get_frame().set_linewidth(1.2)

# Tight layout
plt.tight_layout()

# Save
output_path = '/Users/kimtaewoo/Documents/연구/main_project/최적경로 일치여부/probabilistic-otp/docs/figures/figure2_jaccard_distribution.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight',
            facecolor='white', edgecolor='none', format='png')
plt.close()

print(f"Figure 2 saved successfully to:\n{output_path}")
