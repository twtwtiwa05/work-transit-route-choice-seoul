"""
Phase 3 Step 1: Choice Set 생성

입력 (output/iter{N}/):
- similarity_results.parquet

출력 (output/iter{N}/):
- choice_set.parquet

환경변수:
- ITERATION: 반복 회차 (기본 0)

로직:
1. similarity_results 로드
2. chain_id별 sim_total 최대 대안 찾기
3. best_sim >= THRESHOLD 필터링
4. choice 변수 생성
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm

# 경로 설정 - iteration_paths 사용
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from utils.iteration_paths import get_paths, print_iteration_info

# Iteration별 경로 가져오기
paths = get_paths()

# 설정
import os
THRESHOLD = float(os.environ.get("CHOICE_THRESHOLD", "0.50"))  # 환경변수로 조정 가능, 기본 0.50


def main():
    print("=" * 70)
    print("Phase 3 Step 1: Choice Set 생성")
    print("=" * 70)
    print_iteration_info()
    print(f"Threshold: {THRESHOLD}")
    print()

    # 1. 데이터 로드
    print("1. 데이터 로드 중...")
    sim_df = pd.read_parquet(paths.similarity_results)
    print(f"   총 쌍: {len(sim_df):,}")
    print(f"   체인 수: {sim_df['chain_id'].nunique():,}")
    print(f"   OD 수: {sim_df['od_id'].nunique():,}")
    print()

    # 2. 체인별 best match 찾기
    print("2. 체인별 Best Match 찾기...")

    # 각 체인의 best_sim (최고 sim_total)
    best_sim_per_chain = sim_df.groupby('chain_id')['sim_total'].max()
    sim_df['best_sim'] = sim_df['chain_id'].map(best_sim_per_chain)

    # 각 체인에서 sim_total이 best_sim인 대안 찾기 (동점 시 첫 번째)
    sim_df['is_best'] = sim_df['sim_total'] == sim_df['best_sim']

    # 동점 처리: 같은 chain_id 내에서 첫 번째 is_best만 유지
    sim_df['rank_in_best'] = sim_df.groupby(['chain_id', 'is_best']).cumcount()
    sim_df['is_best_unique'] = sim_df['is_best'] & (sim_df['rank_in_best'] == 0)

    n_best = sim_df['is_best_unique'].sum()
    print(f"   Best match 수: {n_best:,}")
    print()

    # 3. Threshold 기준 필터링
    print(f"3. Threshold ({THRESHOLD}) 기준 필터링...")

    # 통계
    total_chains = sim_df['chain_id'].nunique()
    chains_above_threshold = (best_sim_per_chain >= THRESHOLD).sum()

    print(f"   전체 체인: {total_chains:,}")
    print(f"   best_sim >= {THRESHOLD}: {chains_above_threshold:,} ({chains_above_threshold/total_chains*100:.1f}%)")
    print()

    # Threshold 분포 상세
    print("   Threshold별 체인 수:")
    for th in [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
        n = (best_sim_per_chain >= th).sum()
        print(f"     >= {th}: {n:,} ({n/total_chains*100:.1f}%)")
    print()

    # 4. 필터링된 데이터셋 생성
    print("4. Choice Set 생성...")

    # threshold 이상인 체인만 선택
    valid_chains = best_sim_per_chain[best_sim_per_chain >= THRESHOLD].index
    choice_df = sim_df[sim_df['chain_id'].isin(valid_chains)].copy()

    # choice 변수 생성
    choice_df['choice'] = choice_df['is_best_unique'].astype(np.int8)

    # 필요한 컬럼만 선택
    output_columns = [
        'chain_id', 'od_id', 'alt_id',
        'choice', 'sim_total', 'best_sim', 'exact_match',
        'otp_duration', 'otp_n_transfers', 'otp_generalized_cost',
        'sim_route_seq', 'sim_mode_seq', 'sim_jaccard_full', 'sim_lcs',
        'sim_boarding_alighting', 'sim_time'
    ]
    choice_df = choice_df[output_columns]

    n_filtered_chains = choice_df['chain_id'].nunique()
    print(f"   필터링된 쌍: {len(choice_df):,}")
    print(f"   필터링된 체인: {n_filtered_chains:,}")
    if n_filtered_chains > 0:
        print(f"   체인당 평균 대안: {len(choice_df) / n_filtered_chains:.2f}")
    else:
        print("   경고: 필터링된 체인이 없습니다. Threshold를 낮추세요.")
        print("   (환경변수 CHOICE_THRESHOLD=0.30 등으로 설정)")
        sys.exit(1)
    print()

    # 5. 검증
    print("5. 검증...")

    # 각 체인당 choice=1이 정확히 1개인지
    choice_per_chain = choice_df.groupby('chain_id')['choice'].sum()
    chains_with_one_choice = (choice_per_chain == 1).sum()
    chains_with_zero_choice = (choice_per_chain == 0).sum()
    chains_with_multi_choice = (choice_per_chain > 1).sum()

    print(f"   choice=1이 1개인 체인: {chains_with_one_choice:,}")
    print(f"   choice=1이 0개인 체인: {chains_with_zero_choice:,}")
    print(f"   choice=1이 2+개인 체인: {chains_with_multi_choice:,}")

    if chains_with_zero_choice > 0 or chains_with_multi_choice > 0:
        print("   [!] 경고: choice 변수 이상")
    else:
        print("   [OK] choice 변수 정상")
    print()

    # 6. 대안 수 분포
    print("6. 대안 수 분포...")
    alts_per_chain = choice_df.groupby('chain_id').size()
    print(f"   최소: {alts_per_chain.min()}")
    print(f"   최대: {alts_per_chain.max()}")
    print(f"   평균: {alts_per_chain.mean():.2f}")
    print(f"   중앙값: {alts_per_chain.median():.1f}")
    print()

    # 대안 수별 체인 분포
    print("   대안 수별 체인:")
    alt_counts = alts_per_chain.value_counts().sort_index()
    for n_alts, count in alt_counts.items():
        pct = count / len(alts_per_chain) * 100
        print(f"     {n_alts}개: {count:,} ({pct:.1f}%)")
    print()

    # 7. sim_total 분포 (선택된 대안)
    print("7. 선택된 대안(choice=1)의 sim_total 분포...")
    chosen = choice_df[choice_df['choice'] == 1]['sim_total']
    print(f"   평균: {chosen.mean():.3f}")
    print(f"   중앙값: {chosen.median():.3f}")
    print(f"   최소: {chosen.min():.3f}")
    print(f"   최대: {chosen.max():.3f}")
    print(f"   표준편차: {chosen.std():.3f}")
    print()

    # 8. Exact Match 비율
    print("8. Exact Match 비율...")
    exact_chosen = choice_df[choice_df['choice'] == 1]['exact_match'].mean()
    print(f"   choice=1 중 Exact Match: {exact_chosen*100:.1f}%")
    print()

    # 9. 저장
    print("9. 저장 중...")
    output_path = paths.choice_set
    choice_df.to_parquet(output_path, index=False)

    file_size = output_path.stat().st_size / (1024**2)
    print(f"   저장 완료: {output_path}")
    print(f"   파일 크기: {file_size:.1f} MB")
    print()

    # 10. 최종 요약
    print("=" * 70)
    print("최종 요약")
    print("=" * 70)
    print(f"입력: {len(sim_df):,} 쌍 ({sim_df['chain_id'].nunique():,} 체인)")
    print(f"출력: {len(choice_df):,} 쌍 ({choice_df['chain_id'].nunique():,} 체인)")
    print(f"필터링 비율: {choice_df['chain_id'].nunique() / sim_df['chain_id'].nunique() * 100:.1f}%")
    print(f"체인당 평균 대안: {len(choice_df) / choice_df['chain_id'].nunique():.2f}")
    print(f"선택 대안 평균 sim_total: {chosen.mean():.3f}")
    print(f"Exact Match 비율: {exact_chosen*100:.1f}%")
    print()


if __name__ == "__main__":
    main()
