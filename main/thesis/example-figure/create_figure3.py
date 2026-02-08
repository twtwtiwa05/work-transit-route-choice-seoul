import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches as mpatches

# Set publication-quality style with larger fonts
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman', 'DejaVu Serif']
plt.rcParams['font.size'] = 14
plt.rcParams['axes.linewidth'] = 1.2
plt.rcParams['xtick.major.width'] = 1.2
plt.rcParams['ytick.major.width'] = 1.2

# Data
user_types = ['General', 'Youth', 'Elderly', 'Disabled', 'Child']
transfer_aversion = [4.04, 4.59, 5.94, 4.62, 4.78]
subway_preference = [2.49, 2.95, 4.72, 2.93, 2.77]

# Set up the figure with high DPI for publication
fig, ax = plt.subplots(figsize=(10, 6), dpi=300)

# X-axis positions
x = np.arange(len(user_types))
width = 0.35

# Create bars
bars1 = ax.bar(x - width/2, transfer_aversion, width,
               label='Transfer Aversion (β_transfer)',
               color='#D55E00', edgecolor='black', linewidth=1.2, alpha=0.85)

bars2 = ax.bar(x + width/2, subway_preference, width,
               label='Subway Preference (β_subway)',
               color='#0072B2', edgecolor='black', linewidth=1.2, alpha=0.85)

# Highlight Elderly bars with hatching and thicker border
bars1[2].set_edgecolor('#8B0000')
bars1[2].set_linewidth(2.5)
bars1[2].set_hatch('///')
bars1[2].set_alpha(1.0)

bars2[2].set_edgecolor('#00008B')
bars2[2].set_linewidth(2.5)
bars2[2].set_hatch('///')
bars2[2].set_alpha(1.0)

# Add value labels on top of bars
def add_value_labels(bars, values):
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.15,
                f'{value:.2f}',
                ha='center', va='bottom', fontsize=12, fontweight='bold')

add_value_labels(bars1, transfer_aversion)
add_value_labels(bars2, subway_preference)

# Customize the plot
ax.set_xlabel('User Type', fontsize=16, fontweight='bold', labelpad=10)
ax.set_ylabel('Parameter Value (absolute)', fontsize=16, fontweight='bold', labelpad=10)
ax.set_title('MNL Parameter Comparison by User Type', fontsize=18, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(user_types, fontsize=14)
ax.set_ylim(0, 7.0)

# Grid for better readability
ax.yaxis.grid(True, linestyle='--', alpha=0.3, linewidth=0.8)
ax.set_axisbelow(True)

# Legend with custom styling
legend = ax.legend(loc='upper left', frameon=True, fontsize=13,
                   edgecolor='black', fancybox=False, shadow=False,
                   framealpha=1.0)
legend.get_frame().set_linewidth(1.2)

# Add subtle note about elderly emphasis
ax.text(0.99, 0.02, 'Hatched bars: Elderly user type (key finding)',
        transform=ax.transAxes, fontsize=11, style='italic',
        ha='right', va='bottom', color='#333333',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor='gray', alpha=0.8, linewidth=0.8))

# Tight layout
plt.tight_layout()

# Save with high quality settings
output_path = '/Users/kimtaewoo/Documents/연구/main_project/최적경로 일치여부/probabilistic-otp/docs/figures/figure3_parameter_comparison.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight',
            facecolor='white', edgecolor='none', format='png')

print(f"Figure saved successfully to:\n{output_path}")
print(f"\nKey features:")
print("- All labels in English")
print("- Transfer Aversion in orange/red tones")
print("- Subway Preference in blue tones")
print("- Elderly bars highlighted with hatching and thicker borders")
print("- 300 DPI resolution for publication quality")
print("- Professional academic styling")
