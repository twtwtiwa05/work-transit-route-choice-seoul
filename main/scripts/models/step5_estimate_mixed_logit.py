"""
Phase 3 Step 5: Mixed Logit 모델 추정

입력:
- model_input_train.parquet

출력:
- mixed_logit_results.json (추정 결과)
- mixed_logit_results_detailed.txt (상세 결과)

모델:
1. Pooled Mixed Logit: 전체 이용자
2. Segmented Mixed Logit: 유형별 (샘플 충분한 경우)

효용함수:
V_j = β_ride * T_ride + β_walk * T_walk + β_transfer * N_transfer
    + β_subway * D_subway + β_peak_ride * (Peak×T_ride) + β_peak_xfer * (Peak×N_transfer)

랜덤 파라미터:
- T_walk ~ N(μ_walk, σ_walk)
- N_transfer ~ N(μ_transfer, σ_transfer)
- D_subway ~ N(μ_subway, σ_subway)

고정 파라미터:
- T_ride (정규화 기준)
- Peak_T_ride, Peak_N_transfer (추정 안정성)

구현: 순수 numpy/scipy + Halton sequence 시뮬레이션
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from scipy.optimize import minimize
from scipy.stats import norm
import warnings
warnings.filterwarnings('ignore')

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# 모델 변수
VARNAMES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway', 'Peak_T_ride', 'Peak_N_transfer']

# 랜덤 파라미터 (인덱스: T_walk=1, N_transfer=2, D_subway=3)
RANDOM_VARS = ['T_walk', 'N_transfer', 'D_subway']
RANDOM_INDICES = [1, 2, 3]  # VARNAMES에서의 인덱스
FIXED_INDICES = [0, 4, 5]   # T_ride, Peak_T_ride, Peak_N_transfer

# 시뮬레이션 설정
N_DRAWS = 500  # Halton draws 수 (500-1000 권장)
SAMPLE_SIZE = 30000  # 샘플링 체인 수 (None이면 전체 사용)

# user_type 라벨
USER_TYPE_LABELS = {
    1: 'General',
    2: 'Children',
    3: 'Youth',
    4: 'Elderly',
    5: 'Disabled'
}


def halton_sequence(n, base):
    """
    Halton sequence 생성 (의사난수, 저불일치 수열)

    Args:
        n: 생성할 숫자 개수
        base: 소수 기저 (2, 3, 5, 7, ...)

    Returns:
        길이 n의 Halton sequence (0, 1) 범위
    """
    sequence = np.zeros(n)
    for i in range(n):
        f = 1.0
        r = 0.0
        idx = i + 1
        while idx > 0:
            f = f / base
            r = r + f * (idx % base)
            idx = idx // base
        sequence[i] = r
    return sequence


def generate_halton_draws(n_draws, n_random_vars):
    """
    다차원 Halton draws 생성 후 표준정규분포로 변환

    Args:
        n_draws: draw 개수
        n_random_vars: 랜덤 파라미터 개수

    Returns:
        shape (n_draws, n_random_vars)의 표준정규 draws
    """
    primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    draws = np.zeros((n_draws, n_random_vars))

    for j in range(n_random_vars):
        # Halton sequence 생성 (0, 1)
        h = halton_sequence(n_draws, primes[j])
        # 표준정규분포로 변환 (역CDF)
        draws[:, j] = norm.ppf(np.clip(h, 0.001, 0.999))

    return draws


def prepare_data_for_mixl(df):
    """
    Mixed Logit 추정을 위한 데이터 준비

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


def simulated_log_likelihood(params, X_list, y_list, draws):
    """
    시뮬레이션 기반 로그우도 계산

    params 구조:
    - params[0]: β_ride (fixed)
    - params[1]: μ_walk (random mean)
    - params[2]: μ_transfer (random mean)
    - params[3]: μ_subway (random mean)
    - params[4]: β_peak_ride (fixed)
    - params[5]: β_peak_xfer (fixed)
    - params[6]: σ_walk (random std, exp로 양수 보장)
    - params[7]: σ_transfer (random std)
    - params[8]: σ_subway (random std)
    """
    n_draws = draws.shape[0]

    # 파라미터 추출
    beta_ride = params[0]
    mu_walk = params[1]
    mu_transfer = params[2]
    mu_subway = params[3]
    beta_peak_ride = params[4]
    beta_peak_xfer = params[5]

    # σ는 exp 변환으로 양수 보장
    sigma_walk = np.exp(params[6])
    sigma_transfer = np.exp(params[7])
    sigma_subway = np.exp(params[8])

    ll = 0.0

    for X_i, y_i in zip(X_list, y_list):
        # 각 draw에 대한 선택확률 계산
        prob_sum = 0.0

        for r in range(n_draws):
            # 이 draw에서의 랜덤 파라미터 값
            beta_walk = mu_walk + sigma_walk * draws[r, 0]
            beta_transfer = mu_transfer + sigma_transfer * draws[r, 1]
            beta_subway = mu_subway + sigma_subway * draws[r, 2]

            # 효용 계산
            # V = β_ride*X[:,0] + β_walk*X[:,1] + β_transfer*X[:,2] + β_subway*X[:,3]
            #   + β_peak_ride*X[:,4] + β_peak_xfer*X[:,5]
            V = (beta_ride * X_i[:, 0] +
                 beta_walk * X_i[:, 1] +
                 beta_transfer * X_i[:, 2] +
                 beta_subway * X_i[:, 3] +
                 beta_peak_ride * X_i[:, 4] +
                 beta_peak_xfer * X_i[:, 5])

            # 오버플로우 방지
            V = V - V.max()
            exp_V = np.exp(V)
            prob = exp_V / exp_V.sum()

            prob_sum += prob[y_i]

        # 시뮬레이션 평균
        avg_prob = prob_sum / n_draws
        ll += np.log(avg_prob + 1e-10)

    return ll


def neg_simulated_log_likelihood(params, X_list, y_list, draws):
    """최소화용 음의 로그우도"""
    return -simulated_log_likelihood(params, X_list, y_list, draws)


def compute_numerical_hessian(params, X_list, y_list, draws, eps=1e-4):
    """
    수치적 헤시안 계산 (중앙차분)
    """
    n_params = len(params)
    H = np.zeros((n_params, n_params))
    f0 = neg_simulated_log_likelihood(params, X_list, y_list, draws)

    for i in range(n_params):
        for j in range(i, n_params):
            params_pp = params.copy()
            params_pm = params.copy()
            params_mp = params.copy()
            params_mm = params.copy()

            params_pp[i] += eps
            params_pp[j] += eps
            params_pm[i] += eps
            params_pm[j] -= eps
            params_mp[i] -= eps
            params_mp[j] += eps
            params_mm[i] -= eps
            params_mm[j] -= eps

            f_pp = neg_simulated_log_likelihood(params_pp, X_list, y_list, draws)
            f_pm = neg_simulated_log_likelihood(params_pm, X_list, y_list, draws)
            f_mp = neg_simulated_log_likelihood(params_mp, X_list, y_list, draws)
            f_mm = neg_simulated_log_likelihood(params_mm, X_list, y_list, draws)

            H[i, j] = (f_pp - f_pm - f_mp + f_mm) / (4 * eps * eps)
            H[j, i] = H[i, j]

    return H


def estimate_mixed_logit(df, model_name="Pooled", n_draws=N_DRAWS):
    """Mixed Logit 모델 추정"""
    print(f"\n{'='*60}")
    print(f"Mixed Logit 추정: {model_name}")
    print(f"{'='*60}")

    n_chains = df['chain_id'].nunique()
    n_rows = len(df)
    print(f"체인: {n_chains:,}, 행: {n_rows:,}")
    print(f"시뮬레이션 draws: {n_draws}")

    # 데이터 준비
    print("데이터 준비 중...")
    start_time = datetime.now()
    X_list, y_list, n_alts_list = prepare_data_for_mixl(df)
    prep_time = (datetime.now() - start_time).total_seconds()
    print(f"데이터 준비 완료 ({prep_time:.1f}초)")

    # Halton draws 생성
    print("Halton draws 생성 중...")
    draws = generate_halton_draws(n_draws, len(RANDOM_VARS))
    print(f"Draws shape: {draws.shape}")

    # 초기값 (MNL 결과 기반)
    # params: [β_ride, μ_walk, μ_transfer, μ_subway, β_peak_ride, β_peak_xfer,
    #          log(σ_walk), log(σ_transfer), log(σ_subway)]
    params_init = np.array([
        -0.034,   # β_ride
        -0.775,   # μ_walk
        -3.413,   # μ_transfer
        +2.394,   # μ_subway
        -0.007,   # β_peak_ride
        +0.084,   # β_peak_xfer
        np.log(0.3),   # log(σ_walk) - 초기 σ=0.3
        np.log(1.0),   # log(σ_transfer) - 초기 σ=1.0
        np.log(0.5),   # log(σ_subway) - 초기 σ=0.5
    ])

    # 최적화
    print("최적화 중 (시간이 걸립니다)...")
    start_time = datetime.now()

    result = minimize(
        neg_simulated_log_likelihood,
        params_init,
        args=(X_list, y_list, draws),
        method='L-BFGS-B',
        options={'maxiter': 500, 'disp': True, 'ftol': 1e-6}
    )

    opt_time = (datetime.now() - start_time).total_seconds()
    print(f"최적화 완료 ({opt_time/60:.1f}분, 수렴: {result.success})")

    params = result.x
    ll = -result.fun

    # 파라미터 추출
    beta_ride = params[0]
    mu_walk = params[1]
    mu_transfer = params[2]
    mu_subway = params[3]
    beta_peak_ride = params[4]
    beta_peak_xfer = params[5]
    sigma_walk = np.exp(params[6])
    sigma_transfer = np.exp(params[7])
    sigma_subway = np.exp(params[8])

    # 표준오차 계산 (수치적 헤시안)
    print("표준오차 계산 중...")
    try:
        H = compute_numerical_hessian(params, X_list, y_list, draws)
        cov = np.linalg.inv(H)
        se = np.sqrt(np.abs(np.diag(cov)))

        # σ에 대한 delta method: se(exp(x)) = exp(x) * se(x)
        se_sigma = np.array([
            sigma_walk * se[6],
            sigma_transfer * se[7],
            sigma_subway * se[8]
        ])
    except Exception as e:
        print(f"헤시안 계산 실패: {e}")
        se = np.full(9, np.nan)
        se_sigma = np.full(3, np.nan)

    # 결과 출력
    print(f"\n추정 결과:")
    print("-" * 80)
    print(f"{'파라미터':<20} {'추정치':>12} {'표준오차':>12} {'t-stat':>10} {'유의수준':>10}")
    print("-" * 80)

    # Fixed 파라미터
    param_results = {}

    def calc_t_and_sig(coef, std_err):
        if np.isnan(std_err) or std_err == 0:
            return 0.0, 1.0, ''
        t = coef / std_err
        p = 2 * (1 - norm.cdf(abs(t)))
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        return t, p, sig

    # T_ride (fixed)
    t, p, sig = calc_t_and_sig(beta_ride, se[0])
    print(f"{'T_ride (fixed)':<20} {beta_ride:>12.4f} {se[0]:>12.4f} {t:>10.2f} {sig:>10}")
    param_results['T_ride'] = {'coef': beta_ride, 'std_err': se[0], 't_stat': t, 'p_value': p, 'type': 'fixed'}

    # T_walk (random)
    t_mu, p_mu, sig_mu = calc_t_and_sig(mu_walk, se[1])
    t_sig, p_sig, sig_sig = calc_t_and_sig(sigma_walk, se_sigma[0])
    print(f"{'T_walk (μ)':<20} {mu_walk:>12.4f} {se[1]:>12.4f} {t_mu:>10.2f} {sig_mu:>10}")
    print(f"{'T_walk (σ)':<20} {sigma_walk:>12.4f} {se_sigma[0]:>12.4f} {t_sig:>10.2f} {sig_sig:>10}")
    param_results['T_walk'] = {
        'mean': mu_walk, 'std': sigma_walk,
        'se_mean': se[1], 'se_std': se_sigma[0],
        't_mean': t_mu, 't_std': t_sig,
        'p_mean': p_mu, 'p_std': p_sig,
        'type': 'random'
    }

    # N_transfer (random)
    t_mu, p_mu, sig_mu = calc_t_and_sig(mu_transfer, se[2])
    t_sig, p_sig, sig_sig = calc_t_and_sig(sigma_transfer, se_sigma[1])
    print(f"{'N_transfer (μ)':<20} {mu_transfer:>12.4f} {se[2]:>12.4f} {t_mu:>10.2f} {sig_mu:>10}")
    print(f"{'N_transfer (σ)':<20} {sigma_transfer:>12.4f} {se_sigma[1]:>12.4f} {t_sig:>10.2f} {sig_sig:>10}")
    param_results['N_transfer'] = {
        'mean': mu_transfer, 'std': sigma_transfer,
        'se_mean': se[2], 'se_std': se_sigma[1],
        't_mean': t_mu, 't_std': t_sig,
        'p_mean': p_mu, 'p_std': p_sig,
        'type': 'random'
    }

    # D_subway (random)
    t_mu, p_mu, sig_mu = calc_t_and_sig(mu_subway, se[3])
    t_sig, p_sig, sig_sig = calc_t_and_sig(sigma_subway, se_sigma[2])
    print(f"{'D_subway (μ)':<20} {mu_subway:>12.4f} {se[3]:>12.4f} {t_mu:>10.2f} {sig_mu:>10}")
    print(f"{'D_subway (σ)':<20} {sigma_subway:>12.4f} {se_sigma[2]:>12.4f} {t_sig:>10.2f} {sig_sig:>10}")
    param_results['D_subway'] = {
        'mean': mu_subway, 'std': sigma_subway,
        'se_mean': se[3], 'se_std': se_sigma[2],
        't_mean': t_mu, 't_std': t_sig,
        'p_mean': p_mu, 'p_std': p_sig,
        'type': 'random'
    }

    # Peak_T_ride (fixed)
    t, p, sig = calc_t_and_sig(beta_peak_ride, se[4])
    print(f"{'Peak_T_ride (fixed)':<20} {beta_peak_ride:>12.4f} {se[4]:>12.4f} {t:>10.2f} {sig:>10}")
    param_results['Peak_T_ride'] = {'coef': beta_peak_ride, 'std_err': se[4], 't_stat': t, 'p_value': p, 'type': 'fixed'}

    # Peak_N_transfer (fixed)
    t, p, sig = calc_t_and_sig(beta_peak_xfer, se[5])
    print(f"{'Peak_N_transfer (fixed)':<20} {beta_peak_xfer:>12.4f} {se[5]:>12.4f} {t:>10.2f} {sig:>10}")
    param_results['Peak_N_transfer'] = {'coef': beta_peak_xfer, 'std_err': se[5], 't_stat': t, 'p_value': p, 'type': 'fixed'}

    print("-" * 80)

    # Null log-likelihood
    ll_null = sum(np.log(1.0 / n) for n in n_alts_list)

    # 적합도 지표
    n_params = 9
    rho_sq = 1 - (ll / ll_null)
    rho_sq_adj = 1 - ((ll - n_params) / ll_null)
    aic = -2 * ll + 2 * n_params
    bic = -2 * ll + n_params * np.log(n_chains)

    print(f"\n적합도 지표:")
    print(f"  Log-Likelihood: {ll:,.2f}")
    print(f"  Null LL: {ll_null:,.2f}")
    print(f"  ρ² (Rho-squared): {rho_sq:.4f}")
    print(f"  Adjusted ρ²: {rho_sq_adj:.4f}")
    print(f"  AIC: {aic:,.2f}")
    print(f"  BIC: {bic:,.2f}")

    # Hit Rate 계산 (시뮬레이션 평균 확률 기준)
    print("\nHit Rate 계산 중...")
    hits = 0
    prob_sum_total = 0

    for X_i, y_i in zip(X_list, y_list):
        prob_avg = np.zeros(len(X_i))

        for r in range(n_draws):
            beta_walk_r = mu_walk + sigma_walk * draws[r, 0]
            beta_transfer_r = mu_transfer + sigma_transfer * draws[r, 1]
            beta_subway_r = mu_subway + sigma_subway * draws[r, 2]

            V = (beta_ride * X_i[:, 0] +
                 beta_walk_r * X_i[:, 1] +
                 beta_transfer_r * X_i[:, 2] +
                 beta_subway_r * X_i[:, 3] +
                 beta_peak_ride * X_i[:, 4] +
                 beta_peak_xfer * X_i[:, 5])

            V = V - V.max()
            exp_V = np.exp(V)
            prob = exp_V / exp_V.sum()
            prob_avg += prob

        prob_avg /= n_draws

        if np.argmax(prob_avg) == y_i:
            hits += 1
        prob_sum_total += prob_avg[y_i]

    hit_rate = hits / len(X_list)
    mean_prob = prob_sum_total / len(X_list)

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
        'n_parameters': int(n_params),
        'n_draws': int(n_draws)
    }

    # 가중치 계산
    if abs(beta_ride) > 0.001:
        weights = {
            'walk_weight_mean': abs(mu_walk) / abs(beta_ride),
            'transfer_minutes_mean': abs(mu_transfer) / abs(beta_ride),
        }
        print(f"\n가중치 (차내시간 기준, 평균):")
        print(f"  보행 가중치: {weights['walk_weight_mean']:.2f}× (보행 1분 = 차내 {weights['walk_weight_mean']:.1f}분)")
        print(f"  환승 페널티: {weights['transfer_minutes_mean']:.1f}분")

        # 95% CI 계산
        walk_95_low = (abs(mu_walk) - 1.96*sigma_walk) / abs(beta_ride)
        walk_95_high = (abs(mu_walk) + 1.96*sigma_walk) / abs(beta_ride)
        transfer_95_low = (abs(mu_transfer) - 1.96*sigma_transfer) / abs(beta_ride)
        transfer_95_high = (abs(mu_transfer) + 1.96*sigma_transfer) / abs(beta_ride)

        print(f"  보행 가중치 95% 분포: [{walk_95_low:.1f}×, {walk_95_high:.1f}×]")
        print(f"  환승 페널티 95% 분포: [{transfer_95_low:.1f}분, {transfer_95_high:.1f}분]")

        weights['walk_weight_95_low'] = walk_95_low
        weights['walk_weight_95_high'] = walk_95_high
        weights['transfer_minutes_95_low'] = transfer_95_low
        weights['transfer_minutes_95_high'] = transfer_95_high
    else:
        weights = {}
        print("\n⚠️ β_ride ≈ 0, 가중치 계산 불가")

    return {
        'model_name': model_name,
        'n_chains': int(n_chains),
        'n_rows': int(n_rows),
        'coefficients': param_results,
        'metrics': metrics,
        'weights': weights,
        'converged': result.success,
        'optimization_time_min': opt_time / 60
    }


def main():
    print("=" * 70)
    print("Phase 3 Step 5: Mixed Logit 모델 추정")
    print("=" * 70)
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 데이터 로드
    print("1. 데이터 로드 중...")
    train_df = pd.read_parquet(OUTPUT_DIR / "model_input_train.parquet")
    print(f"   Train 데이터: {len(train_df):,} rows, {train_df['chain_id'].nunique():,} chains")

    # 상호작용 변수 생성
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

    # 3. Pooled Mixed Logit
    print("\n" + "=" * 70)
    print("3. Pooled Mixed Logit (전체 이용자)")
    print("=" * 70)

    # 샘플링 (대용량 데이터)
    n_total = train_df['chain_id'].nunique()
    unique_chains = train_df['chain_id'].unique()

    if SAMPLE_SIZE and SAMPLE_SIZE < n_total:
        print(f"   ⚠️ 샘플링: {n_total:,} → {SAMPLE_SIZE:,} 체인 (층화추출)")

        # 층화추출 (user_type별 비율 유지)
        np.random.seed(42)
        sampled_chains = []

        chain_user_type = train_df.groupby('chain_id')['user_type'].first()

        for ut in train_df['user_type'].unique():
            ut_chains = chain_user_type[chain_user_type == ut].index.values
            ut_ratio = len(ut_chains) / n_total
            ut_sample_size = int(SAMPLE_SIZE * ut_ratio)
            ut_sampled = np.random.choice(ut_chains, min(ut_sample_size, len(ut_chains)), replace=False)
            sampled_chains.extend(ut_sampled)

        sampled_chains = np.array(sampled_chains)
        sample_df = train_df[train_df['chain_id'].isin(sampled_chains)].copy()
        print(f"   실제 샘플: {sample_df['chain_id'].nunique():,} 체인, {len(sample_df):,} 행")
    else:
        sample_df = train_df
        print(f"   전체 데이터 사용: {n_total:,} 체인")

    results['pooled'] = estimate_mixed_logit(sample_df, "Pooled (All Users)", n_draws=N_DRAWS)

    # 4. 유형별 Mixed Logit (선택적 - 시간이 많이 걸림)
    print("\n" + "=" * 70)
    print("4. 유형별 Mixed Logit (샘플 충분한 경우만)")
    print("=" * 70)

    results['by_type'] = {}

    # 샘플이 충분한 유형만 추정 (최소 5,000 체인)
    MIN_CHAINS = 5000

    for user_type in sorted(sample_df['user_type'].unique()):
        type_df = sample_df[sample_df['user_type'] == user_type]
        type_label = USER_TYPE_LABELS.get(user_type, f"Type {user_type}")

        n_chains = type_df['chain_id'].nunique()
        if n_chains < MIN_CHAINS:
            print(f"\n⚠️ {type_label}: 샘플 부족 ({n_chains:,} chains < {MIN_CHAINS:,}) - 건너뜀")
            continue

        results['by_type'][str(user_type)] = estimate_mixed_logit(
            type_df, f"Type {user_type}: {type_label}", n_draws=N_DRAWS
        )

    # 5. MNL vs Mixed Logit 비교
    print("\n" + "=" * 70)
    print("5. MNL vs Mixed Logit 비교")
    print("=" * 70)

    # MNL 결과 로드
    try:
        with open(RESULTS_DIR / "mnl_results.json", 'r') as f:
            mnl_results = json.load(f)

        mnl_ll = mnl_results['pooled']['metrics']['log_likelihood']
        mnl_rho = mnl_results['pooled']['metrics']['rho_squared']
        mnl_hit = mnl_results['pooled']['metrics']['hit_rate']
        mnl_k = mnl_results['pooled']['metrics']['n_parameters']

        ml_ll = results['pooled']['metrics']['log_likelihood']
        ml_rho = results['pooled']['metrics']['rho_squared']
        ml_hit = results['pooled']['metrics']['hit_rate']
        ml_k = results['pooled']['metrics']['n_parameters']

        # 우도비 검정 (LRT)
        lrt_stat = 2 * (ml_ll - mnl_ll)
        lrt_df = ml_k - mnl_k  # 자유도 = 추가된 파라미터 수 (σ 3개)
        from scipy.stats import chi2
        lrt_pvalue = 1 - chi2.cdf(lrt_stat, lrt_df)

        print(f"\n{'지표':<25} {'MNL':>15} {'Mixed Logit':>15} {'차이':>15}")
        print("-" * 70)
        print(f"{'Log-Likelihood':<25} {mnl_ll:>15,.2f} {ml_ll:>15,.2f} {ml_ll-mnl_ll:>+15,.2f}")
        print(f"{'ρ²':<25} {mnl_rho:>15.4f} {ml_rho:>15.4f} {ml_rho-mnl_rho:>+15.4f}")
        print(f"{'Hit Rate':<25} {mnl_hit*100:>14.2f}% {ml_hit*100:>14.2f}% {(ml_hit-mnl_hit)*100:>+14.2f}%")
        print(f"{'파라미터 수':<25} {mnl_k:>15} {ml_k:>15} {ml_k-mnl_k:>+15}")
        print(f"{'AIC':<25} {mnl_results['pooled']['metrics']['aic']:>15,.2f} {results['pooled']['metrics']['aic']:>15,.2f}")
        print("-" * 70)
        print(f"\n우도비 검정 (LRT):")
        print(f"  χ² = {lrt_stat:.2f}, df = {lrt_df}, p-value = {lrt_pvalue:.2e}")
        if lrt_pvalue < 0.001:
            print("  → Mixed Logit이 MNL보다 유의하게 개선됨 (p < 0.001)")

        results['comparison'] = {
            'mnl_ll': mnl_ll,
            'ml_ll': ml_ll,
            'lrt_stat': lrt_stat,
            'lrt_df': lrt_df,
            'lrt_pvalue': lrt_pvalue
        }

    except Exception as e:
        print(f"MNL 결과 로드 실패: {e}")

    # 6. 결과 저장
    print("\n" + "=" * 70)
    print("6. 결과 저장")
    print("=" * 70)

    # JSON 저장
    json_path = RESULTS_DIR / "mixed_logit_results.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"   JSON: {json_path}")

    # 상세 텍스트 저장
    txt_path = RESULTS_DIR / "mixed_logit_results_detailed.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("Mixed Logit 추정 결과 상세\n")
        f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        # Pooled 결과
        f.write("1. Pooled Mixed Logit (전체 이용자)\n")
        f.write("-" * 50 + "\n")
        p = results['pooled']
        f.write(f"체인: {p['n_chains']:,}, 행: {p['n_rows']:,}\n")
        f.write(f"시뮬레이션 draws: {p['metrics']['n_draws']}\n\n")

        f.write(f"{'파라미터':<20} {'추정치':>12} {'표준오차':>12} {'t-stat':>10}\n")
        f.write("-" * 60 + "\n")

        for var, vals in p['coefficients'].items():
            if vals['type'] == 'fixed':
                se_str = f"{vals['std_err']:.4f}" if vals['std_err'] and not np.isnan(vals['std_err']) else "N/A"
                f.write(f"{var + ' (fixed)':<20} {vals['coef']:>12.4f} {se_str:>12} {vals['t_stat']:>10.2f}\n")
            else:
                se_mean = f"{vals['se_mean']:.4f}" if vals['se_mean'] and not np.isnan(vals['se_mean']) else "N/A"
                se_std = f"{vals['se_std']:.4f}" if vals['se_std'] and not np.isnan(vals['se_std']) else "N/A"
                f.write(f"{var + ' (μ)':<20} {vals['mean']:>12.4f} {se_mean:>12} {vals['t_mean']:>10.2f}\n")
                f.write(f"{var + ' (σ)':<20} {vals['std']:>12.4f} {se_std:>12} {vals['t_std']:>10.2f}\n")

        f.write("\n")
        f.write(f"ρ²: {p['metrics']['rho_squared']:.4f}\n")
        f.write(f"Hit Rate: {p['metrics']['hit_rate']*100:.2f}%\n")
        f.write(f"AIC: {p['metrics']['aic']:,.2f}\n")

        if p['weights']:
            f.write(f"\n가중치 (평균):\n")
            f.write(f"  보행: {p['weights']['walk_weight_mean']:.2f}×\n")
            f.write(f"  환승: {p['weights']['transfer_minutes_mean']:.1f}분\n")
            if 'walk_weight_95_low' in p['weights']:
                f.write(f"  보행 95% 분포: [{p['weights']['walk_weight_95_low']:.1f}×, {p['weights']['walk_weight_95_high']:.1f}×]\n")

        # 유형별 결과
        if results['by_type']:
            f.write("\n\n2. 유형별 Mixed Logit\n")
            f.write("-" * 50 + "\n")
            for ut, res in results['by_type'].items():
                label = USER_TYPE_LABELS.get(int(ut), f"Type {ut}")
                f.write(f"\n{label} (유형 {ut})\n")
                f.write(f"체인: {res['n_chains']:,}\n")
                for var, vals in res['coefficients'].items():
                    if vals['type'] == 'fixed':
                        f.write(f"  {var}: {vals['coef']:.4f} (t={vals['t_stat']:.2f})\n")
                    else:
                        f.write(f"  {var} (μ): {vals['mean']:.4f} (t={vals['t_mean']:.2f})\n")
                        f.write(f"  {var} (σ): {vals['std']:.4f} (t={vals['t_std']:.2f})\n")
                f.write(f"  ρ²: {res['metrics']['rho_squared']:.4f}, Hit Rate: {res['metrics']['hit_rate']*100:.1f}%\n")

    print(f"   TXT: {txt_path}")

    print("\n" + "=" * 70)
    print("Mixed Logit 추정 완료!")
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
