#!/usr/bin/env python3
"""
Phase 4 Step 1: 파라미터 매퍼 (β → OTP θ)

Phase 3에서 추정된 행태 파라미터(β)를 OTP 라우팅 엔진의
비용함수 파라미터(θ)로 변환한다.
MSA(Method of Successive Averages) 감쇠를 적용하여 안정적 수렴을 보장.

사용법:
    python param_mapper.py                          # Iteration 1 (Phase 3 결과 기반)
    python param_mapper.py --iteration 2 --iter-results mnl_iter1.json
    python param_mapper.py --source mnl_pooled      # MNL Pooled 사용
"""

import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
OTP_DIR = ROOT.parent / "korean-otp"
CONFIG_PATH = OTP_DIR / "calibration_config.json"
LOG_PATH = RESULTS_DIR / "calibration_log.json"

# ── 기본값 및 상한 ─────────────────────────────────────────────
DEFAULT_THETA = {
    "walkReluctance": 1.0,        # 보행 가중치 (1.0 = 보행 1초 = 차내 1초)
    "transferCostSeconds": 120,    # 환승 비용 (초)
    "firstBoardCostSeconds": 60,   # 최초 탑승 비용 (초)
    "waitReluctance": 1.0,        # 대기시간 가중치
    "searchWindowSeconds": 1800,   # RAPTOR 탐색 시간창 (30분)
}

TRANSFER_COST_CAP = 600     # 환승비용 상한 (10분) — 다환승 경로 소멸 방지
WALK_RELUCTANCE_CAP = 15.0  # 보행가중치 상한 — 안전장치


def load_phase3_betas(source="lc_class2"):
    """Phase 3 추정 결과에서 β 계수를 로드한다.

    Parameters
    ----------
    source : str
        "lc_class2"  → Latent Class 다수 클래스 (77.2%, 권장)
        "mnl_pooled" → MNL Pooled 모형
    """
    if source == "lc_class2":
        with open(RESULTS_DIR / "latent_class_results.json") as f:
            lc = json.load(f)
        classes = lc["best_model"]["class_parameters"]
        # 가장 비중이 큰 클래스 (Class 2, 77.2%) 찾기
        weights = lc["best_model"]["class_weights"]
        majority_idx = max(range(len(weights)), key=lambda i: weights[i])
        # class_parameters 키: "class_1", "class_2", ... (1부터 시작)
        majority_class = f"class_{majority_idx + 1}"
        params = classes[majority_class]
        beta = {
            "ride": params["T_ride"]["coef"] if isinstance(params["T_ride"], dict) else params["T_ride"],
            "walk": params["T_walk"]["coef"] if isinstance(params["T_walk"], dict) else params["T_walk"],
            "transfer": params["N_transfer"]["coef"] if isinstance(params["N_transfer"], dict) else params["N_transfer"],
            "subway": params["D_subway"]["coef"] if isinstance(params["D_subway"], dict) else params["D_subway"],
        }
        print(f"  소스: LC {majority_class} (비중={weights[majority_idx]:.1%})")

    elif source == "mnl_pooled":
        with open(RESULTS_DIR / "mnl_results.json") as f:
            mnl = json.load(f)
        params = mnl["pooled"]["parameters"]
        beta = {
            "ride": params["T_ride"]["coef"],
            "walk": params["T_walk"]["coef"],
            "transfer": params["N_transfer"]["coef"],
            "subway": params["D_subway"]["coef"],
        }
        print(f"  소스: MNL Pooled")

    else:
        raise ValueError(f"알 수 없는 소스: {source}")

    print(f"  β_ride={beta['ride']:.4f}, β_walk={beta['walk']:.4f}, "
          f"β_transfer={beta['transfer']:.4f}, β_subway={beta['subway']:.4f}")
    return beta


def load_iteration_betas(iteration_results_path):
    """반복 k의 MNL 추정 결과에서 β를 로드한다 (iteration ≥ 2 용)."""
    with open(iteration_results_path) as f:
        mnl = json.load(f)
    params = mnl["pooled"]["parameters"]
    beta = {
        "ride": params["T_ride"]["coef"],
        "walk": params["T_walk"]["coef"],
        "transfer": params["N_transfer"]["coef"],
        "subway": params["D_subway"]["coef"],
    }
    return beta


def beta_to_theta_target(beta):
    """β 계수를 OTP 목표 파라미터(θ_target)로 변환한다.

    매핑 공식:
        walkReluctance = |β_walk / β_ride|
        transferCostSeconds = min(상한, |β_transfer / β_ride| × 60)

    주의: β_ride > 0인 경우 (고령자/장애인 패턴),
    LC Class 2의 β_ride(-0.077)를 대리값으로 사용.
    """
    if beta["ride"] < 0:
        walk_reluctance = abs(beta["walk"] / beta["ride"])
        transfer_cost_sec = abs(beta["transfer"] / beta["ride"]) * 60
    else:
        # β_ride > 0 (비정상): 대리값 사용
        print(f"  경고: β_ride > 0 ({beta['ride']:.4f}), |β_walk|/0.077 대리값 사용")
        walk_reluctance = abs(beta["walk"]) / 0.077
        transfer_cost_sec = abs(beta["transfer"]) / 0.077 * 60

    # 상한 적용
    walk_reluctance = min(walk_reluctance, WALK_RELUCTANCE_CAP)
    transfer_cost_sec = min(transfer_cost_sec, TRANSFER_COST_CAP)

    theta_target = {
        "walkReluctance": round(walk_reluctance, 2),
        "transferCostSeconds": int(round(transfer_cost_sec)),
    }
    print(f"  θ_target: walkReluctance={theta_target['walkReluctance']:.2f}, "
          f"transferCost={theta_target['transferCostSeconds']}초")
    return theta_target


def msa_update(theta_prev, theta_target, iteration):
    """MSA(Method of Successive Averages) 감쇠를 적용하여 θ를 업데이트한다.

    α_k = min(0.5, 1/k)
    θ_k = θ_{k-1} + α_k × (θ_target − θ_{k-1})

    감쇠 효과: 초기에는 큰 보폭(α=0.5), 반복할수록 미세 조정(α→0)
    → 진동 방지, 수렴 보장 (Sheffi 1985)
    """
    alpha = min(0.5, 1.0 / iteration)
    theta_new = {}

    for key in ["walkReluctance", "transferCostSeconds"]:
        prev = theta_prev.get(key, DEFAULT_THETA[key])
        target = theta_target[key]
        new_val = prev + alpha * (target - prev)

        if key == "transferCostSeconds":
            new_val = int(round(min(new_val, TRANSFER_COST_CAP)))
        else:
            new_val = round(min(new_val, WALK_RELUCTANCE_CAP), 2)

        theta_new[key] = new_val

    # 보정 대상이 아닌 파라미터는 이전 값 유지
    for key in DEFAULT_THETA:
        if key not in theta_new:
            theta_new[key] = theta_prev.get(key, DEFAULT_THETA[key])

    print(f"  MSA α={alpha:.3f}")
    print(f"  θ_new: walkReluctance={theta_new['walkReluctance']:.2f}, "
          f"transferCost={theta_new['transferCostSeconds']}초")
    return theta_new


def load_current_config():
    """현재 calibration_config.json을 로드한다."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return dict(DEFAULT_THETA)


def write_config(theta, path=None):
    """업데이트된 calibration_config.json을 저장한다."""
    path = path or CONFIG_PATH
    with open(path, "w") as f:
        json.dump(theta, f, indent=2)
    print(f"  저장: {path}")


def load_log():
    """보정 로그(반복 이력)를 로드한다."""
    if LOG_PATH.exists():
        with open(LOG_PATH) as f:
            return json.load(f)
    return {"iterations": []}


def save_log(log):
    """보정 로그를 저장한다."""
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print(f"  로그 저장: {LOG_PATH.name}")


def run(iteration, beta_source="lc_class2", iter_results_path=None):
    """지정된 반복 회차의 파라미터 매핑을 실행한다.

    Parameters
    ----------
    iteration : int
        반복 회차 번호 (1부터 시작).
    beta_source : str
        iteration 1일 때: "lc_class2" 또는 "mnl_pooled"
        iteration ≥ 2일 때: 무시됨 (iter_results_path 사용)
    iter_results_path : str or None
        해당 반복의 MNL 결과 JSON 경로 (iteration ≥ 2 전용)
    """
    print(f"\n{'='*50}")
    print(f"  파라미터 매퍼 — Iteration {iteration}")
    print(f"{'='*50}")

    # ── β 로드 ──
    if iteration == 1:
        beta = load_phase3_betas(beta_source)
    else:
        if iter_results_path is None:
            raise ValueError("iteration ≥ 2에서는 iter_results_path 필수")
        beta = load_iteration_betas(iter_results_path)

    # ── 목표 θ 계산 ──
    theta_target = beta_to_theta_target(beta)

    # ── 이전 θ 로드 ──
    theta_prev = load_current_config()
    print(f"  θ_prev: walkReluctance={theta_prev.get('walkReluctance', 1.0):.2f}, "
          f"transferCost={theta_prev.get('transferCostSeconds', 120)}초")

    # ── MSA 감쇠 적용 ──
    theta_new = msa_update(theta_prev, theta_target, iteration)

    # ── 설정 파일 저장 ──
    write_config(theta_new)

    # ── 로그 업데이트 ──
    log = load_log()
    log["iterations"].append({
        "iteration": iteration,
        "beta": beta,
        "theta_target": theta_target,
        "theta_prev": {k: theta_prev.get(k, DEFAULT_THETA[k])
                       for k in ["walkReluctance", "transferCostSeconds"]},
        "theta_new": {k: theta_new[k]
                      for k in ["walkReluctance", "transferCostSeconds"]},
        "alpha": min(0.5, 1.0 / iteration),
    })
    save_log(log)

    return theta_new


def main():
    parser = argparse.ArgumentParser(description="Phase 4: β → OTP θ 파라미터 매퍼")
    parser.add_argument("--iteration", type=int, default=1,
                        help="반복 회차 번호 (1부터 시작)")
    parser.add_argument("--source", default="lc_class2",
                        choices=["lc_class2", "mnl_pooled"],
                        help="iteration 1의 β 소스 (기본: lc_class2)")
    parser.add_argument("--iter-results", type=str, default=None,
                        help="반복 회차 MNL 결과 경로 (iteration ≥ 2용)")
    args = parser.parse_args()

    run(args.iteration, args.source, args.iter_results)


if __name__ == "__main__":
    main()
