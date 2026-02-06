"""
Step 5: TCD 관측 경로 vs OTP 대안 경로 유사도 계산

입력:
- trip_attributes_matched.parquet (1,320,030 체인)
- otp_alternatives.parquet (4,477,498 경로)
- tcd_leg_traversed_stops.parquet (경유 정류장)
- gtfs_tcd_stop_mapping.parquet (정류장 ID 매핑)
- gtfs_tcd_route_mapping.parquet (노선 ID 매핑)

출력:
- similarity_results.parquet (체인별 × 대안별 유사도)
- similarity_summary.parquet (OD별 최선 매칭 요약)

유사도 지표 (4개 레벨):
- Level 1: Exact Match (완전 일치)
- Level 2: Route/Mode Sequence Similarity
- Level 3: Stop-based Similarity (Jaccard, LCS, BAMR)
- Level 4: Temporal Similarity

실행:
    python scripts/matching/step5_calculate_similarity.py
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict
import time

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# 입력 파일
TRIP_ATTRS_FILE = OUTPUT_DIR / "trip_attributes_matched.parquet"
OTP_ALTS_FILE = OUTPUT_DIR / "otp_alternatives.parquet"
TCD_STOPS_FILE = OUTPUT_DIR / "tcd_leg_traversed_stops.parquet"
STOP_MAPPING_FILE = OUTPUT_DIR / "gtfs_tcd_stop_mapping.parquet"
ROUTE_MAPPING_FILE = OUTPUT_DIR / "gtfs_tcd_route_mapping.parquet"

# 출력 파일
SIMILARITY_RESULTS_FILE = OUTPUT_DIR / "similarity_results.parquet"
SIMILARITY_SUMMARY_FILE = OUTPUT_DIR / "similarity_summary.parquet"


def load_id_mappings():
    """ID 매핑 테이블 로드 (버스 + 지하철)"""
    print("ID 매핑 로드 중...")

    # 정류장 매핑: TCD ID → GTFS ID (역방향도 필요)
    stop_map = pd.read_parquet(STOP_MAPPING_FILE)
    tcd_to_gtfs_stop = {}
    gtfs_to_tcd_stop = {}

    for _, row in stop_map.iterrows():
        gtfs_id = row['gtfs_stop_id']
        tcd_id = str(row['tcd_stop_id'])
        tcd_to_gtfs_stop[tcd_id] = gtfs_id
        gtfs_to_tcd_stop[gtfs_id] = tcd_id

    print(f"  정류장 매핑: {len(tcd_to_gtfs_stop):,}개")

    # 버스 노선 매핑: TCD ID → GTFS ID
    route_map = pd.read_parquet(ROUTE_MAPPING_FILE)
    tcd_to_gtfs_route = {}
    gtfs_to_tcd_route = {}

    for _, row in route_map.iterrows():
        gtfs_id = row['gtfs_route_id']
        tcd_id = str(row['tcd_route_id'])
        tcd_to_gtfs_route[tcd_id] = gtfs_id
        gtfs_to_tcd_route[gtfs_id] = tcd_id

    bus_count = len(tcd_to_gtfs_route)
    print(f"  버스 노선 매핑: {bus_count:,}개")

    # 지하철 노선 매핑 추가
    subway_mapping_file = OUTPUT_DIR / "subway_line_mapping.json"
    if subway_mapping_file.exists():
        # GTFS에서 지하철 route_id 로드
        gtfs_routes_file = PROJECT_ROOT.parent / "korean-otp" / "data" / "gtfs" / "routes.txt"
        if gtfs_routes_file.exists():
            gtfs_routes = pd.read_csv(gtfs_routes_file)
            subway_routes = gtfs_routes[gtfs_routes['route_type'].isin([1, 2])]
            subway_by_name = subway_routes.groupby('route_short_name').first().reset_index()
            gtfs_name_to_id = dict(zip(subway_by_name['route_short_name'], subway_by_name['route_id']))

            # 지하철 매핑 JSON 로드
            with open(subway_mapping_file, 'r', encoding='utf-8') as f:
                subway_mapping = json.load(f)

            subway_count = 0
            for tcd_id, info in subway_mapping.items():
                gtfs_name = info['gtfs_name']
                if gtfs_name in gtfs_name_to_id:
                    gtfs_route_id = gtfs_name_to_id[gtfs_name]
                    tcd_to_gtfs_route[tcd_id] = gtfs_route_id
                    gtfs_to_tcd_route[gtfs_route_id] = tcd_id
                    subway_count += 1

            print(f"  지하철 노선 매핑: {subway_count}개")

    print(f"  총 노선 매핑: {len(tcd_to_gtfs_route):,}개")

    return {
        'tcd_to_gtfs_stop': tcd_to_gtfs_stop,
        'gtfs_to_tcd_stop': gtfs_to_tcd_stop,
        'tcd_to_gtfs_route': tcd_to_gtfs_route,
        'gtfs_to_tcd_route': gtfs_to_tcd_route,
    }


def extract_stop_code(gtfs_id):
    """
    GTFS stop ID에서 정류장 고유 코드 추출 (prefix 무시)

    다른 지역 코드(1100, 3100 등)가 같은 정류장을 가리킬 수 있음:
    - "1:BS_1100_116000008" → "116000008"
    - "BS_3100_116000008" → "116000008"
    - "BS_1100_116000008" → "116000008"

    지하철역도 동일하게 처리:
    - "1:SW_1100_123456789" → "123456789"
    """
    if not gtfs_id:
        return None
    # 1: prefix 제거
    if ':' in gtfs_id:
        gtfs_id = gtfs_id.split(':', 1)[1]
    # BS_XXXX_YYYYYYYYY 또는 SW_XXXX_YYYYYYYYY에서 마지막 부분 추출
    parts = gtfs_id.split('_')
    if len(parts) >= 3:
        return parts[2]
    return gtfs_id


def extract_route_code(gtfs_id):
    """
    GTFS route ID에서 노선 고유 코드 추출 (prefix 무시)

    - "1:BR_1100_100100033" → "100100033"
    - "BR_3100_234001719" → "234001719"

    주의: 같은 노선이 다른 코드를 가질 수 있음 (지역 코드에 따라)
    → 노선 비교는 코드보다는 short_name으로 하는 것이 정확
    """
    if not gtfs_id:
        return None
    if ':' in gtfs_id:
        gtfs_id = gtfs_id.split(':', 1)[1]
    parts = gtfs_id.split('_')
    if len(parts) >= 3:
        return parts[2]
    return gtfs_id


def parse_gtfs_stop_id(gtfs_id):
    """
    GTFS stop ID에서 순수 ID 추출 (하위 호환용)
    "1:BS_1100_100000001" → "BS_1100_100000001"
    """
    if gtfs_id and ':' in gtfs_id:
        return gtfs_id.split(':', 1)[1]
    return gtfs_id


def parse_gtfs_route_id(gtfs_id):
    """
    GTFS route ID에서 순수 ID 추출 (하위 호환용)
    "1:BR_1100_100100001" → "BR_1100_100100001"
    """
    if gtfs_id and ':' in gtfs_id:
        return gtfs_id.split(':', 1)[1]
    return gtfs_id


def lcs_length(seq1, seq2):
    """
    두 시퀀스의 LCS (Longest Common Subsequence) 길이
    동적 프로그래밍 O(nm)
    """
    if not seq1 or not seq2:
        return 0

    n, m = len(seq1), len(seq2)
    # 메모리 최적화: 2행만 사용
    prev = [0] * (m + 1)
    curr = [0] * (m + 1)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq1[i-1] == seq2[j-1]:
                curr[j] = prev[j-1] + 1
            else:
                curr[j] = max(prev[j], curr[j-1])
        prev, curr = curr, [0] * (m + 1)

    return prev[m] if n > 0 else 0


def jaccard_index(set1, set2):
    """
    두 집합의 Jaccard Index
    |A ∩ B| / |A ∪ B|
    """
    if not set1 and not set2:
        return 1.0  # 둘 다 빈 집합이면 동일
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def lcs_similarity(seq1, seq2):
    """
    LCS 기반 유사도
    2 * LCS(X, Y) / (|X| + |Y|)
    """
    if not seq1 and not seq2:
        return 1.0
    if not seq1 or not seq2:
        return 0.0

    lcs_len = lcs_length(seq1, seq2)
    return 2 * lcs_len / (len(seq1) + len(seq2))
    


def calculate_similarity(tcd_data, otp_data, mappings):
    """
    단일 TCD 체인 vs 단일 OTP 대안의 유사도 계산

    Args:
        tcd_data: dict with keys: routes, modes, boarding_stops, alighting_stops, traversed_stops
        otp_data: dict with keys: routes, modes, boarding_stops, alighting_stops, stop_sequence
        mappings: ID 매핑 딕셔너리

    Returns:
        dict with all similarity metrics
    """
    results = {}

    # === ID 변환 ===
    # TCD → GTFS 변환 후 코드 추출 (prefix 무시하고 비교하기 위해)

    # 노선: TCD route ID → GTFS route ID → route code
    tcd_routes_code = []
    for r in tcd_data['routes']:
        gtfs_r = mappings['tcd_to_gtfs_route'].get(str(r))
        if gtfs_r:
            tcd_routes_code.append(extract_route_code(gtfs_r))

    # OTP routes에서 코드 추출
    otp_routes_code = [extract_route_code(r) for r in otp_data['routes']]

    # 정류장: TCD stop ID → GTFS stop ID → stop code
    # 코드로 비교해야 1100 vs 3100 prefix 문제 해결됨
    tcd_boarding_code = []
    for s in tcd_data['boarding_stops']:
        gtfs_s = mappings['tcd_to_gtfs_stop'].get(str(s))
        if gtfs_s:
            tcd_boarding_code.append(extract_stop_code(gtfs_s))

    tcd_alighting_code = []
    for s in tcd_data['alighting_stops']:
        gtfs_s = mappings['tcd_to_gtfs_stop'].get(str(s))
        if gtfs_s:
            tcd_alighting_code.append(extract_stop_code(gtfs_s))

    # OTP 정류장에서 코드 추출
    otp_boarding_code = [extract_stop_code(s) for s in otp_data['boarding_stops']]
    otp_alighting_code = [extract_stop_code(s) for s in otp_data['alighting_stops']]
    otp_stop_seq_code = [extract_stop_code(s) for s in otp_data['stop_sequence']]

    # TCD traversed stops → GTFS → code (버스만 있음)
    tcd_stop_seq_code = []
    if tcd_data['traversed_stops']:
        for s in tcd_data['traversed_stops']:
            gtfs_s = mappings['tcd_to_gtfs_stop'].get(str(s))
            if gtfs_s:
                tcd_stop_seq_code.append(extract_stop_code(gtfs_s))

    # === Level 1: Exact Match ===
    # 노선 시퀀스(코드)가 완전 일치하고 승하차 정류장(코드)도 일치
    # 주의: 코드로 비교하여 1100 vs 3100 prefix 차이 무시
    routes_match = (tcd_routes_code == otp_routes_code)
    modes_match = (tcd_data['modes'] == otp_data['modes'])
    boarding_match = (tcd_boarding_code == otp_boarding_code)
    alighting_match = (tcd_alighting_code == otp_alighting_code)

    results['exact_match'] = 1 if (routes_match and modes_match and
                                    boarding_match and alighting_match) else 0

    # === Level 2: Structural Similarity ===
    # 2a. Route Sequence Similarity (LCS 기반)
    results['sim_route_seq'] = lcs_similarity(tcd_routes_code, otp_routes_code)

    # 2b. Mode Sequence Similarity
    results['sim_mode_seq'] = lcs_similarity(tcd_data['modes'], otp_data['modes'])

    # 2c. Transfer Count Match
    tcd_transfers = len(tcd_data['routes']) - 1 if tcd_data['routes'] else 0
    otp_transfers = otp_data['n_transfers']
    results['transfer_match'] = 1 if tcd_transfers == otp_transfers else 0
    results['transfer_diff'] = abs(tcd_transfers - otp_transfers)

    # === Level 3: Stop-based Similarity ===
    # 3a. Jaccard Index (정류장 집합)
    # 전체 경로의 정류장 집합 비교 (코드 기준)
    tcd_all_stops = set(s for s in tcd_boarding_code + tcd_alighting_code if s)
    otp_all_stops = set(s for s in otp_boarding_code + otp_alighting_code if s)
    results['sim_jaccard_ba'] = jaccard_index(tcd_all_stops, otp_all_stops)

    # traversed stops가 있으면 전체 시퀀스로 Jaccard
    if tcd_stop_seq_code:
        tcd_stop_set = set(s for s in tcd_stop_seq_code if s)
        otp_stop_set = set(s for s in otp_stop_seq_code if s)
        results['sim_jaccard_full'] = jaccard_index(tcd_stop_set, otp_stop_set)
    else:
        results['sim_jaccard_full'] = results['sim_jaccard_ba']  # fallback

    # 3b. LCS Ratio (정류장 시퀀스)
    if tcd_stop_seq_code:
        # 버스: 경유 정류장 시퀀스로 LCS
        results['sim_lcs'] = lcs_similarity(tcd_stop_seq_code, otp_stop_seq_code)
    else:
        # 지하철 등 traversed가 없으면 승하차만으로 계산
        # 이 경우 LCS는 승하차점 일치 여부만 반영
        tcd_ba_seq = [s for s in tcd_boarding_code + tcd_alighting_code if s]
        otp_ba_seq = [s for s in otp_boarding_code + otp_alighting_code if s]
        results['sim_lcs'] = lcs_similarity(tcd_ba_seq, otp_ba_seq)

    # 3c. Boarding/Alighting Match Rate
    n_legs = max(len(tcd_boarding_code), len(otp_boarding_code), 1)

    boarding_matches = sum(1 for t, o in zip(tcd_boarding_code, otp_boarding_code) if t and o and t == o)
    alighting_matches = sum(1 for t, o in zip(tcd_alighting_code, otp_alighting_code) if t and o and t == o)

    results['sim_boarding_alighting'] = (boarding_matches + alighting_matches) / (2 * n_legs)

    # 디버깅용: 매핑 성공률
    results['tcd_routes_mapped'] = len(tcd_routes_code)
    results['tcd_stops_mapped'] = len(tcd_boarding_code) + len(tcd_alighting_code)

    # === Level 4: Temporal Similarity ===
    # TCD에서 실제 소요시간, OTP에서 예측 소요시간 비교
    tcd_duration = tcd_data.get('total_duration', 0)
    otp_duration = otp_data.get('total_duration', 0)

    if tcd_duration > 0 and otp_duration > 0:
        # 시간 차이 비율 (0에 가까울수록 유사)
        time_diff = abs(tcd_duration - otp_duration)
        baseline = max(tcd_duration, otp_duration)  # 둘 중 큰 값 기준
        results['sim_time'] = 1.0 - min(1.0, time_diff / baseline)
        results['time_diff_sec'] = time_diff
    else:
        results['sim_time'] = 0.0
        results['time_diff_sec'] = -1

    # === 종합 유사도 (가중 평균) ===
    # 가중치: route_seq(0.25), mode_seq(0.10), jaccard(0.20), lcs(0.25), bamr(0.10), time(0.10)
    results['sim_total'] = (
        0.25 * results['sim_route_seq'] +
        0.10 * results['sim_mode_seq'] +
        0.20 * results['sim_jaccard_full'] +
        0.25 * results['sim_lcs'] +
        0.10 * results['sim_boarding_alighting'] +
        0.10 * results['sim_time']
    )

    return results


def main():
    print()
    print("=" * 70)
    print("  Phase 2 Step 5: 경로 유사도 계산")
    print("=" * 70)
    print()

    start_time = time.time()

    # 1. ID 매핑 로드
    mappings = load_id_mappings()
    print()

    # 2. 데이터 로드
    print("데이터 로드 중...")

    # TCD 체인 정보
    trips = pd.read_parquet(TRIP_ATTRS_FILE)
    print(f"  TCD 체인: {len(trips):,}")

    # OTP 대안 경로
    otp_alts = pd.read_parquet(OTP_ALTS_FILE)
    print(f"  OTP 대안: {len(otp_alts):,}")

    # TCD 경유 정류장 (버스만)
    tcd_stops = pd.read_parquet(TCD_STOPS_FILE)
    tcd_stops_success = tcd_stops[tcd_stops['status'] == 'ok']
    print(f"  TCD 경유 정류장: {len(tcd_stops_success):,} (성공 레그)")
    print()

    # 3. TCD 경유 정류장을 체인별로 그룹핑
    print("TCD 경유 정류장 집계 중...")
    tcd_traversed_by_chain = {}
    for _, row in tcd_stops_success.iterrows():
        chain_id = row['chain_id']
        if chain_id not in tcd_traversed_by_chain:
            tcd_traversed_by_chain[chain_id] = []
        tcd_traversed_by_chain[chain_id].extend(row['traversed_stops'])
    print(f"  체인별 집계: {len(tcd_traversed_by_chain):,}개")
    print()

    # 4. OTP 대안을 od_id별로 그룹핑
    print("OTP 대안 그룹핑 중...")
    otp_by_od = defaultdict(list)
    for _, row in otp_alts.iterrows():
        od_id = row['od_id']
        otp_by_od[od_id].append({
            'alt_id': row['alt_id'],
            'routes': json.loads(row['route_ids']),
            'modes': json.loads(row['modes']),
            'boarding_stops': json.loads(row['boarding_stops']),
            'alighting_stops': json.loads(row['alighting_stops']),
            'stop_sequence': json.loads(row['stop_sequence']),
            'n_transfers': row['n_transfers'],
            'total_duration': row['total_duration'],
            'ride_time_sec': row['ride_time_sec'],
            'walk_time_sec': row['walk_time_sec'],
            'generalized_cost': row['generalized_cost'],
        })
    print(f"  OD별 그룹: {len(otp_by_od):,}개")
    print()

    # 5. 유사도 계산
    print("유사도 계산 시작...")
    print(f"  TCD 체인 × OTP 대안 조합")
    print()

    all_results = []
    stats = {
        'total_pairs': 0,
        'exact_matches': 0,
        'route_matches': 0,
        'transfer_matches': 0,
    }

    # 진행률 표시용
    batch_size = 10000
    processed = 0

    for idx, trip in tqdm(trips.iterrows(), total=len(trips), desc="유사도 계산"):
        chain_id = trip['chain_id']
        od_id = trip['od_id']

        # TCD 데이터 준비
        tcd_data = {
            'routes': json.loads(trip['route_sequence']),
            'modes': json.loads(trip['mode_sequence']),
            'boarding_stops': json.loads(trip['boarding_stops']),
            'alighting_stops': json.loads(trip['alighting_stops']),
            'traversed_stops': tcd_traversed_by_chain.get(chain_id, []),
            'total_duration': trip['total_duration'],
        }

        # 해당 OD의 OTP 대안들 가져오기
        otp_alternatives = otp_by_od.get(od_id, [])

        if not otp_alternatives:
            continue

        # 각 대안과 유사도 계산
        best_sim = -1
        best_alt_id = -1

        for otp_data in otp_alternatives:
            sim = calculate_similarity(tcd_data, otp_data, mappings)

            stats['total_pairs'] += 1
            if sim['exact_match']:
                stats['exact_matches'] += 1
            if sim['sim_route_seq'] >= 0.99:
                stats['route_matches'] += 1
            if sim['transfer_match']:
                stats['transfer_matches'] += 1

            # 결과 저장
            result_row = {
                'chain_id': chain_id,
                'od_id': od_id,
                'alt_id': otp_data['alt_id'],
                'otp_duration': otp_data['total_duration'],
                'otp_n_transfers': otp_data['n_transfers'],
                'otp_generalized_cost': otp_data['generalized_cost'],
                **sim
            }
            all_results.append(result_row)

            if sim['sim_total'] > best_sim:
                best_sim = sim['sim_total']
                best_alt_id = otp_data['alt_id']

        processed += 1

        # 중간 저장 (메모리 관리)
        if processed % 100000 == 0:
            elapsed = time.time() - start_time
            rate = processed / elapsed
            remaining = (len(trips) - processed) / rate
            print(f"\n  {processed:,}/{len(trips):,} | "
                  f"결과: {len(all_results):,} | "
                  f"정확일치: {stats['exact_matches']:,} | "
                  f"남은시간: {remaining/60:.1f}분")

    elapsed = time.time() - start_time
    print(f"\n계산 완료: {elapsed/60:.1f}분")
    print()

    # 6. 결과 DataFrame 생성
    print("결과 저장 중...")
    df = pd.DataFrame(all_results)

    # 데이터 타입 최적화
    df['chain_id'] = df['chain_id'].astype('int32')
    df['od_id'] = df['od_id'].astype('int32')
    df['alt_id'] = df['alt_id'].astype('int8')
    df['exact_match'] = df['exact_match'].astype('int8')
    df['transfer_match'] = df['transfer_match'].astype('int8')
    df['transfer_diff'] = df['transfer_diff'].astype('int8')

    # float 컬럼 최적화
    float_cols = ['sim_route_seq', 'sim_mode_seq', 'sim_jaccard_ba', 'sim_jaccard_full',
                  'sim_lcs', 'sim_boarding_alighting', 'sim_time', 'sim_total']
    for col in float_cols:
        df[col] = df[col].astype('float32')

    print(f"  총 행: {len(df):,}")
    print(f"  컬럼: {list(df.columns)}")

    # 저장
    df.to_parquet(SIMILARITY_RESULTS_FILE, index=False)
    file_size = SIMILARITY_RESULTS_FILE.stat().st_size / (1024**2)
    print(f"  저장: {SIMILARITY_RESULTS_FILE}")
    print(f"  크기: {file_size:.1f} MB")
    print()

    # 7. 요약 통계 생성
    print("=" * 70)
    print("유사도 통계")
    print("=" * 70)

    print(f"\n총 체인-대안 쌍: {stats['total_pairs']:,}")
    print(f"완전 일치 (Exact Match): {stats['exact_matches']:,} ({stats['exact_matches']/stats['total_pairs']*100:.2f}%)")
    print(f"노선 일치 (RSS≥0.99): {stats['route_matches']:,} ({stats['route_matches']/stats['total_pairs']*100:.2f}%)")
    print(f"환승횟수 일치: {stats['transfer_matches']:,} ({stats['transfer_matches']/stats['total_pairs']*100:.2f}%)")
    print()

    # 유사도 분포
    print("유사도 분포:")
    for col in ['sim_total', 'sim_route_seq', 'sim_lcs', 'sim_jaccard_full']:
        print(f"\n  {col}:")
        print(f"    평균: {df[col].mean():.4f}")
        print(f"    중앙값: {df[col].median():.4f}")
        print(f"    표준편차: {df[col].std():.4f}")
        print(f"    최소: {df[col].min():.4f}, 최대: {df[col].max():.4f}")

    # 8. OD별 최선 매칭 요약
    print()
    print("OD별 최선 매칭 요약 생성 중...")

    # 각 체인에서 가장 유사한 대안 선택
    best_matches = df.loc[df.groupby('chain_id')['sim_total'].idxmax()]

    summary = best_matches[['chain_id', 'od_id', 'alt_id', 'exact_match',
                            'sim_total', 'sim_route_seq', 'sim_lcs']].copy()
    summary.to_parquet(SIMILARITY_SUMMARY_FILE, index=False)

    print(f"  체인 수: {len(summary):,}")
    print(f"  저장: {SIMILARITY_SUMMARY_FILE}")
    print()

    # 최선 매칭 통계
    print("최선 매칭 통계 (체인당 1개):")
    print(f"  완전 일치 체인: {summary['exact_match'].sum():,} ({summary['exact_match'].mean()*100:.2f}%)")
    print(f"  평균 최선 유사도: {summary['sim_total'].mean():.4f}")
    print(f"  최선 유사도 중앙값: {summary['sim_total'].median():.4f}")

    # 유사도 구간별 분포
    print()
    print("최선 유사도 구간 분포:")
    bins = [0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
    labels = ['0-50%', '50-60%', '60-70%', '70-80%', '80-90%', '90-95%', '95-100%']
    summary['sim_bin'] = pd.cut(summary['sim_total'], bins=bins, labels=labels)
    dist = summary['sim_bin'].value_counts().sort_index()
    for label, count in dist.items():
        pct = count / len(summary) * 100
        bar = '█' * int(pct / 2)
        print(f"  {label}: {count:,} ({pct:.1f}%) {bar}")

    print()
    print("=" * 70)
    print("Step 5 완료!")
    print("=" * 70)
    print()
    print("산출물:")
    print(f"  - {SIMILARITY_RESULTS_FILE}")
    print(f"  - {SIMILARITY_SUMMARY_FILE}")
    print()


if __name__ == "__main__":
    main()
