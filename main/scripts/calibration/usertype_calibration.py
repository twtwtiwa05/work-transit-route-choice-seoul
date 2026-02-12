#!/usr/bin/env python3
"""
Phase 4: 이용자 유형별 θ 적용 OTP 실행

각 유형별로 다른 θ를 적용하여 맞춤 경로 생성

유형별 θ (Pooled 기준 비율 적용):
  GENERAL:  (4.07, 202)
  ELDERLY:  (1.75, 109)
  YOUTH:    (2.71, 139)
  DISABLED: (7.28, 358)
  CHILDREN: (2.97, 145)

사용법:
    python usertype_calibration.py --plan      # 계획 확인
    python usertype_calibration.py --run       # 서브샘플 실행 (~25분)
    python usertype_calibration.py --full      # 전체 데이터 실행 (~8시간)
    python usertype_calibration.py --status    # 현재 상태
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
USERTYPE_LOG = RESULTS_DIR / "usertype_calibration_log.json"

# ============================================================
# 유형별 θ 설정
# ============================================================

# Pooled 기준값 (Choice Set 고정 보정 결과)
POOLED_THETA = {
    "walkReluctance": 5.47,
    "transferCostSeconds": 276,
}

# Pooled 가중치 (MNL 결과)
POOLED_WEIGHTS = {
    "walk_weight": 22.72,
    "transfer_minutes": 100.0,
}

# 유형별 가중치 (MNL 결과 - PHASE3_RESULTS1_MNL.md)
USERTYPE_WEIGHTS = {
    "GENERAL": {"walk_weight": 16.92, "transfer_minutes": 73.3},
    "CHILDREN": {"walk_weight": 12.33, "transfer_minutes": 52.6},
    "YOUTH": {"walk_weight": 11.24, "transfer_minutes": 50.3},
    "ELDERLY": {"walk_weight": 7.25, "transfer_minutes": 39.6},
    "DISABLED": {"walk_weight": 30.25, "transfer_minutes": 129.6},
}

# 유형별 서브샘플 크기
SAMPLE_SIZE_PER_TYPE = {
    "GENERAL": 20000,
    "ELDERLY": 10000,
    "YOUTH": 5000,
    "DISABLED": 5000,
    "CHILDREN": 5000,
}

def calculate_usertype_theta():
    """유형별 θ 계산 (Pooled 기준 비율 적용)"""
    result = {}
    for utype, weights in USERTYPE_WEIGHTS.items():
        walk_ratio = weights["walk_weight"] / POOLED_WEIGHTS["walk_weight"]
        trans_ratio = weights["transfer_minutes"] / POOLED_WEIGHTS["transfer_minutes"]
        result[utype] = {
            "walkReluctance": round(POOLED_THETA["walkReluctance"] * walk_ratio, 2),
            "transferCostSeconds": round(POOLED_THETA["transferCostSeconds"] * trans_ratio, 0),
        }
    return result

USERTYPE_THETA = calculate_usertype_theta()

# ============================================================
# 유틸리티 함수
# ============================================================

def load_log():
    if USERTYPE_LOG.exists():
        with open(USERTYPE_LOG, encoding='utf-8') as f:
            return json.load(f)
    return {"status": "not_started", "results_by_type": {}, "overall": None}

def save_log(log_data):
    log_data["last_update"] = datetime.now().isoformat()
    with open(USERTYPE_LOG, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

def save_config(theta):
    """OTP calibration_config.json 저장"""
    config = {
        "walkReluctance": float(theta["walkReluctance"]),
        "transferCostSeconds": int(theta["transferCostSeconds"]),
        "firstBoardCostSeconds": 60,
        "waitReluctance": 1.0,
        "searchWindowSeconds": 1800,
    }
    with open(CALIBRATION_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

# ============================================================
# 단일 유형 처리
# ============================================================

def process_single_type(utype, theta, trip_attrs_type, is_subsample=True):
    """
    단일 유형에 대해 OTP 실행 + 파이프라인 + 유사도 계산

    1. 해당 유형 체인만 trip_attributes_subsample.parquet로 저장
    2. od_id를 0부터 재매핑
    3. OD CSV 생성
    4. θ 설정 + OTP 실행
    5. step4 + step5 실행
    6. 유사도 결과 반환
    """
    print(f"\n  [{utype}] θ = ({theta['walkReluctance']:.2f}, {theta['transferCostSeconds']:.0f})")
    print(f"    체인 수: {len(trip_attrs_type):,}")

    # 1. od_id 재매핑 (0부터)
    df = trip_attrs_type.copy().reset_index(drop=True)
    df["od_id"] = df.index

    # 2. trip_attributes_subsample.parquet 저장 (덮어쓰기)
    subsample_file = OUTPUT_DIR / "trip_attributes_subsample.parquet"
    df.to_parquet(subsample_file, index=False)

    # 3. OD CSV 생성
    od_df = df[['origin_lat', 'origin_lon', 'dest_lat', 'dest_lon', 'board_time']].copy()
    od_df.columns = ['from_lat', 'from_lon', 'to_lat', 'to_lon', 'departure_time']
    # board_time은 초 단위 정수 (0~86399) → HH:MM 변환
    od_df['departure_time'] = od_df['departure_time'].apply(
        lambda x: f"{int(x) // 3600:02d}:{(int(x) % 3600) // 60:02d}"
    )

    od_file = OTP_DIR / "data" / f"od_{utype.lower()}.csv"
    od_df.to_csv(od_file, index=False)

    # 4. θ 설정
    save_config(theta)

    # 5. OTP 실행
    result_file = OTP_DIR / f"batch_{utype.lower()}.ndjson"
    jar_file = OTP_DIR / "build" / "libs" / "korean-raptor-1.0.0-SNAPSHOT-all.jar"

    if not jar_file.exists():
        print(f"    [ERROR] JAR 없음: {jar_file}")
        return None

    java_exe = "C:\\Program Files\\Java\\jdk-21\\bin\\java.exe"
    cmd = [java_exe, "-Xmx40G", "-XX:+UseG1GC", "-jar", str(jar_file),
           "batch", str(od_file), str(result_file), "16"]

    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Java\\jdk-21"
    env["PATH"] = f"{env['JAVA_HOME']}\\bin;{env.get('PATH', '')}"

    # 기존 결과 파일 삭제
    if result_file.exists():
        result_file.unlink()

    print(f"    OTP 실행 중...")
    start = time.time()

    # Popen으로 실행하고 결과 파일 모니터링
    proc = subprocess.Popen(cmd, cwd=str(OTP_DIR), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 결과 파일이 생성되고 더 이상 크기가 증가하지 않으면 완료
    last_size = 0
    stable_count = 0
    while True:
        time.sleep(5)
        if result_file.exists():
            current_size = result_file.stat().st_size
            if current_size > 0 and current_size == last_size:
                stable_count += 1
                if stable_count >= 3:  # 15초 동안 크기 변화 없으면 완료
                    break
            else:
                stable_count = 0
            last_size = current_size

        # 프로세스가 이미 종료된 경우
        if proc.poll() is not None:
            break

        # 타임아웃 (30분)
        if time.time() - start > 1800:
            print(f"    [WARN] 타임아웃, 프로세스 종료")
            proc.kill()
            break

    # 프로세스 정리
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except:
            proc.kill()

    otp_elapsed = time.time() - start

    if not result_file.exists() or result_file.stat().st_size < 1024:
        print(f"    [FAIL] OTP 실패")
        return None

    file_size = result_file.stat().st_size / (1024 * 1024)
    print(f"    OTP 완료: {otp_elapsed/60:.1f}분, {file_size:.1f}MB")

    # 6. step4 + step5 실행
    env["PYTHONIOENCODING"] = "utf-8"
    env["OTP_NDJSON_PATH"] = str(result_file)
    env["SUBSAMPLE_MODE"] = "1"
    env["ITERATION"] = "0"

    for name, script in [
        ("파싱", SCRIPTS_DIR / "matching" / "step4_parse_otp_results.py"),
        ("유사도", SCRIPTS_DIR / "matching" / "step5_calculate_similarity.py"),
    ]:
        print(f"    {name}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            cwd=str(ROOT),
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"[FAIL]")
            return None
        print("[OK]")

    # 7. 유사도 결과 수집
    sim_file = OUTPUT_DIR / "similarity_results.parquet"
    if not sim_file.exists():
        return None

    sim_df = pd.read_parquet(sim_file)
    best = sim_df.loc[sim_df.groupby('chain_id')['sim_total'].idxmax()]

    avg_alts = len(sim_df) / sim_df['chain_id'].nunique() if sim_df['chain_id'].nunique() > 0 else 0

    metrics = {
        "exact_match": round(float(best['exact_match'].mean()) * 100, 2),
        "sim_total": round(float(best['sim_total'].mean()), 4),
        "n_chains": int(len(best)),
        "avg_alts": round(avg_alts, 2),
        "otp_elapsed_min": round(otp_elapsed / 60, 1),
    }

    print(f"    결과: Exact={metrics['exact_match']:.1f}%, sim={metrics['sim_total']:.4f}, Alts={metrics['avg_alts']:.1f}")

    return metrics

# ============================================================
# 메인 실행 함수
# ============================================================

def run_subsample():
    """서브샘플로 유형별 θ 적용 테스트"""
    print("\n" + "=" * 60)
    print("  유형별 θ 적용 (서브샘플)")
    print("=" * 60)

    # 데이터 로드
    print("\n  데이터 로드 중...")
    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_filtered.parquet")
    print(f"  전체 체인: {len(trip_attrs):,}")

    log_data = load_log()
    log_data["status"] = "running"
    log_data["start_time"] = datetime.now().isoformat()
    save_log(log_data)

    # 유형별 θ 표시
    print("\n  유형별 θ:")
    print(f"  {'유형':<10} | {'walkRel':>8} | {'transCost':>10} | {'샘플수':>8}")
    print(f"  {'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*8}")
    for utype, theta in USERTYPE_THETA.items():
        n_sample = SAMPLE_SIZE_PER_TYPE.get(utype, 0)
        print(f"  {utype:<10} | {theta['walkReluctance']:>8.2f} | {theta['transferCostSeconds']:>10.0f} | {n_sample:>8,}")

    total_start = time.time()
    results_by_type = {}

    # 유형별 처리
    for utype, theta in USERTYPE_THETA.items():
        # 해당 유형 필터링
        df_type = trip_attrs[trip_attrs['user_type'] == utype]

        if len(df_type) == 0:
            print(f"\n  [{utype}] 데이터 없음, 건너뜀")
            continue

        # 서브샘플 추출
        n_sample = min(len(df_type), SAMPLE_SIZE_PER_TYPE.get(utype, 5000))
        df_sample = df_type.sample(n=n_sample, random_state=42)

        # 처리
        metrics = process_single_type(utype, theta, df_sample, is_subsample=True)

        if metrics:
            results_by_type[utype] = {
                "theta": theta,
                "metrics": metrics,
            }

            # 중간 저장
            log_data["results_by_type"] = results_by_type
            save_log(log_data)

    total_elapsed = time.time() - total_start

    # 전체 통계 계산
    if results_by_type:
        total_chains = sum(r["metrics"]["n_chains"] for r in results_by_type.values())
        weighted_exact = sum(r["metrics"]["exact_match"] * r["metrics"]["n_chains"] for r in results_by_type.values())
        weighted_sim = sum(r["metrics"]["sim_total"] * r["metrics"]["n_chains"] for r in results_by_type.values())

        overall = {
            "exact_match": round(weighted_exact / total_chains, 2) if total_chains > 0 else 0,
            "sim_total": round(weighted_sim / total_chains, 4) if total_chains > 0 else 0,
            "n_chains": total_chains,
            "elapsed_min": round(total_elapsed / 60, 1),
        }

        log_data["overall"] = overall

    log_data["status"] = "completed"
    log_data["end_time"] = datetime.now().isoformat()
    save_log(log_data)

    # 결과 출력
    print("\n" + "=" * 60)
    print("  결과 요약")
    print("=" * 60)

    print(f"\n  {'유형':<10} | {'Exact%':>8} | {'sim_total':>10} | {'Alts':>6} | {'체인수':>8}")
    print(f"  {'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*6}-+-{'-'*8}")

    for utype, result in results_by_type.items():
        m = result["metrics"]
        print(f"  {utype:<10} | {m['exact_match']:>8.1f} | {m['sim_total']:>10.4f} | {m['avg_alts']:>6.1f} | {m['n_chains']:>8,}")

    if log_data.get("overall"):
        o = log_data["overall"]
        print(f"  {'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*6}-+-{'-'*8}")
        print(f"  {'전체':<10} | {o['exact_match']:>8.1f} | {o['sim_total']:>10.4f} | {'-':>6} | {o['n_chains']:>8,}")

    print(f"\n  총 소요 시간: {total_elapsed/60:.1f}분")
    print("\n  완료!")

def run_full():
    """전체 데이터로 유형별 θ 적용"""
    print("\n" + "=" * 60)
    print("  유형별 θ 적용 (전체 데이터)")
    print("=" * 60)

    # 데이터 로드
    print("\n  데이터 로드 중...")
    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_filtered.parquet")
    print(f"  전체 체인: {len(trip_attrs):,}")

    log_data = load_log()

    # 유형별 θ 표시
    print("\n  유형별 θ:")
    for utype, theta in USERTYPE_THETA.items():
        n_chains = len(trip_attrs[trip_attrs['user_type'] == utype])
        print(f"    {utype}: θ=({theta['walkReluctance']:.2f}, {theta['transferCostSeconds']:.0f}), 체인={n_chains:,}")

    print("\n  예상 소요 시간: ~8시간")
    print("  (유형별로 순차 실행)")

    total_start = time.time()
    full_results = {}

    for utype, theta in USERTYPE_THETA.items():
        df_type = trip_attrs[trip_attrs['user_type'] == utype]

        if len(df_type) == 0:
            continue

        metrics = process_single_type(utype, theta, df_type, is_subsample=False)

        if metrics:
            full_results[utype] = {
                "theta": theta,
                "metrics": metrics,
            }

    total_elapsed = time.time() - total_start

    # 전체 통계
    if full_results:
        total_chains = sum(r["metrics"]["n_chains"] for r in full_results.values())
        weighted_exact = sum(r["metrics"]["exact_match"] * r["metrics"]["n_chains"] for r in full_results.values())
        weighted_sim = sum(r["metrics"]["sim_total"] * r["metrics"]["n_chains"] for r in full_results.values())

        log_data["full_run"] = {
            "results_by_type": full_results,
            "overall": {
                "exact_match": round(weighted_exact / total_chains, 2) if total_chains > 0 else 0,
                "sim_total": round(weighted_sim / total_chains, 4) if total_chains > 0 else 0,
                "n_chains": total_chains,
                "elapsed_min": round(total_elapsed / 60, 1),
            },
            "timestamp": datetime.now().isoformat(),
        }
        save_log(log_data)

    print(f"\n  전체 완료: {total_elapsed/60:.1f}분")

# ============================================================
# 상태 및 계획
# ============================================================

def show_plan():
    print("\n" + "=" * 60)
    print("  유형별 θ 적용 계획")
    print("=" * 60)

    print(f"\n  [핵심 아이디어]")
    print(f"    각 이용자 유형의 MNL β를 θ로 변환")
    print(f"    → 유형별 맞춤 OTP 파라미터로 경로 생성")

    print(f"\n  [유형별 θ] (Pooled θ 기준 비율 적용)")
    print(f"  {'유형':<10} | {'walkRel':>8} | {'transCost':>10} | {'특성'}")
    print(f"  {'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*20}")

    traits = {
        "GENERAL": "일반 (기준)",
        "CHILDREN": "보행/환승 덜 민감",
        "YOUTH": "보행/환승 덜 민감",
        "ELDERLY": "보행/환승 매우 덜 민감 (지하철 선호)",
        "DISABLED": "보행/환승 매우 민감",
    }

    for utype, theta in USERTYPE_THETA.items():
        print(f"  {utype:<10} | {theta['walkReluctance']:>8.2f} | {theta['transferCostSeconds']:>10.0f} | {traits.get(utype, '')}")

    print(f"\n  [서브샘플 크기]")
    total = 0
    for utype, n in SAMPLE_SIZE_PER_TYPE.items():
        print(f"    {utype}: {n:,}")
        total += n
    print(f"    총: {total:,} → 예상 ~25분")

    print(f"\n  [실행 흐름]")
    print(f"    1. 유형별 OD 파일 생성")
    print(f"    2. 각 유형에 해당 θ 적용")
    print(f"    3. OTP 5회 실행 (유형별)")
    print(f"    4. 각각 step4 + step5 파이프라인")
    print(f"    5. 유형별 + 전체 유사도 집계")

    print(f"\n  [실행 명령]")
    print(f"    python usertype_calibration.py --run    # 서브샘플 (~25분)")
    print(f"    python usertype_calibration.py --full   # 전체 데이터 (~8시간)")
    print(f"    python usertype_calibration.py --status # 결과 확인")

def show_status():
    print("\n" + "=" * 60)
    print("  현재 상태")
    print("=" * 60)

    log_data = load_log()

    print(f"\n  상태: {log_data.get('status', 'not_started')}")
    print(f"  마지막 업데이트: {log_data.get('last_update', '-')}")

    results = log_data.get("results_by_type", {})
    if results:
        print(f"\n  [서브샘플 결과]")
        print(f"  {'유형':<10} | {'Exact%':>8} | {'sim_total':>10} | {'Alts':>6}")
        print(f"  {'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*6}")

        for utype, result in results.items():
            m = result["metrics"]
            print(f"  {utype:<10} | {m['exact_match']:>8.1f} | {m['sim_total']:>10.4f} | {m['avg_alts']:>6.1f}")

    overall = log_data.get("overall")
    if overall:
        print(f"\n  [전체 평균]")
        print(f"    Exact Match: {overall['exact_match']:.1f}%")
        print(f"    sim_total: {overall['sim_total']:.4f}")
        print(f"    체인 수: {overall['n_chains']:,}")

    full_run = log_data.get("full_run")
    if full_run:
        print(f"\n  [전체 데이터 결과]")
        o = full_run.get("overall", {})
        print(f"    Exact Match: {o.get('exact_match', '-')}%")
        print(f"    sim_total: {o.get('sim_total', '-')}")

# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="User-type specific θ calibration")
    parser.add_argument("--plan", action="store_true", help="계획 확인")
    parser.add_argument("--run", action="store_true", help="서브샘플 실행")
    parser.add_argument("--full", action="store_true", help="전체 데이터 실행")
    parser.add_argument("--status", action="store_true", help="현재 상태")
    args = parser.parse_args()

    if args.plan:
        show_plan()
    elif args.run:
        run_subsample()
    elif args.full:
        run_full()
    elif args.status:
        show_status()
    else:
        show_plan()

if __name__ == "__main__":
    main()
