"""
Phase 3 Step 3: 모델 입력 데이터 준비

입력 (output/iter{N}/):
- choice_set.parquet (Step 1)
- alternative_attributes.parquet (Step 2)

입력 (공통):
- trip_attributes_filtered.parquet (Phase 1)

출력 (output/iter{N}/):
- model_input.parquet (전체)
- model_input_train.parquet (80%)
- model_input_test.parquet (20%)

환경변수:
- ITERATION: 반복 회차 (기본 0)

처리:
1. 세 파일 병합
2. 이상치 제거 (시간 변수 기준)
3. D_peak 생성
4. Train/Test 분할 (체인 수준, 층화)
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split

# 경로 설정 - iteration_paths 사용
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from utils.iteration_paths import get_paths, print_iteration_info

# Iteration별 경로 가져오기
paths = get_paths()

# 이상치 기준
MIN_DURATION_MIN = 1.0       # 최소 1분
MAX_DURATION_MIN = 180.0     # 최대 3시간
MAX_WAIT_MIN = 60.0          # 대기 최대 1시간
MAX_TIME_DIFF_MIN = 1.0      # 시간 합계 오차 최대 1분

# Train/Test 분할 비율
TEST_SIZE = 0.20
RANDOM_STATE = 42

# user_type 매핑 (문자열 → 숫자)
USER_TYPE_MAP = {
    'GENERAL': 1,
    'CHILDREN': 2,
    'YOUTH': 3,
    'ELDERLY': 4,
    'DISABLED': 5
}


def main():
    print("=" * 70)
    print("Phase 3 Step 3: 모델 입력 데이터 준비")
    print("=" * 70)
    print_iteration_info()

    # 1. 데이터 로드
    print("1. 데이터 로드 중...")

    choice_df = pd.read_parquet(paths.choice_set)
    print(f"   choice_set: {len(choice_df):,} rows, {choice_df['chain_id'].nunique():,} chains")

    attr_df = pd.read_parquet(paths.alternative_attributes)
    print(f"   alternative_attributes: {len(attr_df):,} rows")

    trip_df = pd.read_parquet(paths.trip_attrs_filtered)
    print(f"   trip_attributes: {len(trip_df):,} rows")
    print()

    # 2. 병합
    print("2. 데이터 병합 중...")

    # choice_set + alternative_attributes
    merged = choice_df.merge(
        attr_df[['od_id', 'alt_id', 'T_ride', 'T_walk', 'T_wait', 'T_total',
                 'N_transfer', 'D_subway', 'D_bus_only']],
        on=['od_id', 'alt_id'],
        how='left'
    )
    print(f"   choice + attr 병합 후: {len(merged):,} rows")

    # trip_attributes에서 user_type, board_time 가져오기
    # chain_id로 조인
    trip_cols = ['chain_id', 'user_type', 'board_time']

    merged = merged.merge(
        trip_df[trip_cols],
        on='chain_id',
        how='left'
    )
    print(f"   + trip_attr 병합 후: {len(merged):,} rows")

    # user_type 문자열 → 숫자 변환
    merged['user_type'] = merged['user_type'].map(USER_TYPE_MAP)
    print(f"   user_type 변환 완료 (GENERAL=1, CHILDREN=2, YOUTH=3, ELDERLY=4, DISABLED=5)")
    print()

    # 3. 이상치 제거
    print("3. 이상치 제거...")
    print(f"   기준:")
    print(f"     - T_total: {MIN_DURATION_MIN}분 ~ {MAX_DURATION_MIN}분")
    print(f"     - T_wait: 최대 {MAX_WAIT_MIN}분")
    print(f"     - 시간 합계 오차: 최대 {MAX_TIME_DIFF_MIN}분")
    print()

    n_before = len(merged)
    chains_before = merged['chain_id'].nunique()

    # 시간 합계 계산
    merged['time_sum'] = merged['T_ride'] + merged['T_walk'] + merged['T_wait']
    merged['time_diff'] = (merged['T_total'] - merged['time_sum']).abs()

    # 이상치 플래그
    merged['is_outlier'] = (
        (merged['T_total'] < MIN_DURATION_MIN) |
        (merged['T_total'] > MAX_DURATION_MIN) |
        (merged['T_wait'] > MAX_WAIT_MIN) |
        (merged['time_diff'] > MAX_TIME_DIFF_MIN)
    )

    # 이상치 통계
    outlier_count = merged['is_outlier'].sum()
    print(f"   이상치 행: {outlier_count:,} ({outlier_count/n_before*100:.2f}%)")

    # 이상치 상세
    print(f"     - T_total < {MIN_DURATION_MIN}분: {(merged['T_total'] < MIN_DURATION_MIN).sum():,}")
    print(f"     - T_total > {MAX_DURATION_MIN}분: {(merged['T_total'] > MAX_DURATION_MIN).sum():,}")
    print(f"     - T_wait > {MAX_WAIT_MIN}분: {(merged['T_wait'] > MAX_WAIT_MIN).sum():,}")
    print(f"     - 시간 오차 > {MAX_TIME_DIFF_MIN}분: {(merged['time_diff'] > MAX_TIME_DIFF_MIN).sum():,}")

    # 이상치가 있는 체인 전체 제거 (한 체인 내 하나라도 이상치면 제거)
    outlier_chains = merged[merged['is_outlier']]['chain_id'].unique()
    print(f"   이상치 포함 체인: {len(outlier_chains):,}")

    # 이상치 체인 제거
    clean_df = merged[~merged['chain_id'].isin(outlier_chains)].copy()

    n_after = len(clean_df)
    chains_after = clean_df['chain_id'].nunique()

    print(f"   제거 전: {n_before:,} rows, {chains_before:,} chains")
    print(f"   제거 후: {n_after:,} rows, {chains_after:,} chains")
    print(f"   제거율: {(1 - chains_after/chains_before)*100:.2f}%")
    print()

    # 4. 추가 변수 생성
    print("4. 추가 변수 생성...")

    # D_peak: 첨두시간대 (07-09, 18-20)
    # board_time은 초 단위 (seconds from midnight)
    clean_df['hour'] = (clean_df['board_time'] // 3600).astype(int)

    clean_df['D_peak'] = (
        ((clean_df['hour'] >= 7) & (clean_df['hour'] < 9)) |
        ((clean_df['hour'] >= 18) & (clean_df['hour'] < 20))
    ).astype(np.int8)

    peak_rate = clean_df.groupby('chain_id')['D_peak'].first().mean()
    print(f"   D_peak=1 (첨두시간대): {peak_rate*100:.1f}%")
    print()

    # 5. 검증: choice 변수
    print("5. Choice 변수 검증...")
    choice_per_chain = clean_df.groupby('chain_id')['choice'].sum()
    valid_choice = (choice_per_chain == 1).all()
    print(f"   모든 체인에 choice=1이 정확히 1개: {'[OK]' if valid_choice else '[X]'}")

    if not valid_choice:
        bad_chains = choice_per_chain[choice_per_chain != 1]
        print(f"   문제 체인 수: {len(bad_chains)}")
        # 문제 체인 제거
        clean_df = clean_df[clean_df['chain_id'].isin(choice_per_chain[choice_per_chain == 1].index)]
        print(f"   수정 후: {clean_df['chain_id'].nunique():,} chains")
    print()

    # 6. 대안 수 분포
    print("6. 대안 수 분포...")
    alts_per_chain = clean_df.groupby('chain_id').size()
    print(f"   최소: {alts_per_chain.min()}, 최대: {alts_per_chain.max()}, 평균: {alts_per_chain.mean():.2f}")

    # 대안 1개인 체인 제거 (선택 모델에 의미 없음)
    single_alt_chains = alts_per_chain[alts_per_chain == 1].index
    if len(single_alt_chains) > 0:
        print(f"   [!] 대안 1개인 체인: {len(single_alt_chains):,} (제거)")
        clean_df = clean_df[~clean_df['chain_id'].isin(single_alt_chains)]
        alts_per_chain = clean_df.groupby('chain_id').size()
        print(f"   제거 후: {clean_df['chain_id'].nunique():,} chains")
    print()

    # 7. user_type 분포
    print("7. user_type 분포...")
    user_dist = clean_df.groupby('chain_id')['user_type'].first().value_counts().sort_index()
    total_chains = user_dist.sum()
    for ut, cnt in user_dist.items():
        print(f"   유형 {ut}: {cnt:,} ({cnt/total_chains*100:.1f}%)")
    print()

    # 8. 최종 데이터 정리
    print("8. 최종 데이터 정리...")

    output_cols = [
        'chain_id', 'od_id', 'alt_id', 'choice',
        'T_ride', 'T_walk', 'T_wait', 'T_total',
        'N_transfer', 'D_subway', 'D_bus_only', 'D_peak',
        'user_type', 'sim_total', 'exact_match'
    ]
    final_df = clean_df[output_cols].copy()

    # 데이터 타입 최적화
    final_df['chain_id'] = final_df['chain_id'].astype('int32')
    final_df['od_id'] = final_df['od_id'].astype('int32')
    final_df['alt_id'] = final_df['alt_id'].astype('int8')
    final_df['choice'] = final_df['choice'].astype('int8')
    final_df['N_transfer'] = final_df['N_transfer'].astype('int8')
    final_df['D_subway'] = final_df['D_subway'].astype('int8')
    final_df['D_bus_only'] = final_df['D_bus_only'].astype('int8')
    final_df['D_peak'] = final_df['D_peak'].astype('int8')
    final_df['user_type'] = final_df['user_type'].astype('int8')
    final_df['exact_match'] = final_df['exact_match'].astype('int8')

    print(f"   최종 행: {len(final_df):,}")
    print(f"   최종 체인: {final_df['chain_id'].nunique():,}")
    print(f"   컬럼: {list(final_df.columns)}")
    print()

    # 9. Train/Test 분할
    print("9. Train/Test 분할...")

    unique_chains = final_df['chain_id'].unique()

    # 층화 추출을 위한 user_type
    chain_user_type = final_df.groupby('chain_id')['user_type'].first()

    # 각 클래스의 최소 샘플 수 확인 (층화 분할에는 최소 2개 필요)
    min_class_count = chain_user_type.value_counts().min()
    use_stratify = min_class_count >= 2

    if use_stratify:
        train_chains, test_chains = train_test_split(
            unique_chains,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=chain_user_type[unique_chains].values
        )
    else:
        print(f"   [!] 일부 user_type이 1개뿐이므로 층화 분할 건너뜀")
        train_chains, test_chains = train_test_split(
            unique_chains,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE
        )

    train_df = final_df[final_df['chain_id'].isin(train_chains)]
    test_df = final_df[final_df['chain_id'].isin(test_chains)]

    print(f"   Train: {len(train_df):,} rows, {len(train_chains):,} chains ({len(train_chains)/len(unique_chains)*100:.0f}%)")
    print(f"   Test: {len(test_df):,} rows, {len(test_chains):,} chains ({len(test_chains)/len(unique_chains)*100:.0f}%)")
    print()

    # Train/Test user_type 분포 비교
    print("   Train user_type 분포:")
    train_user = train_df.groupby('chain_id')['user_type'].first().value_counts(normalize=True).sort_index()
    for ut, pct in train_user.items():
        print(f"     유형 {ut}: {pct*100:.1f}%")

    print("   Test user_type 분포:")
    test_user = test_df.groupby('chain_id')['user_type'].first().value_counts(normalize=True).sort_index()
    for ut, pct in test_user.items():
        print(f"     유형 {ut}: {pct*100:.1f}%")
    print()

    # 10. 저장
    print("10. 저장 중...")

    # 전체
    full_path = paths.model_input
    final_df.to_parquet(full_path, index=False)
    print(f"   전체: {full_path} ({full_path.stat().st_size/(1024**2):.1f} MB)")

    # Train
    train_path = paths.model_input_train
    train_df.to_parquet(train_path, index=False)
    print(f"   Train: {train_path} ({train_path.stat().st_size/(1024**2):.1f} MB)")

    # Test
    test_path = paths.model_input_test
    test_df.to_parquet(test_path, index=False)
    print(f"   Test: {test_path} ({test_path.stat().st_size/(1024**2):.1f} MB)")
    print()

    # 11. 기술 통계
    print("=" * 70)
    print("최종 기술 통계")
    print("=" * 70)
    print()

    stats_vars = ['T_ride', 'T_walk', 'T_wait', 'T_total', 'N_transfer']
    print("전체 대안:")
    print(final_df[stats_vars].describe().round(2).to_string())
    print()

    print("선택된 대안 (choice=1):")
    chosen = final_df[final_df['choice'] == 1]
    print(chosen[stats_vars].describe().round(2).to_string())
    print()

    # 12. 최종 요약
    print("=" * 70)
    print("최종 요약")
    print("=" * 70)
    print(f"입력 체인: {chains_before:,}")
    print(f"이상치 제거: {chains_before - chains_after:,} ({(chains_before - chains_after)/chains_before*100:.2f}%)")
    print(f"단일 대안 제거: {len(single_alt_chains):,}")
    print(f"최종 체인: {final_df['chain_id'].nunique():,}")
    print(f"최종 행 (대안): {len(final_df):,}")
    print(f"체인당 평균 대안: {len(final_df)/final_df['chain_id'].nunique():.2f}")
    print(f"Train/Test: {len(train_chains):,} / {len(test_chains):,}")
    print()


if __name__ == "__main__":
    main()
