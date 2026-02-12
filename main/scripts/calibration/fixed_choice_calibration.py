#!/usr/bin/env python3
"""
Phase 4: Choice Set 고정 반복 보정

기존 방식의 문제:
  - OTP 파라미터 변경 → 새 경로 생성 → Choice Set 변경 → β 불안정

해결책 (Option 1):
  - Phase 3에서 추정한 β를 고정
  - β → θ 변환만 MSA로 반복
  - OTP 재실행 없이 θ 수렴

사용법:
    python fixed_choice_calibration.py --run
    python fixed_choice_calibration.py --status
"""

import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
OTP_DIR = ROOT.parent / "korean-otp"

# Phase 3 MNL 결과 파일
MNL_RESULTS_FILE = RESULTS_DIR / "mnl_results.json"
# 보정 설정 파일
CALIBRATION_CONFIG = OTP_DIR / "calibration_config.json"
# 보정 로그
CALIBRATION_LOG = RESULTS_DIR / "calibration_log_fixed.json"

# OTP 기본값
DEFAULT_THETA = {
    "walkReluctance": 2.0,
    "transferCostSeconds": 120,
}

# 파라미터 상한 (물리적 한계)
WALK_RELUCTANCE_CAP = 6.0      # 보행 1분 = 차내 6분
TRANSFER_COST_CAP = 300        # 환승 1회 = 5분

# MSA 설정
MAX_ITERATIONS = 20
CONVERGENCE_THRESHOLD = 0.01  # 1% 변화 이하면 수렴


def load_phase3_beta():
    """Phase 3 MNL 결과에서 β 로드"""
    if not MNL_RESULTS_FILE.exists():
        print(f"  오류: {MNL_RESULTS_FILE} 없음")
        return None

    with open(MNL_RESULTS_FILE) as f:
        mnl = json.load(f)

    # Pooled 결과 사용
    if "pooled" not in mnl:
        print("  오류: pooled 결과 없음")
        return None

    # coefficients 또는 parameters 키 확인
    pooled = mnl["pooled"]
    if "coefficients" in pooled:
        params = pooled["coefficients"]
    elif "parameters" in pooled:
        params = pooled["parameters"]
    else:
        print("  오류: coefficients/parameters 없음")
        return None

    # 값 추출 (dict 또는 scalar)
    def get_coef(p, key):
        if key not in p:
            return 0
        val = p[key]
        if isinstance(val, dict):
            return val.get("coef", val.get("value", 0))
        return val

    beta = {
        "ride": get_coef(params, "T_ride"),
        "walk": get_coef(params, "T_walk"),
        "transfer": get_coef(params, "N_transfer"),
        "subway": get_coef(params, "D_subway"),
    }

    return beta


def compute_theta_target(beta):
    """β에서 목표 θ 계산

    공식:
      walkReluctance = |β_walk / β_ride|
      transferCostSeconds = |β_transfer / β_ride| × 60
    """
    if beta["ride"] == 0:
        print("  오류: β_ride = 0")
        return None

    walk_rel = abs(beta["walk"] / beta["ride"])
    transfer_cost = abs(beta["transfer"] / beta["ride"]) * 60

    # 상한 적용
    walk_rel = min(walk_rel, WALK_RELUCTANCE_CAP)
    transfer_cost = min(transfer_cost, TRANSFER_COST_CAP)

    return {
        "walkReluctance": round(walk_rel, 2),
        "transferCostSeconds": round(transfer_cost, 0),
    }


def msa_update(theta_prev, theta_target, iteration):
    """MSA 업데이트

    θ_new = θ_prev + α × (θ_target - θ_prev)
    α = min(0.3, 1/(k+1))
    """
    alpha = min(0.3, 1.0 / (iteration + 1))

    theta_new = {}
    for key in theta_target:
        prev = theta_prev.get(key, DEFAULT_THETA.get(key, 0))
        target = theta_target[key]
        new_val = prev + alpha * (target - prev)

        # 반올림
        if key == "walkReluctance":
            new_val = round(new_val, 2)
        else:
            new_val = round(new_val, 0)

        theta_new[key] = new_val

    return theta_new, alpha


def check_convergence(theta_prev, theta_new):
    """수렴 확인: 모든 파라미터가 threshold 이하로 변화"""
    for key in theta_new:
        prev = theta_prev.get(key, DEFAULT_THETA.get(key, 0))
        new = theta_new[key]
        if prev == 0:
            continue
        change = abs(new - prev) / abs(prev)
        if change > CONVERGENCE_THRESHOLD:
            return False
    return True


def save_config(theta):
    """calibration_config.json 저장"""
    config = {
        "walkReluctance": theta["walkReluctance"],
        "transferCostSeconds": theta["transferCostSeconds"],
        "firstBoardCostSeconds": 60,
        "waitReluctance": 1.0,
        "searchWindowSeconds": 1800,
    }
    with open(CALIBRATION_CONFIG, 'w') as f:
        json.dump(config, f, indent=2)


def save_log(log_data):
    """보정 로그 저장"""
    with open(CALIBRATION_LOG, 'w') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


def load_log():
    """보정 로그 로드"""
    if CALIBRATION_LOG.exists():
        with open(CALIBRATION_LOG) as f:
            return json.load(f)
    return {"iterations": []}


def run_calibration():
    """Choice Set 고정 반복 보정 실행"""
    print("\n" + "=" * 60)
    print("  Choice Set 고정 반복 보정")
    print("=" * 60)

    # 1. Phase 3 β 로드
    print("\n[1] Phase 3 β 로드")
    beta = load_phase3_beta()
    if beta is None:
        return False

    print(f"  β_ride = {beta['ride']:.4f}")
    print(f"  β_walk = {beta['walk']:.4f}")
    print(f"  β_transfer = {beta['transfer']:.4f}")
    print(f"  β_subway = {beta['subway']:.4f}")

    # 2. 목표 θ 계산
    print("\n[2] 목표 θ 계산")
    theta_target = compute_theta_target(beta)
    if theta_target is None:
        return False

    print(f"  walkReluctance 목표: {theta_target['walkReluctance']}")
    print(f"  transferCost 목표: {theta_target['transferCostSeconds']}초")

    # 3. MSA 반복
    print("\n[3] MSA 반복 수렴")
    print("-" * 60)
    print(f"  {'Iter':>4} {'alpha':>6} {'walkRel':>10} {'transCost':>12} {'상태':>8}")
    print("-" * 60)

    log_data = {"beta": beta, "theta_target": theta_target, "iterations": []}
    theta_prev = DEFAULT_THETA.copy()

    print(f"  {'0':>4} {'-':>6} {theta_prev['walkReluctance']:>10.2f} {theta_prev['transferCostSeconds']:>12.0f} {'초기값':>8}")

    for k in range(1, MAX_ITERATIONS + 1):
        theta_new, alpha = msa_update(theta_prev, theta_target, k)

        # 수렴 확인
        converged = check_convergence(theta_prev, theta_new)
        status = "수렴!" if converged else ""

        print(f"  {k:>4} {alpha:>6.3f} {theta_new['walkReluctance']:>10.2f} {theta_new['transferCostSeconds']:>12.0f} {status:>8}")

        # 로그 저장
        log_data["iterations"].append({
            "iteration": k,
            "alpha": alpha,
            "theta": theta_new.copy(),
            "converged": converged,
        })

        if converged:
            break

        theta_prev = theta_new.copy()

    print("-" * 60)

    # 4. 최종 결과
    final_theta = log_data["iterations"][-1]["theta"]
    print(f"\n[4] 최종 결과")
    print(f"  walkReluctance: {DEFAULT_THETA['walkReluctance']} → {final_theta['walkReluctance']}")
    print(f"  transferCost: {DEFAULT_THETA['transferCostSeconds']} → {final_theta['transferCostSeconds']}초")

    # 5. 설정 파일 저장
    save_config(final_theta)
    print(f"\n  calibration_config.json 저장 완료")

    # 6. 로그 저장
    save_log(log_data)
    print(f"  calibration_log_fixed.json 저장 완료")

    # 7. 해석
    print("\n" + "=" * 60)
    print("  해석")
    print("=" * 60)
    print(f"  보행 가중치: 차내시간 1분 = 보행 {final_theta['walkReluctance']:.1f}분")
    print(f"  환승 페널티: 환승 1회 = 차내시간 {final_theta['transferCostSeconds']/60:.1f}분")
    print()
    print("  이 값을 OTP에 적용하면 MNL 추정 결과와")
    print("  일관된 경로 비용 계산이 가능합니다.")

    return True


def show_status():
    """현재 보정 상태 출력"""
    print("\n" + "=" * 60)
    print("  보정 상태")
    print("=" * 60)

    log = load_log()
    if not log.get("iterations"):
        print("  보정 기록 없음")
        print("  실행: python fixed_choice_calibration.py --run")
        return

    print(f"\n  β (Phase 3):")
    beta = log.get("beta", {})
    print(f"    β_ride = {beta.get('ride', 'N/A')}")
    print(f"    β_walk = {beta.get('walk', 'N/A')}")
    print(f"    β_transfer = {beta.get('transfer', 'N/A')}")

    print(f"\n  θ_target:")
    target = log.get("theta_target", {})
    print(f"    walkReluctance = {target.get('walkReluctance', 'N/A')}")
    print(f"    transferCostSeconds = {target.get('transferCostSeconds', 'N/A')}")

    print(f"\n  반복 이력:")
    for it in log["iterations"]:
        theta = it["theta"]
        status = " [수렴]" if it.get("converged") else ""
        print(f"    Iter {it['iteration']}: walkRel={theta['walkReluctance']:.2f}, "
              f"transCost={theta['transferCostSeconds']:.0f}{status}")


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: Choice Set 고정 반복 보정")
    parser.add_argument("--run", action="store_true",
                        help="보정 실행")
    parser.add_argument("--status", action="store_true",
                        help="현재 상태 확인")
    args = parser.parse_args()

    if args.run:
        run_calibration()
    elif args.status:
        show_status()
    else:
        show_status()


if __name__ == "__main__":
    main()
