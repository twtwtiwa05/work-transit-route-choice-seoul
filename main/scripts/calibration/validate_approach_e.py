#!/usr/bin/env python3
"""
Phase 4 접근법 E: 전체 데이터 검증

접근법 E에서 찾은 유형별 최적 θ*를 모집단 비례 샘플(층화 없음)에 적용하여
베이스라인(20.34%)과 직접 비교 가능한 수치를 산출.

핵심 차이점 (vs probabilistic_rsm_calibration.py):
  - 층화 추출 없음 → 모집단과 동일한 환승 비율 유지
  - 유형당 10,000개 랜덤 샘플 → 직접 비교 가능
  - 유형별 가중 평균 → 전체 모집단 추정치

사용법:
    cd main
    python scripts/calibration/validate_approach_e.py
"""

import json
import subprocess
import sys
import os
import time
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

# ============================================================
# 접근법 E 최적 θ* (probabilistic_rsm_results.txt 기반)
# ============================================================
OPTIMAL_THETAS = {
    "GENERAL":  {"walkReluctance": 28.58, "transferCostSeconds": 216, "subwayReluctance": 1.81},
    "CHILDREN": {"walkReluctance": 30.00, "transferCostSeconds": 91,  "subwayReluctance": 2.00},
    "YOUTH":    {"walkReluctance": 27.17, "transferCostSeconds": 32,  "subwayReluctance": 1.61},
    "ELDERLY":  {"walkReluctance": 30.00, "transferCostSeconds": 71,  "subwayReluctance": 2.00},
    "DISABLED": {"walkReluctance": 27.17, "transferCostSeconds": 32,  "subwayReluctance": 1.61},
}

# MNL β 계수 (Phase 3)
MNL_BETAS = {
    "pooled": {
        "T_ride": -0.07498770610598887, "T_walk": -0.6441589132495491,
        "N_transfer": -3.051072746767041, "D_subway": 2.5379894848151454,
    },
    "GENERAL": {
        "T_ride": -0.07847618693371328, "T_walk": -0.6283492422815684,
        "N_transfer": -2.9662034150581422, "D_subway": 2.3622194545159676,
    },
    "YOUTH": {
        "T_ride": -0.11452109982658194, "T_walk": -0.7469108516609095,
        "N_transfer": -3.295156986515721, "D_subway": 2.238237605781155,
    },
    "ELDERLY": {
        "T_ride": -0.03202585311224609, "T_walk": -0.7233903787410852,
        "N_transfer": -3.996075762065534, "D_subway": 4.551235043260515,
    },
}

SAMPLE_PER_TYPE = 10000

# 베이스라인 (전체 데이터, 디폴트 θ)
BASELINE = {
    "overall_det": 20.34,
    "overall_mnl": 22.23,
    "per_type_det": {
        "GENERAL": 19.84, "YOUTH": 27.83, "CHILDREN": 31.30,
        "ELDERLY": 19.84, "DISABLED": 23.60,
    },
}


def get_betas(utype):
    return MNL_BETAS.get(utype, MNL_BETAS["pooled"])


def save_config(theta):
    config = {
        "walkReluctance": float(theta["walkReluctance"]),
        "transferCostSeconds": int(theta["transferCostSeconds"]),
        "subwayReluctance": float(theta.get("subwayReluctance", 1.0)),
        "firstBoardCostSeconds": 60,
        "waitReluctance": 1.0,
        "searchWindowSeconds": 1800,
    }
    with open(CALIBRATION_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def prepare_od_and_attrs(utype, df_sample):
    """
    샘플 체인에서 OD CSV + trip_attributes_subsample 생성

    Returns: od_file path
    """
    df = df_sample.copy().reset_index(drop=True)
    df["od_id"] = df.index

    # trip_attributes_subsample.parquet 저장 (step4에서 참조)
    subsample_file = OUTPUT_DIR / "trip_attributes_subsample.parquet"
    df.to_parquet(subsample_file, index=False)

    # OD CSV 생성
    od_df = df[['origin_lat', 'origin_lon', 'dest_lat', 'dest_lon', 'board_time']].copy()
    od_df.columns = ['from_lat', 'from_lon', 'to_lat', 'to_lon', 'departure_time']
    od_df['departure_time'] = od_df['departure_time'].apply(
        lambda x: f"{int(x) // 3600:02d}:{(int(x) % 3600) // 60:02d}"
    )

    od_file = OTP_DIR / "data" / f"od_validate_{utype.lower()}.csv"
    od_df.to_csv(od_file, index=False)
    print(f"    OD CSV: {od_file.name} ({len(od_df):,}개)")
    return od_file


def run_otp_batch(utype, od_file, theta):
    """OTP multi-batch 실행 (RSM과 동일 방식, 단일 config)"""
    jar_file = OTP_DIR / "build" / "libs" / "korean-raptor-1.0.0-SNAPSHOT-all.jar"
    java_exe = "C:\\Program Files\\Java\\jdk-21\\bin\\java.exe"

    if not jar_file.exists():
        print(f"    [ERROR] JAR 없음: {jar_file}")
        return None

    # config 파일 + manifest 생성 (multi-batch 방식)
    config_dir = OTP_DIR / "calibration_configs"
    config_dir.mkdir(exist_ok=True)

    config_path = config_dir / f"validate_{utype.lower()}.json"
    config_data = {
        "walkReluctance": float(theta["walkReluctance"]),
        "transferCostSeconds": int(theta["transferCostSeconds"]),
        "subwayReluctance": float(theta.get("subwayReluctance", 1.0)),
        "firstBoardCostSeconds": 60,
        "waitReluctance": 1.0,
        "searchWindowSeconds": 1800,
    }
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2)

    result_file = OTP_DIR / f"batch_validate_{utype.lower()}.ndjson"
    if result_file.exists():
        result_file.unlink()
    progress_file = Path(str(result_file) + ".progress")
    if progress_file.exists():
        progress_file.unlink()

    # manifest: config_path,result_path
    manifest_file = config_dir / f"manifest_validate_{utype.lower()}.txt"
    manifest_file.write_text(f"{config_path},{result_file}", encoding='utf-8')

    # calibration_config.json도 설정 (초기 로드용)
    save_config(theta)

    cmd = [java_exe, "-Xmx40G", "-XX:+UseG1GC", "-jar", str(jar_file),
           "multi-batch", str(od_file), str(manifest_file), "16"]

    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Java\\jdk-21"
    env["PATH"] = f"{env['JAVA_HOME']}\\bin;{env.get('PATH', '')}"

    log_file = OTP_DIR / f"validate_{utype.lower()}.log"

    print(f"    OTP multi-batch 시작 (10K OD)...")
    start = time.time()

    with open(log_file, 'w', encoding='utf-8') as log_fh:
        proc = subprocess.Popen(cmd, cwd=str(OTP_DIR), env=env,
                                stdout=log_fh, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=1800)  # 30분 (GTFS 로드 + 10K OD 충분)
        except subprocess.TimeoutExpired:
            print(f"    [TIMEOUT] 1800초 초과 → kill")
            proc.kill()
            proc.wait(timeout=10)
            return None

    elapsed = time.time() - start
    print(f"    OTP 완료: {elapsed:.1f}초")
    return result_file


def run_step4_step5(result_file):
    """step4(파싱) + step5(유사도) 실행"""
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
            stderr = result.stderr.decode('utf-8', errors='replace')[:500]
            print(f"    [ERR] {script.name}: {stderr}")
            return False
    return True


def evaluate_results(utype, df_sample):
    """step4+step5 결과를 로드하고 확률적+결정론적 평가"""
    sim_file = OUTPUT_DIR / "similarity_results.parquet"
    otp_file = OUTPUT_DIR / "otp_alternatives.parquet"
    if not sim_file.exists() or not otp_file.exists():
        return None

    sim_df = pd.read_parquet(sim_file)
    otp_df = pd.read_parquet(otp_file)

    if len(sim_df) == 0:
        return None

    # ── MNL 확률 계산 ──
    betas = get_betas(utype)
    merged = sim_df.merge(
        otp_df[['od_id', 'alt_id', 'ride_time_sec', 'walk_time_sec',
                'n_transfers', 'has_subway']],
        on=['od_id', 'alt_id'], how='left'
    ).dropna(subset=['ride_time_sec'])

    merged['V'] = (
        betas["T_ride"] * (merged["ride_time_sec"] / 60.0)
        + betas["T_walk"] * (merged["walk_time_sec"] / 60.0)
        + betas["N_transfer"] * merged["n_transfers"]
        + betas["D_subway"] * merged["has_subway"]
    )

    merged['V_max'] = merged.groupby('chain_id')['V'].transform('max')
    merged['exp_V'] = np.exp(merged['V'] - merged['V_max'])
    merged['sum_exp_V'] = merged.groupby('chain_id')['exp_V'].transform('sum')
    merged['P_mnl'] = merged['exp_V'] / merged['sum_exp_V']
    merged['P_sim'] = merged['P_mnl'] * merged['sim_total']
    merged['P_exact'] = merged['P_mnl'] * merged['exact_match']

    # ── F₁, F₂ ──
    chain_F1 = merged.groupby('chain_id')['P_sim'].sum()
    chain_F2 = merged.groupby('chain_id')['P_exact'].sum()
    F1 = chain_F1.mean()
    F2 = chain_F2.mean()

    # ── 결정론적: OTP 1순위 (generalized_cost 최소) ──
    det_best = sim_df.loc[sim_df.groupby('chain_id')['otp_generalized_cost'].idxmin()]
    det_exact = det_best['exact_match'].mean()
    det_sim = det_best['sim_total'].mean()

    # ── MNL 1순위 (V 최대) ──
    mnl_best = merged.loc[merged.groupby('chain_id')['V'].idxmax()]
    mnl_exact = mnl_best['exact_match'].mean()
    mnl_sim = mnl_best['sim_total'].mean()

    n_chains = sim_df['chain_id'].nunique()

    # ── 환승별 세부 (OTP 1순위 기준) ──
    subsample_df = pd.read_parquet(OUTPUT_DIR / "trip_attributes_subsample.parquet",
                                   columns=['chain_id', 'n_transfers'])
    det_chain = det_best[['chain_id', 'exact_match', 'sim_total']].merge(
        subsample_df, on='chain_id', how='left')

    stratum = {}
    for nt in [0, 1]:
        mask = det_chain['n_transfers'] == nt
        if mask.sum() > 0:
            stratum[f"det_exact_{nt}t"] = float(det_chain.loc[mask, 'exact_match'].mean())
            stratum[f"det_sim_{nt}t"] = float(det_chain.loc[mask, 'sim_total'].mean())
            stratum[f"count_{nt}t"] = int(mask.sum())
    mask_2p = det_chain['n_transfers'] >= 2
    if mask_2p.sum() > 0:
        stratum["det_exact_2t"] = float(det_chain.loc[mask_2p, 'exact_match'].mean())
        stratum["count_2t"] = int(mask_2p.sum())

    return {
        "F1": float(F1), "F2": float(F2),
        "det_exact": float(det_exact), "det_sim": float(det_sim),
        "mnl_exact": float(mnl_exact), "mnl_sim": float(mnl_sim),
        "n_chains": n_chains,
        "n_sample_input": len(df_sample),
        **stratum,
    }


def main():
    print("=" * 70)
    print("  접근법 E: 전체 데이터 검증 (모집단 비례, 층화 없음)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  유형당 최대 {SAMPLE_PER_TYPE:,}개 체인 (랜덤, 층화 없음)")
    print("=" * 70)

    # ── 데이터 로드 ──
    ta_file = OUTPUT_DIR / "trip_attributes_filtered.parquet"
    print(f"\ntrip_attributes_filtered 로드...")
    df_all = pd.read_parquet(ta_file)
    print(f"  전체: {len(df_all):,}개 체인")

    # 유형별 분포
    type_counts = df_all['user_type'].value_counts()
    type_weights = {}
    print(f"\n유형별 분포 (모집단):")
    for ut, cnt in type_counts.items():
        pct = cnt / len(df_all) * 100
        type_weights[ut.upper()] = cnt / len(df_all)
        print(f"  {ut}: {cnt:,} ({pct:.1f}%)")

    # ── 유형별 실행 ──
    all_results = {}
    total_start = time.time()

    for utype in ["GENERAL", "CHILDREN", "YOUTH", "ELDERLY", "DISABLED"]:
        print(f"\n{'=' * 60}")
        print(f"  [{utype}]")
        print(f"{'=' * 60}")

        theta = OPTIMAL_THETAS[utype]
        print(f"  θ*: w={theta['walkReluctance']:.2f}, "
              f"t={theta['transferCostSeconds']}, "
              f"s={theta['subwayReluctance']:.2f}")

        # 1. 모집단 비례 랜덤 샘플 (층화 없음!)
        df_type = df_all[df_all['user_type'] == utype].copy()
        n_sample = min(SAMPLE_PER_TYPE, len(df_type))
        df_sample = df_type.sample(n=n_sample, random_state=42)

        trans_dist = df_sample['n_transfers'].value_counts().sort_index()
        print(f"  샘플: {n_sample:,} / {len(df_type):,}")
        print(f"  환승 분포: {dict(trans_dist)}")

        # 2. OD 준비
        od_file = prepare_od_and_attrs(utype, df_sample)

        # 3. OTP 실행 (multi-batch 모드, config 자동 설정)
        result_file = run_otp_batch(utype, od_file, theta)
        if result_file is None or not result_file.exists():
            print(f"  [FAIL] OTP 실패")
            continue

        # 5. step4 + step5
        print(f"    step4+step5 실행...")
        s45_start = time.time()
        ok = run_step4_step5(result_file)
        if not ok:
            print(f"  [FAIL] step4/step5 실패")
            continue
        print(f"    step4+step5 완료: {time.time() - s45_start:.1f}초")

        # 6. 평가
        result = evaluate_results(utype, df_sample)
        if result is None:
            print(f"  [FAIL] 평가 실패")
            continue

        all_results[utype] = result
        bl = BASELINE["per_type_det"].get(utype, 0)
        delta = result['det_exact'] * 100 - bl

        print(f"\n  ── {utype} 결과 ──")
        print(f"  det_exact (OTP 1순위):  {result['det_exact']*100:.2f}%"
              f"  (베이스라인: {bl:.2f}%, Δ={delta:+.2f}%p)")
        print(f"  mnl_exact (MNL 1순위):  {result['mnl_exact']*100:.2f}%")
        print(f"  F₁ (기대 유사도):       {result['F1']:.4f}")
        print(f"  F₂ (기대 완전일치):     {result['F2']*100:.2f}%")
        print(f"  매칭 체인:              {result['n_chains']:,} / {n_sample:,}")
        for nt in [0, 1]:
            key = f"det_exact_{nt}t"
            cnt_key = f"count_{nt}t"
            if key in result:
                print(f"  환승{nt}회: {result[key]*100:.2f}% ({result[cnt_key]:,}개)")
        if "det_exact_2t" in result:
            print(f"  환승2회+: {result['det_exact_2t']*100:.2f}% ({result['count_2t']:,}개)")

    # ============================================================
    # 종합 비교
    # ============================================================
    total_elapsed = (time.time() - total_start) / 60

    print(f"\n\n{'=' * 70}")
    print(f"  종합 비교: 접근법 E θ* vs 베이스라인")
    print(f"  (모집단 비례 샘플 → 전체 데이터 추정치)")
    print(f"{'=' * 70}")

    # 베이스라인 출력
    print(f"\n[ 베이스라인 (전체 1.32M, 디폴트 θ) ]")
    print(f"  OTP 1순위: {BASELINE['overall_det']:.2f}%")
    print(f"  MNL 1순위: {BASELINE['overall_mnl']:.2f}%")

    # 유형별 비교 테이블
    print(f"\n{'유형':<12} {'베이스라인':>10} {'det_exact':>10} {'Δdet':>8} "
          f"{'mnl_exact':>10} {'F₁':>8} {'체인':>8}")
    print("─" * 70)

    weighted_det = 0
    weighted_mnl = 0
    weighted_f1 = 0
    total_weight = 0

    for utype in ["GENERAL", "CHILDREN", "YOUTH", "ELDERLY", "DISABLED"]:
        if utype not in all_results:
            continue

        r = all_results[utype]
        w = type_weights.get(utype, 0)
        bl = BASELINE["per_type_det"].get(utype, 0)
        delta = r['det_exact'] * 100 - bl

        print(f"{utype:<12} {bl:>9.2f}% {r['det_exact']*100:>9.2f}% {delta:>+7.2f}p "
              f"{r['mnl_exact']*100:>9.2f}% {r['F1']:>7.4f} {r['n_chains']:>7,}")

        weighted_det += w * r['det_exact']
        weighted_mnl += w * r['mnl_exact']
        weighted_f1 += w * r['F1']
        total_weight += w

    if total_weight > 0:
        weighted_det /= total_weight
        weighted_mnl /= total_weight
        weighted_f1 /= total_weight

    print("─" * 70)
    det_delta = weighted_det * 100 - BASELINE['overall_det']
    mnl_delta = weighted_mnl * 100 - BASELINE['overall_mnl']
    print(f"{'가중평균':<12} {BASELINE['overall_det']:>9.2f}% "
          f"{weighted_det*100:>9.2f}% {det_delta:>+7.2f}p "
          f"{weighted_mnl*100:>9.2f}% {weighted_f1:>7.4f}")

    print(f"\n  ▸ OTP 1순위 개선: {BASELINE['overall_det']:.2f}% → "
          f"{weighted_det*100:.2f}% ({det_delta:+.2f}%p)")
    print(f"  ▸ MNL 1순위 개선: {BASELINE['overall_mnl']:.2f}% → "
          f"{weighted_mnl*100:.2f}% ({mnl_delta:+.2f}%p)")

    print(f"\n총 소요 시간: {total_elapsed:.1f}분")

    # ── 결과 저장 ──
    save_data = {
        "method": "Approach E Full Validation (population-representative)",
        "timestamp": datetime.now().isoformat(),
        "sample_per_type": SAMPLE_PER_TYPE,
        "stratified": False,
        "baseline": BASELINE,
        "optimal_thetas": OPTIMAL_THETAS,
        "type_weights": {k: float(v) for k, v in type_weights.items()},
        "results": all_results,
        "summary": {
            "weighted_det_exact": float(weighted_det),
            "weighted_mnl_exact": float(weighted_mnl),
            "weighted_F1": float(weighted_f1),
            "det_delta_pp": float(det_delta),
            "mnl_delta_pp": float(mnl_delta),
        },
        "total_elapsed_min": total_elapsed,
    }

    save_path = RESULTS_DIR / "approach_e_validation.json"
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\n결과 저장: {save_path}")

    # 텍스트 결과도 저장
    txt_path = RESULTS_DIR / "approach_e_validation.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("  접근법 E 전체 데이터 검증 결과\n")
        f.write(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  유형당 샘플: {SAMPLE_PER_TYPE:,} (모집단 비례, 층화 없음)\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"{'유형':<12} {'베이스라인':>10} {'θ* det':>10} {'Δdet':>8} "
                f"{'θ* mnl':>10} {'θ* (w,t,s)':>20}\n")
        f.write("─" * 72 + "\n")

        for utype in ["GENERAL", "CHILDREN", "YOUTH", "ELDERLY", "DISABLED"]:
            if utype not in all_results:
                continue
            r = all_results[utype]
            bl = BASELINE["per_type_det"].get(utype, 0)
            delta = r['det_exact'] * 100 - bl
            th = OPTIMAL_THETAS[utype]
            theta_str = f"({th['walkReluctance']:.1f},{th['transferCostSeconds']},{th['subwayReluctance']:.1f})"
            f.write(f"{utype:<12} {bl:>9.2f}% {r['det_exact']*100:>9.2f}% "
                    f"{delta:>+7.2f}p {r['mnl_exact']*100:>9.2f}% {theta_str:>20}\n")

        f.write("─" * 72 + "\n")
        f.write(f"{'가중평균':<12} {BASELINE['overall_det']:>9.2f}% "
                f"{weighted_det*100:>9.2f}% {det_delta:>+7.2f}p "
                f"{weighted_mnl*100:>9.2f}%\n")
        f.write(f"\n  OTP 1순위: {BASELINE['overall_det']:.2f}% → "
                f"{weighted_det*100:.2f}% ({det_delta:+.2f}%p)\n")
        f.write(f"  MNL 1순위: {BASELINE['overall_mnl']:.2f}% → "
                f"{weighted_mnl*100:.2f}% ({mnl_delta:+.2f}%p)\n")
        f.write(f"\n총 소요 시간: {total_elapsed:.1f}분\n")

    print(f"텍스트 결과: {txt_path}")


if __name__ == "__main__":
    main()
