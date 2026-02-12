"""
전체 Phase 2 데이터로 OTP 1순위 vs Best Match 베이스라인 비교

목적: 1.32M 체인 전체에서 generalized_cost 기준 OTP 1순위 추천 경로의
      exact_match/sim_total을 유형별로 계산

입력:
- korean-otp/batch_result_iter0.ndjson (32.6GB, Phase 2 원본)
- output/trip_attributes_filtered.parquet (1,466,691 체인)
- output/gtfs_tcd_route_mapping.parquet

출력: 콘솔에 전체/유형별 통계
"""

import json
import re
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent.parent
OTP_DIR = PROJECT_ROOT.parent / "korean-otp"
NDJSON_FILE = OTP_DIR / "batch_result_iter0.ndjson"

print("=" * 70)
print("  전체 Phase 2 데이터 OTP 1순위 vs Best Match 분석")
print("=" * 70)
print()

# ─────────────────────────────────────────────────────
# 1. 매핑 테이블 로드
# ─────────────────────────────────────────────────────
print("[1/4] 매핑 테이블 로드...")

# Route mapping: GTFS → TCD
route_map_df = pd.read_parquet(PROJECT_ROOT / "output" / "gtfs_tcd_route_mapping.parquet")
gtfs_to_tcd = {}
for _, row in route_map_df.iterrows():
    # OTP 출력은 "1:BR_1100_xxx" 형태, 매핑은 "BR_1100_xxx"
    gtfs_id = row['gtfs_route_id']
    tcd_id = row['tcd_route_id']
    gtfs_to_tcd[gtfs_id] = tcd_id
    gtfs_to_tcd[f"1:{gtfs_id}"] = tcd_id  # "1:" prefix 포함 버전도 등록
print(f"  노선 매핑: {len(route_map_df)} 쌍")

# ─────────────────────────────────────────────────────
# 2. trip_attributes 로드
# ─────────────────────────────────────────────────────
print("[2/4] trip_attributes 로드...")
trip_attrs = pd.read_parquet(PROJECT_ROOT / "output" / "trip_attributes_filtered.parquet")
print(f"  체인: {len(trip_attrs):,}")

# od_id → (chain_id, user_type, route_sequence, mode_sequence, duration) 매핑
od_to_chain = {}
for _, row in trip_attrs.iterrows():
    tcd_routes = json.loads(row['route_sequence']) if isinstance(row['route_sequence'], str) else row['route_sequence']
    tcd_modes = json.loads(row['mode_sequence']) if isinstance(row['mode_sequence'], str) else row['mode_sequence']
    od_to_chain[row['od_id']] = {
        'chain_id': row['chain_id'],
        'user_type': row['user_type'],
        'tcd_routes': tcd_routes,
        'tcd_modes': tcd_modes,
        'tcd_duration': row['total_duration'],
        'n_transfers': row['n_transfers'],
    }
print(f"  OD 매핑 완료: {len(od_to_chain):,}")
print()

# ─────────────────────────────────────────────────────
# 3. NDJSON 파싱 (단일 패스, 필요 필드만)
# ─────────────────────────────────────────────────────
print("[3/4] NDJSON 파싱 (32.6GB, 단일 패스)...")
print(f"  파일: {NDJSON_FILE}")

# points 필드 제거 패턴 (JSON 파싱 문제 방지)
points_pattern = re.compile(r'"points":"[^"]*(?:\\.[^"]*)*"')

def extract_route_ids(legs):
    """legs에서 transit route GTFS ID만 추출"""
    route_ids = []
    modes = []
    for leg in legs:
        mode = leg.get('mode', '')
        if mode in ('BUS', 'SUBWAY', 'RAIL', 'TRAM', 'FERRY'):
            route = leg.get('route', {})
            if route:
                route_ids.append(route.get('gtfsId', ''))
            modes.append(mode)
    return route_ids, modes

def compute_similarity(tcd_info, otp_routes_mapped, otp_modes, otp_duration):
    """TCD vs OTP 경로 유사도 계산 (간이 버전)"""
    tcd_routes = tcd_info['tcd_routes']
    tcd_modes = tcd_info['tcd_modes']
    tcd_dur = tcd_info['tcd_duration']

    # 1. Exact Match (노선 시퀀스 완전 일치)
    exact_match = 1 if tcd_routes == otp_routes_mapped else 0

    # 2. Mode Match (수단 시퀀스 완전 일치)
    # OTP modes를 TCD 형식으로 변환
    otp_modes_mapped = []
    for m in otp_modes:
        if m in ('SUBWAY', 'RAIL'):
            otp_modes_mapped.append('SUBWAY')
        else:
            otp_modes_mapped.append('BUS')
    tcd_modes_mapped = tcd_modes  # 이미 BUS/SUBWAY

    mode_match = 1 if tcd_modes_mapped == otp_modes_mapped else 0

    # 3. Route Sequence Similarity (LCS 기반)
    def lcs_length(a, b):
        if not a or not b:
            return 0
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]

    max_len = max(len(tcd_routes), len(otp_routes_mapped))
    if max_len > 0:
        route_lcs = lcs_length(tcd_routes, otp_routes_mapped) / max_len
    else:
        route_lcs = 1.0

    # 4. Jaccard (노선 집합 기반)
    tcd_set = set(tcd_routes)
    otp_set = set(otp_routes_mapped)
    if tcd_set or otp_set:
        jaccard = len(tcd_set & otp_set) / len(tcd_set | otp_set)
    else:
        jaccard = 1.0

    # 5. Time Similarity
    if tcd_dur > 0:
        time_sim = 1 - min(abs(tcd_dur - otp_duration) / tcd_dur, 1.0)
    else:
        time_sim = 0.0

    # 6. Mode Sequence LCS
    max_mode_len = max(len(tcd_modes_mapped), len(otp_modes_mapped))
    if max_mode_len > 0:
        mode_lcs = lcs_length(tcd_modes_mapped, otp_modes_mapped) / max_mode_len
    else:
        mode_lcs = 1.0

    # sim_total (가중 평균) - Phase 2와 동일 가중치
    # route_seq(0.25) + mode_seq(0.10) + jaccard(0.20) + lcs(0.25) + bamr(0.10) + time(0.10)
    # BAMR은 stop 수준 비교가 필요해서 여기선 jaccard로 대체 (근사)
    sim_total = (route_lcs * 0.25 + mode_lcs * 0.10 + jaccard * 0.20 +
                 route_lcs * 0.25 + jaccard * 0.10 + time_sim * 0.10)

    return {
        'exact_match': exact_match,
        'route_lcs': route_lcs,
        'mode_lcs': mode_lcs,
        'jaccard': jaccard,
        'time_sim': time_sim,
        'sim_total': sim_total,
    }

# 결과 저장: chain_id → {best_match: {}, otp_first: {}}
results = {}
failed_count = 0
success_count = 0
parse_errors = 0

start_time = time.time()

# 파일 크기로 대략적 라인 수 추정 (진행률용)
file_size = NDJSON_FILE.stat().st_size
estimated_lines = 1_263_000  # Phase 2 OD 수

with open(NDJSON_FILE, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(tqdm(f, total=estimated_lines, desc="파싱")):
        try:
            # JSON 파싱
            line_fixed = points_pattern.sub('"points":""', line.strip())
            data = json.loads(line_fixed)
            od_id = data['id']

            # 이 OD에 대한 TCD 정보
            if od_id not in od_to_chain:
                continue

            tcd_info = od_to_chain[od_id]
            itineraries = data['data']['plan'].get('itineraries', [])

            if not itineraries:
                failed_count += 1
                continue

            success_count += 1

            # 각 대안의 유사도 + generalized_cost 계산
            alternatives = []
            seen_routes = set()

            for itin in itineraries:
                legs = itin.get('legs', [])
                otp_route_ids, otp_modes = extract_route_ids(legs)
                otp_duration = itin.get('duration', 0)
                gen_cost = itin.get('generalizedCost', 0)

                # OTP route_ids → TCD route_ids 매핑
                otp_routes_mapped = []
                for rid in otp_route_ids:
                    if rid in gtfs_to_tcd:
                        otp_routes_mapped.append(gtfs_to_tcd[rid])
                    else:
                        otp_routes_mapped.append(rid)  # 매핑 실패시 원본 유지

                # 중복 제거 (동일 노선 조합)
                route_key = tuple(otp_route_ids)
                if route_key in seen_routes:
                    continue
                seen_routes.add(route_key)

                # 유사도 계산
                sim = compute_similarity(tcd_info, otp_routes_mapped, otp_modes, otp_duration)
                sim['generalized_cost'] = gen_cost

                alternatives.append(sim)

            if not alternatives:
                failed_count += 1
                continue

            # OTP 1순위: generalized_cost 최소
            otp_first = min(alternatives, key=lambda x: x['generalized_cost'])

            # Best Match: sim_total 최대
            best_match = max(alternatives, key=lambda x: x['sim_total'])

            chain_id = tcd_info['chain_id']
            user_type = tcd_info['user_type']

            results[chain_id] = {
                'user_type': user_type,
                'n_alternatives': len(alternatives),
                # OTP 1순위
                'otp_first_exact': otp_first['exact_match'],
                'otp_first_sim': otp_first['sim_total'],
                'otp_first_route_lcs': otp_first['route_lcs'],
                'otp_first_jaccard': otp_first['jaccard'],
                'otp_first_time_sim': otp_first['time_sim'],
                # Best Match
                'best_exact': best_match['exact_match'],
                'best_sim': best_match['sim_total'],
                'best_route_lcs': best_match['route_lcs'],
                'best_jaccard': best_match['jaccard'],
                'best_time_sim': best_match['time_sim'],
            }

        except Exception as e:
            parse_errors += 1
            if parse_errors <= 5:
                print(f"\n  파싱 오류 (라인 {line_num}): {e}")
            continue

        # 진행률 (10만건마다)
        if (line_num + 1) % 100000 == 0:
            elapsed = time.time() - start_time
            rate = (line_num + 1) / elapsed
            remaining = max(0, (estimated_lines - line_num - 1) / rate)
            print(f"\n  {line_num+1:,}/{estimated_lines:,} | "
                  f"성공: {success_count:,} | "
                  f"남은시간: {remaining/60:.1f}분")

elapsed = time.time() - start_time
print(f"\n파싱 완료: {elapsed/60:.1f}분 ({line_num+1:,}줄)")
print(f"  성공: {success_count:,}")
print(f"  실패(경로없음): {failed_count:,}")
print(f"  파싱오류: {parse_errors:,}")
print(f"  결과 체인: {len(results):,}")
print()

# ─────────────────────────────────────────────────────
# 4. 집계 및 출력
# ─────────────────────────────────────────────────────
print("[4/4] 집계 및 출력...")
print()

df = pd.DataFrame.from_dict(results, orient='index')
df.index.name = 'chain_id'

def print_stats(label, subset):
    n = len(subset)
    print(f"  {label:12s} | n={n:>9,} | "
          f"Exact(1st)={subset['otp_first_exact'].mean()*100:5.2f}% | "
          f"Exact(best)={subset['best_exact'].mean()*100:5.2f}% | "
          f"Sim(1st)={subset['otp_first_sim'].mean():.4f} | "
          f"Sim(best)={subset['best_sim'].mean():.4f} | "
          f"Gap_exact={((subset['best_exact'].mean()-subset['otp_first_exact'].mean())*100):+.2f}%p | "
          f"Gap_sim={(subset['best_sim'].mean()-subset['otp_first_sim'].mean()):+.4f}")

print("=" * 150)
print("  전체 + 유형별 OTP 1순위 vs Best Match 비교 (전체 Phase 2 데이터)")
print("=" * 150)
print()
print(f"  {'유형':12s} | {'체인수':>9s} | "
      f"{'Exact(1st)':>11s} | {'Exact(best)':>12s} | "
      f"{'Sim(1st)':>9s} | {'Sim(best)':>10s} | "
      f"{'Gap_exact':>10s} | {'Gap_sim':>8s}")
print("-" * 150)

# 전체
print_stats("전체", df)
print("-" * 150)

# 유형별
for utype in ['GENERAL', 'ELDERLY', 'YOUTH', 'CHILDREN', 'DISABLED']:
    sub = df[df['user_type'] == utype]
    if len(sub) > 0:
        print_stats(utype, sub)

print("-" * 150)
print()

# 추가 통계: route_lcs, jaccard, time_sim
print("=" * 120)
print("  세부 유사도 지표 (OTP 1순위 기준)")
print("=" * 120)
print()
print(f"  {'유형':12s} | {'Route LCS':>10s} | {'Jaccard':>8s} | {'Time Sim':>9s} | {'Mode LCS':>9s}")
print("-" * 120)

for label, subset in [("전체", df)] + [(ut, df[df['user_type']==ut]) for ut in ['GENERAL','ELDERLY','YOUTH','CHILDREN','DISABLED']]:
    if len(subset) > 0:
        print(f"  {label:12s} | "
              f"{subset['otp_first_route_lcs'].mean():.4f}     | "
              f"{subset['otp_first_jaccard'].mean():.4f}  | "
              f"{subset['otp_first_time_sim'].mean():.4f}    | "
              f"{subset.get('otp_first_route_lcs', subset['otp_first_sim']).mean():.4f}")

print()

# 대안 수 통계
print(f"평균 대안 수: {df['n_alternatives'].mean():.2f}")
print(f"대안 1개 (선택지 없음): {(df['n_alternatives']==1).sum():,} ({(df['n_alternatives']==1).mean()*100:.1f}%)")
print()

# 환승 횟수별 (trip_attrs에서)
print("=" * 120)
print("  환승 횟수별 Exact Match (OTP 1순위)")
print("=" * 120)
# trip_attrs에서 환승 정보 가져오기
for _, row in trip_attrs.iterrows():
    cid = row['chain_id']
    if cid in results:
        results[cid]['n_transfers'] = row['n_transfers']

df = pd.DataFrame.from_dict(results, orient='index')
for nt in sorted(df['n_transfers'].dropna().unique()):
    sub = df[df['n_transfers'] == nt]
    if len(sub) > 0:
        print(f"  환승 {int(nt)}회 | n={len(sub):>9,} | "
              f"Exact(1st)={sub['otp_first_exact'].mean()*100:5.2f}% | "
              f"Exact(best)={sub['best_exact'].mean()*100:5.2f}%")

print()
print(f"총 소요시간: {(time.time()-start_time)/60:.1f}분")
print("완료!")
