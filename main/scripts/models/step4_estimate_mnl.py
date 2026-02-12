"""
Phase 3 Step 4: MNL (Multinomial Logit) 모델 추정

입력 (output/iter{N}/):
- model_input_train.parquet

출력 (results/iter{N}/):
- mnl_results.json (추정 결과)

환경변수:
- ITERATION: 반복 회차 (기본 0)

모델:
1. Pooled MNL: 전체 이용자
2. Segmented MNL: 유형별 (5개)

효용함수:
V_j = β_ride * T_ride + β_walk * T_walk + β_transfer * N_transfer
    + β_subway * D_subway + β_peak_ride * (Peak×T_ride) + β_peak_xfer * (Peak×N_transfer)

구현: 순수 numpy/scipy (최적화된 벡터 연산)
"""

import sys
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from scipy.optimize import minimize
from scipy.stats import norm
import warnings
warnings.filterwarnings('ignore')

# 경로 설정 - iteration_paths 사용
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from utils.iteration_paths import get_paths, print_iteration_info

# Iteration별 경로 가져오기
paths = get_paths()

# 모델 변수 (T_wait 제거, Peak 상호작용 추가)
VARNAMES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway', 'Peak_T_ride', 'Peak_N_transfer']

# user_type 라벨
USER_TYPE_LABELS = {
    1: 'General',
    2: 'Children',
    3: 'Youth',
    4: 'Elderly',
    5: 'Disabled'
}


def prepare_data_for_mnl(df):
    """
    MNL 추정을 위한 데이터 준비 (벡터화)

    Returns:
        X_list: 각 choice set의 X 행렬 리스트
        y_list: 각 choice set의 선택 인덱스 리스트
        n_alts_list: 각 choice set의 대안 수 리스트
    """
    df = df.sort_values(['chain_id', 'alt_id']).reset_index(drop=True)

    # 그룹 경계 찾기
    chain_ids = df['chain_id'].values
    boundaries = np.where(np.diff(chain_ids) != 0)[0] + 1
    boundaries = np.concatenate([[0], boundaries, [len(df)]])

    X_all = df[VARNAMES].values.astype(np.float64)
    choice_all = df['choice'].values

    X_list = []
    y_list = []
    n_alts_list = []

    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        X_list.append(X_all[start:end])
        y_list.append(np.where(choice_all[start:end] == 1)[0][0])
        n_alts_list.append(end - start)

    return X_list, y_list, n_alts_list


def neg_log_likelihood(beta, X_list, y_list):
    """
    음의 로그 우도 계산 (최소화용)
    """
    ll = 0.0
    for X_i, y_i in zip(X_list, y_list):
        V = X_i @ beta
        V = V - V.max()  # 오버플로우 방지
        exp_V = np.exp(V)
        prob = exp_V / exp_V.sum()
        ll += np.log(prob[y_i] + 1e-10)
    return -ll


def neg_log_likelihood_with_grad(beta, X_list, y_list):
    """
    음의 로그 우도 + 그래디언트 계산 (최적화 가속)
    """
    n_vars = len(beta)
    ll = 0.0
    grad = np.zeros(n_vars)

    for X_i, y_i in zip(X_list, y_list):
        V = X_i @ beta
        V = V - V.max()
        exp_V = np.exp(V)
        prob = exp_V / exp_V.sum()

        ll += np.log(prob[y_i] + 1e-10)

        # 그래디언트: x_chosen - Σ(p_j * x_j)
        grad += X_i[y_i] - (prob.reshape(-1, 1) * X_i).sum(axis=0)

    return -ll, -grad


def compute_hessian(beta, X_list, y_list):
    """
    헤시안 행렬 계산 (표준오차용)
    """
    n_vars = len(beta)
    H = np.zeros((n_vars, n_vars))

    for X_i, y_i in zip(X_list, y_list):
        V = X_i @ beta
        V = V - V.max()
        exp_V = np.exp(V)
        prob = exp_V / exp_V.sum()

        # 헤시안 성분
        weighted_X = X_i * prob.reshape(-1, 1)
        H -= weighted_X.T @ X_i
        mean_X = weighted_X.sum(axis=0)
        H += np.outer(mean_X, mean_X)

    return H


def estimate_mnl(df, model_name="Pooled"):
    """MNL 모델 추정"""
    print(f"\n{'='*60}")
    print(f"MNL 추정: {model_name}")
    print(f"{'='*60}")

    n_chains = df['chain_id'].nunique()
    n_rows = len(df)
    print(f"체인: {n_chains:,}, 행: {n_rows:,}")

    # 데이터 준비
    print("데이터 준비 중...")
    start_time = datetime.now()
    X_list, y_list, n_alts_list = prepare_data_for_mnl(df)
    prep_time = (datetime.now() - start_time).total_seconds()
    print(f"데이터 준비 완료 ({prep_time:.1f}초)")

    # 초기값
    n_vars = len(VARNAMES)
    beta_init = np.zeros(n_vars)

    # 최적화 (L-BFGS-B with gradient)
    print("최적화 중...")
    start_time = datetime.now()

    result = minimize(
        neg_log_likelihood_with_grad,
        beta_init,
        args=(X_list, y_list),
        method='L-BFGS-B',
        jac=True,
        options={'maxiter': 1000, 'disp': False}
    )

    opt_time = (datetime.now() - start_time).total_seconds()
    print(f"최적화 완료 ({opt_time:.1f}초, 수렴: {result.success})")

    beta = result.x
    ll = -result.fun

    # 표준오차 계산 (헤시안 역행렬)
    print("표준오차 계산 중...")
    H = compute_hessian(beta, X_list, y_list)
    try:
        cov = np.linalg.inv(-H)
        se = np.sqrt(np.diag(cov))
    except:
        se = np.full(n_vars, np.nan)

    # 결과 출력
    print(f"\n추정 결과:")
    print("-" * 70)
    print(f"{'변수':<15} {'계수':>12} {'표준오차':>12} {'t-stat':>10} {'p-value':>10}")
    print("-" * 70)

    coefficients = {}
    for i, var in enumerate(VARNAMES):
        coef = beta[i]
        std_err = se[i]
        t_stat = coef / std_err if not np.isnan(std_err) and std_err != 0 else 0
        p_value = 2 * (1 - norm.cdf(abs(t_stat))) if t_stat != 0 else 1.0

        coefficients[var] = {
            'coef': float(coef),
            'std_err': float(std_err) if not np.isnan(std_err) else None,
            't_stat': float(t_stat),
            'p_value': float(p_value)
        }

        sig = '***' if p_value < 0.001 else '**' if p_value < 0.01 else '*' if p_value < 0.05 else ''
        se_str = f"{std_err:12.4f}" if not np.isnan(std_err) else "        N/A"
        print(f"{var:<15} {coef:>12.4f} {se_str} {t_stat:>10.2f} {p_value:>10.4f} {sig}")

    print("-" * 70)

    # Null log-likelihood (균등 확률)
    ll_null = sum(np.log(1.0 / n) for n in n_alts_list)

    # 적합도 지표
    rho_sq = 1 - (ll / ll_null)
    rho_sq_adj = 1 - ((ll - n_vars) / ll_null)
    aic = -2 * ll + 2 * n_vars
    bic = -2 * ll + n_vars * np.log(n_chains)

    print(f"\n적합도 지표:")
    print(f"  Log-Likelihood: {ll:,.2f}")
    print(f"  Null LL: {ll_null:,.2f}")
    print(f"  ρ² (Rho-squared): {rho_sq:.4f}")
    print(f"  Adjusted ρ²: {rho_sq_adj:.4f}")
    print(f"  AIC: {aic:,.2f}")
    print(f"  BIC: {bic:,.2f}")

    # Hit Rate 계산
    print("\nHit Rate 계산 중...")
    hits = 0
    prob_sum = 0
    for X_i, y_i in zip(X_list, y_list):
        V = X_i @ beta
        V = V - V.max()
        exp_V = np.exp(V)
        prob = exp_V / exp_V.sum()

        if np.argmax(prob) == y_i:
            hits += 1
        prob_sum += prob[y_i]

    hit_rate = hits / len(X_list)
    mean_prob = prob_sum / len(X_list)

    print(f"\n예측 성능:")
    print(f"  Hit Rate: {hit_rate*100:.2f}%")
    print(f"  Mean Choice Prob: {mean_prob:.4f}")

    metrics = {
        'log_likelihood': float(ll),
        'null_log_likelihood': float(ll_null),
        'rho_squared': float(rho_sq),
        'rho_squared_adj': float(rho_sq_adj),
        'aic': float(aic),
        'bic': float(bic),
        'hit_rate': float(hit_rate),
        'mean_choice_prob': float(mean_prob),
        'n_observations': int(n_chains),
        'n_parameters': int(n_vars)
    }

    # 가중치 계산
    beta_ride = abs(coefficients['T_ride']['coef'])
    if beta_ride > 0.001:
        weights = {
            'walk_weight': abs(coefficients['T_walk']['coef']) / beta_ride,
            'transfer_minutes': abs(coefficients['N_transfer']['coef']) / beta_ride,
        }
        print(f"\n가중치 (차내시간 기준):")
        print(f"  보행 가중치: {weights['walk_weight']:.2f}× (보행 1분 = 차내 {weights['walk_weight']:.1f}분)")
        print(f"  환승 페널티: {weights['transfer_minutes']:.1f}분 (환승 1회 = 차내 {weights['transfer_minutes']:.1f}분)")
    else:
        weights = {}
        print("\n[!] β_ride ≈ 0, 가중치 계산 불가")

    return {
        'model_name': model_name,
        'n_chains': int(n_chains),
        'n_rows': int(n_rows),
        'coefficients': coefficients,
        'metrics': metrics,
        'weights': weights,
        'converged': result.success
    }


def main():
    print("=" * 70)
    print("Phase 3 Step 4: MNL 모델 추정")
    print("=" * 70)
    print_iteration_info()
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 데이터 로드
    print("1. 데이터 로드 중...")
    train_df = pd.read_parquet(paths.model_input_train)
    print(f"   Train 데이터: {len(train_df):,} rows, {train_df['chain_id'].nunique():,} chains")

    # 상호작용 변수 생성 (Peak × 시간/환승)
    print("   상호작용 변수 생성: Peak_T_ride, Peak_N_transfer")
    train_df['Peak_T_ride'] = train_df['D_peak'] * train_df['T_ride']
    train_df['Peak_N_transfer'] = train_df['D_peak'] * train_df['N_transfer']
    print(f"   D_peak=1 비율: {train_df['D_peak'].mean()*100:.1f}%")
    print()

    # 변수 기술통계
    print("2. 변수 기술통계...")
    print(train_df[VARNAMES].describe().round(2).to_string())
    print()

    results = {}

    # 3. Pooled MNL
    print("\n" + "=" * 70)
    print("3. Pooled MNL (전체 이용자)")
    print("=" * 70)
    results['pooled'] = estimate_mnl(train_df, "Pooled (All Users)")

    # 4. 유형별 MNL
    print("\n" + "=" * 70)
    print("4. 유형별 MNL (Segmented)")
    print("=" * 70)

    results['by_type'] = {}
    for user_type in sorted(train_df['user_type'].unique()):
        type_df = train_df[train_df['user_type'] == user_type]
        type_label = USER_TYPE_LABELS.get(user_type, f"Type {user_type}")

        n_chains = type_df['chain_id'].nunique()
        if n_chains < 500:
            print(f"\n[!] {type_label}: 샘플 부족 ({n_chains} chains) - 건너뜀")
            continue

        results['by_type'][str(user_type)] = estimate_mnl(type_df, f"Type {user_type}: {type_label}")

    # 5. 결과 비교표
    print("\n" + "=" * 70)
    print("5. 유형별 결과 비교")
    print("=" * 70)

    print(f"\n{'유형':<12} {'β_ride':>8} {'β_walk':>8} {'β_xfer':>8} {'β_sub':>8} {'β_Pk×R':>8} {'β_Pk×X':>8} {'ρ²':>7} {'Hit%':>7}")
    print("-" * 95)

    # Pooled
    p = results['pooled']
    c = p['coefficients']
    print(f"{'Pooled':<12} {c['T_ride']['coef']:>8.4f} {c['T_walk']['coef']:>8.4f} {c['N_transfer']['coef']:>8.4f} {c['D_subway']['coef']:>8.4f} {c['Peak_T_ride']['coef']:>8.4f} {c['Peak_N_transfer']['coef']:>8.4f} {p['metrics']['rho_squared']:>7.4f} {p['metrics']['hit_rate']*100:>6.1f}%")

    # 유형별
    for ut, res in results['by_type'].items():
        label = USER_TYPE_LABELS.get(int(ut), f"Type {ut}")[:10]
        c = res['coefficients']
        print(f"{label:<12} {c['T_ride']['coef']:>8.4f} {c['T_walk']['coef']:>8.4f} {c['N_transfer']['coef']:>8.4f} {c['D_subway']['coef']:>8.4f} {c['Peak_T_ride']['coef']:>8.4f} {c['Peak_N_transfer']['coef']:>8.4f} {res['metrics']['rho_squared']:>7.4f} {res['metrics']['hit_rate']*100:>6.1f}%")

    # 6. 가중치 비교표
    print(f"\n{'유형':<12} {'보행가중치':>12} {'환승(분)':>12}")
    print("-" * 40)

    if results['pooled']['weights']:
        w = results['pooled']['weights']
        print(f"{'Pooled':<12} {w['walk_weight']:>12.2f} {w['transfer_minutes']:>12.1f}")

    for ut, res in results['by_type'].items():
        if res['weights']:
            label = USER_TYPE_LABELS.get(int(ut), f"Type {ut}")[:10]
            w = res['weights']
            print(f"{label:<12} {w['walk_weight']:>12.2f} {w['transfer_minutes']:>12.1f}")

    # 7. 결과 저장
    print("\n" + "=" * 70)
    print("6. 결과 저장")
    print("=" * 70)

    # JSON 저장
    json_path = paths.mnl_results
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"   JSON: {json_path}")

    # 상세 텍스트 저장
    txt_path = paths.results_dir / "mnl_results_detailed.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("MNL 추정 결과 상세\n")
        f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        # Pooled 결과
        f.write("1. Pooled MNL (전체 이용자)\n")
        f.write("-" * 50 + "\n")
        p = results['pooled']
        f.write(f"체인: {p['n_chains']:,}, 행: {p['n_rows']:,}\n\n")
        f.write(f"{'변수':<15} {'계수':>12} {'표준오차':>12} {'t-stat':>10}\n")
        for var, vals in p['coefficients'].items():
            se_str = f"{vals['std_err']:12.4f}" if vals['std_err'] else "        N/A"
            f.write(f"{var:<15} {vals['coef']:>12.4f} {se_str} {vals['t_stat']:>10.2f}\n")
        f.write(f"\nρ²: {p['metrics']['rho_squared']:.4f}\n")
        f.write(f"Hit Rate: {p['metrics']['hit_rate']*100:.2f}%\n")
        if p['weights']:
            f.write(f"\n가중치:\n")
            f.write(f"  보행: {p['weights']['walk_weight']:.2f}×\n")
            f.write(f"  환승: {p['weights']['transfer_minutes']:.1f}분\n")

        # 유형별 결과
        f.write("\n\n2. 유형별 MNL\n")
        f.write("-" * 50 + "\n")
        for ut, res in results['by_type'].items():
            label = USER_TYPE_LABELS.get(int(ut), f"Type {ut}")
            f.write(f"\n{label} (유형 {ut})\n")
            f.write(f"체인: {res['n_chains']:,}\n")
            for var, vals in res['coefficients'].items():
                f.write(f"  {var}: {vals['coef']:.4f} (t={vals['t_stat']:.2f})\n")
            f.write(f"  ρ²: {res['metrics']['rho_squared']:.4f}, Hit Rate: {res['metrics']['hit_rate']*100:.1f}%\n")
            if res['weights']:
                f.write(f"  보행가중치: {res['weights']['walk_weight']:.2f}×\n")

    print(f"   TXT: {txt_path}")

    print("\n" + "=" * 70)
    print("MNL 추정 완료!")
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
