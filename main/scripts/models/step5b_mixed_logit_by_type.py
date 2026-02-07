"""
Phase 3 Step 5b: Mixed Logit 유형별 추정 (최적화 버전)

사용법:
    python step5b_mixed_logit_by_type.py --type general
    python step5b_mixed_logit_by_type.py --type elderly
    python step5b_mixed_logit_by_type.py --type disabled
    python step5b_mixed_logit_by_type.py --type all  # 모든 유형 순차 실행

최적화:
1. 벡터화된 로그우도 계산 (draws 루프 제거)
2. 멀티프로세싱으로 체인별 병렬 처리
3. 유형별 독립 실행 가능
"""

import argparse
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from scipy.optimize import minimize
from scipy.stats import norm
from multiprocessing import Pool, cpu_count
import warnings
warnings.filterwarnings('ignore')

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# 모델 변수
VARNAMES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway', 'Peak_T_ride', 'Peak_N_transfer']
N_VARS = len(VARNAMES)

# 설정
N_DRAWS = 500
N_WORKERS = max(1, cpu_count() - 2)  # CPU 코어 - 2
MAX_SAMPLE_SIZE = 15000  # 유형별 최대 샘플 크기 (자동 샘플링)

# 유형 매핑 (실행 순서: 작은 것 먼저)
USER_TYPES = {
    'disabled': 5,
    'elderly': 4,
    'children': 2,
    'youth': 3,
    'general': 1  # 가장 마지막
}

# 실행 순서 (작은 샘플 → 큰 샘플)
RUN_ORDER = ['disabled', 'elderly', 'children', 'youth', 'general']


def halton_sequence(n, base):
    """Halton sequence 생성 (벡터화)"""
    sequence = np.zeros(n)
    for i in range(n):
        f, r, idx = 1.0, 0.0, i + 1
        while idx > 0:
            f /= base
            r += f * (idx % base)
            idx //= base
        sequence[i] = r
    return sequence


def generate_halton_draws(n_draws, n_dims):
    """다차원 Halton draws (표준정규 변환)"""
    primes = [2, 3, 5, 7, 11, 13]
    draws = np.zeros((n_draws, n_dims))
    for j in range(n_dims):
        h = halton_sequence(n_draws, primes[j])
        draws[:, j] = norm.ppf(np.clip(h, 0.001, 0.999))
    return draws


# 전역 변수 (멀티프로세싱용)
_DRAWS = None
_PARAMS = None


def init_worker(draws, params):
    """워커 초기화 - 전역 변수 설정"""
    global _DRAWS, _PARAMS
    _DRAWS = draws
    _PARAMS = params


def compute_chain_loglik(args):
    """단일 체인의 로그우도 계산 (벡터화)"""
    X_i, y_i = args
    global _DRAWS, _PARAMS

    n_draws = _DRAWS.shape[0]

    # 파라미터 추출
    beta_ride = _PARAMS[0]
    mu_walk, mu_transfer, mu_subway = _PARAMS[1], _PARAMS[2], _PARAMS[3]
    beta_peak_ride, beta_peak_xfer = _PARAMS[4], _PARAMS[5]
    sigma_walk = np.exp(_PARAMS[6])
    sigma_transfer = np.exp(_PARAMS[7])
    sigma_subway = np.exp(_PARAMS[8])

    # 랜덤 파라미터: (n_draws,) 각각
    beta_walk_r = mu_walk + sigma_walk * _DRAWS[:, 0]
    beta_transfer_r = mu_transfer + sigma_transfer * _DRAWS[:, 1]
    beta_subway_r = mu_subway + sigma_subway * _DRAWS[:, 2]

    # 효용 계산: (n_draws, n_alts)
    # X_i: (n_alts, n_vars)
    n_alts = X_i.shape[0]

    # 고정 부분: (n_alts,)
    V_fixed = (beta_ride * X_i[:, 0] +
               beta_peak_ride * X_i[:, 4] +
               beta_peak_xfer * X_i[:, 5])

    # 랜덤 부분: (n_draws, n_alts)
    V_random = (beta_walk_r[:, np.newaxis] * X_i[:, 1] +
                beta_transfer_r[:, np.newaxis] * X_i[:, 2] +
                beta_subway_r[:, np.newaxis] * X_i[:, 3])

    # 총 효용: (n_draws, n_alts)
    V = V_fixed + V_random

    # 오버플로우 방지
    V = V - V.max(axis=1, keepdims=True)
    exp_V = np.exp(V)
    probs = exp_V / exp_V.sum(axis=1, keepdims=True)  # (n_draws, n_alts)

    # 선택된 대안의 확률 평균
    avg_prob = probs[:, y_i].mean()

    return np.log(avg_prob + 1e-10)


def simulated_log_likelihood_parallel(params, X_list, y_list, draws, n_workers):
    """병렬 시뮬레이션 로그우도"""
    global _DRAWS, _PARAMS
    _DRAWS = draws
    _PARAMS = params

    if n_workers > 1:
        with Pool(n_workers, initializer=init_worker, initargs=(draws, params)) as pool:
            lls = pool.map(compute_chain_loglik, zip(X_list, y_list))
    else:
        # 단일 스레드
        lls = [compute_chain_loglik((X, y)) for X, y in zip(X_list, y_list)]

    return sum(lls)


def simulated_log_likelihood_vectorized(params, X_list, y_list, draws):
    """완전 벡터화된 로그우도 (단일 스레드, 메모리 효율적)"""
    n_draws = draws.shape[0]

    beta_ride = params[0]
    mu_walk, mu_transfer, mu_subway = params[1], params[2], params[3]
    beta_peak_ride, beta_peak_xfer = params[4], params[5]
    sigma_walk = np.exp(params[6])
    sigma_transfer = np.exp(params[7])
    sigma_subway = np.exp(params[8])

    # 랜덤 파라미터
    beta_walk_r = mu_walk + sigma_walk * draws[:, 0]
    beta_transfer_r = mu_transfer + sigma_transfer * draws[:, 1]
    beta_subway_r = mu_subway + sigma_subway * draws[:, 2]

    ll = 0.0

    for X_i, y_i in zip(X_list, y_list):
        # 고정 부분
        V_fixed = (beta_ride * X_i[:, 0] +
                   beta_peak_ride * X_i[:, 4] +
                   beta_peak_xfer * X_i[:, 5])

        # 랜덤 부분: (n_draws, n_alts)
        V_random = (beta_walk_r[:, np.newaxis] * X_i[:, 1] +
                    beta_transfer_r[:, np.newaxis] * X_i[:, 2] +
                    beta_subway_r[:, np.newaxis] * X_i[:, 3])

        V = V_fixed + V_random
        V = V - V.max(axis=1, keepdims=True)
        exp_V = np.exp(V)
        probs = exp_V / exp_V.sum(axis=1, keepdims=True)

        avg_prob = probs[:, y_i].mean()
        ll += np.log(avg_prob + 1e-10)

    return ll


def neg_ll(params, X_list, y_list, draws):
    """최소화용 음의 로그우도"""
    return -simulated_log_likelihood_vectorized(params, X_list, y_list, draws)


def prepare_data(df):
    """데이터 준비"""
    df = df.sort_values(['chain_id', 'alt_id']).reset_index(drop=True)

    chain_ids = df['chain_id'].values
    boundaries = np.where(np.diff(chain_ids) != 0)[0] + 1
    boundaries = np.concatenate([[0], boundaries, [len(df)]])

    X_all = df[VARNAMES].values.astype(np.float64)
    choice_all = df['choice'].values

    X_list, y_list, n_alts_list = [], [], []

    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        X_list.append(X_all[start:end])
        chosen_idx = np.where(choice_all[start:end] == 1)[0]
        y_list.append(chosen_idx[0] if len(chosen_idx) > 0 else 0)
        n_alts_list.append(end - start)

    return X_list, y_list, n_alts_list


def compute_hessian(params, X_list, y_list, draws, eps=1e-4):
    """수치적 헤시안"""
    n = len(params)
    H = np.zeros((n, n))

    for i in range(n):
        for j in range(i, n):
            pp, pm, mp, mm = [params.copy() for _ in range(4)]
            pp[i] += eps; pp[j] += eps
            pm[i] += eps; pm[j] -= eps
            mp[i] -= eps; mp[j] += eps
            mm[i] -= eps; mm[j] -= eps

            f_pp = neg_ll(pp, X_list, y_list, draws)
            f_pm = neg_ll(pm, X_list, y_list, draws)
            f_mp = neg_ll(mp, X_list, y_list, draws)
            f_mm = neg_ll(mm, X_list, y_list, draws)

            H[i, j] = (f_pp - f_pm - f_mp + f_mm) / (4 * eps * eps)
            H[j, i] = H[i, j]

    return H


def estimate_mixed_logit(df, model_name, n_draws=N_DRAWS, sample_size=None):
    """Mixed Logit 추정"""
    print(f"\n{'='*60}")
    print(f"Mixed Logit: {model_name}")
    print(f"{'='*60}")

    # 샘플링 (자동 또는 지정)
    n_total = df['chain_id'].nunique()

    # 샘플 크기 결정: 지정값 > 자동제한 > 전체
    if sample_size is None and n_total > MAX_SAMPLE_SIZE:
        sample_size = MAX_SAMPLE_SIZE
        print(f"⚠️ 자동 샘플링: {n_total:,} → {sample_size:,} 체인")

    if sample_size and sample_size < n_total:
        print(f"샘플링: {n_total:,} → {sample_size:,}")
        np.random.seed(42)
        chains = df['chain_id'].unique()
        sampled = np.random.choice(chains, sample_size, replace=False)
        df = df[df['chain_id'].isin(sampled)].copy()

    n_chains = df['chain_id'].nunique()
    print(f"체인: {n_chains:,}, 행: {len(df):,}")
    print(f"Draws: {n_draws}, CPU: {N_WORKERS}코어")

    # 데이터 준비
    print("데이터 준비...")
    X_list, y_list, n_alts_list = prepare_data(df)

    # Halton draws
    print("Halton draws 생성...")
    draws = generate_halton_draws(n_draws, 3)

    # 초기값
    params_init = np.array([
        -0.034,  # β_ride
        -0.775,  # μ_walk
        -3.413,  # μ_transfer
        +2.394,  # μ_subway
        -0.007,  # β_peak_ride
        +0.084,  # β_peak_xfer
        np.log(0.3),   # log(σ_walk)
        np.log(1.0),   # log(σ_transfer)
        np.log(0.5),   # log(σ_subway)
    ])

    # 최적화
    print("최적화 시작...")
    start = datetime.now()

    result = minimize(
        neg_ll,
        params_init,
        args=(X_list, y_list, draws),
        method='L-BFGS-B',
        options={'maxiter': 500, 'disp': True, 'ftol': 1e-6}
    )

    opt_time = (datetime.now() - start).total_seconds() / 60
    print(f"최적화 완료: {opt_time:.1f}분, 수렴: {result.success}")

    params = result.x
    ll = -result.fun

    # 파라미터 추출
    beta_ride = params[0]
    mu_walk, mu_transfer, mu_subway = params[1], params[2], params[3]
    beta_peak_ride, beta_peak_xfer = params[4], params[5]
    sigma_walk = np.exp(params[6])
    sigma_transfer = np.exp(params[7])
    sigma_subway = np.exp(params[8])

    # 표준오차
    print("표준오차 계산...")
    try:
        H = compute_hessian(params, X_list, y_list, draws)
        cov = np.linalg.inv(H)
        se = np.sqrt(np.abs(np.diag(cov)))
        se_sigma = [sigma_walk * se[6], sigma_transfer * se[7], sigma_subway * se[8]]
    except:
        se = np.full(9, np.nan)
        se_sigma = [np.nan, np.nan, np.nan]

    # 결과 출력
    def t_stat(coef, std_err):
        if np.isnan(std_err) or std_err == 0:
            return 0, ''
        t = coef / std_err
        p = 2 * (1 - norm.cdf(abs(t)))
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        return t, sig

    print(f"\n{'파라미터':<25} {'추정치':>10} {'SE':>10} {'t':>8} {'sig':>5}")
    print("-" * 60)

    t, sig = t_stat(beta_ride, se[0])
    print(f"{'T_ride (fixed)':<25} {beta_ride:>10.4f} {se[0]:>10.4f} {t:>8.2f} {sig:>5}")

    t, sig = t_stat(mu_walk, se[1])
    print(f"{'T_walk (μ)':<25} {mu_walk:>10.4f} {se[1]:>10.4f} {t:>8.2f} {sig:>5}")
    t, sig = t_stat(sigma_walk, se_sigma[0])
    print(f"{'T_walk (σ)':<25} {sigma_walk:>10.4f} {se_sigma[0]:>10.4f} {t:>8.2f} {sig:>5}")

    t, sig = t_stat(mu_transfer, se[2])
    print(f"{'N_transfer (μ)':<25} {mu_transfer:>10.4f} {se[2]:>10.4f} {t:>8.2f} {sig:>5}")
    t, sig = t_stat(sigma_transfer, se_sigma[1])
    print(f"{'N_transfer (σ)':<25} {sigma_transfer:>10.4f} {se_sigma[1]:>10.4f} {t:>8.2f} {sig:>5}")

    t, sig = t_stat(mu_subway, se[3])
    print(f"{'D_subway (μ)':<25} {mu_subway:>10.4f} {se[3]:>10.4f} {t:>8.2f} {sig:>5}")
    t, sig = t_stat(sigma_subway, se_sigma[2])
    print(f"{'D_subway (σ)':<25} {sigma_subway:>10.4f} {se_sigma[2]:>10.4f} {t:>8.2f} {sig:>5}")

    t, sig = t_stat(beta_peak_ride, se[4])
    print(f"{'Peak_T_ride (fixed)':<25} {beta_peak_ride:>10.4f} {se[4]:>10.4f} {t:>8.2f} {sig:>5}")

    t, sig = t_stat(beta_peak_xfer, se[5])
    print(f"{'Peak_N_transfer (fixed)':<25} {beta_peak_xfer:>10.4f} {se[5]:>10.4f} {t:>8.2f} {sig:>5}")

    # 적합도
    ll_null = sum(np.log(1.0 / n) for n in n_alts_list)
    rho_sq = 1 - (ll / ll_null)
    aic = -2 * ll + 18

    print(f"\n적합도:")
    print(f"  LL: {ll:,.2f}, Null LL: {ll_null:,.2f}")
    print(f"  ρ²: {rho_sq:.4f}")
    print(f"  AIC: {aic:,.2f}")

    # Hit Rate
    print("Hit Rate 계산...")
    beta_walk_r = mu_walk + sigma_walk * draws[:, 0]
    beta_transfer_r = mu_transfer + sigma_transfer * draws[:, 1]
    beta_subway_r = mu_subway + sigma_subway * draws[:, 2]

    hits = 0
    for X_i, y_i in zip(X_list, y_list):
        V_fixed = beta_ride * X_i[:, 0] + beta_peak_ride * X_i[:, 4] + beta_peak_xfer * X_i[:, 5]
        V_random = (beta_walk_r[:, np.newaxis] * X_i[:, 1] +
                    beta_transfer_r[:, np.newaxis] * X_i[:, 2] +
                    beta_subway_r[:, np.newaxis] * X_i[:, 3])
        V = V_fixed + V_random
        V = V - V.max(axis=1, keepdims=True)
        exp_V = np.exp(V)
        probs = exp_V / exp_V.sum(axis=1, keepdims=True)
        avg_prob = probs.mean(axis=0)
        if np.argmax(avg_prob) == y_i:
            hits += 1

    hit_rate = hits / len(X_list)
    print(f"  Hit Rate: {hit_rate*100:.2f}%")

    # 가중치
    if abs(beta_ride) > 0.001:
        walk_weight = abs(mu_walk) / abs(beta_ride)
        transfer_pen = abs(mu_transfer) / abs(beta_ride)
        walk_95 = [abs(mu_walk - 1.96*sigma_walk) / abs(beta_ride),
                   abs(mu_walk + 1.96*sigma_walk) / abs(beta_ride)]
        print(f"\n가중치:")
        print(f"  보행: {walk_weight:.1f}× (95%: {walk_95[0]:.1f}~{walk_95[1]:.1f})")
        print(f"  환승: {transfer_pen:.1f}분")

    return {
        'model_name': model_name,
        'n_chains': n_chains,
        'params': {
            'beta_ride': beta_ride,
            'mu_walk': mu_walk, 'sigma_walk': sigma_walk,
            'mu_transfer': mu_transfer, 'sigma_transfer': sigma_transfer,
            'mu_subway': mu_subway, 'sigma_subway': sigma_subway,
            'beta_peak_ride': beta_peak_ride,
            'beta_peak_xfer': beta_peak_xfer
        },
        'se': se.tolist(),
        'metrics': {
            'log_likelihood': ll,
            'rho_squared': rho_sq,
            'hit_rate': hit_rate,
            'aic': aic
        },
        'converged': result.success,
        'opt_time_min': opt_time
    }


def save_result(utype, result):
    """개별 유형 결과 즉시 저장"""
    out_file = RESULTS_DIR / f"mixed_logit_{utype}.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"  → 저장 완료: {out_file}")
    return out_file


def main():
    parser = argparse.ArgumentParser(description='Mixed Logit 유형별 추정')
    parser.add_argument('--type', choices=['general', 'elderly', 'disabled', 'children', 'youth', 'all'],
                        default='all', help='추정할 유형 (기본: all)')
    parser.add_argument('--sample', type=int, default=None,
                        help=f'샘플 크기 (기본: 자동, 최대 {MAX_SAMPLE_SIZE:,})')
    parser.add_argument('--draws', type=int, default=500, help='Simulation draws')
    parser.add_argument('--min-chains', type=int, default=500, help='최소 체인 수')
    args = parser.parse_args()

    print("=" * 60)
    print(f"Mixed Logit 유형별 추정 (최적화 버전)")
    print(f"유형: {args.type}, Draws: {args.draws}")
    print("=" * 60)

    # 데이터 로드
    print("\n데이터 로드...")
    train_df = pd.read_parquet(OUTPUT_DIR / "model_input_train.parquet")
    train_df['Peak_T_ride'] = train_df['D_peak'] * train_df['T_ride']
    train_df['Peak_N_transfer'] = train_df['D_peak'] * train_df['N_transfer']
    print(f"전체: {len(train_df):,} rows, {train_df['chain_id'].nunique():,} chains")

    # 유형별 체인 수 확인
    print("\n유형별 체인 수:")
    type_counts = train_df.groupby('user_type')['chain_id'].nunique()
    type_names = {1: 'General', 2: 'Children', 3: 'Youth', 4: 'Elderly', 5: 'Disabled'}
    for code, count in type_counts.items():
        name = type_names.get(code, f'Type {code}')
        print(f"  {name}: {count:,}")

    # 실행할 유형 결정
    if args.type == 'all':
        types_to_run = RUN_ORDER  # disabled → elderly → children → youth → general
    else:
        types_to_run = [args.type]

    print(f"\n실행 순서: {' → '.join(types_to_run)}")
    print("=" * 60)

    all_results = {}
    completed = []
    skipped = []

    for i, utype in enumerate(types_to_run, 1):
        type_code = USER_TYPES[utype]
        type_df = train_df[train_df['user_type'] == type_code].copy()

        n_chains = type_df['chain_id'].nunique()
        print(f"\n[{i}/{len(types_to_run)}] {utype.upper()}: {n_chains:,} 체인")

        if n_chains < args.min_chains:
            print(f"  → 샘플 부족 ({n_chains:,} < {args.min_chains:,}), 건너뜀")
            skipped.append(utype)
            continue

        try:
            result = estimate_mixed_logit(
                type_df,
                f"{utype.capitalize()}",
                n_draws=args.draws,
                sample_size=args.sample
            )
            all_results[utype] = result

            # 개별 결과 즉시 저장
            save_result(utype, result)
            completed.append(utype)

        except Exception as e:
            print(f"  → 오류 발생: {e}")
            skipped.append(utype)
            continue

    # 전체 결과 통합 저장
    if all_results:
        combined_file = RESULTS_DIR / "mixed_logit_by_type.json"
        with open(combined_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n통합 결과 저장: {combined_file}")

    # 요약
    print("\n" + "=" * 60)
    print("실행 요약")
    print("=" * 60)
    print(f"  완료: {', '.join(completed) if completed else '없음'}")
    print(f"  건너뜀: {', '.join(skipped) if skipped else '없음'}")

    if completed:
        print("\n저장된 파일:")
        for utype in completed:
            print(f"  - results/mixed_logit_{utype}.json")
        print(f"  - results/mixed_logit_by_type.json (통합)")

    print("\n완료!")


if __name__ == "__main__":
    main()
