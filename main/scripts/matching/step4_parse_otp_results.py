"""
Step 4: OTP 배치 결과 파싱 + 속성 추출

입력:
- batch_result_iter{N}.ndjson (OTP 배치 결과)
- trip_attributes_filtered.parquet (1,467,135 체인)

출력 (output/iter{N}/):
- otp_alternatives.parquet (~10M행, OD별 최대 10개 경로)
- failed_od_ids.parquet (경로 없음 OD 목록)
- trip_attributes_matched.parquet (경로 있는 체인만)

환경변수:
- ITERATION: 반복 회차 (기본 0)
- OTP_NDJSON_PATH: NDJSON 경로 (선택)

실행:
    python scripts/matching/step4_parse_otp_results.py
    ITERATION=1 python scripts/matching/step4_parse_otp_results.py
"""

import json
import os
import sys
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from tqdm import tqdm
import time

# 경로 설정 - iteration_paths 사용
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from utils.iteration_paths import get_paths, get_otp_ndjson_path, print_iteration_info

# Iteration별 경로 가져오기
paths = get_paths()
OTP_RESULT = get_otp_ndjson_path()

# 출력 파일 (iteration별)
OTP_ALTERNATIVES_FILE = paths.otp_alternatives
FAILED_OD_FILE = paths.failed_od_ids
TRIP_ATTRS_MATCHED_FILE = paths.trip_attrs_matched

# 서브샘플 모드 확인: SUBSAMPLE_MODE=1이면 trip_attributes_subsample.parquet 사용
SUBSAMPLE_MODE = os.environ.get("SUBSAMPLE_MODE", "0") == "1"
if SUBSAMPLE_MODE:
    # output/ 디렉토리에 있는 서브샘플 전용 파일 사용
    # (run_subsample.py에서 생성, od_id가 0부터 재매핑됨)
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    TRIP_ATTRS_FILTERED_FILE = PROJECT_ROOT / "output" / "trip_attributes_subsample.parquet"
    print(f"[서브샘플 모드] trip_attributes_subsample.parquet 사용")
else:
    TRIP_ATTRS_FILTERED_FILE = paths.trip_attrs_filtered


def extract_route_info_from_legs(legs):
    """
    legs에서 노선 정보 추출

    Returns:
        route_ids: ["1:BR_1100_100100586", "1:RR_ACC1_S-2-01-1D", ...]
        route_names: ["302", "2호선", ...]
        boarding_stops: ["1:BS_1100_xxx", ...]
        alighting_stops: ["1:BS_1100_yyy", ...]
    """
    route_ids = []
    route_names = []
    boarding_stops = []
    alighting_stops = []

    for leg in legs:
        mode = leg.get('mode', '')

        # transit leg만 처리 (WALK 제외)
        if mode in ['BUS', 'SUBWAY', 'RAIL', 'TRAM', 'FERRY']:
            # 노선 정보
            route = leg.get('route', {})
            if route:
                route_id = route.get('gtfsId', '')
                route_name = route.get('shortName', '') or route.get('longName', '')
                route_ids.append(route_id)
                route_names.append(route_name)

            # 승하차 정류장
            from_stop = leg.get('from', {}).get('stop', {})
            to_stop = leg.get('to', {}).get('stop', {})

            if from_stop:
                boarding_stops.append(from_stop.get('gtfsId', ''))
            if to_stop:
                alighting_stops.append(to_stop.get('gtfsId', ''))

    return route_ids, route_names, boarding_stops, alighting_stops


def parse_otp_results():
    """OTP NDJSON 파싱 + 속성 추출"""

    print("=" * 70)
    print("Step 4: OTP 배치 결과 파싱")
    print("=" * 70)
    print(f"입력: {OTP_RESULT}")
    print(f"출력: {OTP_ALTERNATIVES_FILE}")
    print()

    # 파일 라인 수 확인
    print("파일 라인 수 확인 중...")
    with open(OTP_RESULT, 'r', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)
    print(f"총 라인: {total_lines:,}")
    print()

    # 결과 저장용
    all_rows = []
    failed_od_ids = []
    success_od_ids = []

    # 통계
    total_itineraries = 0
    itinerary_counts = []

    start_time = time.time()

    # 스트리밍 파싱
    print("파싱 시작...")
    print("추출 속성: od_id, alt_id, duration, ride/walk/wait_time, n_transfers,")
    print("          has_subway, modes, route_ids, route_names, stop_sequence,")
    print("          boarding_stops, alighting_stops, generalized_cost")
    print()

    import re

    def fix_json_escapes(line):
        """
        polyline 인코딩에서 발생하는 escape 문제 수정

        문제: "points" 필드에 백슬래시가 포함되어 JSON 파싱 실패
        해결: "points":"..." 필드를 통째로 제거 (step4에서 불필요)
        """
        # "points":"..." 패턴을 제거 (빈 문자열로 대체)
        # 주의: points 값에 이스케이프된 따옴표가 있을 수 있어서 복잡한 패턴 사용
        fixed = re.sub(r'"points":"[^"]*(?:\\.[^"]*)*"', '"points":""', line)
        return fixed

    with open(OTP_RESULT, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(tqdm(f, total=total_lines, desc="파싱")):
            try:
                # JSON 파싱 전에 escape 문제 수정
                line_fixed = fix_json_escapes(line.strip())
                data = json.loads(line_fixed)
                od_id = data['id']
                itineraries = data['data']['plan'].get('itineraries', [])

                if not itineraries:
                    # 경로 없음
                    failed_od_ids.append(od_id)
                    continue

                success_od_ids.append(od_id)
                itinerary_counts.append(len(itineraries))

                for alt_id, itin in enumerate(itineraries):
                    summary = itin.get('summary', {})
                    legs = itin.get('legs', [])

                    # 기본 속성 (summary에서)
                    ride_time_sec = summary.get('ride_time_sec', 0)
                    walk_time_sec = summary.get('walk_time_sec', 0)
                    total_duration = itin.get('duration', 0)

                    # wait_time 계산: 총시간 - 차내시간 - 도보시간
                    wait_time_sec = max(0, total_duration - ride_time_sec - walk_time_sec)

                    # legs에서 노선 정보 추출
                    route_ids, route_names, boarding_stops, alighting_stops = \
                        extract_route_info_from_legs(legs)

                    row = {
                        'od_id': od_id,
                        'alt_id': alt_id,

                        # 시간 속성
                        'total_duration': total_duration,
                        'ride_time_sec': ride_time_sec,
                        'walk_time_sec': walk_time_sec,
                        'wait_time_sec': wait_time_sec,

                        # 환승/수단
                        'n_transfers': summary.get('n_transfers', 0),
                        'has_subway': 1 if summary.get('has_subway', False) else 0,
                        'modes': json.dumps(summary.get('modes', [])),

                        # 노선 정보 (NEW!)
                        'route_ids': json.dumps(route_ids),
                        'route_names': json.dumps(route_names),

                        # 정류장 정보
                        'stop_sequence': json.dumps(summary.get('stop_sequence', [])),
                        'boarding_stops': json.dumps(boarding_stops),
                        'alighting_stops': json.dumps(alighting_stops),

                        # 비용
                        'generalized_cost': itin.get('generalizedCost', 0),
                        'walk_distance': itin.get('walkDistance', 0),
                    }
                    all_rows.append(row)
                    total_itineraries += 1

            except Exception as e:
                print(f"\n라인 {line_num} 파싱 오류: {e}")
                continue

            # 청크 단위로 진행률 표시
            if (line_num + 1) % 100000 == 0:
                elapsed = time.time() - start_time
                rate = (line_num + 1) / elapsed
                remaining = (total_lines - line_num - 1) / rate
                print(f"\n  {line_num + 1:,}/{total_lines:,} | "
                      f"경로: {total_itineraries:,} | "
                      f"실패: {len(failed_od_ids):,} | "
                      f"남은시간: {remaining/60:.1f}분")

    elapsed = time.time() - start_time
    print(f"\n파싱 완료: {elapsed/60:.1f}분")
    print()

    # DataFrame 생성
    print("DataFrame 생성 중...")
    df = pd.DataFrame(all_rows)

    # 데이터 타입 최적화
    df['od_id'] = df['od_id'].astype('int32')
    df['alt_id'] = df['alt_id'].astype('int8')
    df['total_duration'] = df['total_duration'].astype('int32')
    df['ride_time_sec'] = df['ride_time_sec'].astype('int32')
    df['walk_time_sec'] = df['walk_time_sec'].astype('int32')
    df['wait_time_sec'] = df['wait_time_sec'].astype('int32')
    df['n_transfers'] = df['n_transfers'].astype('int8')
    df['has_subway'] = df['has_subway'].astype('int8')
    df['generalized_cost'] = df['generalized_cost'].astype('int32')
    df['walk_distance'] = df['walk_distance'].astype('float32')

    print(f"  행 수: {len(df):,}")
    print(f"  컬럼: {list(df.columns)}")
    print()

    # 중복 제거: 동일 OD 내에서 동일 노선 조합(route_ids)은 첫 번째만 유지
    print("중복 제거 중 (동일 OD + 동일 노선 조합)...")
    before_dedup = len(df)
    df = df.drop_duplicates(subset=['od_id', 'route_ids'], keep='first')
    after_dedup = len(df)
    removed = before_dedup - after_dedup
    print(f"  제거 전: {before_dedup:,}")
    print(f"  제거 후: {after_dedup:,}")
    print(f"  중복 제거: {removed:,} ({removed/before_dedup*100:.1f}%)")
    print(f"  OD당 평균 대안: {after_dedup / df['od_id'].nunique():.2f}")
    print()

    # alt_id 재정렬 (중복 제거 후 연속적으로)
    df = df.sort_values(['od_id', 'total_duration'])
    df['alt_id'] = df.groupby('od_id').cumcount().astype('int8')

    # 저장
    print(f"저장 중: {OTP_ALTERNATIVES_FILE}")
    df.to_parquet(OTP_ALTERNATIVES_FILE, index=False)
    file_size = OTP_ALTERNATIVES_FILE.stat().st_size / (1024**3)
    print(f"  크기: {file_size:.2f} GB")
    print()

    # 실패 OD 저장
    print(f"실패 OD 저장 중: {FAILED_OD_FILE}")
    failed_df = pd.DataFrame({'od_id': failed_od_ids})
    failed_df['od_id'] = failed_df['od_id'].astype('int32')
    failed_df.to_parquet(FAILED_OD_FILE, index=False)
    print(f"  경로 없음: {len(failed_od_ids):,}건")
    print()

    # 통계
    print("=" * 70)
    print("파싱 결과 통계")
    print("=" * 70)
    print(f"총 OD: {total_lines:,}")
    print(f"성공 (경로 있음): {len(success_od_ids):,} ({len(success_od_ids)/total_lines*100:.1f}%)")
    print(f"실패 (경로 없음): {len(failed_od_ids):,} ({len(failed_od_ids)/total_lines*100:.1f}%)")
    print()
    print(f"총 경로 수 (중복 제거 전): {total_itineraries:,}")
    print(f"총 경로 수 (중복 제거 후): {len(df):,}")
    print(f"OD당 평균 경로: {len(df)/len(success_od_ids):.2f}개")
    alts_per_od = df.groupby('od_id').size()
    print(f"OD당 최대 경로: {alts_per_od.max()}개")
    print()

    # 경로 수 분포 (중복 제거 후)
    from collections import Counter
    dedup_counts = df.groupby('od_id').size().tolist()
    count_dist = Counter(dedup_counts)
    print("경로 수 분포 (중복 제거 후):")
    for n in sorted(count_dist.keys()):
        print(f"  {n}개: {count_dist[n]:,} ({count_dist[n]/len(success_od_ids)*100:.1f}%)")
    print()

    # 샘플 출력
    print("=" * 70)
    print("샘플 데이터 (첫 3행)")
    print("=" * 70)
    sample = df.head(3)
    for idx, row in sample.iterrows():
        print(f"\n[alt {row['alt_id']}] od_id={row['od_id']}")
        print(f"  시간: 총 {row['total_duration']}초 = 차내 {row['ride_time_sec']} + 도보 {row['walk_time_sec']} + 대기 {row['wait_time_sec']}")
        print(f"  환승: {row['n_transfers']}회, 지하철: {'있음' if row['has_subway'] else '없음'}")
        print(f"  수단: {row['modes']}")
        print(f"  노선: {row['route_names']}")
        print(f"  노선ID: {row['route_ids']}")

    return success_od_ids, failed_od_ids


def filter_trip_attributes(success_od_ids):
    """경로 있는 OD만 trip_attributes에서 필터링"""

    print()
    print("=" * 70)
    print("trip_attributes 필터링")
    print("=" * 70)

    # trip_attributes 로드
    print(f"로드 중: {TRIP_ATTRS_FILTERED_FILE}")
    trip_attrs = pd.read_parquet(TRIP_ATTRS_FILTERED_FILE)
    print(f"  원본 체인: {len(trip_attrs):,}")

    # 성공 OD만 필터링
    success_od_set = set(success_od_ids)
    trip_attrs_matched = trip_attrs[trip_attrs['od_id'].isin(success_od_set)]
    print(f"  매칭 체인: {len(trip_attrs_matched):,}")

    # 저장
    print(f"저장 중: {TRIP_ATTRS_MATCHED_FILE}")
    trip_attrs_matched.to_parquet(TRIP_ATTRS_MATCHED_FILE, index=False)
    print()

    # 통계
    print(f"체인 필터링 결과:")
    print(f"  원본: {len(trip_attrs):,}")
    print(f"  매칭: {len(trip_attrs_matched):,} ({len(trip_attrs_matched)/len(trip_attrs)*100:.1f}%)")
    print(f"  제외: {len(trip_attrs) - len(trip_attrs_matched):,}")
    print()

    return trip_attrs_matched


def analyze_failed_ods(failed_od_ids):
    """경로 없는 OD 원인 분석 (간단히)"""

    print("=" * 70)
    print("경로 없음 OD 분석")
    print("=" * 70)

    # od_pairs_filtered.csv 로드
    od_pairs_file = Path(r"C:\Users\USER\OneDrive\Desktop\연구실\강릉ITS\korean-otp\data\od_pairs_filtered.csv")
    od_pairs = pd.read_csv(od_pairs_file)

    # 실패 OD만 추출
    failed_ods = od_pairs.iloc[failed_od_ids].copy()

    # 출발 시간 분포
    print("실패 OD 출발 시간 분포:")
    failed_ods['hour'] = failed_ods['departure_time'].apply(lambda x: int(x.split(':')[0]))
    hour_dist = failed_ods['hour'].value_counts().sort_index()
    for hour, count in hour_dist.items():
        pct = count / len(failed_ods) * 100
        bar = '#' * int(pct / 2)
        print(f"  {hour:02d}시: {count:,} ({pct:.1f}%) {bar}")
    print()

    # 심야 시간대 비율 (23시~05시)
    night_hours = [23, 0, 1, 2, 3, 4, 5]
    night_count = failed_ods[failed_ods['hour'].isin(night_hours)].shape[0]
    print(f"심야 시간대 (23-05시): {night_count:,} ({night_count/len(failed_ods)*100:.1f}%)")
    print()


def main():
    print()
    print("=" * 70)
    print("  Phase 2 Step 4: OTP 결과 파싱 + 속성 추출")
    print("=" * 70)
    print_iteration_info()
    print(f"  NDJSON: {OTP_RESULT}")
    print(f"  출력 디렉토리: {paths.output_dir}")
    print()

    # 1. OTP 결과 파싱
    success_od_ids, failed_od_ids = parse_otp_results()

    # 2. trip_attributes 필터링
    filter_trip_attributes(success_od_ids)

    # 3. 실패 OD 분석
    if failed_od_ids:
        analyze_failed_ods(failed_od_ids)

    print("=" * 70)
    print("Step 4 완료!")
    print("=" * 70)
    print()
    print("산출물:")
    print(f"  - {OTP_ALTERNATIVES_FILE}")
    print(f"  - {FAILED_OD_FILE}")
    print(f"  - {TRIP_ATTRS_MATCHED_FILE}")
    print()
    print("추출된 컬럼:")
    print("  - od_id, alt_id")
    print("  - total_duration, ride_time_sec, walk_time_sec, wait_time_sec")
    print("  - n_transfers, has_subway")
    print("  - modes, route_ids, route_names")
    print("  - stop_sequence, boarding_stops, alighting_stops")
    print("  - generalized_cost, walk_distance")
    print()


if __name__ == "__main__":
    main()
