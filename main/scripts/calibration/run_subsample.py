#!/usr/bin/env python3
"""
Phase 4: 서브샘플 추출 및 빠른 반복 테스트 모듈

전체 126만 OD를 OTP로 돌리면 수 시간이 걸리므로,
10K OD 서브샘플을 추출하여 빠르게 파라미터 변화 효과를 검증한다.

기능:
  1. trip_attributes_filtered.parquet에서 층화 랜덤 추출 (시간대/수단 비율 유지)
  2. OTP 입력용 CSV 생성
  3. 서브샘플 NDJSON으로 파이프라인 실행

사용법:
    # 서브샘플 추출 (10K OD)
    python run_subsample.py --extract --n 10000

    # 추출된 CSV 확인
    python run_subsample.py --info

    # 서브샘플 NDJSON으로 파이프라인 실행
    python run_subsample.py --pipeline --ndjson batch_result_sub.ndjson --iteration 1
"""

import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output"
RESULTS_DIR = ROOT / "results"
OTP_DIR = ROOT.parent / "korean-otp"

# 입출력 파일
TRIP_ATTRS_FILE = OUTPUT_DIR / "trip_attributes_filtered.parquet"
SUBSAMPLE_CSV = OTP_DIR / "data" / "od_subsample.csv"
SUBSAMPLE_IDS_FILE = OUTPUT_DIR / "subsample_chain_ids.parquet"

# 기본 서브샘플 크기
DEFAULT_N = 10000


def extract_subsample(n=DEFAULT_N, seed=42):
    """trip_attributes에서 층화 랜덤 서브샘플을 추출한다.

    층화 기준:
      - 출발 시간대 (시간별)
      - 수단 유형 (있는 경우)
    → 전체 데이터의 시간대 분포를 보존

    Parameters
    ----------
    n : int
        추출할 OD 수 (기본 10,000).
    seed : int
        재현성을 위한 랜덤 시드.
    """
    print(f"\n{'='*50}")
    print(f"  서브샘플 추출 (n={n:,})")
    print(f"{'='*50}")

    if not TRIP_ATTRS_FILE.exists():
        print(f"  오류: {TRIP_ATTRS_FILE.name} 없음")
        return None

    print(f"  로드: {TRIP_ATTRS_FILE.name}...")
    df = pd.read_parquet(TRIP_ATTRS_FILE)
    total = len(df)
    print(f"  전체: {total:,}개 체인")

    # 서브샘플 크기가 전체보다 크면 전체 사용
    if n >= total:
        print(f"  서브샘플 크기({n:,}) ≥ 전체({total:,}), 전체 데이터 사용")
        sample = df
    else:
        # ── 층화 추출: 시간대별 비율 유지 ──
        # 출발 시간 컬럼 찾기
        time_col = None
        for col in ["departure_time", "dep_time", "start_time", "TIME_BOARDING"]:
            if col in df.columns:
                time_col = col
                break

        if time_col:
            # 시간대 추출
            try:
                df["_hour"] = pd.to_datetime(df[time_col], format="%H:%M").dt.hour
            except (ValueError, TypeError):
                try:
                    df["_hour"] = pd.to_datetime(df[time_col]).dt.hour
                except Exception:
                    df["_hour"] = 0  # 파싱 실패 시 균등 추출

            # 시간대별 층화 추출
            print(f"  층화 기준: {time_col} (시간대)")
            sample = df.groupby("_hour", group_keys=False).apply(
                lambda x: x.sample(
                    n=max(1, int(len(x) / total * n)),
                    random_state=seed
                )
            )
            # 목표 수에 맞추기 (소수점 반올림으로 약간 차이 발생)
            if len(sample) > n:
                sample = sample.sample(n=n, random_state=seed)
            elif len(sample) < n:
                # 부족분 랜덤 추가
                remaining = df[~df.index.isin(sample.index)]
                extra = remaining.sample(
                    n=min(n - len(sample), len(remaining)),
                    random_state=seed
                )
                sample = pd.concat([sample, extra])

            sample = sample.drop(columns=["_hour"], errors="ignore")
        else:
            # 시간 컬럼 없으면 단순 랜덤 추출
            print(f"  시간 컬럼 없음, 단순 랜덤 추출")
            sample = df.sample(n=n, random_state=seed)

    print(f"  추출: {len(sample):,}개 체인")

    # ── OTP 입력 CSV 생성 ──
    # 필요 컬럼: from_lat, from_lon, to_lat, to_lon, departure_time
    lat_lon_cols = {
        "from_lat": ["from_lat", "origin_lat", "o_lat", "BOARDING_Y"],
        "from_lon": ["from_lon", "origin_lon", "o_lon", "BOARDING_X"],
        "to_lat": ["to_lat", "dest_lat", "d_lat", "ALIGHTING_Y"],
        "to_lon": ["to_lon", "dest_lon", "d_lon", "ALIGHTING_X"],
    }

    csv_data = {}
    for target, candidates in lat_lon_cols.items():
        found = False
        for col in candidates:
            if col in sample.columns:
                csv_data[target] = sample[col].values
                found = True
                break
        if not found:
            print(f"  오류: {target} 에 해당하는 컬럼을 찾을 수 없음")
            print(f"    사용 가능한 컬럼: {list(sample.columns)}")
            return None

    # 출발 시간
    time_col_final = None
    for col in ["departure_time", "dep_time", "start_time", "TIME_BOARDING"]:
        if col in sample.columns:
            time_col_final = col
            break

    if time_col_final:
        csv_data["departure_time"] = sample[time_col_final].values
    else:
        # 기본값: 08:00
        print(f"  경고: 출발 시간 컬럼 없음, 08:00 기본값 사용")
        csv_data["departure_time"] = ["08:00"] * len(sample)

    csv_df = pd.DataFrame(csv_data)

    # CSV 저장
    SUBSAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    csv_df.to_csv(SUBSAMPLE_CSV, index=False)
    print(f"  OTP 입력 CSV 저장: {SUBSAMPLE_CSV}")

    # chain_id 저장 (나중에 파이프라인에서 필터링용)
    if "chain_id" in sample.columns:
        chain_ids = sample[["chain_id"]].reset_index(drop=True)
        chain_ids.to_parquet(SUBSAMPLE_IDS_FILE)
        print(f"  chain_id 저장: {SUBSAMPLE_IDS_FILE.name}")

    # ── 시간대 분포 비교 ──
    print(f"\n  시간대 분포 비교:")
    print(f"  {'시간':>4} {'전체':>10} {'서브샘플':>10} {'비율':>8}")
    if time_col_final:
        try:
            full_hours = pd.to_datetime(df[time_col_final], format="%H:%M").dt.hour
            sub_hours = pd.to_datetime(csv_df["departure_time"], format="%H:%M").dt.hour
        except Exception:
            full_hours = pd.to_datetime(df[time_col_final]).dt.hour
            sub_hours = pd.to_datetime(csv_df["departure_time"]).dt.hour

        full_dist = full_hours.value_counts(normalize=True).sort_index()
        sub_dist = sub_hours.value_counts(normalize=True).sort_index()

        for hour in range(5, 25):
            h = hour % 24
            fp = full_dist.get(h, 0) * 100
            sp = sub_dist.get(h, 0) * 100
            if fp > 0 or sp > 0:
                print(f"  {h:>4}시 {fp:>9.1f}% {sp:>9.1f}% "
                      f"{'✓' if abs(fp - sp) < 2 else '△'}")

    # OTP 실행 안내
    print(f"\n  다음 단계 — OTP 서브샘플 배치 실행:")
    print(f"    cd {OTP_DIR}")
    print(f"    java -jar build/libs/korean-otp.jar batch \\")
    print(f"      data/od_subsample.csv \\")
    print(f"      batch_result_subsample.ndjson \\")
    print(f"      8")
    print(f"\n  예상 소요: ~{n // 1000 * 2}분 (10K OD 기준 ~20분)")

    return sample


def show_info():
    """현재 서브샘플 상태를 출력한다."""
    print(f"\n{'='*50}")
    print(f"  서브샘플 상태")
    print(f"{'='*50}")

    if SUBSAMPLE_CSV.exists():
        csv_df = pd.read_csv(SUBSAMPLE_CSV)
        print(f"  CSV: {SUBSAMPLE_CSV}")
        print(f"  OD 수: {len(csv_df):,}")
        print(f"  컬럼: {list(csv_df.columns)}")
        print(f"  미리보기:")
        print(csv_df.head(3).to_string(index=False))
    else:
        print(f"  서브샘플 CSV 없음")
        print(f"  먼저 추출 실행: python run_subsample.py --extract")

    if SUBSAMPLE_IDS_FILE.exists():
        ids = pd.read_parquet(SUBSAMPLE_IDS_FILE)
        print(f"\n  chain_id 파일: {SUBSAMPLE_IDS_FILE.name}")
        print(f"  chain 수: {len(ids):,}")


def run_subsample_pipeline(ndjson_path, iteration):
    """서브샘플 NDJSON으로 축소 파이프라인을 실행한다.

    calibration_orchestrator의 step_pipeline과 동일하지만,
    서브샘플 전용 출력 디렉토리를 사용한다.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    print(f"\n{'='*50}")
    print(f"  서브샘플 파이프라인 (Iteration {iteration})")
    print(f"{'='*50}")

    ndjson = Path(ndjson_path)
    if not ndjson.exists():
        print(f"  오류: NDJSON 파일 없음 — {ndjson}")
        return False

    print(f"  NDJSON: {ndjson}")
    print(f"  크기: {ndjson.stat().st_size / (1024**2):.1f} MB")

    # 오케스트레이터의 파이프라인 호출
    from calibration_orchestrator import step_pipeline
    return step_pipeline(iteration, str(ndjson))


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: 서브샘플 추출 및 빠른 반복 테스트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  1. 서브샘플 추출:
     python run_subsample.py --extract --n 10000

  2. OTP 배치 실행 (수동):
     cd korean-otp
     java -jar build/libs/korean-otp.jar batch \\
       data/od_subsample.csv batch_result_subsample.ndjson 8

  3. 서브샘플 파이프라인:
     python run_subsample.py --pipeline \\
       --ndjson batch_result_subsample.ndjson --iteration 1
""")

    parser.add_argument("--extract", action="store_true",
                        help="서브샘플 추출")
    parser.add_argument("--n", type=int, default=DEFAULT_N,
                        help=f"추출할 OD 수 (기본: {DEFAULT_N:,})")
    parser.add_argument("--seed", type=int, default=42,
                        help="랜덤 시드 (기본: 42)")
    parser.add_argument("--info", action="store_true",
                        help="서브샘플 상태 확인")
    parser.add_argument("--pipeline", action="store_true",
                        help="서브샘플 파이프라인 실행")
    parser.add_argument("--ndjson", type=str, default=None,
                        help="서브샘플 OTP 결과 NDJSON 경로")
    parser.add_argument("--iteration", type=int, default=1,
                        help="반복 회차")

    args = parser.parse_args()

    if args.extract:
        extract_subsample(n=args.n, seed=args.seed)
    elif args.info:
        show_info()
    elif args.pipeline:
        if not args.ndjson:
            print("  오류: --ndjson 경로를 지정하세요")
            return
        run_subsample_pipeline(args.ndjson, args.iteration)
    else:
        # 기본: 상태 출력
        show_info()


if __name__ == "__main__":
    main()
