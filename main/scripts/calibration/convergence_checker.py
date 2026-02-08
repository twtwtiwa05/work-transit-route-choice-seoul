#!/usr/bin/env python3
"""
Phase 4: 수렴 진단 모듈

반복 보정 루프의 수렴 여부를 판정하고, 반복별 궤적을 시각화한다.

수렴 기준 (4가지 동시 충족):
  1. β 안정성:  max|β_k − β_{k-1}| / max|β_{k-1}| < 0.01
  2. θ 안정성:  max|θ_k − θ_{k-1}| / max|θ_{k-1}| < 0.01
  3. 매칭률 안정: |match_k − match_{k-1}| < 0.005 (0.5%p)
  4. 최대 반복:  k ≤ 10

사용법:
    python convergence_checker.py                # 로그 읽어서 수렴 여부 출력
    python convergence_checker.py --plot         # 수렴 궤적 그래프 생성
"""

import json
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
FIGURE_DIR = RESULTS_DIR / "figures"
LOG_PATH = RESULTS_DIR / "calibration_log.json"

# ── 수렴 임계값 ────────────────────────────────────────────────
BETA_THRESHOLD = 0.01       # β 상대 변화 < 1%
THETA_THRESHOLD = 0.01      # θ 상대 변화 < 1%
MATCH_RATE_THRESHOLD = 0.005  # 매칭률 변화 < 0.5%p
MAX_ITERATIONS = 10         # 최대 반복 횟수


def load_log(log_path=None):
    """보정 로그를 로드한다."""
    path = log_path or LOG_PATH
    if not path.exists():
        print(f"  오류: 로그 파일 없음 ({path})")
        return None
    with open(path) as f:
        return json.load(f)


def compute_beta_change(beta_prev, beta_curr):
    """β의 최대 상대 변화량을 계산한다.

    Δ_β = max|β_k − β_{k-1}| / max|β_{k-1}|
    """
    if not beta_prev:
        return float('inf')

    diffs = []
    bases = []
    for key in beta_curr:
        if key in beta_prev:
            diffs.append(abs(beta_curr[key] - beta_prev[key]))
            bases.append(abs(beta_prev[key]))

    if not bases or max(bases) == 0:
        return float('inf')

    return max(diffs) / max(bases)


def compute_theta_change(theta_prev, theta_curr):
    """θ의 최대 상대 변화량을 계산한다.

    Δ_θ = max|θ_k − θ_{k-1}| / max|θ_{k-1}|
    """
    diffs = []
    bases = []
    for key in theta_curr:
        if key in theta_prev:
            prev_val = theta_prev[key]
            curr_val = theta_curr[key]
            diffs.append(abs(curr_val - prev_val))
            bases.append(abs(prev_val) if prev_val != 0 else 1.0)

    if not bases or max(bases) == 0:
        return float('inf')

    return max(diffs) / max(bases)


def check_convergence(log, verbose=True):
    """최신 반복의 수렴 여부를 판정한다.

    Returns
    -------
    dict
        converged: bool, delta_beta: float, delta_theta: float,
        delta_match_rate: float, iteration: int
    """
    iters = log.get("iterations", [])
    if len(iters) < 2:
        if verbose:
            print("  반복 2회 미만 — 수렴 판정 불가")
        return {"converged": False, "iteration": len(iters),
                "reason": "반복 2회 미만"}

    curr = iters[-1]
    prev = iters[-2]

    # β 변화
    delta_beta = compute_beta_change(prev.get("beta", {}),
                                     curr.get("beta", {}))

    # θ 변화
    delta_theta = compute_theta_change(prev.get("theta_new", {}),
                                       curr.get("theta_new", {}))

    # 매칭률 변화
    match_curr = curr.get("match_rate", 0)
    match_prev = prev.get("match_rate", 0)
    delta_match = abs(match_curr - match_prev) if (match_curr and match_prev) else float('inf')

    iteration = curr.get("iteration", len(iters))

    # 수렴 판정
    beta_ok = delta_beta < BETA_THRESHOLD
    theta_ok = delta_theta < THETA_THRESHOLD
    match_ok = delta_match < MATCH_RATE_THRESHOLD
    max_ok = iteration >= MAX_ITERATIONS

    # 매칭률 데이터가 없으면 β, θ만으로 판정
    if match_curr == 0 and match_prev == 0:
        converged = beta_ok and theta_ok
        match_ok = True  # 데이터 없으므로 무시
    else:
        converged = beta_ok and theta_ok and match_ok

    forced_stop = max_ok and not converged

    result = {
        "converged": converged or forced_stop,
        "naturally_converged": converged,
        "forced_stop": forced_stop,
        "iteration": iteration,
        "delta_beta": delta_beta,
        "delta_theta": delta_theta,
        "delta_match_rate": delta_match,
        "beta_ok": beta_ok,
        "theta_ok": theta_ok,
        "match_ok": match_ok,
    }

    if verbose:
        print(f"\n{'='*50}")
        print(f"  수렴 진단 — Iteration {iteration}")
        print(f"{'='*50}")
        status = lambda ok: "✓" if ok else "✗"
        print(f"  {status(beta_ok)} Δβ = {delta_beta:.4f}  (임계값 < {BETA_THRESHOLD})")
        print(f"  {status(theta_ok)} Δθ = {delta_theta:.4f}  (임계값 < {THETA_THRESHOLD})")
        if match_curr or match_prev:
            print(f"  {status(match_ok)} Δ매칭률 = {delta_match:.4f}  (임계값 < {MATCH_RATE_THRESHOLD})")
        else:
            print(f"  — 매칭률 데이터 없음 (무시)")
        print()
        if converged:
            print(f"  → 수렴 완료! (Iteration {iteration})")
        elif forced_stop:
            print(f"  → 최대 반복 도달 (K_max={MAX_ITERATIONS}), 강제 종료")
        else:
            print(f"  → 미수렴, 다음 반복 필요")

    return result


def plot_convergence(log, output_dir=None):
    """반복별 수렴 궤적 그래프를 생성한다.

    생성 그래프:
      1. θ 궤적 (walkReluctance, transferCost)
      2. β 궤적 (ride, walk, transfer, subway)
      3. 매칭률 궤적 (있는 경우)
    """
    output_dir = Path(output_dir) if output_dir else FIGURE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 출판 스타일
    plt.rcParams.update({
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'font.size': 12,
        'axes.linewidth': 1.2,
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'savefig.facecolor': 'white',
    })

    iters = log.get("iterations", [])
    if not iters:
        print("  반복 데이터 없음, 그래프 생성 불가")
        return

    # iter 0 (기본값) 추가
    iterations = [0] + [it["iteration"] for it in iters]

    # ── θ 궤적 ──
    walk_vals = [1.0] + [it["theta_new"]["walkReluctance"] for it in iters]
    transfer_vals = [120] + [it["theta_new"]["transferCostSeconds"] for it in iters]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.plot(iterations, walk_vals, 'o-', color='#0072B2', linewidth=2,
             markersize=8, label='walkReluctance')
    # 목표선 (있는 경우)
    if iters:
        target_walk = iters[-1].get("theta_target", {}).get("walkReluctance")
        if target_walk:
            ax1.axhline(y=target_walk, color='gray', linestyle='--',
                        alpha=0.5, label=f'Target ({target_walk:.1f})')
    ax1.set_xlabel('Iteration', fontsize=14, fontweight='bold')
    ax1.set_ylabel('walkReluctance', fontsize=14, fontweight='bold')
    ax1.set_title('Walk Reluctance Convergence', fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(iterations)

    ax2.plot(iterations, transfer_vals, 's-', color='#D55E00', linewidth=2,
             markersize=8, label='transferCostSeconds')
    if iters:
        target_tc = iters[-1].get("theta_target", {}).get("transferCostSeconds")
        if target_tc:
            ax2.axhline(y=target_tc, color='gray', linestyle='--',
                        alpha=0.5, label=f'Target ({target_tc}s)')
    ax2.set_xlabel('Iteration', fontsize=14, fontweight='bold')
    ax2.set_ylabel('transferCostSeconds', fontsize=14, fontweight='bold')
    ax2.set_title('Transfer Cost Convergence', fontsize=14, fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(iterations)

    plt.tight_layout()
    path = output_dir / "fig_convergence_theta.png"
    plt.savefig(path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  → {path.name}")

    # ── β 궤적 ──
    beta_keys = ["ride", "walk", "transfer", "subway"]
    colors = {'ride': '#0072B2', 'walk': '#D55E00',
              'transfer': '#56B4E9', 'subway': '#CC79A7'}

    fig, ax = plt.subplots(figsize=(10, 6))
    for key in beta_keys:
        vals = [it["beta"].get(key, 0) for it in iters]
        ax.plot([it["iteration"] for it in iters], vals, 'o-',
                color=colors[key], linewidth=2, markersize=7,
                label=f'β_{key}')

    ax.set_xlabel('Iteration', fontsize=14, fontweight='bold')
    ax.set_ylabel('β Coefficient', fontsize=14, fontweight='bold')
    ax.set_title('Parameter Convergence', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linewidth=0.5)

    plt.tight_layout()
    path = output_dir / "fig_convergence_beta.png"
    plt.savefig(path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  → {path.name}")

    # ── 매칭률 궤적 (데이터 있는 경우) ──
    match_rates = [it.get("match_rate") for it in iters]
    if any(m is not None and m > 0 for m in match_rates):
        fig, ax = plt.subplots(figsize=(8, 5))
        valid = [(it["iteration"], it["match_rate"])
                 for it in iters if it.get("match_rate")]
        if valid:
            x, y = zip(*valid)
            ax.plot(x, [v * 100 for v in y], 'o-', color='#009E73',
                    linewidth=2, markersize=8)
            ax.set_xlabel('Iteration', fontsize=14, fontweight='bold')
            ax.set_ylabel('Match Rate (%)', fontsize=14, fontweight='bold')
            ax.set_title('Matching Rate Improvement', fontsize=14,
                         fontweight='bold')
            ax.grid(True, alpha=0.3)

            plt.tight_layout()
            path = output_dir / "fig_convergence_match_rate.png"
            plt.savefig(path, dpi=300, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            plt.close()
            print(f"  → {path.name}")

    print("  그래프 생성 완료")


def print_summary(log):
    """전체 반복 이력을 표로 출력한다."""
    iters = log.get("iterations", [])
    if not iters:
        print("  반복 이력 없음")
        return

    print(f"\n{'='*70}")
    print(f"  반복 보정 이력 요약")
    print(f"{'='*70}")
    print(f"  {'Iter':>4} {'α':>5} {'walkRel':>8} {'transCost':>10} "
          f"{'β_walk':>8} {'β_ride':>8} {'매칭률':>8}")
    print(f"  {'-'*4:>4} {'-'*5:>5} {'-'*8:>8} {'-'*10:>10} "
          f"{'-'*8:>8} {'-'*8:>8} {'-'*8:>8}")

    # iter 0 (초기값)
    print(f"  {'0':>4} {'—':>5} {'1.00':>8} {'120':>10} "
          f"{'—':>8} {'—':>8} {'42.5%':>8}")

    for it in iters:
        k = it["iteration"]
        alpha = it.get("alpha", 0)
        wr = it["theta_new"]["walkReluctance"]
        tc = it["theta_new"]["transferCostSeconds"]
        bw = it["beta"].get("walk", 0)
        br = it["beta"].get("ride", 0)
        mr = it.get("match_rate", 0)
        mr_str = f"{mr:.1%}" if mr else "—"

        print(f"  {k:>4} {alpha:>5.3f} {wr:>8.2f} {tc:>10} "
              f"{bw:>8.4f} {br:>8.4f} {mr_str:>8}")


def main():
    parser = argparse.ArgumentParser(description="Phase 4: 수렴 진단 모듈")
    parser.add_argument("--log", type=str, default=None,
                        help="보정 로그 JSON 경로")
    parser.add_argument("--plot", action="store_true",
                        help="수렴 궤적 그래프 생성")
    parser.add_argument("--summary", action="store_true",
                        help="전체 반복 이력 출력")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else None
    log = load_log(log_path)
    if log is None:
        return

    if args.summary:
        print_summary(log)

    result = check_convergence(log)

    if args.plot:
        plot_convergence(log)

    return result


if __name__ == "__main__":
    main()
