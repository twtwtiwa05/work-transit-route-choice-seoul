#!/usr/bin/env python3
"""
Phase 4 접근법 E-IPW: 확률 기반 LHS + RSM 보정 (IPW 가중)

기존 RSM(접근법 D)과 동일한 인프라를 사용하되,
평가 방식을 결정론적(OTP 1순위) → 확률적(MNL 가중)으로 변경.
층화추출(환승 과표집) + IPW(역확률가중)으로 모집단 대표성 확보.

목적함수:
  F₁(θ) = Σ_i w_i × Σ_j P(j|β,C_i(θ)) × sim(i,j) / Σ_i w_i
  where P(j) = exp(V_j) / Σ exp(V_k),  V_j = β'x_j
        w_i = pop_proportion_k / sample_proportion_k  (chain i ∈ stratum k)

사용법:
    cd main
    python scripts/calibration/probabilistic_rsm_calibration.py --type GENERAL
    python scripts/calibration/probabilistic_rsm_calibration.py --run
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
PROB_LOG = RESULTS_DIR / "probabilistic_rsm_log.json"

# ============================================================
# MNL β 계수 (Phase 3 결과, 고정)
# ============================================================

MNL_BETAS = {
    "pooled": {
        "T_ride": -0.07498770610598887,
        "T_walk": -0.6441589132495491,
        "N_transfer": -3.051072746767041,
        "D_subway": 2.5379894848151454,
    },
    "GENERAL": {
        "T_ride": -0.07847618693371328,
        "T_walk": -0.6283492422815684,
        "N_transfer": -2.9662034150581422,
        "D_subway": 2.3622194545159676,
    },
    "YOUTH": {
        "T_ride": -0.11452109982658194,
        "T_walk": -0.7469108516609095,
        "N_transfer": -3.295156986515721,
        "D_subway": 2.238237605781155,
    },
    "ELDERLY": {
        "T_ride": -0.03202585311224609,
        "T_walk": -0.7233903787410852,
        "N_transfer": -3.996075762065534,
        "D_subway": 4.551235043260515,
    },
    # CHILDREN, DISABLED → pooled 사용
}


def get_betas(utype):
    """유형별 MNL β 반환 (없으면 pooled)"""
    return MNL_BETAS.get(utype, MNL_BETAS["pooled"])

# ============================================================
# 탐색 설정
# ============================================================

PARAM_BOUNDS = {
    "walkReluctance": (2.0, 40.0),
    "transferCostSeconds": (15, 500),
    "subwayReluctance": (0.2, 3.0),
}

N_LHS_SAMPLES = 22
SAMPLE_SIZE = 5000

# 층화 샘플링: 환승 횟수별 최소 비율
# 환승 1회 이상이 보정 핵심이므로 과표집(oversampling)
STRATIFICATION = {
    0: 0.50,   # 환승 0회: 50%
    1: 0.40,   # 환승 1회: 40% (원본 ~16% → 2.5배 과표집)
    "2+": 0.10, # 환승 2회+: 10% (원본 ~2% → 5배 과표집)
}


def stratified_sample(df_type, n_total, seed=42):
    """
    환승 횟수별 층화 샘플링

    trip_attributes_filtered에서 이미 좌표/GTFS 매칭 검증된 체인만 있으므로,
    어떤 체인을 뽑아도 OTP 라우팅에 문제 없음.
    """
    rng = np.random.RandomState(seed)

    # 환승 그룹 분리
    g0 = df_type[df_type['n_transfers'] == 0]
    g1 = df_type[df_type['n_transfers'] == 1]
    g2plus = df_type[df_type['n_transfers'] >= 2]

    # 목표 할당
    target_0 = int(n_total * STRATIFICATION[0])
    target_1 = int(n_total * STRATIFICATION[1])
    target_2 = n_total - target_0 - target_1  # 나머지

    # 실제 가용 수보다 많이 요청하면 전부 사용하고 나머지 재분배
    actual_0 = min(target_0, len(g0))
    actual_1 = min(target_1, len(g1))
    actual_2 = min(target_2, len(g2plus))

    # 미달분을 다른 그룹에 재분배
    remaining = n_total - actual_0 - actual_1 - actual_2
    if remaining > 0:
        # 가용 여유가 있는 그룹에 분배
        for g, actual, cap in [(g0, actual_0, len(g0)),
                                (g1, actual_1, len(g1)),
                                (g2plus, actual_2, len(g2plus))]:
            add = min(remaining, cap - actual)
            if g is g0:
                actual_0 += add
            elif g is g1:
                actual_1 += add
            else:
                actual_2 += add
            remaining -= add
            if remaining <= 0:
                break

    # 샘플링
    parts = []
    if actual_0 > 0:
        parts.append(g0.sample(n=actual_0, random_state=seed))
    if actual_1 > 0:
        parts.append(g1.sample(n=actual_1, random_state=seed))
    if actual_2 > 0:
        parts.append(g2plus.sample(n=actual_2, random_state=seed))

    result = pd.concat(parts, ignore_index=True)

    # IPW 가중치: 모집단 비율 / 샘플 비율 → 층화추출 편향 보정
    pop_total = len(df_type)
    sample_total = actual_0 + actual_1 + actual_2

    def _get_ipw(nt):
        if nt == 0:
            pop_n, samp_n = len(g0), actual_0
        elif nt == 1:
            pop_n, samp_n = len(g1), actual_1
        else:
            pop_n, samp_n = len(g2plus), actual_2
        pop_prop = pop_n / pop_total if pop_total > 0 else 0
        samp_prop = samp_n / sample_total if sample_total > 0 else 0
        return pop_prop / samp_prop if samp_prop > 0 else 1.0

    result['ipw_weight'] = result['n_transfers'].apply(_get_ipw)

    # 섞기 (순서가 환승별로 뭉치지 않게)
    return result.sample(frac=1, random_state=seed).reset_index(drop=True)

# ============================================================
# 유틸리티 함수
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


def compute_mnl_probabilities(sim_df, otp_df, betas):
    """
    MNL 선택확률 계산

    Returns:
        merged DataFrame with 'P_mnl', 'P_sim', 'P_exact' columns
    """
    # 속성 병합
    merged = sim_df.merge(
        otp_df[['od_id', 'alt_id', 'ride_time_sec', 'walk_time_sec',
                'n_transfers', 'has_subway']],
        on=['od_id', 'alt_id'],
        how='left'
    )

    # null 제거 (병합 실패 행)
    n_before = len(merged)
    merged = merged.dropna(subset=['ride_time_sec'])
    if len(merged) < n_before:
        pass  # 소량 손실 허용

    # V_j = β'x_j
    merged['V'] = (
        betas["T_ride"] * (merged["ride_time_sec"] / 60.0)
        + betas["T_walk"] * (merged["walk_time_sec"] / 60.0)
        + betas["N_transfer"] * merged["n_transfers"]
        + betas["D_subway"] * merged["has_subway"]
    )

    # Softmax (수치 안정성: chain 내 max V 차감)
    merged['V_max'] = merged.groupby('chain_id')['V'].transform('max')
    merged['exp_V'] = np.exp(merged['V'] - merged['V_max'])
    merged['sum_exp_V'] = merged.groupby('chain_id')['exp_V'].transform('sum')
    merged['P_mnl'] = merged['exp_V'] / merged['sum_exp_V']

    # 확률 가중 지표
    merged['P_sim'] = merged['P_mnl'] * merged['sim_total']
    merged['P_exact'] = merged['P_mnl'] * merged['exact_match']

    return merged


def evaluate_result_file(result_file, utype):
    """
    OTP 결과 파일에 대해 step4+step5 실행 후 확률적 평가

    Returns:
        dict with F1 (expected sim), F2 (expected exact), + 결정론적 지표 for 비교
    """
    if not result_file.exists() or result_file.stat().st_size < 1024:
        return None

    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Java\\jdk-21"
    env["PATH"] = f"{env['JAVA_HOME']}\\bin;{env.get('PATH', '')}"
    env["PYTHONIOENCODING"] = "utf-8"
    env["OTP_NDJSON_PATH"] = str(result_file)
    env["SUBSAMPLE_MODE"] = "1"
    env["ITERATION"] = "0"

    # step4 + step5 실행
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

    # 결과 로드
    sim_file = OUTPUT_DIR / "similarity_results.parquet"
    otp_file = OUTPUT_DIR / "otp_alternatives.parquet"
    if not sim_file.exists() or not otp_file.exists():
        return None

    sim_df = pd.read_parquet(sim_file)
    otp_df = pd.read_parquet(otp_file)

    # ── IPW 가중치 로드 (층화추출 보정) ──
    _sub = pd.read_parquet(OUTPUT_DIR / "trip_attributes_subsample.parquet")
    if 'ipw_weight' in _sub.columns:
        subsample_ipw = _sub[['chain_id', 'ipw_weight']].copy()
    else:
        subsample_ipw = _sub[['chain_id']].copy()
        subsample_ipw['ipw_weight'] = 1.0

    # ── 확률적 평가 (F₁, F₂) — IPW 가중 ──
    betas = get_betas(utype)
    merged = compute_mnl_probabilities(sim_df, otp_df, betas)

    # Chain-level: Σ_j P(j) × sim(j), Σ_j P(j) × em(j)
    chain_f1 = merged.groupby('chain_id')['P_sim'].sum()
    chain_f2 = merged.groupby('chain_id')['P_exact'].sum()

    chain_metrics = pd.DataFrame({'F1': chain_f1, 'F2': chain_f2}).reset_index()
    chain_metrics = chain_metrics.merge(subsample_ipw, on='chain_id', how='left')
    chain_metrics['ipw_weight'] = chain_metrics['ipw_weight'].fillna(1.0)

    w = chain_metrics['ipw_weight']
    F1 = (chain_metrics['F1'] * w).sum() / w.sum()
    F2 = (chain_metrics['F2'] * w).sum() / w.sum()

    # ── 결정론적 평가 (IPW 가중, 비교용) ──
    det_best = sim_df.loc[sim_df.groupby('chain_id')['otp_generalized_cost'].idxmin()].copy()
    det_best = det_best.merge(subsample_ipw, on='chain_id', how='left')
    det_best['ipw_weight'] = det_best['ipw_weight'].fillna(1.0)
    w_det = det_best['ipw_weight']
    det_exact = (det_best['exact_match'] * w_det).sum() / w_det.sum()
    det_sim = (det_best['sim_total'] * w_det).sum() / w_det.sum()

    # MNL 1순위 (V max, IPW 가중)
    mnl_best = merged.loc[merged.groupby('chain_id')['V'].idxmax()].copy()
    mnl_best = mnl_best.merge(subsample_ipw, on='chain_id', how='left')
    mnl_best['ipw_weight'] = mnl_best['ipw_weight'].fillna(1.0)
    w_mnl = mnl_best['ipw_weight']
    mnl_exact = (mnl_best['exact_match'] * w_mnl).sum() / w_mnl.sum()
    mnl_sim = (mnl_best['sim_total'] * w_mnl).sum() / w_mnl.sum()

    n_chains = sim_df['chain_id'].nunique()

    return {
        # 확률적 지표 (최적화 대상)
        "F1_expected_sim": float(F1),
        "F2_expected_exact": float(F2),
        # 결정론적 지표 (비교용)
        "det_exact_match": float(det_exact),
        "det_sim_total": float(det_sim),
        # MNL 1순위 지표 (비교용)
        "mnl_exact_match": float(mnl_exact),
        "mnl_sim_total": float(mnl_sim),
        # 메타
        "n_chains": n_chains,
    }


def prepare_od_file(utype, df_sample):
    """서브샘플에서 OD CSV + trip_attributes_subsample 준비"""
    df = df_sample.copy().reset_index(drop=True)
    df["od_id"] = df.index

    subsample_file = OUTPUT_DIR / "trip_attributes_subsample.parquet"
    df.to_parquet(subsample_file, index=False)

    od_df = df[['origin_lat', 'origin_lon', 'dest_lat', 'dest_lon', 'board_time']].copy()
    od_df.columns = ['from_lat', 'from_lon', 'to_lat', 'to_lon', 'departure_time']
    od_df['departure_time'] = od_df['departure_time'].apply(
        lambda x: f"{int(x) // 3600:02d}:{(int(x) % 3600) // 60:02d}"
    )

    od_file = OTP_DIR / "data" / f"od_prob_{utype.lower()}.csv"
    od_df.to_csv(od_file, index=False)
    print(f"  OD 파일 생성: {od_file.name} ({len(od_df):,}개)")
    return od_file

# ============================================================
# Latin Hypercube Sampling
# ============================================================

def generate_lhs_samples(n_samples, param_bounds, seed=42):
    """LHS로 3D 파라미터 공간 균등 탐색"""
    rng = np.random.RandomState(seed)
    param_names = list(param_bounds.keys())
    n_params = len(param_names)

    samples = np.zeros((n_samples, n_params))
    for j in range(n_params):
        perm = rng.permutation(n_samples)
        for i in range(n_samples):
            samples[i, j] = (perm[i] + rng.uniform()) / n_samples

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
    여러 config를 Java multi-batch로 일괄 실행 후 확률적 평가

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

        result_path = OTP_DIR / f"batch_prob_{utype.lower()}_{i}.ndjson"
        if result_path.exists():
            result_path.unlink()
        progress_path = Path(str(result_path) + ".progress")
        if progress_path.exists():
            progress_path.unlink()

        manifest_lines.append(f"{config_path},{result_path}")
        result_files.append(result_path)

    manifest_file = config_dir / "manifest.txt"
    manifest_file.write_text("\n".join(manifest_lines), encoding='utf-8')

    save_config(configs[0])

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
        # 5000 OD: config당 ~4분, 데이터 로드 ~2분
        timeout = len(configs) * 300 + 300
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {timeout}초 초과 → kill")
            proc.kill()
            proc.wait(timeout=10)

    otp_elapsed = time.time() - start
    print(f"  OTP 완료: {otp_elapsed:.1f}초 ({len(configs)}개 배치)")

    # step4+step5 + 확률적 평가
    print(f"  확률적 평가 중 ({len(configs)}개)...")
    eval_start = time.time()
    results = []
    for i, theta in enumerate(configs):
        result = evaluate_result_file(result_files[i], utype)
        results.append((theta, result))
        w = theta['walkReluctance']
        t = theta['transferCostSeconds']
        s = theta['subwayReluctance']
        if result:
            f1 = result['F1_expected_sim']
            f2 = result['F2_expected_exact'] * 100
            det_e = result['det_exact_match'] * 100
            print(f"    [{i+1:2d}/{len(configs)}] w={w:6.2f} t={t:3d} s={s:.2f}"
                  f" → F₁={f1:.4f} F₂={f2:.1f}% (det={det_e:.1f}%)")
        else:
            print(f"    [{i+1:2d}/{len(configs)}] w={w:6.2f} t={t:3d} s={s:.2f}"
                  f" → [FAIL]")

    eval_elapsed = time.time() - eval_start
    print(f"  평가 완료: {eval_elapsed:.1f}초")

    return results

# ============================================================
# 반응표면 피팅 (F₁ 기준)
# ============================================================

def fit_response_surface(results):
    """
    2차 다항식 반응표면 피팅 — F₁(기대 유사도) 기준

    F₁ = b0 + b1*w + b2*t + b3*s
            + b11*w² + b22*t² + b33*s²
            + b12*w*t + b13*w*s + b23*t*s
    """
    from scipy.optimize import minimize as scipy_minimize

    valid = [(theta, r) for theta, r in results if r is not None]
    n = len(valid)
    if n < 10:
        print(f"  [WARN] 유효 결과 {n}개 < 10, 피팅 불가")
        return None

    X = np.zeros((n, 10))
    y_f1 = np.zeros(n)
    y_f2 = np.zeros(n)

    for i, (theta, result) in enumerate(valid):
        w = theta["walkReluctance"]
        t = theta["transferCostSeconds"]
        s = theta["subwayReluctance"]
        X[i] = [1, w, t, s, w**2, t**2, s**2, w*t, w*s, t*s]
        y_f1[i] = result["F1_expected_sim"]
        y_f2[i] = result["F2_expected_exact"]

    # F₁ 기준 피팅
    coeffs, residuals, rank, sv = np.linalg.lstsq(X, y_f1, rcond=None)

    y_pred = X @ coeffs
    ss_res = np.sum((y_f1 - y_pred) ** 2)
    ss_tot = np.sum((y_f1 - np.mean(y_f1)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    rmse = np.sqrt(ss_res / max(n - 10, 1))

    print(f"\n  ── 반응표면 피팅 결과 (F₁ = 기대 유사도) ──")
    print(f"  유효 데이터: {n}개, R² = {r_squared:.4f}, RMSE = {rmse:.6f}")
    print(f"  F₁ 범위: [{y_f1.min():.4f}, {y_f1.max():.4f}], 평균: {y_f1.mean():.4f}")
    print(f"  F₂ 범위: [{y_f2.min()*100:.2f}%, {y_f2.max()*100:.2f}%]")

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
    for idx, pair in [(7, "walkRel × transCost"),
                      (8, "walkRel × subwayRel"),
                      (9, "transCost × subwayRel")]:
        if abs(coeffs[idx]) > rmse:
            direction = "양(+)" if coeffs[idx] > 0 else "음(-)"
            print(f"    {pair}: {direction} 상호작용 ({coeffs[idx]:+.8f})")

    # 최적점 탐색 (F₁ 최대화)
    def neg_f1(params):
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
        res = scipy_minimize(neg_f1, x0, method='L-BFGS-B', bounds=bounds)
        if res.fun < best_val:
            best_val = res.fun
            best_result = res

    opt_w, opt_t, opt_s = best_result.x
    opt_f1 = -best_val

    predicted = {
        "walkReluctance": round(opt_w, 2),
        "transferCostSeconds": int(round(opt_t)),
        "subwayReluctance": round(opt_s, 2),
    }

    print(f"\n  예측 최적점 (F₁ 최대화):")
    print(f"    walkReluctance     = {predicted['walkReluctance']:.2f}")
    print(f"    transferCostSeconds = {predicted['transferCostSeconds']}")
    print(f"    subwayReluctance   = {predicted['subwayReluctance']:.2f}")
    print(f"    예측 F₁            = {opt_f1:.4f}")

    obs_best = max(valid, key=lambda x: x[1]["F1_expected_sim"])
    obs_f1 = obs_best[1]["F1_expected_sim"]
    print(f"    관측 최고 F₁       = {obs_f1:.4f} (차이: {opt_f1 - obs_f1:+.4f})")

    return {
        "coefficients": coeffs.tolist(),
        "coeff_names": coeff_names,
        "r_squared": float(r_squared),
        "rmse": float(rmse),
        "predicted_optimum": predicted,
        "predicted_f1": float(opt_f1),
        "observed_best_f1": float(obs_f1),
        "f1_range": [float(y_f1.min()), float(y_f1.max())],
        "f2_range": [float(y_f2.min()), float(y_f2.max())],
    }


def generate_verification_configs(predicted, observed_results):
    """검증 포인트 생성"""
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

    # 2. 예측 최적점 ±15% 변동
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

    # 3. 관측 Top 2와 예측점의 중간점
    valid = [(t, r) for t, r in observed_results if r is not None]
    top2 = sorted(valid, key=lambda x: x[1]["F1_expected_sim"], reverse=True)[:2]
    for theta, _ in top2:
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
    """단일 유형 확률적 LHS + RSM 최적화"""
    betas = get_betas(utype)
    beta_source = utype if utype in MNL_BETAS else "pooled"

    print(f"\n{'='*70}")
    print(f"  [{utype}] 확률적 LHS + RSM 최적화 (접근법 E)")
    print(f"  샘플: {len(df_sample):,}개")
    print(f"  MNL β: {beta_source} (T_ride={betas['T_ride']:.4f}, "
          f"T_walk={betas['T_walk']:.4f}, "
          f"N_transfer={betas['N_transfer']:.4f}, "
          f"D_subway={betas['D_subway']:.4f})")
    print(f"  목적함수: F₁ = Σ w_ipw × P(j|β) × sim(j) / Σ w_ipw  (IPW 보정)")
    print(f"  파라미터 범위:")
    for name, (low, high) in PARAM_BOUNDS.items():
        print(f"    {name}: [{low}, {high}]")
    print(f"{'='*70}")

    type_start = time.time()

    # OD 파일 준비
    od_file = prepare_od_file(utype, df_sample)

    # ── Phase 1: LHS 탐색 ──
    print(f"\n  ━━ Phase 1: LHS 탐색 ({N_LHS_SAMPLES}개) ━━")
    lhs_configs = generate_lhs_samples(N_LHS_SAMPLES, PARAM_BOUNDS)

    print(f"  LHS 샘플 생성 완료:")
    for i, c in enumerate(lhs_configs):
        print(f"    [{i+1:2d}] w={c['walkReluctance']:6.2f}"
              f" t={c['transferCostSeconds']:3d}"
              f" s={c['subwayReluctance']:.2f}")

    phase1_results = run_multi_batch(utype, lhs_configs, od_file, "Phase 1")

    valid1 = [(t, r) for t, r in phase1_results if r is not None]
    if not valid1:
        print("  [ERROR] Phase 1 결과 없음!")
        return None

    # Phase 1 Top 5 (F₁ 기준)
    top5 = sorted(valid1, key=lambda x: x[1]["F1_expected_sim"], reverse=True)[:5]
    print(f"\n  Phase 1 Top 5 (F₁ 기준):")
    print(f"  {'#':>3} {'walkRel':>8} {'transCost':>10} {'subwayRel':>10}"
          f" │ {'F₁(E[sim])':>10} {'F₂(E[em])':>10}"
          f" │ {'det_exact':>10} {'mnl_exact':>10}")
    print(f"  {'─'*3} {'─'*8} {'─'*10} {'─'*10}"
          f" │ {'─'*10} {'─'*10}"
          f" │ {'─'*10} {'─'*10}")
    for rank, (theta, result) in enumerate(top5, 1):
        print(f"  {rank:>3} {theta['walkReluctance']:>8.2f} "
              f"{theta['transferCostSeconds']:>10} "
              f"{theta['subwayReluctance']:>10.2f}"
              f" │ {result['F1_expected_sim']:>10.4f} "
              f"{result['F2_expected_exact']*100:>9.2f}%"
              f" │ {result['det_exact_match']*100:>9.2f}% "
              f"{result['mnl_exact_match']*100:>9.2f}%")

    # ── Phase 2: RSM 피팅 ──
    print(f"\n  ━━ Phase 2: 반응표면 피팅 (F₁ 기준) ━━")
    rsm = fit_response_surface(phase1_results)

    if rsm is None:
        best_theta, best_result = top5[0]
        return {
            "optimal_theta": best_theta,
            "best_F1": best_result["F1_expected_sim"],
            "best_F2": best_result["F2_expected_exact"],
            "best_det_exact": best_result["det_exact_match"],
            "best_mnl_exact": best_result["mnl_exact_match"],
            "method": "LHS_best (RSM failed)",
        }

    # ── Phase 3: 검증 ──
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

    # ── 최종 결과 ──
    all_results = phase1_results + phase3_results
    all_valid = [(t, r) for t, r in all_results if r is not None]
    best_theta, best_result = max(all_valid, key=lambda x: x[1]["F1_expected_sim"])

    type_elapsed = time.time() - type_start

    print(f"\n  {'='*60}")
    print(f"  [{utype}] 최종 결과 (총 {type_elapsed/60:.1f}분)")
    print(f"  {'='*60}")
    print(f"    walkReluctance      = {best_theta['walkReluctance']:.2f}")
    print(f"    transferCostSeconds  = {best_theta['transferCostSeconds']}")
    print(f"    subwayReluctance    = {best_theta['subwayReluctance']:.2f}")
    print(f"    ─────────────────────────────────")
    print(f"    F₁ (기대 유사도)    = {best_result['F1_expected_sim']:.4f}")
    print(f"    F₂ (기대 완전일치)  = {best_result['F2_expected_exact']*100:.2f}%")
    print(f"    ─────────────────────────────────")
    print(f"    결정론적 exact      = {best_result['det_exact_match']*100:.2f}%")
    print(f"    MNL 1순위 exact     = {best_result['mnl_exact_match']*100:.2f}%")
    print(f"    RSM R²              = {rsm['r_squared']:.4f}")
    print(f"  {'='*60}")

    return {
        "optimal_theta": best_theta,
        "best_F1": best_result["F1_expected_sim"],
        "best_F2": best_result["F2_expected_exact"],
        "best_det_exact": best_result["det_exact_match"],
        "best_det_sim": best_result["det_sim_total"],
        "best_mnl_exact": best_result["mnl_exact_match"],
        "best_mnl_sim": best_result["mnl_sim_total"],
        "rsm_r_squared": rsm["r_squared"],
        "rsm_rmse": rsm["rmse"],
        "rsm_coefficients": dict(zip(rsm["coeff_names"], rsm["coefficients"])),
        "rsm_predicted_optimum": rsm["predicted_optimum"],
        "rsm_predicted_f1": rsm["predicted_f1"],
        "total_evaluations": len(all_valid),
        "elapsed_min": round(type_elapsed / 60, 1),
        "beta_source": beta_source,
        "phase1_top5": [
            {
                "theta": t,
                "F1": r["F1_expected_sim"],
                "F2": r["F2_expected_exact"],
                "det_exact": r["det_exact_match"],
                "mnl_exact": r["mnl_exact_match"],
            }
            for t, r in sorted(all_valid,
                                key=lambda x: x[1]["F1_expected_sim"],
                                reverse=True)[:5]
        ],
    }

# ============================================================
# 실행
# ============================================================

def run_optimization(target_types=None):
    """전체 또는 특정 유형 확률적 최적화"""
    print("\n" + "=" * 70)
    print("  접근법 E-IPW: 확률 기반 LHS + RSM 최적화 (IPW 보정)")
    print("  목적함수: F₁ = Σ w_ipw × P(j|MNL β) × sim(j) / Σ w_ipw")
    print("=" * 70)

    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_filtered.parquet")
    print(f"  전체 체인: {len(trip_attrs):,}")

    log_data = {
        "method": "Probabilistic LHS + RSM (Approach E-IPW)",
        "objective": "F1 = Σ w_ipw × P(j|MNL β) × sim(j) / Σ w_ipw (IPW-weighted)",
        "status": "running",
        "start_time": datetime.now().isoformat(),
        "settings": {
            "n_lhs_samples": N_LHS_SAMPLES,
            "sample_size": SAMPLE_SIZE,
            "param_bounds": {k: list(v) for k, v in PARAM_BOUNDS.items()},
            "mnl_betas": {k: v for k, v in MNL_BETAS.items()},
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

    total_start = time.time()

    for utype in types_to_run:
        df_type = trip_attrs[trip_attrs['user_type'] == utype]
        if len(df_type) == 0:
            print(f"\n  [{utype}] 데이터 없음, 건너뜀")
            continue

        n_sample = min(len(df_type), SAMPLE_SIZE)
        df_sample = stratified_sample(df_type, n_sample, seed=42)
        print(f"\n  [{utype}] 층화 샘플링 결과 (IPW 보정):")
        for nt in sorted(df_sample['n_transfers'].unique()):
            orig_n = (df_type['n_transfers'] == nt).sum()
            samp_n = (df_sample['n_transfers'] == nt).sum()
            ipw_val = df_sample.loc[df_sample['n_transfers'] == nt, 'ipw_weight'].iloc[0]
            print(f"    환승 {int(nt)}회: {samp_n:,}개 "
                  f"(원본 {orig_n:,}개, IPW={ipw_val:.3f})")

        result = optimize_type(utype, df_sample)
        if result:
            log_data["results"][utype] = {
                **result,
                "timestamp": datetime.now().isoformat(),
            }

        # 중간 저장
        with open(PROB_LOG, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)

    total_elapsed = time.time() - total_start

    # ── 결과 요약 ──
    print("\n" + "=" * 90)
    print("  확률적 최적화 결과 요약 (접근법 E-IPW)")
    print("=" * 90)

    header = (f"  {'유형':<10} │ {'F₁(E[sim])':>10} │ {'F₂(E[em])':>10}"
              f" │ {'det_exact':>10} │ {'mnl_exact':>10}"
              f" │ {'walkRel':>8} │ {'transCost':>10} │ {'subRel':>6}"
              f" │ {'R²':>6}")
    print(f"\n{header}")
    print(f"  {'─'*10}─┼─{'─'*10}─┼─{'─'*10}"
          f"─┼─{'─'*10}─┼─{'─'*10}"
          f"─┼─{'─'*8}─┼─{'─'*10}─┼─{'─'*6}"
          f"─┼─{'─'*6}")

    # 베이스라인 행
    baseline_det = {"GENERAL": 19.84, "ELDERLY": 19.84, "YOUTH": 27.83,
                    "CHILDREN": 31.30, "DISABLED": 23.60}

    for utype in types_to_run:
        if utype in log_data["results"]:
            r = log_data["results"][utype]
            opt = r["optimal_theta"]
            bl = baseline_det.get(utype, 20.34)
            det_diff = r["best_det_exact"] * 100 - bl
            print(f"  {utype:<10} │ {r['best_F1']:>10.4f} │ "
                  f"{r['best_F2']*100:>9.2f}%"
                  f" │ {r['best_det_exact']*100:>9.2f}%"
                  f" │ {r['best_mnl_exact']*100:>9.2f}%"
                  f" │ {opt['walkReluctance']:>8.2f}"
                  f" │ {opt['transferCostSeconds']:>10}"
                  f" │ {opt['subwayReluctance']:>6.2f}"
                  f" │ {r.get('rsm_r_squared', 0):>6.3f}")

    print(f"\n  총 소요 시간: {total_elapsed/60:.1f}분")

    # 코드용 최적 θ
    print(f"\n  [최적 θ - 코드용]")
    print(f"  OPTIMAL_THETA_E = {{")
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
    with open(PROB_LOG, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)

    # ── TXT 결과 저장 ──
    txt_file = RESULTS_DIR / "probabilistic_rsm_results.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("  접근법 E-IPW: 확률 기반 LHS + RSM 최적화 결과 (IPW 보정)\n")
        f.write(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  목적함수: F₁ = E[sim_total] = Σ P(j|MNL β) × sim(j)\n")
        f.write(f"  샘플 크기: {SAMPLE_SIZE:,} / LHS: {N_LHS_SAMPLES}개\n")
        f.write("=" * 80 + "\n\n")

        # 베이스라인
        f.write("[ 베이스라인 (전체 데이터, OTP 1순위 기준) ]\n")
        f.write("  전체: Exact=20.34%, GENERAL=19.84%, ELDERLY=19.84%\n")
        f.write("  YOUTH=27.83%, CHILDREN=31.30%, DISABLED=23.60%\n")
        f.write("  (MNL 1순위 기준: 전체 22.23%)\n\n")

        # 요약 테이블
        f.write(f"{'유형':<10} │ {'F₁(E[sim])':>10} │ {'F₂(E[em])':>10}"
                f" │ {'det_exact':>10} │ {'mnl_exact':>10}"
                f" │ {'walkRel':>8} │ {'transCost':>10} │ {'subRel':>6}"
                f" │ {'R²':>6}\n")
        f.write("─" * 100 + "\n")

        for utype in types_to_run:
            if utype in log_data["results"]:
                r = log_data["results"][utype]
                opt = r["optimal_theta"]
                f.write(f"{utype:<10} │ {r['best_F1']:>10.4f} │ "
                        f"{r['best_F2']*100:>9.2f}%"
                        f" │ {r['best_det_exact']*100:>9.2f}%"
                        f" │ {r['best_mnl_exact']*100:>9.2f}%"
                        f" │ {opt['walkReluctance']:>8.2f}"
                        f" │ {opt['transferCostSeconds']:>10}"
                        f" │ {opt['subwayReluctance']:>6.2f}"
                        f" │ {r.get('rsm_r_squared', 0):>6.3f}\n")

        f.write("\n")

        # 유형별 상세
        for utype in types_to_run:
            if utype not in log_data["results"]:
                continue
            r = log_data["results"][utype]
            f.write(f"\n{'='*70}\n")
            f.write(f"  [{utype}] 상세 결과 (β: {r.get('beta_source', 'pooled')})\n")
            f.write(f"{'='*70}\n")
            f.write(f"  최적 θ: walkRel={r['optimal_theta']['walkReluctance']:.2f}, "
                    f"transCost={r['optimal_theta']['transferCostSeconds']}, "
                    f"subwayRel={r['optimal_theta']['subwayReluctance']:.2f}\n")
            f.write(f"  F₁ (기대 유사도)   = {r['best_F1']:.4f}\n")
            f.write(f"  F₂ (기대 완전일치) = {r['best_F2']*100:.2f}%\n")
            f.write(f"  결정론적 exact     = {r['best_det_exact']*100:.2f}%\n")
            f.write(f"  MNL 1순위 exact    = {r['best_mnl_exact']*100:.2f}%\n")
            f.write(f"  RSM R²             = {r.get('rsm_r_squared', 0):.4f}\n")
            f.write(f"  평가 횟수          = {r.get('total_evaluations', 0)}개\n")
            f.write(f"  소요 시간          = {r.get('elapsed_min', 0):.1f}분\n")

            if "phase1_top5" in r:
                f.write(f"\n  Top 5 (F₁ 기준):\n")
                for rank, item in enumerate(r["phase1_top5"][:5], 1):
                    t = item["theta"]
                    f.write(f"    #{rank} w={t['walkReluctance']:6.2f} "
                            f"t={t['transferCostSeconds']:3d} "
                            f"s={t['subwayReluctance']:.2f} "
                            f"→ F₁={item['F1']:.4f} "
                            f"F₂={item['F2']*100:.1f}% "
                            f"det={item['det_exact']*100:.1f}% "
                            f"mnl={item['mnl_exact']*100:.1f}%\n")

        f.write(f"\n\n총 소요 시간: {total_elapsed/60:.1f}분\n")

    print(f"\n  결과 저장:")
    print(f"    JSON: {PROB_LOG}")
    print(f"    TXT:  {txt_file}")
    print("\n  완료!")


def main():
    parser = argparse.ArgumentParser(
        description="접근법 E: 확률 기반 LHS + RSM 최적화")
    parser.add_argument("--run", action="store_true", help="전체 유형 최적화")
    parser.add_argument("--type", type=str, nargs="+",
                        help="특정 유형 (예: --type GENERAL)")
    args = parser.parse_args()

    if args.run:
        run_optimization()
    elif args.type:
        run_optimization(target_types=args.type)
    else:
        print("\n접근법 E-IPW: 확률 기반 LHS + RSM 최적화 (IPW 보정)")
        print("─" * 50)
        print("목적함수: F₁ = Σ w_ipw × P(j|MNL β) × sim(j) / Σ w_ipw")
        print()
        print("사용법:")
        print("  python probabilistic_rsm_calibration.py --run           # 전체 유형")
        print("  python probabilistic_rsm_calibration.py --type GENERAL  # 특정 유형")
        print(f"\n설정:")
        print(f"  샘플 크기: {SAMPLE_SIZE:,}")
        print(f"  LHS 탐색: {N_LHS_SAMPLES}개")
        print(f"  파라미터 범위:")
        for name, (low, high) in PARAM_BOUNDS.items():
            print(f"    {name}: [{low}, {high}]")
        print(f"\nMNL β 계수:")
        for utype, betas in MNL_BETAS.items():
            print(f"  {utype}: T_ride={betas['T_ride']:.4f}, "
                  f"T_walk={betas['T_walk']:.4f}, "
                  f"N_transfer={betas['N_transfer']:.4f}, "
                  f"D_subway={betas['D_subway']:.4f}")


if __name__ == "__main__":
    main()
