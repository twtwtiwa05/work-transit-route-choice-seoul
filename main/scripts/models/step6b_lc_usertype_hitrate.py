#!/usr/bin/env python3
"""
Step 6b: LC 모형 유형별 Hit Rate 산출 (보충 분석)
=================================================
저장된 LC 파라미터를 로드하여 test set에서 유형별 hit rate를 계산.
모형 재추정 없이 1분 이내 완료.

출력:
  - latent_class_results.json에 hit_rate_by_user_type 추가
  - 콘솔에 유형별 결과 출력
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output"
RESULTS_DIR = ROOT / "results"

VARNAMES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway']
N_VARS = 4
COV_NAMES = ['D_children', 'D_youth', 'D_elderly', 'D_disabled', 'D_peak']
N_COV = 5
N_MEMBERSHIP_PER_CLASS = 1 + N_COV  # 6

USER_TYPE_MAP = {1: 'General', 2: 'Children', 3: 'Youth',
                 4: 'Elderly', 5: 'Disabled'}


def prepare_padded_data(df):
    """가변 길이 choice set → 고정 크기 패딩."""
    df = df.sort_values(['chain_id', 'alt_id']).reset_index(drop=True)

    chain_ids_raw = df['chain_id'].values
    boundaries = np.concatenate([[0], np.where(np.diff(chain_ids_raw) != 0)[0] + 1, [len(df)]])

    N = len(boundaries) - 1
    X_all = df[VARNAMES].values.astype(np.float64)
    choice_all = df['choice'].values
    user_type_all = df['user_type'].values
    peak_all = df['D_peak'].values

    sizes = np.diff(boundaries)
    max_J = int(sizes.max())

    X_pad = np.zeros((N, max_J, N_VARS), dtype=np.float64)
    mask = np.zeros((N, max_J), dtype=np.float64)
    y_idx = np.zeros(N, dtype=np.int64)
    user_types = np.zeros(N, dtype=np.int64)
    peak_chain = np.zeros(N, dtype=np.float64)

    for i in range(N):
        s, e = boundaries[i], boundaries[i + 1]
        J_i = e - s
        X_pad[i, :J_i, :] = X_all[s:e]
        mask[i, :J_i] = 1.0
        y_idx[i] = np.where(choice_all[s:e] == 1)[0][0]
        user_types[i] = user_type_all[s]
        peak_chain[i] = peak_all[s]

    Z_cov = np.zeros((N, N_COV), dtype=np.float64)
    Z_cov[:, 0] = (user_types == 2).astype(np.float64)
    Z_cov[:, 1] = (user_types == 3).astype(np.float64)
    Z_cov[:, 2] = (user_types == 4).astype(np.float64)
    Z_cov[:, 3] = (user_types == 5).astype(np.float64)
    Z_cov[:, 4] = peak_chain

    return X_pad, mask, y_idx, user_types, Z_cov


def individual_class_probs(membership_params, Z, K):
    """개인별 클래스 소속 확률. Returns: (K, N)"""
    N = Z.shape[0]
    npc = N_MEMBERSHIP_PER_CLASS

    alpha = np.zeros((K, N))
    for c in range(K - 1):
        gamma_c = membership_params[c * npc]
        delta_c = membership_params[c * npc + 1: (c + 1) * npc]
        alpha[c] = gamma_c + Z @ delta_c

    alpha = alpha - alpha.max(axis=0, keepdims=True)
    exp_alpha = np.exp(alpha)
    pi = exp_alpha / exp_alpha.sum(axis=0, keepdims=True)
    return pi


def mnl_probs_vectorized(X_pad, mask, beta):
    """Class-specific MNL probabilities. Returns: (N, max_J)"""
    V = X_pad @ beta
    V = np.where(mask == 1, V, -1e20)
    V = V - V.max(axis=1, keepdims=True)
    exp_V = np.exp(V)
    exp_V = np.where(mask == 1, exp_V, 0.0)
    denom = exp_V.sum(axis=1, keepdims=True)
    return exp_V / denom


def compute_hit_rate(params, X_pad, mask, y_idx, Z, K):
    """Hit rate + mean choice probability."""
    N = X_pad.shape[0]
    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (K - 1) * npc

    membership_params = params[:n_membership]
    betas = params[n_membership:].reshape(K, N_VARS)

    pi = individual_class_probs(membership_params, Z, K)

    mix_probs = np.zeros((N, X_pad.shape[1]))
    for c in range(K):
        P_c = mnl_probs_vectorized(X_pad, mask, betas[c])
        mix_probs += pi[c][:, None] * P_c

    predicted = np.argmax(mix_probs, axis=1)
    hit_rate = (predicted == y_idx).mean()
    mean_prob = mix_probs[np.arange(N), y_idx].mean()

    return float(hit_rate), float(mean_prob)


def reconstruct_params(lc_results):
    """JSON에서 flat params 배열 복원."""
    best = lc_results['best_model']
    K = best['K']

    # Membership params: (K-1) classes × 6 params each
    membership_flat = []
    for c in range(K - 1):
        key = f"class_{c + 1}"
        mp = best['membership_params'][key]
        membership_flat.append(mp['Intercept']['coef'])
        for cov in COV_NAMES:
            membership_flat.append(mp[cov]['coef'])

    # Beta params: K classes × 4 vars each
    beta_flat = []
    for c in range(K):
        key = f"class_{c + 1}"
        cp = best['class_parameters'][key]
        for var in VARNAMES:
            beta_flat.append(cp[var]['coef'])

    return np.array(membership_flat + beta_flat), K


def main():
    print("=" * 60)
    print("  Step 6b: LC 유형별 Hit Rate 보충 분석")
    print("=" * 60)

    # 1. JSON에서 파라미터 복원
    json_path = RESULTS_DIR / "latent_class_results.json"
    with open(json_path) as f:
        lc_results = json.load(f)

    params, K = reconstruct_params(lc_results)
    print(f"\n  K = {K}, 파라미터 수 = {len(params)}")

    # 2. Test 데이터 로드
    print("\n  Test 데이터 로드...")
    try:
        test_df = pd.read_parquet(OUTPUT_DIR / "model_input_test.parquet")
    except OSError:
        test_df = pd.read_parquet(OUTPUT_DIR / "model_input_test.parquet",
                                   engine='fastparquet')

    n_chains = test_df['chain_id'].nunique()
    print(f"  {len(test_df):,} rows, {n_chains:,} chains")

    # 3. 패딩 데이터 준비
    print("  패딩 데이터 준비...")
    X_pad, mask, y_idx, user_types, Z_cov = prepare_padded_data(test_df)
    print(f"  N = {X_pad.shape[0]:,}, max_J = {X_pad.shape[1]}")

    # 4. 전체 Hit Rate 검증
    print("\n  전체 Test Hit Rate 검증...")
    hr_all, mp_all = compute_hit_rate(params, X_pad, mask, y_idx, Z_cov, K)
    stored_hr = lc_results['best_model']['metrics']['hit_rate_test']
    print(f"  계산된 HR: {hr_all:.4f} (저장된 값: {stored_hr:.4f})")

    # 5. 유형별 Hit Rate
    print(f"\n  {'유형':<12} {'Hit Rate':>10} {'Mean Prob':>10} {'N chains':>10}")
    print(f"  {'-'*44}")

    hit_rate_by_type = {}
    for ut, label in USER_TYPE_MAP.items():
        ut_mask = user_types == ut
        n_ut = int(ut_mask.sum())
        if n_ut < 10:
            continue

        hr_ut, mp_ut = compute_hit_rate(
            params,
            X_pad[ut_mask], mask[ut_mask], y_idx[ut_mask],
            Z_cov[ut_mask], K
        )

        hit_rate_by_type[label] = {
            'hit_rate': hr_ut,
            'mean_choice_prob': mp_ut,
            'n_chains': n_ut
        }

        print(f"  {label:<12} {hr_ut:>10.4f} {mp_ut:>10.4f} {n_ut:>10,}")

    # 6. JSON 업데이트
    lc_results['best_model']['metrics']['hit_rate_by_user_type'] = hit_rate_by_type
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(lc_results, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON 업데이트: {json_path.name}")

    # 7. LightGBM 비교
    lgb_path = RESULTS_DIR / "lightgbm_results.json"
    if lgb_path.exists():
        with open(lgb_path) as f:
            lgb = json.load(f)
        lgb_by_type = lgb['full_model']['hit_rate_by_user_type']

        print(f"\n  {'유형':<12} {'LC':>8} {'LGB-Full':>10} {'차이':>8}")
        print(f"  {'-'*40}")
        for label in hit_rate_by_type:
            lc_hr = hit_rate_by_type[label]['hit_rate']
            lgb_hr = lgb_by_type.get(label, {}).get('hit_rate', 0)
            diff = lc_hr - lgb_hr
            print(f"  {label:<12} {lc_hr:>7.1%} {lgb_hr:>9.1%} {diff:>+7.1%}p")

    print(f"\n  완료!")


if __name__ == '__main__':
    main()
