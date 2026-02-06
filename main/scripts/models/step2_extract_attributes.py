"""
Phase 3 Step 2: 대안 속성 추출

입력:
- otp_alternatives.parquet (4.47M 경로)

출력:
- alternative_attributes.parquet
  - od_id, alt_id
  - T_ride, T_walk, T_wait, T_total (분 단위)
  - N_transfer
  - D_subway, D_bus_only
  - modes

로직:
1. otp_alternatives 로드
2. 시간 변수 초→분 변환
3. 더미 변수 계산
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


def main():
    print("=" * 70)
    print("Phase 3 Step 2: 대안 속성 추출")
    print("=" * 70)
    print()

    # 1. 데이터 로드
    print("1. 데이터 로드 중...")
    otp_df = pd.read_parquet(OUTPUT_DIR / "otp_alternatives.parquet")
    print(f"   총 경로: {len(otp_df):,}")
    print(f"   OD 수: {otp_df['od_id'].nunique():,}")
    print(f"   컬럼: {list(otp_df.columns)}")
    print()

    # 2. 변수 변환/생성
    print("2. 변수 변환/생성...")

    # 시간 변수: 초 → 분
    otp_df['T_ride'] = otp_df['ride_time_sec'] / 60.0
    otp_df['T_walk'] = otp_df['walk_time_sec'] / 60.0
    otp_df['T_wait'] = otp_df['wait_time_sec'] / 60.0
    otp_df['T_total'] = otp_df['total_duration'] / 60.0

    # 환승 횟수 (이미 있음)
    otp_df['N_transfer'] = otp_df['n_transfers']

    # 더미 변수
    otp_df['D_subway'] = otp_df['has_subway'].astype(np.int8)

    # D_bus_only: 지하철 없고 버스만 있는 경우
    def check_bus_only(modes_str):
        try:
            modes = json.loads(modes_str) if isinstance(modes_str, str) else modes_str
            if not modes:
                return 0
            return 1 if all(m == 'BUS' for m in modes) else 0
        except:
            return 0

    otp_df['D_bus_only'] = otp_df['modes'].apply(check_bus_only).astype(np.int8)

    print("   T_ride, T_walk, T_wait, T_total (분 단위) 생성")
    print("   N_transfer, D_subway, D_bus_only 생성")
    print()

    # 3. 기술 통계
    print("3. 변수별 기술 통계...")
    stats_vars = ['T_ride', 'T_walk', 'T_wait', 'T_total', 'N_transfer']
    stats = otp_df[stats_vars].describe()
    print(stats.round(2).to_string())
    print()

    # 더미 변수 분포
    print("   D_subway 분포:")
    subway_dist = otp_df['D_subway'].value_counts()
    for val, cnt in subway_dist.items():
        print(f"     {val}: {cnt:,} ({cnt/len(otp_df)*100:.1f}%)")

    print("   D_bus_only 분포:")
    bus_dist = otp_df['D_bus_only'].value_counts()
    for val, cnt in bus_dist.items():
        print(f"     {val}: {cnt:,} ({cnt/len(otp_df)*100:.1f}%)")
    print()

    # 환승 횟수 분포
    print("   N_transfer 분포:")
    transfer_dist = otp_df['N_transfer'].value_counts().sort_index()
    for val, cnt in transfer_dist.items():
        print(f"     {val}회: {cnt:,} ({cnt/len(otp_df)*100:.1f}%)")
    print()

    # 4. 출력 데이터프레임 구성
    print("4. 출력 데이터 구성...")

    output_columns = [
        'od_id', 'alt_id',
        'T_ride', 'T_walk', 'T_wait', 'T_total',
        'N_transfer', 'D_subway', 'D_bus_only',
        'modes', 'route_ids', 'generalized_cost', 'walk_distance'
    ]
    attr_df = otp_df[output_columns].copy()

    # 데이터 타입 최적화
    attr_df['T_ride'] = attr_df['T_ride'].astype(np.float32)
    attr_df['T_walk'] = attr_df['T_walk'].astype(np.float32)
    attr_df['T_wait'] = attr_df['T_wait'].astype(np.float32)
    attr_df['T_total'] = attr_df['T_total'].astype(np.float32)
    attr_df['N_transfer'] = attr_df['N_transfer'].astype(np.int8)
    attr_df['generalized_cost'] = attr_df['generalized_cost'].astype(np.int32)
    attr_df['walk_distance'] = attr_df['walk_distance'].astype(np.float32)

    print(f"   출력 행: {len(attr_df):,}")
    print(f"   출력 컬럼: {list(attr_df.columns)}")
    print()

    # 5. 저장
    print("5. 저장 중...")
    output_path = OUTPUT_DIR / "alternative_attributes.parquet"
    attr_df.to_parquet(output_path, index=False)

    file_size = output_path.stat().st_size / (1024**2)
    print(f"   저장 완료: {output_path}")
    print(f"   파일 크기: {file_size:.1f} MB")
    print()

    # 6. 샘플 확인
    print("6. 샘플 데이터 (5행)...")
    sample = attr_df.head()
    print(sample[['od_id', 'alt_id', 'T_ride', 'T_walk', 'T_wait', 'N_transfer', 'D_subway', 'D_bus_only']].to_string())
    print()

    # 7. 최종 요약
    print("=" * 70)
    print("최종 요약")
    print("=" * 70)
    print(f"총 경로: {len(attr_df):,}")
    print(f"OD 수: {attr_df['od_id'].nunique():,}")
    print(f"평균 T_ride: {attr_df['T_ride'].mean():.1f}분")
    print(f"평균 T_walk: {attr_df['T_walk'].mean():.1f}분")
    print(f"평균 N_transfer: {attr_df['N_transfer'].mean():.2f}회")
    print(f"D_subway=1 비율: {attr_df['D_subway'].mean()*100:.1f}%")
    print(f"D_bus_only=1 비율: {attr_df['D_bus_only'].mean()*100:.1f}%")
    print()


if __name__ == "__main__":
    main()
