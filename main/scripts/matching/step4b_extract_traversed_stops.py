"""
Step 4b: TCD 레그별 경유 정류장 시퀀스 추출

기존 leg_stop_sequences.parquet의 traversed_stops가 비어있어서 재추출

입력:
- trip_attributes_filtered.parquet (체인 정보)
- route_stop_sequences.parquet (노선별 정류장 시퀀스)

출력:
- tcd_leg_traversed_stops.parquet (레그별 경유 정류장)

로직:
1. 각 체인의 레그별로
2. route_id로 노선 정류장 시퀀스 조회
3. boarding_stop, alighting_stop 위치 찾기
4. 승차~하차 구간 정류장 추출
"""

import pandas as pd
import json
from pathlib import Path
from tqdm import tqdm
import numpy as np

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

def main():
    print("=" * 70)
    print("Step 4b: TCD 레그별 경유 정류장 시퀀스 추출")
    print("=" * 70)
    print()

    # 1. 데이터 로드
    print("데이터 로드 중...")

    # 노선별 정류장 시퀀스
    route_stops_df = pd.read_parquet(OUTPUT_DIR / "route_stop_sequences.parquet")
    route_stops_dict = {}
    for _, row in route_stops_df.iterrows():
        seq = row['stop_sequence']
        # 문자열로 저장된 경우 리스트로 변환
        if isinstance(seq, str):
            # "[1, 2, 3]" 형태의 문자열을 파싱
            import ast
            try:
                seq = ast.literal_eval(seq)
            except:
                seq = []
        route_stops_dict[row['route_id']] = seq
    print(f"  노선 수: {len(route_stops_dict):,}")

    # 체인 정보 (필터링된 것)
    trips = pd.read_parquet(OUTPUT_DIR / "trip_attributes_filtered.parquet")
    print(f"  체인 수: {len(trips):,}")
    print()

    # 2. 레그별 경유 정류장 추출
    print("레그별 경유 정류장 추출 중...")

    results = []
    stats = {
        'total_legs': 0,
        'success': 0,
        'no_route': 0,
        'board_not_found': 0,
        'alight_not_found': 0,
        'invalid_range': 0,
    }

    for _, trip in tqdm(trips.iterrows(), total=len(trips), desc="체인 처리"):
        chain_id = trip['chain_id']
        od_id = trip['od_id']

        # JSON 파싱
        routes = json.loads(trip['route_sequence'])
        modes = json.loads(trip['mode_sequence'])
        boarding = json.loads(trip['boarding_stops'])
        alighting = json.loads(trip['alighting_stops'])

        n_legs = len(routes)

        for leg_idx in range(n_legs):
            stats['total_legs'] += 1

            route_id = str(routes[leg_idx])
            mode = modes[leg_idx]
            board_stop = boarding[leg_idx] if leg_idx < len(boarding) else None
            alight_stop = alighting[leg_idx] if leg_idx < len(alighting) else None

            # 노선 정류장 시퀀스 조회
            if route_id not in route_stops_dict:
                stats['no_route'] += 1
                results.append({
                    'chain_id': chain_id,
                    'od_id': od_id,
                    'leg_index': leg_idx,
                    'route_id': route_id,
                    'mode': mode,
                    'status': 'no_route',
                    'traversed_stops': [],
                    'n_traversed': 0,
                })
                continue

            stop_seq = route_stops_dict[route_id]

            # 승차/하차 정류장 위치 찾기
            try:
                board_idx = stop_seq.index(board_stop)
            except (ValueError, TypeError):
                stats['board_not_found'] += 1
                results.append({
                    'chain_id': chain_id,
                    'od_id': od_id,
                    'leg_index': leg_idx,
                    'route_id': route_id,
                    'mode': mode,
                    'status': 'board_not_found',
                    'traversed_stops': [],
                    'n_traversed': 0,
                })
                continue

            try:
                alight_idx = stop_seq.index(alight_stop)
            except (ValueError, TypeError):
                stats['alight_not_found'] += 1
                results.append({
                    'chain_id': chain_id,
                    'od_id': od_id,
                    'leg_index': leg_idx,
                    'route_id': route_id,
                    'mode': mode,
                    'status': 'alight_not_found',
                    'traversed_stops': [],
                    'n_traversed': 0,
                })
                continue

            # 경유 정류장 추출 (승차~하차 구간)
            # 순환 노선 고려: board_idx < alight_idx 또는 반대 방향
            if board_idx <= alight_idx:
                traversed = stop_seq[board_idx:alight_idx + 1]
            else:
                # 역방향 또는 순환 노선
                traversed = stop_seq[board_idx:] + stop_seq[:alight_idx + 1]

            if len(traversed) == 0:
                stats['invalid_range'] += 1
                results.append({
                    'chain_id': chain_id,
                    'od_id': od_id,
                    'leg_index': leg_idx,
                    'route_id': route_id,
                    'mode': mode,
                    'status': 'invalid_range',
                    'traversed_stops': [],
                    'n_traversed': 0,
                })
                continue

            stats['success'] += 1
            results.append({
                'chain_id': chain_id,
                'od_id': od_id,
                'leg_index': leg_idx,
                'route_id': route_id,
                'mode': mode,
                'status': 'ok',
                'traversed_stops': traversed,
                'n_traversed': len(traversed),
            })

    print()
    print("=" * 70)
    print("추출 결과 통계")
    print("=" * 70)
    print(f"총 레그: {stats['total_legs']:,}")
    print(f"성공: {stats['success']:,} ({stats['success']/stats['total_legs']*100:.1f}%)")
    print(f"노선 없음: {stats['no_route']:,} ({stats['no_route']/stats['total_legs']*100:.1f}%)")
    print(f"승차 정류장 못찾음: {stats['board_not_found']:,} ({stats['board_not_found']/stats['total_legs']*100:.1f}%)")
    print(f"하차 정류장 못찾음: {stats['alight_not_found']:,} ({stats['alight_not_found']/stats['total_legs']*100:.1f}%)")
    print(f"범위 오류: {stats['invalid_range']:,} ({stats['invalid_range']/stats['total_legs']*100:.1f}%)")
    print()

    # 3. 결과 저장
    print("결과 저장 중...")
    df = pd.DataFrame(results)
    output_path = OUTPUT_DIR / "tcd_leg_traversed_stops.parquet"
    df.to_parquet(output_path, index=False)

    file_size = output_path.stat().st_size / (1024**2)
    print(f"저장 완료: {output_path}")
    print(f"파일 크기: {file_size:.1f} MB")
    print(f"행 수: {len(df):,}")
    print()

    # 4. 샘플 확인
    print("=" * 70)
    print("샘플 데이터 (성공 케이스)")
    print("=" * 70)
    success_sample = df[df['status'] == 'ok'].head(5)
    for _, row in success_sample.iterrows():
        print(f"chain_id={row['chain_id']}, leg={row['leg_index']}, route={row['route_id']}")
        print(f"  경유 정류장 수: {row['n_traversed']}")
        stops = row['traversed_stops']
        if len(stops) > 6:
            print(f"  정류장: {stops[:3]} ... {stops[-3:]}")
        else:
            print(f"  정류장: {stops}")
        print()


if __name__ == "__main__":
    main()
