#!/usr/bin/env python3
"""
Phase 4: 좌표 하강법 (Coordinate Descent) 기반 θ 최적화

각 유형별로 최적의 (walkReluctance, transferCostSeconds)를 찾음.
한 번에 하나의 파라미터만 탐색하여 효율적으로 수렴.

사용법:
    python coordinate_descent_calibration.py --run       # 전체 유형 최적화
    python coordinate_descent_calibration.py --type ELDERLY  # 특정 유형만
    python coordinate_descent_calibration.py --status    # 현재 상태
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
CD_LOG = RESULTS_DIR / "coordinate_descent_log.json"

# ============================================================
# 탐색 설정
# ============================================================

# 초기 θ (Phase 4 이전 결과 반영 — 실제 OTP 최적값은 MNL 비율보다 2~3배 높음)
INITIAL_THETA = {
    "GENERAL": {"walkReluctance": 9.24, "transferCostSeconds": 258, "subwayReluctance": 1.0},
    "CHILDREN": {"walkReluctance": 5.91, "transferCostSeconds": 145, "subwayReluctance": 1.0},
    "YOUTH": {"walkReluctance": 5.54, "transferCostSeconds": 222, "subwayReluctance": 1.0},
    "ELDERLY": {"walkReluctance": 15.0, "transferCostSeconds": 90, "subwayReluctance": 0.5},
    "DISABLED": {"walkReluctance": 10.0, "transferCostSeconds": 358, "subwayReluctance": 1.0},
}

# 탐색 설정 (초기값 기준 주변 탐색)
SEARCH_RANGE = 0.8  # 초기값의 ±80% 범위 (Round 1에서 넓게 탐색)
SEARCH_STEPS = 5    # 빠른 탐색 (5단계)

def generate_search_grid(center, range_ratio=SEARCH_RANGE, steps=SEARCH_STEPS, min_val=0.5):
    """
    초기값 중심으로 탐색 그리드 생성

    예: center=1.75, range=0.6, steps=7
        → [0.70, 1.05, 1.40, 1.75, 2.10, 2.45, 2.80]
    """
    low = max(center * (1 - range_ratio), min_val)
    high = center * (1 + range_ratio)
    grid = [low + (high - low) * i / (steps - 1) for i in range(steps)]
    # 반올림 (walkRel은 소수점 1자리, transCost는 정수)
    return grid

# 유형별 서브샘플 크기 (빠른 탐색: 2K)
SAMPLE_SIZE_PER_TYPE = {
    "GENERAL": 2000,
    "ELDERLY": 2000,
    "YOUTH": 2000,
    "DISABLED": 2000,
    "CHILDREN": 2000,
}

# 수렴 조건
MAX_ROUNDS = 1  # 빠른 1회 탐색
CONVERGENCE_THRESHOLD = 0.003  # sim_total 개선폭 < 0.3%면 수렴

# ============================================================
# 유틸리티 함수
# ============================================================

def load_log():
    if CD_LOG.exists():
        with open(CD_LOG, encoding='utf-8') as f:
            return json.load(f)
    return {"status": "not_started", "results": {}}

def save_log(log_data):
    log_data["last_update"] = datetime.now().isoformat()
    with open(CD_LOG, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

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

# ============================================================
# OTP 실행 + 유사도 계산
# ============================================================

def evaluate_result_file(result_file):
    """
    OTP 결과 파일에 대해 step4+step5 실행 후 유사도 반환

    Returns:
        dict: {"exact_match": float, "sim_total": float, "n_chains": int}
        None: 실패 시
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

    for script in [
        SCRIPTS_DIR / "matching" / "step4_parse_otp_results.py",
        SCRIPTS_DIR / "matching" / "step5_calculate_similarity.py",
    ]:
        result = subprocess.run(
            [sys.executable, str(script)],
            env=env,
            cwd=str(ROOT),
            capture_output=True,
        )
        if result.returncode != 0:
            return None

    sim_file = OUTPUT_DIR / "similarity_results.parquet"
    if not sim_file.exists():
        return None

    sim_df = pd.read_parquet(sim_file)
    # OTP 1순위 추천 경로 = generalized_cost 최소 (파라미터 튜닝 효과 반영)
    best = sim_df.loc[sim_df.groupby('chain_id')['otp_generalized_cost'].idxmin()]

    return {
        "exact_match": float(best['exact_match'].mean()),
        "sim_total": float(best['sim_total'].mean()),
        "n_chains": len(best),
    }


def prepare_od_file(utype, df_sample):
    """서브샘플에서 OD CSV + trip_attributes_subsample 준비 (1회만)"""
    df = df_sample.copy().reset_index(drop=True)
    df["od_id"] = df.index

    subsample_file = OUTPUT_DIR / "trip_attributes_subsample.parquet"
    df.to_parquet(subsample_file, index=False)

    od_df = df[['origin_lat', 'origin_lon', 'dest_lat', 'dest_lon', 'board_time']].copy()
    od_df.columns = ['from_lat', 'from_lon', 'to_lat', 'to_lon', 'departure_time']
    od_df['departure_time'] = od_df['departure_time'].apply(
        lambda x: f"{int(x) // 3600:02d}:{(int(x) % 3600) // 60:02d}"
    )

    od_file = OTP_DIR / "data" / f"od_cd_{utype.lower()}.csv"
    od_df.to_csv(od_file, index=False)
    return od_file


def run_step_multi_batch(utype, grid_values, param_name, current_theta, od_file):
    """
    한 Step의 후보들을 OTP multi-batch로 일괄 실행.
    데이터 1회 로드로 모든 후보를 순차 처리.

    Returns:
        list of (value, result_dict_or_None)
    """
    jar_file = OTP_DIR / "build" / "libs" / "korean-raptor-1.0.0-SNAPSHOT-all.jar"
    if not jar_file.exists():
        print(f"  [ERROR] JAR 없음: {jar_file}")
        return [(v, None) for v in grid_values]

    java_exe = "C:\\Program Files\\Java\\jdk-21\\bin\\java.exe"

    # 1. config JSON들 생성
    config_dir = OTP_DIR / "calibration_configs"
    config_dir.mkdir(exist_ok=True)
    manifest_lines = []
    result_files = []

    for i, val in enumerate(grid_values):
        theta = current_theta.copy()
        theta[param_name] = val

        config_path = config_dir / f"config_{i}.json"
        save_config(theta, config_path)

        result_path = OTP_DIR / f"batch_cd_{utype.lower()}_{i}.ndjson"
        # 기존 결과 삭제
        if result_path.exists():
            result_path.unlink()
        progress_path = Path(str(result_path) + ".progress")
        if progress_path.exists():
            progress_path.unlink()

        manifest_lines.append(f"{config_path},{result_path}")
        result_files.append(result_path)

    # 2. 매니페스트 파일 생성
    manifest_file = config_dir / "manifest.txt"
    manifest_file.write_text("\n".join(manifest_lines), encoding='utf-8')

    # 3. 초기 config 설정 (multi-batch의 초기 로드용)
    save_config(current_theta)

    # 4. Java multi-batch 1회 실행
    cmd = [java_exe, "-Xmx40G", "-XX:+UseG1GC", "-jar", str(jar_file),
           "multi-batch", str(od_file), str(manifest_file), "16"]

    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Java\\jdk-21"
    env["PATH"] = f"{env['JAVA_HOME']}\\bin;{env.get('PATH', '')}"

    # Java 로그를 파일로 리다이렉트 (PIPE는 버퍼 가득차면 hang)
    log_file = config_dir / "multi_batch.log"
    start = time.time()
    with open(log_file, 'w', encoding='utf-8') as log_fh:
        proc = subprocess.Popen(cmd, cwd=str(OTP_DIR), env=env,
                                stdout=log_fh, stderr=subprocess.STDOUT)

        # 프로세스 완료 대기 (타임아웃: 후보 수 × 3분 + 초기화 3분, 2K OD 기준)
        timeout = len(grid_values) * 180 + 180  # 초기화 180초 + 후보당 180초
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] multi-batch {timeout}초 초과 → kill")
            proc.kill()
            proc.wait(timeout=10)

    elapsed = time.time() - start
    print(f"  multi-batch 완료: {elapsed:.1f}초 ({len(grid_values)}개 배치)")

    # 5. 각 결과에 대해 step4+step5 실행
    results = []
    for i, val in enumerate(grid_values):
        result = evaluate_result_file(result_files[i])
        results.append((val, result))

    return results


def run_otp_and_evaluate(utype, theta, df_sample):
    """
    단일 θ에 대해 OTP 실행 + 유사도 계산

    Returns:
        dict: {"exact_match": float, "sim_total": float, "n_chains": int}
        None: 실패 시
    """
    # 1. od_id 재매핑
    df = df_sample.copy().reset_index(drop=True)
    df["od_id"] = df.index

    # 2. trip_attributes_subsample.parquet 저장
    subsample_file = OUTPUT_DIR / "trip_attributes_subsample.parquet"
    df.to_parquet(subsample_file, index=False)

    # 3. OD CSV 생성
    od_df = df[['origin_lat', 'origin_lon', 'dest_lat', 'dest_lon', 'board_time']].copy()
    od_df.columns = ['from_lat', 'from_lon', 'to_lat', 'to_lon', 'departure_time']
    od_df['departure_time'] = od_df['departure_time'].apply(
        lambda x: f"{int(x) // 3600:02d}:{(int(x) % 3600) // 60:02d}"
    )

    od_file = OTP_DIR / "data" / f"od_cd_{utype.lower()}.csv"
    od_df.to_csv(od_file, index=False)

    # 4. θ 설정
    save_config(theta)

    # 5. OTP 실행
    result_file = OTP_DIR / f"batch_cd_{utype.lower()}.ndjson"
    jar_file = OTP_DIR / "build" / "libs" / "korean-raptor-1.0.0-SNAPSHOT-all.jar"

    if not jar_file.exists():
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

    start = time.time()

    # Popen으로 실행
    proc = subprocess.Popen(cmd, cwd=str(OTP_DIR), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 결과 파일 모니터링
    last_size = 0
    stable_count = 0
    timed_out = False
    while True:
        time.sleep(3)
        if result_file.exists():
            current_size = result_file.stat().st_size
            if current_size > 0 and current_size == last_size:
                stable_count += 1
                if stable_count >= 3:
                    break
            else:
                stable_count = 0
            last_size = current_size

        if proc.poll() is not None:
            break

        if time.time() - start > 1200:  # 20분 타임아웃 (GENERAL 20K 고려)
            timed_out = True
            break

    # 프로세스 정리: 자연 종료 대기 → terminate → kill 순서
    if proc.poll() is None:
        if timed_out:
            proc.kill()
            proc.wait(timeout=10)
        else:
            # 파일 안정 후 자연 종료 대기
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)

    if not result_file.exists() or result_file.stat().st_size < 1024:
        return None

    # 6. step4 + step5 실행
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
            env=env,
            cwd=str(ROOT),
            capture_output=True,
        )
        if result.returncode != 0:
            return None

    # 7. 유사도 결과 수집
    sim_file = OUTPUT_DIR / "similarity_results.parquet"
    if not sim_file.exists():
        return None

    sim_df = pd.read_parquet(sim_file)
    # OTP 1순위 추천 경로 = generalized_cost 최소 (파라미터 튜닝 효과 반영)
    best = sim_df.loc[sim_df.groupby('chain_id')['otp_generalized_cost'].idxmin()]

    return {
        "exact_match": float(best['exact_match'].mean()),
        "sim_total": float(best['sim_total'].mean()),
        "n_chains": len(best),
    }

# ============================================================
# 좌표 하강법
# ============================================================

def optimize_single_type(utype, df_sample, initial_theta):
    """
    단일 유형에 대해 좌표 하강법으로 θ 최적화
    3파라미터: walkReluctance, transferCostSeconds, subwayReluctance
    초기값 주변에서 탐색하고, 라운드마다 범위를 좁혀감
    """
    print(f"\n{'='*60}")
    print(f"  [{utype}] 좌표 하강법 시작 (3파라미터)")
    print(f"  초기 θ: walkRel={initial_theta['walkReluctance']:.2f}, "
          f"transCost={initial_theta['transferCostSeconds']:.0f}, "
          f"subwayRel={initial_theta.get('subwayReluctance', 1.0):.2f}")
    print(f"  샘플 수: {len(df_sample):,}")
    print(f"  탐색 범위: 초기값 ±{SEARCH_RANGE*100:.0f}%, {SEARCH_STEPS}단계")
    print(f"{'='*60}")

    current_theta = initial_theta.copy()
    if "subwayReluctance" not in current_theta:
        current_theta["subwayReluctance"] = 1.0
    best_sim = 0
    history = []

    # OD 파일 1회 준비 (모든 라운드/스텝에 재사용)
    od_file = prepare_od_file(utype, df_sample)

    # 라운드마다 탐색 범위 축소 (수렴 가속)
    range_decay = [1.0, 0.7, 0.5, 0.35, 0.25, 0.2, 0.15, 0.1, 0.08, 0.05]

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n  --- Round {round_num} ---")
        round_start_sim = best_sim

        # 현재 라운드의 탐색 범위 (라운드마다 축소)
        current_range = SEARCH_RANGE * range_decay[min(round_num - 1, len(range_decay) - 1)]
        print(f"  탐색 범위: ±{current_range*100:.0f}%")

        # Step 1: walkReluctance 탐색 (transferCost, subwayRel 고정)
        walk_grid = generate_search_grid(current_theta["walkReluctance"], current_range, SEARCH_STEPS, min_val=0.5)
        walk_grid = [round(v, 2) for v in walk_grid]
        print(f"\n  [Step 1] walkReluctance 탐색 (multi-batch): {[f'{v:.2f}' for v in walk_grid]}")
        print(f"           (transCost={current_theta['transferCostSeconds']:.0f}, "
              f"subwayRel={current_theta['subwayReluctance']:.2f} 고정)")
        best_walk = current_theta["walkReluctance"]

        step_results = run_step_multi_batch(utype, walk_grid, "walkReluctance", current_theta, od_file)
        for walk_val, result in step_results:
            if result:
                sim = result["sim_total"]
                exact = result["exact_match"] * 100
                print(f"    walkRel={walk_val:.2f}: sim={sim:.4f}, exact={exact:.1f}%")
                history.append({
                    "round": round_num, "step": "walkRel",
                    "theta": {**current_theta, "walkReluctance": walk_val},
                    "sim_total": sim, "exact_match": exact,
                })
                if sim > best_sim:
                    best_sim = sim
                    best_walk = walk_val
            else:
                print(f"    walkRel={walk_val:.2f}: [FAIL]")

        current_theta["walkReluctance"] = best_walk
        print(f"  → 최적 walkRel: {best_walk:.2f} (sim={best_sim:.4f})")

        # Step 2: transferCost 탐색 (walkReluctance, subwayRel 고정)
        trans_grid = generate_search_grid(current_theta["transferCostSeconds"], current_range, SEARCH_STEPS, min_val=30)
        trans_grid = [round(v) for v in trans_grid]
        print(f"\n  [Step 2] transferCost 탐색 (multi-batch): {trans_grid}")
        print(f"           (walkRel={current_theta['walkReluctance']:.2f}, "
              f"subwayRel={current_theta['subwayReluctance']:.2f} 고정)")
        best_trans = current_theta["transferCostSeconds"]

        step_results = run_step_multi_batch(utype, trans_grid, "transferCostSeconds", current_theta, od_file)
        for trans_val, result in step_results:
            if result:
                sim = result["sim_total"]
                exact = result["exact_match"] * 100
                print(f"    transCost={trans_val}: sim={sim:.4f}, exact={exact:.1f}%")
                history.append({
                    "round": round_num, "step": "transCost",
                    "theta": {**current_theta, "transferCostSeconds": trans_val},
                    "sim_total": sim, "exact_match": exact,
                })
                if sim > best_sim:
                    best_sim = sim
                    best_trans = trans_val
            else:
                print(f"    transCost={trans_val}: [FAIL]")

        current_theta["transferCostSeconds"] = best_trans
        print(f"  → 최적 transCost: {best_trans} (sim={best_sim:.4f})")

        # Step 3: subwayReluctance 탐색 (walkReluctance, transferCost 고정)
        subway_grid = generate_search_grid(current_theta["subwayReluctance"], current_range, SEARCH_STEPS, min_val=0.3)
        subway_grid = [round(v, 2) for v in subway_grid]
        print(f"\n  [Step 3] subwayReluctance 탐색 (multi-batch): {[f'{v:.2f}' for v in subway_grid]}")
        print(f"           (walkRel={current_theta['walkReluctance']:.2f}, "
              f"transCost={current_theta['transferCostSeconds']:.0f} 고정)")
        best_subway = current_theta["subwayReluctance"]

        step_results = run_step_multi_batch(utype, subway_grid, "subwayReluctance", current_theta, od_file)
        for subway_val, result in step_results:
            if result:
                sim = result["sim_total"]
                exact = result["exact_match"] * 100
                print(f"    subwayRel={subway_val:.2f}: sim={sim:.4f}, exact={exact:.1f}%")
                history.append({
                    "round": round_num, "step": "subwayRel",
                    "theta": {**current_theta, "subwayReluctance": subway_val},
                    "sim_total": sim, "exact_match": exact,
                })
                if sim > best_sim:
                    best_sim = sim
                    best_subway = subway_val
            else:
                print(f"    subwayRel={subway_val:.2f}: [FAIL]")

        current_theta["subwayReluctance"] = best_subway
        print(f"  → 최적 subwayRel: {best_subway:.2f} (sim={best_sim:.4f})")

        # 수렴 확인
        improvement = best_sim - round_start_sim
        print(f"\n  Round {round_num} 완료: sim={best_sim:.4f}, 개선={improvement:.4f}")

        if improvement < CONVERGENCE_THRESHOLD:
            print(f"  → 수렴! (개선폭 < {CONVERGENCE_THRESHOLD})")
            break

    # 최종 결과
    print(f"\n  최종 θ: walkRel={current_theta['walkReluctance']:.2f}, "
          f"transCost={current_theta['transferCostSeconds']:.0f}, "
          f"subwayRel={current_theta['subwayReluctance']:.2f}")
    print(f"  최종 sim_total: {best_sim:.4f}")

    return {
        "optimal_theta": current_theta,
        "best_sim_total": best_sim,
        "history": history,
        "rounds": round_num,
    }

# ============================================================
# 메인 실행
# ============================================================

def run_optimization(target_types=None):
    """전체 또는 특정 유형 최적화"""
    print("\n" + "=" * 70)
    print("  좌표 하강법 θ 최적화")
    print("=" * 70)

    # 데이터 로드
    print("\n  데이터 로드 중...")
    trip_attrs = pd.read_parquet(OUTPUT_DIR / "trip_attributes_filtered.parquet")
    print(f"  전체 체인: {len(trip_attrs):,}")

    # 로그 초기화
    log_data = load_log()
    log_data["status"] = "running"
    log_data["start_time"] = datetime.now().isoformat()
    save_log(log_data)

    # 유형 목록
    if target_types:
        types_to_run = [t.upper() for t in target_types]
    else:
        types_to_run = list(INITIAL_THETA.keys())

    print(f"\n  대상 유형: {types_to_run}")
    print(f"  유형별 샘플:")
    for utype in types_to_run:
        print(f"    {utype}: {SAMPLE_SIZE_PER_TYPE.get(utype, 5000):,}")
    print(f"  탐색 방식: 초기값 ±{SEARCH_RANGE*100:.0f}%, {SEARCH_STEPS}단계, 라운드마다 범위 축소")

    total_start = time.time()
    results = log_data.get("results", {})

    for utype in types_to_run:
        if utype not in INITIAL_THETA:
            print(f"\n  [WARN] {utype} 유형 없음, 건너뜀")
            continue

        # 해당 유형 필터링 + 서브샘플
        df_type = trip_attrs[trip_attrs['user_type'] == utype]
        if len(df_type) == 0:
            print(f"\n  [{utype}] 데이터 없음, 건너뜀")
            continue

        sample_size = SAMPLE_SIZE_PER_TYPE.get(utype, 5000)
        n_sample = min(len(df_type), sample_size)
        df_sample = df_type.sample(n=n_sample, random_state=42)

        # 좌표 하강법 실행
        initial = INITIAL_THETA[utype]
        result = optimize_single_type(utype, df_sample, initial)

        results[utype] = {
            "initial_theta": initial,
            "optimal_theta": result["optimal_theta"],
            "best_sim_total": result["best_sim_total"],
            "rounds": result["rounds"],
            "history": result["history"],
            "timestamp": datetime.now().isoformat(),
        }

        # 중간 저장
        log_data["results"] = results
        save_log(log_data)

    total_elapsed = time.time() - total_start

    # 최종 결과 출력
    print("\n" + "=" * 70)
    print("  최적화 결과 요약")
    print("=" * 70)

    print(f"\n  {'유형':<10} | {'초기 sim':>10} | {'최적 sim':>10} | {'walkRel':>8} | {'transCost':>10} | {'subwayRel':>10}")
    print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*10}")

    for utype in types_to_run:
        if utype in results:
            r = results[utype]
            init_sim = r["history"][0]["sim_total"] if r["history"] else 0
            opt_sim = r["best_sim_total"]
            opt_theta = r["optimal_theta"]
            print(f"  {utype:<10} | {init_sim:>10.4f} | {opt_sim:>10.4f} | "
                  f"{opt_theta['walkReluctance']:>8.1f} | {opt_theta['transferCostSeconds']:>10.0f} | "
                  f"{opt_theta.get('subwayReluctance', 1.0):>10.2f}")

    print(f"\n  총 소요 시간: {total_elapsed/60:.1f}분")

    # 최적 θ 출력 (복사용)
    print("\n  [최적 θ - 코드용]")
    print("  OPTIMAL_THETA = {")
    for utype in types_to_run:
        if utype in results:
            opt = results[utype]["optimal_theta"]
            print(f'      "{utype}": {{"walkReluctance": {opt["walkReluctance"]}, '
                  f'"transferCostSeconds": {opt["transferCostSeconds"]}, '
                  f'"subwayReluctance": {opt.get("subwayReluctance", 1.0)}}},')
    print("  }")

    log_data["status"] = "completed"
    log_data["end_time"] = datetime.now().isoformat()
    log_data["total_elapsed_min"] = round(total_elapsed / 60, 1)
    save_log(log_data)

    print("\n  완료!")

def show_status():
    """현재 상태 출력"""
    print("\n" + "=" * 60)
    print("  좌표 하강법 현재 상태")
    print("=" * 60)

    log_data = load_log()

    print(f"\n  상태: {log_data.get('status', 'not_started')}")
    print(f"  마지막 업데이트: {log_data.get('last_update', '-')}")

    results = log_data.get("results", {})
    if results:
        print(f"\n  {'유형':<10} | {'최적 sim':>10} | {'walkRel':>8} | {'transCost':>10} | {'subwayRel':>10} | {'Rounds':>6}")
        print(f"  {'-'*10}-+-{'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*10}-+-{'-'*6}")

        for utype, r in results.items():
            opt = r["optimal_theta"]
            print(f"  {utype:<10} | {r['best_sim_total']:>10.4f} | "
                  f"{opt['walkReluctance']:>8.1f} | {opt['transferCostSeconds']:>10.0f} | "
                  f"{opt.get('subwayReluctance', 1.0):>10.2f} | "
                  f"{r['rounds']:>6}")

# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Coordinate Descent θ Optimization")
    parser.add_argument("--run", action="store_true", help="전체 유형 최적화 실행")
    parser.add_argument("--type", type=str, nargs="+", help="특정 유형만 실행 (예: --type ELDERLY DISABLED)")
    parser.add_argument("--status", action="store_true", help="현재 상태")
    args = parser.parse_args()

    if args.run:
        run_optimization()
    elif args.type:
        run_optimization(target_types=args.type)
    elif args.status:
        show_status()
    else:
        print("\n사용법:")
        print("  python coordinate_descent_calibration.py --run           # 전체 유형")
        print("  python coordinate_descent_calibration.py --type ELDERLY  # 특정 유형")
        print("  python coordinate_descent_calibration.py --status        # 상태 확인")
        print()
        print("탐색 방식: 초기값 주변 탐색 (Coordinate Descent, 3파라미터)")
        print(f"  탐색 범위: 초기값 ±{SEARCH_RANGE*100:.0f}%")
        print(f"  탐색 단계: {SEARCH_STEPS}개")
        print(f"  파라미터: walkReluctance, transferCostSeconds, subwayReluctance")
        print(f"  라운드마다 범위 축소 (수렴 가속)")
        print()
        print("초기 θ (MNL 기반):")
        for utype, theta in INITIAL_THETA.items():
            print(f"  {utype}: walkRel={theta['walkReluctance']:.2f}, "
                  f"transCost={theta['transferCostSeconds']:.0f}, "
                  f"subwayRel={theta.get('subwayReluctance', 1.0):.2f}")
        print()
        print("유형별 샘플 크기:")
        for utype, size in SAMPLE_SIZE_PER_TYPE.items():
            print(f"  {utype}: {size:,}")
        print()
        print("예상 시간: ~3-4시간 (5유형, 라운드당 21회 OTP)")

if __name__ == "__main__":
    main()
