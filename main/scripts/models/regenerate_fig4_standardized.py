#!/usr/bin/env python3
"""Regenerate the SHAP vs MNL cross-validation figure with honest statistics.

Replaces the fabricated 'Spearman rho = 1.0' version (2026-08-16 정정):
- Raw |beta| cannot be rank-compared across variables (per-minute vs.
  per-transfer vs. 0/1 dummy units); actual raw-|beta| vs SHAP rho = 0.0.
- Mean |SHAP| is proportional to |beta| * spread(x) in a linear model, so
  MNL importance is standardized as |beta| * SD(x) on the test set.
- Spearman rho is COMPUTED (= 0.8), not asserted.

Outputs:
  results/figures/fig4_shap_beta_validation.png   (titled, for docs)
  thesis/latex/figures/figure3_shap_validation.png (untitled, for paper)

Uses polars (the local pandas/pyarrow install is numpy-2.x incompatible).
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
COLS = ["T_walk", "N_transfer", "T_ride", "D_subway"]  # SHAP descending order
LABELS = ["Walking\nTime", "Transfer\nCount", "In-vehicle\nTime", "Subway\nIncluded"]


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation for tie-free vectors."""
    ra = np.argsort(np.argsort(-a))
    rb = np.argsort(np.argsort(-b))
    n = len(a)
    return 1 - 6 * float(((ra - rb) ** 2).sum()) / (n * (n * n - 1))


def load_importance() -> tuple[np.ndarray, np.ndarray, float]:
    """Return (mnl |b|*SD, shap mean|SHAP|, spearman rho)."""
    mnl = json.load(open(ROOT / "results" / "mnl_results.json", encoding="utf-8"))
    lgb = json.load(open(ROOT / "results" / "lightgbm_results.json", encoding="utf-8"))
    df = pl.read_parquet(ROOT / "output" / "model_input_test.parquet")
    beta_sd = np.array([abs(mnl["pooled"]["coefficients"][c]["coef"])
                        * float(df[c].std()) for c in COLS])
    shap = np.array([lgb["core_model"]["shap"]["global_importance"][c]
                     for c in COLS])
    return beta_sd, shap, spearman(beta_sd, shap)


def draw(mnl_norm: np.ndarray, shap_norm: np.ndarray, rho: float,
         with_title: bool, out_path: Path) -> None:
    _fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    x = np.arange(len(COLS))
    width = 0.36
    b1 = ax.bar(x - width / 2, mnl_norm, width,
                label=r"MNL $|\beta| \times$ SD (Normalized)",
                color="#0072B2", edgecolor="black", linewidth=1.2, alpha=0.85)
    b2 = ax.bar(x + width / 2, shap_norm, width,
                label="SHAP Importance (Normalized)",
                color="#CC79A7", edgecolor="black", linewidth=1.2, alpha=0.85)
    for bars, vals in [(b1, mnl_norm), (b2, shap_norm)]:
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{v:.1f}%", ha="center", va="bottom",
                    fontsize=11, fontweight="bold")
    ax.set_xlabel("Variable (Sorted by SHAP Importance)", fontsize=16,
                  fontweight="bold", labelpad=10)
    ax.set_ylabel("Relative Importance (%)", fontsize=16,
                  fontweight="bold", labelpad=10)
    if with_title:
        ax.set_title("Cross-Validation: Standardized MNL Importance vs. SHAP\n"
                     rf"(Spearman $\rho$ = {rho:.1f}; top-2 factors agree)",
                     fontsize=16, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, fontsize=13)
    ax.set_ylim(0, max(mnl_norm.max(), shap_norm.max()) * 1.22)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)
    legend = ax.legend(fontsize=12, loc="upper right", edgecolor="black",
                       fancybox=False, framealpha=1.0)
    legend.get_frame().set_linewidth(1.2)
    ax.text(0.99, 0.55,
            "Both methods rank walking time and transfers first;\n"
            "they differ only on in-vehicle time vs. subway dummy",
            transform=ax.transAxes, fontsize=11, style="italic",
            ha="right", va="center", color="#333333",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="gray", alpha=0.8, linewidth=0.8))
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print("saved:", out_path)


def main() -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 14,
        "axes.linewidth": 1.2,
        "xtick.major.width": 1.2,
        "ytick.major.width": 1.2,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
    })
    beta_sd, shap, rho = load_importance()
    mnl_norm = beta_sd / beta_sd.sum() * 100
    shap_norm = shap / shap.sum() * 100
    print("MNL |b|*SD normalized:", np.round(mnl_norm, 1))
    print("SHAP normalized      :", np.round(shap_norm, 1))
    print("Spearman rho         :", rho)
    draw(mnl_norm, shap_norm, rho, True,
         ROOT / "results" / "figures" / "fig4_shap_beta_validation.png")
    draw(mnl_norm, shap_norm, rho, False,
         ROOT / "thesis" / "latex" / "figures" / "figure3_shap_validation.png")


if __name__ == "__main__":
    main()
