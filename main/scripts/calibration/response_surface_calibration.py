#!/usr/bin/env python3
"""
Phase 4: LHS + Response Surface Method (RSM) 기반 3D 동시 최적화

3개 파라미터(walkReluctance, transferCostSeconds, subwayReluctance)를
동시에 탐색하여 최적 조합을 찾음.

방법:
  Phase 1: Latin Hypercube Sampling → 20개 점 multi-batch 실행
  Phase 2: 2차 반응표면 피팅 → 수학적 최적점 + 상호작용 분석
  Phase 3: 예측 최적점 + 주변 검증 → multi-batch 실행

사용법:
    python response_surface_calibration.py --type ELDERLY
    python response_surface_calibration.py --run
"""

import json
import subprocess
import sys
import os
import time
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

# ============================================================
# 경로 설정
# ============================================================

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output"
RESULTS_DIR = ROOT / "results"
SCRIPTS_DIR = ROOT / "scripts"
OTP_DIR = ROOT.parent / "korean-otp"

CALIBRATION_CONFIG = OTP_DIR / "calibration_config.json"
RSM_LOG = RESULTS_DIR / "rsm_calibration_log.json"

# ============================================================
# 탐색 설정
# ============================================================

# 파라미터 범위 (전체 탐색 공간)
PARAM_BOUNDS = {
    "walkReluctance": (1.0, 30.0),
    "transferCostSeconds": (30, 400),
    "subwayReluctance": (0.2, 2.0),
}

N_LHS_SAMPLES = 20   # Phase 1 LHS 샘플 수
SAMPLE_SIZE = 2000    # OD 서브샘플 크기

# ============================================================
# 유틸리티 함수 (기존 인프라 재사용)
# ============================================================

def save_config(theta, path=None):
    """OTP calibration_config.json 저장"""
    config = {
        "walkReluctance": float(theta["walkReluctance"]),
        "transferCostSeconds": int(theta["transferCostSeconds"]),
        "subwayReluctance": float(theta.get("subwayReluctance", 1.0)),
        "firstBoardCostSeconds": 60,
        "waitReluctance": 1.0,
        "searchWindowSeconds": 1800,
    }
    target = path or CALIBRATION_CONFIG
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def evaluate_result_file(result_file):
    """OTP 결과 파일에 대해 step4+step5 실행 후 유사도 반환"""
    if not result_file.exists() or result_file.stat().st_size < 1024:
        return None

    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Java\\jdk-21"
    env["PATH"] = f"{env['JAVA_HOME']}\\bin;{env.get('PATH', '')}"
    env["PYTHONIOENCODING"] = "utf-8"
    env["OTP_NDJSON_PATH"] = str(result_file)
    env["SUBSAMPLE_MODE"] = "1"
    env["ITERATION"] = "0"

    for script in [
        SCRIPTS_DIR / "matching" / "step4_parse_otp_results.py",
        SCRIPTS_DIR / "matching" / "step5_calculate_similarity.py",
    ]:
        result = subprocess.run(
            [sys.executable, str(script)],
            env=env, cwd=str(ROOT), capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')[:200]
            print(f"      [ERR] {script.name}: {stderr}")
            return None

    sim_file = OUTPUT_DIR / "similarity_results.parquet"
    if not sim_file.exists():
        return None

    sim_df = pd.read_parquet(sim_file)

    # OTP 1순위 추천 경로 = generalized_cost가 가장 낮은 대안
    # (파라미터 튜닝 효과를 정확히 반영)
    best = sim_df.loc[sim_df.groupby('chain_id')['otp_generalized_cost'].idxmin()]

    return {
        "exact_match": float(best['exact_match'].mean()),
        "sim_total": float(best['sim_total'].mean()),
        "n_chains": len(best),
    }


def prepare_od_file(utype, df_sample):
    """서브샘플에서 OD CSV + trip_attributes_subsample 준비 (1회)"""
    df = df_sample.copy().reset_index(drop=True)
    df["od_id"] = df.index

    subsample_file = OUTPUT_DIR / "trip_attributes_subsample.parquet"
    df.to_parquet(subsample_file, index=False)

    od_df = df[['origin_lat', 'origin_lon', 'dest_lat', 'dest_lon', 'board_time']].copy()
    od_df.columns = ['from_lat', 'from_lon', 'to_lat', 'to_lon', 'departure_time']
    od_df['departure_time'] = od_df['departure_time'].apply(
        lambda x: f"{int(x) // 3600:02d}:{(int(x) % 3600) // 60:02d}"
    )

    od_file = OTP_DIR / "data" / f"od_rsm_{utype.lower()}.csv"
    od_df.to_csv(od_file, index=False)
    print(f"  OD 파일 생성: {od_file.name} ({len(od_df):,}개)")
    return od_file

# ============================================================
# Latin Hypercube Sampling
# ============================================================

def generate_lhs_samples(n_samples, param_bounds, seed=42):
    """
    Latin Hypercube Sampling으로 3D 파라미터 공간 균등 탐색

    각 차원을 n_samples 구간으로 나누고, 각 구간에서 정확히 1개씩 샘플링.
    그리드보다 같은 수의 점으로 훨씬 넓은 영역을 커버.
    """
    rng = np.random.RandomState(seed)
    param_names = list(param_bounds.keys())
    n_params = len(param_names)

    # LHS 코어: 각 차원을 n_samples 구간으로 분할
    samples = np.zeros((n_samples, n_params))
    for j in range(n_params):
        perm = rng.permutation(n_samples)
        for i in range(n_samples):
            samples[i, j] = (perm[i] + rng.uniform()) / n_samples

    # [0,1] → 실제 파라미터 범위로 변환
    configs = []
    for i in range(n_samples):
        theta = {}
        for j, name in enumerate(param_names):
            low, high = param_bounds[name]
            val = low + samples[i, j] * (high - low)
            if name == "transferCostSeconds":
                val = int(round(val))
            else:
                val = round(val, 2)
            theta[name] = val
        configs.append(theta)

    return configs

# ============================================================
# Multi-batch 실행
# ============================================================

def run_multi_batch(utype, configs, od_file, batch_label=""):
    """
    여러 config를 Java multi-batch로 일괄 실행 후 평가

    Returns:
        list of (theta_dict, result_dict_or_None)
    """
    jar_file = OTP_DIR / "build" / "libs" / "korean-raptor-1.0.0-SNAPSHOT-all.jar"
    java_exe = "C:\\Program Files\\Java\\jdk-21\\bin\\java.exe"

    if not jar_file.exists():
        print(f"  [ERROR] JAR 없음: {jar_file}")
        return [(c, None) for c in configs]

    config_dir = OTP_DIR / "calibration_configs"
    config_dir.mkdir(exist_ok=True)
    manifest_lines = []
    result_files = []

    for i, theta in enumerate(configs):
        config_path = config_dir / f"config_{i}.json"
        save_config(theta, config_path)

        result_path = OTP_DIR / f"batch_rsm_{utype.lower()}_{i}.ndjson"
        if result_path.exists():
            result_path.unlink()
        progress_path = Path(str(result_path) + ".progress")
        if progress_path.exists():
            progress_path.unlink()

        manifest_lines.append(f"{config_path},{result_path}")
        result_files.append(result_path)

    # 매니페스트 파일
    manifest_file = config_dir / "manifest.txt"
    manifest_file.write_text("\n".join(manifest_lines), encoding='utf-8')

    # 초기 config (Java 데이터 로드용)
    save_config(configs[0])

    # Java multi-batch 실행
    cmd = [java_exe, "-Xmx40G", "-XX:+UseG1GC", "-jar", str(jar_file),
           "multi-batch", str(od_file), str(manifest_file), "16"]

    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Java\\jdk-21"
    env["PATH"] = f"{env['JAVA_HOME']}\\bin;{env.get('PATH', '')}"

    log_file = config_dir / "multi_batch.log"
    print(f"\n  [{batch_label}] multi-batch 시작 ({len(configs)}개 config)...")
    start = time.time()

    with open(log_file, 'w', encoding='utf-8') as log_fh:
        proc = subprocess.Popen(cmd, cwd=str(OTP_DIR), env=env,
                                stdout=log_fh, stderr=subprocess.STDOUT)
        timeout = len(configs) * 180 + 180
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {timeout}초 초과 → kill")
            proc.kill()
            proc.wait(timeout=10)

    otp_elapsed = time.time() - start
    print(f"  OTP 완료: {otp_elapsed:.1f}초 ({len(configs)}개 배치)")

    # step4+step5 평가
    print(f"  step4+step5 평가 중 ({len(configs)}개)...")
    eval_start = time.time()
    results = []
    for i, theta in enumerate(configs):
        result = evaluate_result_file(result_files[i])
        results.append((theta, result))
        w = theta['walkReluctance']
        t = theta['transferCostSeconds']
        s = theta['subwayReluctance']
        if result:
            sim = result['sim_total']
            exact = result['exact_match'] * 100
            print(f"    [{i+1:2d}/{len(configs)}] w={w:6.2f} t={t:3d} s={s:.2f}"
                  f" → sim={sim:.4f} exact={exact:.1f}%")
        else:
            print(f"    [{i+1:2d}/{len(configs)}] w={w:6.2f} t={t:3d} s={s:.2f}"
                  f" → [FAIL]")

    eval_elapsed = time.time() - eval_start
    print(f"  평가 완료: {eval_elapsed:.1f}초")

    return results

# ============================================================
# 반응표면 피팅
# ============================================================

def fit_response_surface(results):
    """
    2차 다항식 반응표면 피팅 + 최적점 예측

    sim = b0 + b1*w + b2*t + b3*s
             + b11*w^2 + b22*t^2 + b33*s^2
             + b12*w*t + b13*w*s + b23*t*s

    10개 계수, 상호작용항(b12, b13, b23)이 핵심.
    """
    from scipy.optimize import minimize as scipy_minimize

    # 유효 결과만
    valid = [(theta, r) for theta, r in results if r is not None]
    n = len(valid)
    if n < 10:
        print(f"  [WARN] 유효 결과 {n}개 < 10, 피팅 불가")
        return None

    # 디자인 행렬 구성
    X = np.zeros((n, 10))
    y = np.zeros(n)

    for i, (theta, result) in enumerate(valid):
        w = theta["walkReluctance"]
        t = theta["transferCostSeconds"]
        s = theta["subwayReluctance"]
        X[i] = [1, w, t, s, w**2, t**2, s**2, w*t, w*s, t*s]
        y[i] = result["sim_total"]

    # 최소제곱 피팅
    coeffs, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)

    # R^2
    y_pred = X @ coeffs
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # 잔차 표준편차 (예측 불확실성)
    rmse = np.sqrt(ss_res / max(n - 10, 1))

    print(f"\n  ── 반응표면 피팅 결과 ──")
    print(f"  유효 데이터: {n}개, R² = {r_squared:.4f}, RMSE = {rmse:.6f}")

    coeff_names = [
        "intercept", "walkRel", "transCost", "subwayRel",
        "walkRel^2", "transCost^2", "subwayRel^2",
        "walkRel*transCost", "walkRel*subwayRel", "transCost*subwayRel",
    ]
    print(f"  계수:")
    for name, c in zip(coeff_names, coeffs):
        marker = " ***" if abs(c) > rmse * 2 else ""
        print(f"    {name:>22s}: {c:+.8f}{marker}")

    # 상호작용 해석
    print(f"\n  상호작용 분석:")
    if abs(coeffs[7]) > rmse:
        direction = "양(+)" if coeffs[7] > 0 else "음(-)"
        print(f"    walkRel × transCost: {direction} 상호작용 ({coeffs[7]:+.8f})")
    if abs(coeffs[8]) > rmse:
        direction = "양(+)" if coeffs[8] > 0 else "음(-)"
        print(f"    walkRel × subwayRel: {direction} 상호작용 ({coeffs[8]:+.8f})")
    if abs(coeffs[9]) > rmse:
        direction = "양(+)" if coeffs[9] > 0 else "음(-)"
        print(f"    transCost × subwayRel: {direction} 상호작용 ({coeffs[9]:+.8f})")

    # 예측 최적점 (scipy L-BFGS-B, 다중 시작점)
    def neg_sim(params):
        w, t, s = params
        x = np.array([1, w, t, s, w**2, t**2, s**2, w*t, w*s, t*s])
        return -(x @ coeffs)

    bounds = [
        PARAM_BOUNDS["walkReluctance"],
        PARAM_BOUNDS["transferCostSeconds"],
        PARAM_BOUNDS["subwayReluctance"],
    ]

    best_result = None
    best_val = float('inf')
    rng = np.random.RandomState(123)

    for _ in range(50):
        x0 = [rng.uniform(*b) for b in bounds]
        res = scipy_minimize(neg_sim, x0, method='L-BFGS-B', bounds=bounds)
        if res.fun < best_val:
            best_val = res.fun
            best_result = res

    opt_w, opt_t, opt_s = best_result.x
    opt_sim = -best_val

    predicted = {
        "walkReluctance": round(opt_w, 2),
        "transferCostSeconds": int(round(opt_t)),
        "subwayReluctance": round(opt_s, 2),
    }

    print(f"\n  예측 최적점:")
    print(f"    walkReluctance     = {predicted['walkReluctance']:.2f}")
    print(f"    transferCostSeconds = {predicted['transferCostSeconds']}")
    print(f"    subwayReluctance   = {predicted['subwayReluctance']:.2f}")
    print(f"    예측 sim_total     = {opt_sim:.4f}")

    # 관측값 중 최고와 비교
    obs_best = max(valid, key=lambda x: x[1]["sim_total"])
    obs_sim = obs_best[1]["sim_total"]
    print(f"    관측 최고 sim      = {obs_sim:.4f} (차이: {opt_sim - obs_sim:+.4f})")

    return {
        "coefficients": coeffs.tolist(),
        "coeff_names": coeff_names,
        "r_squared": float(r_squared),
        "rmse": float(rmse),
        "predicted_optimum": predicted,
        "predicted_sim": float(opt_sim),
        "observed_best_sim": float(obs_sim),
    }


def generate_verification_configs(predicted, observed_results):
    """
    검증 포인트 생성:
    1. 예측 최적점
    2. 관측 Top 3 주변 정밀 탐색
    3. 예측 최적점 ±10% 변동
    """
    configs = []
    seen = set()

    def add_config(theta):
        key = (round(theta["walkReluctance"], 1),
               int(theta["transferCostSeconds"]),
               round(theta["subwayReluctance"], 1))
        if key not in seen:
            seen.add(key)
            configs.append(theta)

    # 1. 예측 최적점
    add_config(predicted.copy())

    # 2. 예측 최적점 ±15% 변동 (각 파라미터)
    for param in ["walkReluctance", "transferCostSeconds", "subwayReluctance"]:
        base = predicted[param]
        low, high = PARAM_BOUNDS[param]

        for direction in [+0.15, -0.15]:
            perturbed = predicted.copy()
            val = base * (1 + direction)
            val = max(min(val, high), low)
            if param == "transferCostSeconds":
                val = int(round(val))
            else:
                val = round(val, 2)
            perturbed[param] = val
            add_config(perturbed)

    # 3. 관측 Top 2 (이미 평가된 것과 다른 조합)
    valid = [(t, r) for t, r in observed_results if r is not None]
    top2 = sorted(valid, key=lambda x: x[1]["sim_total"], reverse=True)[:2]
    for theta, _ in top2:
        # Top 결과와 예측 최적점의 중간점
        mid = {
            "walkReluctance": round((theta["walkReluctance"] + predicted["walkReluctance"]) / 2, 2),
            "transferCostSeconds": int(round((theta["transferCostSeconds"] + predicted["transferCostSeconds"]) / 2)),
            "subwayReluctance": round((theta["subwayReluctance"] + predicted["subwayReluctance"]) / 2, 2),
        }
        add_config(mid)

    return configs

# ============================================================
# 메인 최적화 루프
# ============================================================

def optimize_type(utype, df_sample):
    """단일 유형 LHS + RSM 최적화"""
    print(f"\n{'='*65}")
    print(f"  [{utype}] LHS + 반응표면법 3D 동시 최적화")
    print(f"  샘플: {len(df_sample):,}개")
    print(f"  파라미터 범위:")
    for name, (low, high) in PARAM_BOUNDS.items():
        print(f"    {name}: [{low}, {high}]")
    print(f"  Phase 1: LHS {N_LHS_SAMPLES}개 → Phase 2: RSM 피팅 → Phase 3: 검증")
    print(f"{'='*65}")

    type_start = time.time()

    # OD 파일 1회 준비
    od_file = prepare_od_file(utype, df_sample)

    # ────────────────────────────────────────────────
    # Phase 1: Latin Hypercube Sampling
    # ────────────────────────────────────────────────
    print(f"\n  ━━ Phase 1: LHS 탐색 ({N_LHS_SAMPLES}개) ━━")
    lhs_configs = generate_lhs_samples(N_LHS_SAMPLES, PARAM_BOUNDS)

    print(f"  LHS 샘플 생성 완료:")
    for i, c in enumerate(lhs_configs):
        print(f"    [{i+1:2d}] w={c['walkReluctance']:6.2f}"
              f" t={c['transferCostSeconds']:3d}"
              f" s={c['subwayReluctance']:.2f}")

    phase1_results = run_multi_batch(utype, lhs_configs, od_file, "Phase 1")

    # Phase 1 Top 5
    valid1 = [(t, r) for t, r in phase1_results if r is not None]
    if not valid1:
        print("  [ERROR] Phase 1 결과 없음!")
        return None

    top5 = sorted(valid1, key=lambda x: x[1]["sim_total"], reverse=True)[:5]
    print(f"\n  Phase 1 Top 5:")
    for rank, (theta, result) in enumerate(top5, 1):
        print(f"    #{rank} w={theta['walkReluctance']:6.2f}"
              f" t={theta['transferCostSeconds']:3d}"
              f" s={theta['subwayReluctance']:.2f}"
              f" → sim={result['sim_total']:.4f}"
              f" exact={result['exact_match']*100:.1f}%")

    # ────────────────────────────────────────────────
    # Phase 2: 반응표면 피팅
    # ────────────────────────────────────────────────
    print(f"\n  ━━ Phase 2: 반응표면 피팅 ━━")
    rsm = fit_response_surface(phase1_results)

    if rsm is None:
        # RSM 실패 시 Phase 1 최고점
        best_theta, best_result = top5[0]
        return {
            "optimal_theta": best_theta,
            "best_sim_total": best_result["sim_total"],
            "best_exact_match": best_result["exact_match"],
            "method": "LHS_best (RSM failed)",
            "phase1_top5": [(t, r) for t, r in top5],
        }

    # ────────────────────────────────────────────────
    # Phase 3: 검증
    # ────────────────────────────────────────────────
    print(f"\n  ━━ Phase 3: 예측 최적점 검증 ━━")
    verify_configs = generate_verification_configs(
        rsm["predicted_optimum"], phase1_results
    )
    print(f"  검증 포인트 {len(verify_configs)}개:")
    for i, c in enumerate(verify_configs):
        print(f"    [{i+1}] w={c['walkReluctance']:6.2f}"
              f" t={c['transferCostSeconds']:3d}"
              f" s={c['subwayReluctance']:.2f}")

    phase3_results = run_multi_batch(utype, verify_configs, od_file, "Phase 3")

    # ────────────────────────────────────────────────
    # 최종 결과
    # ────────────────────────────────────────────────
    all_results = phase1_results + phase3_results
    all_valid = [(t, r) for t, r in all_results if r is not None]
    best_theta, best_result = max(all_valid, key=lambda x: x[1]["sim_total"])

    type_elapsed = time.time() - type_start

    print(f"\n  {'='*50}")
    print(f"  [{utype}] 최종 결과 (총 {type_elapsed/60:.1f}분)")
    print(f"  {'='*50}")
    print(f"    walkReluctance     = {best_theta['walkReluctance']:.2f}")
    print(f"    transferCostSeconds = {best_theta['transferCostSeconds']}")
    print(f"    subwayReluctance   = {best_theta['subwayReluctance']:.2f}")
    print(f"    sim_total          = {best_result['sim_total']:.4f}")
    print(f"    exact_match        = {best_result['exact_match']*100:.1f}%")
    print(f"    RSM R²             = {rsm['r_squared']:.4f}")
    print(f"    평가 횟수          = {len(all_valid)}개")
    print(f"  {'='*50}")

    return {
        "optimal_theta": best_theta,
        "best_sim_total": best_result["sim_total"],
        "best_exact_match": best_result["exact_match"],
        "rsm_r_squared": rsm["r_squared"],
        "rsm_rmse": rsm["rmse"],
        "rsm_coefficients": dict(zip(rsm["coeff_names"], rsm["coefficients"])),
        "rsm_predicted_optimum": rsm["predicted_optimum"],
        "rsm_predicted_sim": rsm["predicted_sim"],
        "total_evaluations": len(all_valid),
        "elapsed_min": round(type_elapsed / 60, 1),
        "phase1_top5": [
            {"theta": t, "sim": r["sim_total"], "exact": r["exact_match"]}
            for t, r in sorted(all_valid, key=lambda x: x[1]["sim_total"], reverse=True)[:5]
        ],
    }

# ============================================================
# 실행
# ============================================================

def run_optimization(target_types=None):
    """전체 또는 특정 유형 최적화"""
    print("\n" + "=" * 70)
    print("  LHS + 반응표면법 (RSM) 3D 동시 최적화")
    print("=" * 70)

    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_filtered.parquet")
    print(f"  전체 체인: {len(trip_attrs):,}")

    log_data = {
        "method": "LHS + Response Surface Method",
        "status": "running",
        "start_time": datetime.now().isoformat(),
        "settings": {
            "n_lhs_samples": N_LHS_SAMPLES,
            "sample_size": SAMPLE_SIZE,
            "param_bounds": {k: list(v) for k, v in PARAM_BOUNDS.items()},
        },
        "results": {},
    }

    if target_types:
        types_to_run = [t.upper() for t in target_types]
    else:
        types_to_run = ["GENERAL", "CHILDREN", "YOUTH", "ELDERLY", "DISABLED"]

    print(f"\n  대상 유형: {types_to_run}")
    print(f"  샘플 크기: {SAMPLE_SIZE:,}")
    print(f"  LHS 샘플: {N_LHS_SAMPLES}개 + 검증 ~7개 = ~{N_LHS_SAMPLES + 7}개/유형")
    print(f"  예상 시간: 유형당 ~35분, 전체 ~{len(types_to_run) * 35}분")

    total_start = time.time()

    for utype in types_to_run:
        df_type = trip_attrs[trip_attrs['user_type'] == utype]
        if len(df_type) == 0:
            print(f"\n  [{utype}] 데이터 없음, 건너뜀")
            continue

        n_sample = min(len(df_type), SAMPLE_SIZE)
        df_sample = df_type.sample(n=n_sample, random_state=42)

        result = optimize_type(utype, df_sample)
        if result:
            log_data["results"][utype] = {
                **result,
                "timestamp": datetime.now().isoformat(),
            }

        # 중간 저장
        with open(RSM_LOG, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)

    total_elapsed = time.time() - total_start

    # ────────────────────────────────────────────────
    # 결과 요약
    # ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  최적화 결과 요약")
    print("=" * 70)

    header = (f"  {'유형':<10} | {'sim_total':>10} | {'exact%':>8} | "
              f"{'walkRel':>8} | {'transCost':>10} | {'subwayRel':>10} | {'R²':>6}")
    print(f"\n{header}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}-+-{'-'*10}-+-{'-'*6}")

    for utype in types_to_run:
        if utype in log_data["results"]:
            r = log_data["results"][utype]
            opt = r["optimal_theta"]
            print(f"  {utype:<10} | {r['best_sim_total']:>10.4f} | "
                  f"{r['best_exact_match']*100:>7.1f}% | "
                  f"{opt['walkReluctance']:>8.2f} | "
                  f"{opt['transferCostSeconds']:>10} | "
                  f"{opt['subwayReluctance']:>10.2f} | "
                  f"{r.get('rsm_r_squared', 0):>6.3f}")

    print(f"\n  총 소요 시간: {total_elapsed/60:.1f}분")

    # 코드용 최적 θ
    print(f"\n  [최적 θ - 코드용]")
    print(f"  OPTIMAL_THETA = {{")
    for utype in types_to_run:
        if utype in log_data["results"]:
            opt = log_data["results"][utype]["optimal_theta"]
            print(f'      "{utype}": {{"walkReluctance": {opt["walkReluctance"]}, '
                  f'"transferCostSeconds": {opt["transferCostSeconds"]}, '
                  f'"subwayReluctance": {opt["subwayReluctance"]}}},')
    print(f"  }}")

    log_data["status"] = "completed"
    log_data["end_time"] = datetime.now().isoformat()
    log_data["total_elapsed_min"] = round(total_elapsed / 60, 1)
    with open(RSM_LOG, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)

    # ────────────────────────────────────────────────
    # 텍스트 결과 저장
    # ────────────────────────────────────────────────
    txt_file = RESULTS_DIR / "rsm_calibration_results.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"  LHS + RSM 3D 최적화 결과\n")
        f.write(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  평가 기준: OTP 1순위 (generalized_cost min)\n")
        f.write(f"  샘플 크기: {SAMPLE_SIZE:,} / LHS: {N_LHS_SAMPLES}개\n")
        f.write("=" * 80 + "\n\n")

        # 베이스라인 참조
        f.write("[ 베이스라인 (OTP 1순위, 전체 데이터) ]\n")
        f.write("  전체: Exact=20.34%, GENERAL=19.84%, ELDERLY=19.84%\n")
        f.write("  YOUTH=27.83%, CHILDREN=31.30%, DISABLED=23.60%\n\n")

        # 유형별 결과
        f.write(f"{'유형':<10} | {'sim_total':>10} | {'exact%':>8} | "
                f"{'walkRel':>8} | {'transCost':>10} | {'subwayRel':>10} | "
                f"{'R²':>6} | {'시간':>6}\n")
        f.write("-" * 80 + "\n")

        for utype in types_to_run:
            if utype in log_data["results"]:
                r = log_data["results"][utype]
                opt = r["optimal_theta"]
                f.write(f"{utype:<10} | {r['best_sim_total']:>10.4f} | "
                        f"{r['best_exact_match']*100:>7.1f}% | "
                        f"{opt['walkReluctance']:>8.2f} | "
                        f"{opt['transferCostSeconds']:>10} | "
                        f"{opt['subwayReluctance']:>10.2f} | "
                        f"{r.get('rsm_r_squared', 0):>6.3f} | "
                        f"{r.get('elapsed_min', 0):>5.1f}m\n")

        f.write("\n")

        # 유형별 상세
        for utype in types_to_run:
            if utype not in log_data["results"]:
                continue
            r = log_data["results"][utype]
            f.write(f"\n{'='*60}\n")
            f.write(f"  [{utype}] 상세 결과\n")
            f.write(f"{'='*60}\n")
            f.write(f"  최적 θ: walkRel={r['optimal_theta']['walkReluctance']:.2f}, "
                    f"transCost={r['optimal_theta']['transferCostSeconds']}, "
                    f"subwayRel={r['optimal_theta']['subwayReluctance']:.2f}\n")
            f.write(f"  sim_total = {r['best_sim_total']:.4f}\n")
            f.write(f"  exact_match = {r['best_exact_match']*100:.2f}%\n")
            f.write(f"  RSM R² = {r.get('rsm_r_squared', 0):.4f}\n")
            f.write(f"  평가 횟수 = {r.get('total_evaluations', 0)}개\n")
            f.write(f"  소요 시간 = {r.get('elapsed_min', 0):.1f}분\n")

            if "phase1_top5" in r:
                f.write(f"\n  Top 5:\n")
                for rank, item in enumerate(r["phase1_top5"][:5], 1):
                    t = item["theta"] if isinstance(item.get("theta"), dict) else item
                    s = item.get("sim", item.get("sim_total", 0))
                    e = item.get("exact", item.get("exact_match", 0))
                    if isinstance(e, float) and e < 1:
                        e = e * 100
                    f.write(f"    #{rank} w={t['walkReluctance']:6.2f} "
                            f"t={t['transferCostSeconds']:3d} "
                            f"s={t['subwayReluctance']:.2f} "
                            f"→ sim={s:.4f} exact={e:.1f}%\n")

            if "rsm_coefficients" in r:
                f.write(f"\n  RSM 계수:\n")
                for name, val in r["rsm_coefficients"].items():
                    f.write(f"    {name:>22s}: {val:+.8f}\n")

        f.write(f"\n\n총 소요 시간: {total_elapsed/60:.1f}분\n")

    print(f"\n  결과 저장: {txt_file}")
    print("\n  완료!")


def main():
    parser = argparse.ArgumentParser(description="LHS + RSM 3D Optimization")
    parser.add_argument("--run", action="store_true", help="전체 유형 최적화")
    parser.add_argument("--type", type=str, nargs="+", help="특정 유형 (예: --type ELDERLY)")
    args = parser.parse_args()

    if args.run:
        run_optimization()
    elif args.type:
        run_optimization(target_types=args.type)
    else:
        print("\n사용법:")
        print("  python response_surface_calibration.py --run           # 전체 유형")
        print("  python response_surface_calibration.py --type ELDERLY  # 특정 유형")
        print(f"\n설정:")
        print(f"  샘플 크기: {SAMPLE_SIZE:,}")
        print(f"  LHS 탐색: {N_LHS_SAMPLES}개")
        print(f"  파라미터 범위:")
        for name, (low, high) in PARAM_BOUNDS.items():
            print(f"    {name}: [{low}, {high}]")
        print(f"\n예상 시간:")
        print(f"  유형당 ~35분 (Phase 1: ~25분, Phase 2: ~1초, Phase 3: ~10분)")
        print(f"  전체 5유형: ~3시간")


if __name__ == "__main__":
    main()
