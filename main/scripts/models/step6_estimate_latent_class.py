"""
Phase 3 Step 6: Latent Class Logit Model 추정 (v2 — 공변량 소속 함수)

입력:
- model_input_train.parquet (329K chains)
- model_input_test.parquet

출력:
- latent_class_results.json
- PHASE3_RESULTS2_LC.md

모델:
Latent Class Logit with covariates in class membership function

클래스 소속 확률 (개인별):
π_c(n) = exp(γ_c + δ_c'×Z_n) / Σ_k exp(γ_k + δ_k'×Z_n)
Z_n = [D_children, D_youth, D_elderly, D_disabled, D_peak]

효용함수 (class-specific, 4 core variables):
V^c_j = β^c_ride×T_ride + β^c_walk×T_walk + β^c_transfer×N_transfer + β^c_subway×D_subway

구현: 순수 numpy/scipy, 완전 벡터화
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

# ── 경로 설정 ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── 모델 변수 (Peak 제거 — ML에서 비유의) ─────────────────
VARNAMES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway']
N_VARS = len(VARNAMES)

# ── 클래스 소속 공변량 ─────────────────────────────────────
COV_NAMES = ['D_children', 'D_youth', 'D_elderly', 'D_disabled', 'D_peak']
N_COV = len(COV_NAMES)
N_MEMBERSHIP_PER_CLASS = 1 + N_COV  # intercept + covariates

USER_TYPE_LABELS = {
    1: 'General',
    2: 'Children',
    3: 'Youth',
    4: 'Elderly',
    5: 'Disabled'
}

# ── 추정 설정 ───────────────────────────────────────────────
K_VALUES = [2, 3, 4, 5]
N_STARTS = 10
MAX_ITER = 1000
FTOL = 1e-8
SAMPLE_SIZE = 50000

np.random.seed(42)


# ═══════════════════════════════════════════════════════════
# 1. 데이터 준비
# ═══════════════════════════════════════════════════════════

def prepare_padded_data(df):
    """
    가변 길이 choice set → 고정 크기 패딩.
    Returns:
        X_pad      : (N, max_J, 4)  attribute matrix
        mask       : (N, max_J)     1=valid, 0=padding
        y_idx      : (N,)           chosen alternative index
        n_alts     : (N,)           number of real alternatives
        user_types : (N,)           card type label
        chain_ids  : (N,)           chain_id
        Z_cov      : (N, 5)        membership covariates
    """
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
    n_alts = np.zeros(N, dtype=np.int64)
    user_types = np.zeros(N, dtype=np.int64)
    chain_ids = np.zeros(N, dtype=np.int64)
    peak_chain = np.zeros(N, dtype=np.float64)

    for i in range(N):
        s, e = boundaries[i], boundaries[i + 1]
        J_i = e - s
        X_pad[i, :J_i, :] = X_all[s:e]
        mask[i, :J_i] = 1.0
        y_idx[i] = np.where(choice_all[s:e] == 1)[0][0]
        n_alts[i] = J_i
        user_types[i] = user_type_all[s]
        chain_ids[i] = chain_ids_raw[s]
        peak_chain[i] = peak_all[s]

    # 소속 공변량 행렬 (N, 5)
    Z_cov = np.zeros((N, N_COV), dtype=np.float64)
    Z_cov[:, 0] = (user_types == 2).astype(np.float64)  # D_children
    Z_cov[:, 1] = (user_types == 3).astype(np.float64)  # D_youth
    Z_cov[:, 2] = (user_types == 4).astype(np.float64)  # D_elderly
    Z_cov[:, 3] = (user_types == 5).astype(np.float64)  # D_disabled
    Z_cov[:, 4] = peak_chain                              # D_peak

    return X_pad, mask, y_idx, n_alts, user_types, chain_ids, Z_cov


# ═══════════════════════════════════════════════════════════
# 2. 핵심 계산
# ═══════════════════════════════════════════════════════════

def individual_class_probs(membership_params, Z, K):
    """
    개인별 클래스 소속 확률.
    membership_params: ((K-1) * (1+N_COV),) — 마지막 클래스 K는 reference (0)
    Z: (N, N_COV)
    Returns: (K, N) class probabilities
    """
    N = Z.shape[0]
    npc = N_MEMBERSHIP_PER_CLASS  # 1 + N_COV = 6

    # α_c(n) = γ_c + δ_c' × Z_n
    alpha = np.zeros((K, N))
    for c in range(K - 1):
        gamma_c = membership_params[c * npc]
        delta_c = membership_params[c * npc + 1: (c + 1) * npc]
        alpha[c] = gamma_c + Z @ delta_c  # (N,)
    # alpha[K-1] = 0 (reference)

    # Softmax (numerical stability)
    alpha = alpha - alpha.max(axis=0, keepdims=True)
    exp_alpha = np.exp(alpha)
    pi = exp_alpha / exp_alpha.sum(axis=0, keepdims=True)  # (K, N)

    return pi


def mnl_probs_vectorized(X_pad, mask, beta):
    """class-specific MNL probabilities. Returns: (N, max_J)"""
    V = X_pad @ beta  # (N, max_J)
    V = np.where(mask == 1, V, -1e20)
    V = V - V.max(axis=1, keepdims=True)
    exp_V = np.exp(V)
    exp_V = np.where(mask == 1, exp_V, 0.0)
    denom = exp_V.sum(axis=1, keepdims=True)
    return exp_V / denom


def lc_neg_ll_and_grad(params, X_pad, mask, y_idx, Z, K):
    """
    음의 로그 우도 + 해석적 그래디언트 (개인별 소속 확률).

    params layout:
    [0 : (K-1)*npc]           = membership params (γ, δ per class)
    [(K-1)*npc : end]         = beta params (K × N_VARS)
    """
    N = X_pad.shape[0]
    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (K - 1) * npc

    # Unpack
    membership_params = params[:n_membership]
    betas = params[n_membership:].reshape(K, N_VARS)

    # 개인별 클래스 소속 확률
    pi = individual_class_probs(membership_params, Z, K)  # (K, N)

    # 각 클래스별 조건부 확률
    P_all = np.zeros((K, N, X_pad.shape[1]))
    L_nc = np.zeros((K, N))

    for c in range(K):
        P_c = mnl_probs_vectorized(X_pad, mask, betas[c])
        P_all[c] = P_c
        L_nc[c] = P_c[np.arange(N), y_idx]

    # Mixture likelihood
    mixture = (pi * L_nc).sum(axis=0)  # (N,)
    mixture = np.maximum(mixture, 1e-300)

    ll = np.log(mixture).sum()

    # ── Gradient ──
    w_nc = (pi * L_nc) / mixture[None, :]  # (K, N) posterior

    # Gradient w.r.t. membership params
    grad_membership = np.zeros(n_membership)
    Z_ext = np.column_stack([np.ones(N), Z])  # (N, 1+N_COV) = (N, 6)

    for m in range(K - 1):
        diff = w_nc[m] - pi[m]  # (N,)
        grad_m = (diff[:, None] * Z_ext).sum(axis=0)  # (1+N_COV,)
        grad_membership[m * npc: (m + 1) * npc] = grad_m

    # Gradient w.r.t. β^c
    grad_beta = np.zeros((K, N_VARS))
    X_chosen = X_pad[np.arange(N), y_idx, :]  # (N, N_VARS)

    for c in range(K):
        E_X = (P_all[c][:, :, None] * X_pad).sum(axis=1)  # (N, N_VARS)
        residual = X_chosen - E_X
        grad_beta[c] = (w_nc[c][:, None] * residual).sum(axis=0)

    grad = np.concatenate([grad_membership, grad_beta.ravel()])
    return -ll, -grad


# ═══════════════════════════════════════════════════════════
# 3. 추정
# ═══════════════════════════════════════════════════════════

def load_mnl_betas():
    """MNL 결과에서 4개 핵심 변수 초기값 로드"""
    mnl_path = RESULTS_DIR / "mnl_results.json"
    if not mnl_path.exists():
        return None, None
    with open(mnl_path, 'r') as f:
        mnl = json.load(f)

    pooled_beta = np.array([mnl['pooled']['coefficients'][v]['coef'] for v in VARNAMES])

    type_betas = {}
    for ut, res in mnl['by_type'].items():
        type_betas[int(ut)] = np.array([res['coefficients'][v]['coef'] for v in VARNAMES])

    return pooled_beta, type_betas


def generate_initial_params(K, pooled_beta, type_betas, start_idx):
    """시작점 생성"""
    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (K - 1) * npc

    # 소속 함수 초기값: 작은 랜덤값
    rng = np.random.RandomState(42 + start_idx * 100 + K * 1000)
    membership_init = rng.randn(n_membership) * 0.1

    if start_idx == 0 and type_betas is not None and len(type_betas) >= K:
        type_keys = sorted(type_betas.keys())[:K]
        betas_init = np.array([type_betas[k] for k in type_keys])
    elif pooled_beta is not None:
        perturbation = 1.0 + rng.uniform(-0.3, 0.3, size=(K, N_VARS))
        betas_init = pooled_beta[None, :] * perturbation
    else:
        betas_init = rng.randn(K, N_VARS) * 0.1

    return np.concatenate([membership_init, betas_init.ravel()])


def estimate_lc_single(X_pad, mask, y_idx, Z, K, params_init):
    """단일 시작점에서 LC 추정"""
    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (K - 1) * npc
    n_beta = K * N_VARS

    # Bounds: 소속 params [-5, 5], β [-10, 10]
    bounds = [(-5.0, 5.0)] * n_membership + [(-10.0, 10.0)] * n_beta

    result = minimize(
        lc_neg_ll_and_grad,
        params_init,
        args=(X_pad, mask, y_idx, Z, K),
        method='L-BFGS-B',
        jac=True,
        bounds=bounds,
        options={'maxiter': MAX_ITER, 'ftol': FTOL, 'disp': False}
    )
    return result


def estimate_lc_for_K(X_pad, mask, y_idx, Z, K, pooled_beta, type_betas):
    """K 클래스 LC 모델 추정 (다중 시작점)"""
    print(f"\n{'─'*50}")
    print(f"K = {K} 클래스 추정 ({N_STARTS} 시작점)")
    print(f"{'─'*50}")

    best_result = None
    best_ll = -np.inf
    n_converged = 0

    for s in range(N_STARTS):
        params_init = generate_initial_params(K, pooled_beta, type_betas, s)
        try:
            result = estimate_lc_single(X_pad, mask, y_idx, Z, K, params_init)
            ll = -result.fun
            converged = result.success
            if converged:
                n_converged += 1
            status = "✓" if converged else "×"
            print(f"  시작 {s:2d}: LL = {ll:,.2f} {status}")

            if ll > best_ll:
                best_ll = ll
                best_result = result
        except Exception as e:
            print(f"  시작 {s:2d}: 실패 ({e})")

    if best_result is not None:
        print(f"  → 최적 LL = {best_ll:,.2f} (수렴: {n_converged}/{N_STARTS})")
    else:
        print(f"  → 모든 시작점 실패!")

    return best_result, n_converged


# ═══════════════════════════════════════════════════════════
# 4. 모델 선택 + 표준 오차
# ═══════════════════════════════════════════════════════════

def compute_n_params(K):
    """총 파라미터 수"""
    return (K - 1) * N_MEMBERSHIP_PER_CLASS + K * N_VARS


def compute_information_criteria(ll, K, N):
    """BIC, AIC, CAIC"""
    n_params = compute_n_params(K)
    aic = -2 * ll + 2 * n_params
    bic = -2 * ll + n_params * np.log(N)
    caic = -2 * ll + n_params * (np.log(N) + 1)
    return {'AIC': aic, 'BIC': bic, 'CAIC': caic, 'n_params': n_params}


def compute_standard_errors(params, X_pad, mask, y_idx, Z, K):
    """수치 헤시안 기반 표준 오차"""
    n_params = len(params)
    eps = 1e-5

    H = np.zeros((n_params, n_params))

    for i in range(n_params):
        params_p = params.copy()
        params_m = params.copy()
        params_p[i] += eps
        params_m[i] -= eps
        _, grad_p = lc_neg_ll_and_grad(params_p, X_pad, mask, y_idx, Z, K)
        _, grad_m = lc_neg_ll_and_grad(params_m, X_pad, mask, y_idx, Z, K)
        H[i, :] = (grad_p - grad_m) / (2 * eps)

    try:
        H = (H + H.T) / 2
        cov = np.linalg.inv(H)
        se = np.sqrt(np.maximum(np.diag(cov), 0))
    except np.linalg.LinAlgError:
        se = np.full(n_params, np.nan)

    return se


# ═══════════════════════════════════════════════════════════
# 5. 사후 분석
# ═══════════════════════════════════════════════════════════

def compute_posteriors(params, X_pad, mask, y_idx, Z, K):
    """사후 확률 w_nc 계산"""
    N = X_pad.shape[0]
    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (K - 1) * npc

    membership_params = params[:n_membership]
    betas = params[n_membership:].reshape(K, N_VARS)

    pi = individual_class_probs(membership_params, Z, K)  # (K, N)

    L_nc = np.zeros((K, N))
    for c in range(K):
        P_c = mnl_probs_vectorized(X_pad, mask, betas[c])
        L_nc[c] = P_c[np.arange(N), y_idx]

    mixture = (pi * L_nc).sum(axis=0)
    mixture = np.maximum(mixture, 1e-300)
    w_nc = (pi * L_nc) / mixture[None, :]
    return w_nc, pi, betas


def cross_tabulation_analysis(w_nc, user_types, K):
    """교차표 분석"""
    hard_assign = np.argmax(w_nc, axis=0)

    type_values = sorted(np.unique(user_types))
    contingency = np.zeros((K, len(type_values)), dtype=np.int64)
    for c in range(K):
        for j, ut in enumerate(type_values):
            contingency[c, j] = np.sum((hard_assign == c) & (user_types == ut))

    from scipy.stats import chi2_contingency
    row_sums = contingency.sum(axis=1)
    valid_rows = row_sums > 0
    if valid_rows.sum() < 2:
        chi2_stat, p_value, dof = 0.0, 1.0, 0
        cramers_v = 0.0
    else:
        chi2_stat, p_value, dof, _ = chi2_contingency(contingency[valid_rows])
        n_total = contingency.sum()
        min_dim = min(valid_rows.sum(), len(type_values)) - 1
        cramers_v = np.sqrt(chi2_stat / (n_total * min_dim)) if min_dim > 0 else 0

    soft_assignment = {}
    for j, ut in enumerate(type_values):
        ut_mask = user_types == ut
        label = USER_TYPE_LABELS.get(ut, f"Type {ut}")
        soft_assignment[label] = w_nc[:, ut_mask].mean(axis=1).tolist()

    class_sizes = [int((hard_assign == c).sum()) for c in range(K)]

    return {
        'contingency_table': contingency.tolist(),
        'row_labels': [f"Class {c+1}" for c in range(K)],
        'col_labels': [USER_TYPE_LABELS.get(ut, f"Type {ut}") for ut in type_values],
        'chi_squared': float(chi2_stat),
        'dof': int(dof),
        'p_value': float(p_value),
        'cramers_v': float(cramers_v),
        'soft_assignment': soft_assignment,
        'class_sizes': class_sizes
    }


def profile_classes(betas, mean_pi):
    """클래스 프로파일링"""
    K = betas.shape[0]
    profiles = {}

    for c in range(K):
        beta = betas[c]
        traits = []

        if abs(beta[0]) > 0.08:
            traits.append("time-sensitive")
        elif beta[0] > 0:
            traits.append("comfort-seeking")

        if abs(beta[1]) > 1.0:
            traits.append("walk-averse")

        if abs(beta[2]) > 4.0:
            traits.append("transfer-averse")
        elif abs(beta[2]) < 2.0:
            traits.append("transfer-tolerant")

        if beta[3] > 3.0:
            traits.append("subway-preferring")
        elif beta[3] < 1.0:
            traits.append("subway-indifferent")

        if not traits:
            traits.append("moderate")

        name = " / ".join(traits[:3])
        profiles[f"class_{c+1}"] = {
            'name': name.title(),
            'weight': float(mean_pi[c]),
            'betas': {VARNAMES[k]: float(beta[k]) for k in range(N_VARS)},
            'traits': traits
        }

    return profiles


# ═══════════════════════════════════════════════════════════
# 6. 예측 성능
# ═══════════════════════════════════════════════════════════

def compute_hit_rate(params, X_pad, mask, y_idx, Z, K):
    """Hit rate + mean choice probability"""
    N = X_pad.shape[0]
    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (K - 1) * npc

    membership_params = params[:n_membership]
    betas = params[n_membership:].reshape(K, N_VARS)

    pi = individual_class_probs(membership_params, Z, K)  # (K, N)

    mix_probs = np.zeros((N, X_pad.shape[1]))
    for c in range(K):
        P_c = mnl_probs_vectorized(X_pad, mask, betas[c])
        mix_probs += pi[c][:, None] * P_c  # 개인별 가중치

    predicted = np.argmax(mix_probs, axis=1)
    hit_rate = (predicted == y_idx).mean()
    mean_prob = mix_probs[np.arange(N), y_idx].mean()

    return float(hit_rate), float(mean_prob)


# ═══════════════════════════════════════════════════════════
# 7. Markdown 리포트
# ═══════════════════════════════════════════════════════════

def generate_markdown_report(results):
    """Markdown 결과 리포트 생성"""
    lines = []
    lines.append("# Phase 3 Step 6: Latent Class Logit Model Results (v2)")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("**Key changes from v1:**")
    lines.append("- Covariates in class membership: user_type dummies + D_peak")
    lines.append("- Peak interactions removed from utility (non-significant in ML)")
    lines.append("- 4 core utility variables: T_ride, T_walk, N_transfer, D_subway")
    lines.append("")

    # ── Model Selection ──
    lines.append("## 1. Model Selection")
    lines.append("")
    lines.append("| K | #Params | Log-Likelihood | AIC | BIC | CAIC |")
    lines.append("|---|---------|---------------|-----|-----|------|")

    ms = results['model_selection']
    best_K = ms['best_K']
    for i, K in enumerate(ms['K_values']):
        ll = ms['log_likelihoods'][i]
        aic = ms['AIC'][i]
        bic = ms['BIC'][i]
        caic = ms['CAIC'][i]
        n_p = ms['n_params'][i]
        marker = " **" if K == best_K else ""
        lines.append(f"| {K}{marker} | {n_p} | {ll:,.2f} | {aic:,.2f} | {bic:,.2f} | {caic:,.2f} |")

    lines.append(f"\n**Best K = {best_K}** (minimum BIC)")
    lines.append("")

    # ── Best Model ──
    bm = results['best_model']
    lines.append("## 2. Best Model Parameters")
    lines.append(f"\n**K = {bm['K']} classes**")
    lines.append("")

    lines.append("### 2.1 Mean Class Weights")
    lines.append("")
    for c in range(bm['K']):
        pct = bm['class_weights'][c] * 100
        lines.append(f"- Class {c+1}: {pct:.1f}%")
    lines.append("")

    # Membership coefficients
    if 'membership_params' in bm:
        lines.append("### 2.2 Class Membership Coefficients")
        lines.append("")
        mp = bm['membership_params']
        header = "| Covariate |"
        sep = "|-----------|"
        for c in range(bm['K'] - 1):
            header += f" Class {c+1} (δ) | SE | t-stat |"
            sep += "------------|------|--------|"
        lines.append(header)
        lines.append(sep)

        cov_labels = ['Intercept'] + COV_NAMES
        for cov_name in cov_labels:
            row = f"| {cov_name} |"
            for c in range(bm['K'] - 1):
                key = f"class_{c+1}"
                if key in mp and cov_name in mp[key]:
                    info = mp[key][cov_name]
                    coef = info['coef']
                    se_val = info['std_err']
                    t = info['t_stat']
                    p = info['p_value']
                    sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
                    se_str = f"{se_val:.4f}" if se_val is not None and not np.isnan(se_val) else "N/A"
                    row += f" {coef:>8.4f}{sig} | {se_str} | {t:.2f} |"
            lines.append(row)
        lines.append("")

    # Utility parameters
    lines.append("### 2.3 Utility Parameter Estimates")
    lines.append("")
    header = "| Variable |"
    sep = "|----------|"
    for c in range(bm['K']):
        header += f" Class {c+1} (β) | SE | t-stat |"
        sep += "------------|------|--------|"
    lines.append(header)
    lines.append(sep)

    for var in VARNAMES:
        row = f"| {var} |"
        for c in range(bm['K']):
            key = f"class_{c+1}"
            info = bm['class_parameters'][key][var]
            coef = info['coef']
            se_val = info['std_err']
            t = info['t_stat']
            p = info['p_value']
            sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
            se_str = f"{se_val:.4f}" if se_val is not None and not np.isnan(se_val) else "N/A"
            row += f" {coef:>9.4f}{sig} | {se_str} | {t:.2f} |"
        lines.append(row)
    lines.append("")

    # ── Class Profiles ──
    lines.append("## 3. Class Profiles")
    lines.append("")
    for c in range(bm['K']):
        key = f"class_{c+1}"
        prof = bm['class_profiles'][key]
        lines.append(f"### Class {c+1}: {prof['name']} ({prof['weight']*100:.1f}%)")
        lines.append("")
        for var in VARNAMES:
            val = prof['betas'][var]
            lines.append(f"- {var}: {val:.4f}")
        lines.append(f"- Traits: {', '.join(prof['traits'])}")
        lines.append("")

    # ── Model Fit ──
    lines.append("## 4. Model Fit")
    lines.append("")
    m = bm['metrics']
    lines.append(f"- Log-Likelihood: {m['log_likelihood']:,.2f}")
    lines.append(f"- rho-squared: {m['rho_squared']:.4f}")
    lines.append(f"- AIC: {m['AIC']:,.2f}")
    lines.append(f"- BIC: {m['BIC']:,.2f}")
    lines.append(f"- Train Hit Rate: {m['hit_rate_train']*100:.2f}%")
    lines.append(f"- Test Hit Rate: {m['hit_rate_test']*100:.2f}%")
    lines.append("")

    # ── Cross-Tabulation ──
    ct = results['cross_tabulation']
    lines.append("## 5. Cross-Tabulation: Latent Class x Card Type")
    lines.append("")
    lines.append("### Hard Assignment")
    lines.append("")
    header = "| |"
    sep = "|---|"
    for col in ct['col_labels']:
        header += f" {col} |"
        sep += "------|"
    header += " Total |"
    sep += "------|"
    lines.append(header)
    lines.append(sep)

    table = ct['contingency_table']
    for i, row_label in enumerate(ct['row_labels']):
        row_vals = table[i]
        row_total = sum(row_vals)
        row = f"| {row_label} |"
        for v in row_vals:
            row += f" {v:,} |"
        row += f" {row_total:,} |"
        lines.append(row)

    lines.append("")
    lines.append(f"- Chi-squared: {ct['chi_squared']:,.2f} (df={ct['dof']})")
    lines.append(f"- p-value: {ct['p_value']:.2e}")
    lines.append(f"- Cramers V: {ct['cramers_v']:.4f}")
    lines.append("")

    # Soft assignment
    lines.append("### Soft Assignment (Mean Posterior per Card Type)")
    lines.append("")
    header = "| Card Type |"
    sep = "|-----------|"
    for c in range(bm['K']):
        header += f" Class {c+1} |"
        sep += "--------|"
    lines.append(header)
    lines.append(sep)
    for card_type, probs in ct['soft_assignment'].items():
        row = f"| {card_type} |"
        for p in probs:
            row += f" {p*100:.1f}% |"
        lines.append(row)
    lines.append("")

    # ── Comparison ──
    lines.append("## 6. Comparison with MNL")
    lines.append("")
    if 'mnl_comparison' in results:
        comp = results['mnl_comparison']
        lines.append("| Metric | Pooled MNL | LC Model | Improvement |")
        lines.append("|--------|-----------|----------|-------------|")
        for metric, vals in comp.items():
            if 'mnl' in vals and 'lc' in vals:
                diff = vals['lc'] - vals['mnl']
                sign = "+" if diff > 0 else ""
                lines.append(f"| {metric} | {vals['mnl']:.4f} | {vals['lc']:.4f} | {sign}{diff:.4f} |")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("Phase 3 Step 6: Latent Class Logit (v2 — covariate membership)")
    print("=" * 70)
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"효용 변수: {VARNAMES}")
    print(f"소속 공변량: {COV_NAMES}")
    print()

    # ── 1. 데이터 로드 ──
    print("1. 데이터 로드 중...")
    train_df = pd.read_parquet(OUTPUT_DIR / "model_input_train.parquet")
    n_total = train_df['chain_id'].nunique()
    print(f"   Train: {len(train_df):,} rows, {n_total:,} chains")

    # 층화 샘플링
    if SAMPLE_SIZE and SAMPLE_SIZE < n_total:
        print(f"   샘플링: {n_total:,} -> {SAMPLE_SIZE:,} 체인 (층화추출)")
        unique_chains = train_df.groupby('user_type')['chain_id'].unique()
        sampled_chains = []
        for ut, ut_chains in unique_chains.items():
            ut_ratio = len(ut_chains) / n_total
            ut_sample_size = int(SAMPLE_SIZE * ut_ratio)
            ut_sampled = np.random.choice(ut_chains, min(ut_sample_size, len(ut_chains)), replace=False)
            sampled_chains.extend(ut_sampled)
            label = USER_TYPE_LABELS.get(ut, f"Type {ut}")
            print(f"     {label}: {len(ut_sampled):,} 체인 ({ut_ratio*100:.1f}%)")
        sampled_chains = np.array(sampled_chains)
        train_df = train_df[train_df['chain_id'].isin(sampled_chains)].copy()
        print(f"   실제 샘플: {train_df['chain_id'].nunique():,} 체인, {len(train_df):,} 행")
    else:
        print("   전체 데이터 사용")

    print("   패딩 데이터 준비 중...")
    t0 = datetime.now()
    X_pad, mask, y_idx, n_alts, user_types, chain_ids, Z_cov = prepare_padded_data(train_df)
    N = X_pad.shape[0]
    max_J = X_pad.shape[1]
    print(f"   완료: N={N:,}, max_J={max_J}, Z={Z_cov.shape} ({(datetime.now()-t0).total_seconds():.1f}초)")

    # 공변량 분포 확인
    print(f"\n   공변량 분포:")
    for i, name in enumerate(COV_NAMES):
        pct = Z_cov[:, i].mean() * 100
        print(f"     {name}: {pct:.1f}%")
    print()

    # MNL 초기값
    pooled_beta, type_betas = load_mnl_betas()
    if pooled_beta is not None:
        print(f"   MNL 초기값 로드 완료 (4 core vars)")
    print()

    # Null LL
    ll_null = -np.log(n_alts.astype(np.float64)).sum()
    print(f"   Null LL: {ll_null:,.2f}")
    print()

    # ── 2. K별 추정 ──
    print("2. K별 Latent Class 모델 추정")
    print("=" * 70)

    all_results = {}
    for K in K_VALUES:
        result, n_conv = estimate_lc_for_K(X_pad, mask, y_idx, Z_cov, K, pooled_beta, type_betas)
        if result is not None:
            all_results[K] = (result, n_conv)

    # ── 3. 모델 선택 ──
    print("\n" + "=" * 70)
    print("3. 모델 선택")
    print("=" * 70)

    model_selection = {
        'K_values': [], 'log_likelihoods': [], 'AIC': [], 'BIC': [],
        'CAIC': [], 'n_params': [], 'n_converged': []
    }

    print(f"\n{'K':>3} {'#Params':>8} {'LL':>16} {'AIC':>16} {'BIC':>16} {'CAIC':>16} {'Conv':>6}")
    print("-" * 90)

    for K in K_VALUES:
        if K not in all_results:
            continue
        result, n_conv = all_results[K]
        ll = -result.fun
        ic = compute_information_criteria(ll, K, N)

        model_selection['K_values'].append(K)
        model_selection['log_likelihoods'].append(float(ll))
        model_selection['AIC'].append(float(ic['AIC']))
        model_selection['BIC'].append(float(ic['BIC']))
        model_selection['CAIC'].append(float(ic['CAIC']))
        model_selection['n_params'].append(int(ic['n_params']))
        model_selection['n_converged'].append(n_conv)

        print(f"{K:>3} {ic['n_params']:>8} {ll:>16,.2f} {ic['AIC']:>16,.2f} {ic['BIC']:>16,.2f} {ic['CAIC']:>16,.2f} {n_conv:>4}/{N_STARTS}")

    bic_values = model_selection['BIC']
    best_idx = np.argmin(bic_values)
    best_K = model_selection['K_values'][best_idx]
    model_selection['best_K'] = best_K
    print(f"\n-> 최적 K = {best_K} (최소 BIC = {bic_values[best_idx]:,.2f})")

    # ── 4. Best model 상세 분석 ──
    print("\n" + "=" * 70)
    print(f"4. 최적 모델 상세 분석 (K={best_K})")
    print("=" * 70)

    best_result = all_results[best_K][0]
    best_params = best_result.x
    best_ll = -best_result.fun

    npc = N_MEMBERSHIP_PER_CLASS
    n_membership = (best_K - 1) * npc
    membership_params_best = best_params[:n_membership]
    betas_best = best_params[n_membership:].reshape(best_K, N_VARS)

    # 평균 클래스 가중치
    pi_all = individual_class_probs(membership_params_best, Z_cov, best_K)  # (K, N)
    mean_pi = pi_all.mean(axis=1)

    print(f"\n평균 클래스 가중치:")
    for c in range(best_K):
        print(f"  Class {c+1}: {mean_pi[c]*100:.1f}%")

    # 유형별 클래스 소속 확률
    print(f"\n유형별 클래스 소속 확률:")
    print(f"{'유형':>10}", end="")
    for c in range(best_K):
        print(f" {'Class '+str(c+1):>10}", end="")
    print()
    for ut in sorted(np.unique(user_types)):
        ut_mask = user_types == ut
        label = USER_TYPE_LABELS.get(ut, f"Type {ut}")
        pi_ut = pi_all[:, ut_mask].mean(axis=1)
        print(f"{label:>10}", end="")
        for c in range(best_K):
            print(f" {pi_ut[c]*100:>9.1f}%", end="")
        print()

    # 표준오차
    print("\n표준오차 계산 중...")
    t0 = datetime.now()
    se = compute_standard_errors(best_params, X_pad, mask, y_idx, Z_cov, best_K)
    print(f"완료 ({(datetime.now()-t0).total_seconds():.1f}초)")

    # 소속 함수 파라미터
    print(f"\n소속 함수 파라미터 (reference = Class {best_K}):")
    cov_labels = ['Intercept'] + COV_NAMES
    membership_results = {}

    for c in range(best_K - 1):
        key = f"class_{c+1}"
        membership_results[key] = {}
        print(f"\n  Class {c+1}:")
        for j, cov_name in enumerate(cov_labels):
            param_idx = c * npc + j
            coef = membership_params_best[param_idx]
            std_err = se[param_idx] if param_idx < len(se) else np.nan
            t_stat = coef / std_err if not np.isnan(std_err) and std_err > 1e-10 else 0
            p_val = 2 * (1 - norm.cdf(abs(t_stat))) if t_stat != 0 else 1.0
            sig = '***' if p_val < 0.001 else '**' if p_val < 0.01 else '*' if p_val < 0.05 else ''
            print(f"    {cov_name:<15} {coef:>8.4f} (SE={std_err:.4f}, t={t_stat:.2f}){sig}")

            membership_results[key][cov_name] = {
                'coef': float(coef),
                'std_err': float(std_err) if not np.isnan(std_err) else None,
                't_stat': float(t_stat),
                'p_value': float(p_val)
            }

    # 효용 파라미터
    print(f"\n효용 파라미터:")
    print(f"{'변수':<15}", end="")
    for c in range(best_K):
        print(f"  {'Class '+str(c+1)+' B':>12} {'SE':>10} {'t':>8}", end="")
    print()
    print("-" * (15 + best_K * 32))

    class_parameters = {}
    for c in range(best_K):
        key = f"class_{c+1}"
        class_parameters[key] = {}
        for k, var in enumerate(VARNAMES):
            param_idx = n_membership + c * N_VARS + k
            coef = betas_best[c, k]
            std_err = se[param_idx] if param_idx < len(se) else np.nan
            t_stat = coef / std_err if not np.isnan(std_err) and std_err > 1e-10 else 0
            p_val = 2 * (1 - norm.cdf(abs(t_stat))) if t_stat != 0 else 1.0

            class_parameters[key][var] = {
                'coef': float(coef),
                'std_err': float(std_err) if not np.isnan(std_err) else None,
                't_stat': float(t_stat),
                'p_value': float(p_val)
            }

    for var in VARNAMES:
        row = f"{var:<15}"
        for c in range(best_K):
            key = f"class_{c+1}"
            info = class_parameters[key][var]
            coef = info['coef']
            se_v = info['std_err']
            t_v = info['t_stat']
            p_v = info['p_value']
            sig = '***' if p_v < 0.001 else '**' if p_v < 0.01 else '*' if p_v < 0.05 else ''
            se_str = f"{se_v:10.4f}" if se_v is not None else "       N/A"
            row += f"  {coef:>12.4f} {se_str} {t_v:>8.2f}{sig}"
        print(row)

    # Hit rate
    print("\n예측 성능 (Train)...")
    hit_train, prob_train = compute_hit_rate(best_params, X_pad, mask, y_idx, Z_cov, best_K)
    print(f"  Hit Rate: {hit_train*100:.2f}%")
    print(f"  Mean Choice Prob: {prob_train:.4f}")

    # ── 5. Test set ──
    print("\n" + "=" * 70)
    print("5. Test Set 평가")
    print("=" * 70)

    test_df = pd.read_parquet(OUTPUT_DIR / "model_input_test.parquet")
    print(f"   Test: {len(test_df):,} rows, {test_df['chain_id'].nunique():,} chains")

    X_test, mask_test, y_test, _, ut_test, _, Z_test = prepare_padded_data(test_df)
    hit_test, prob_test = compute_hit_rate(best_params, X_test, mask_test, y_test, Z_test, best_K)
    print(f"  Hit Rate: {hit_test*100:.2f}%")
    print(f"  Mean Choice Prob: {prob_test:.4f}")

    # ── 6. 교차표 ──
    print("\n" + "=" * 70)
    print("6. 교차표 분석 (Latent Class x Card Type)")
    print("=" * 70)

    w_nc, _, _ = compute_posteriors(best_params, X_pad, mask, y_idx, Z_cov, best_K)
    ct = cross_tabulation_analysis(w_nc, user_types, best_K)

    print(f"\n{'':>10}", end="")
    for col in ct['col_labels']:
        print(f" {col:>10}", end="")
    print(f" {'Total':>10}")
    print("-" * (10 + (len(ct['col_labels']) + 1) * 11))

    for i, row_label in enumerate(ct['row_labels']):
        row_vals = ct['contingency_table'][i]
        row_total = sum(row_vals)
        print(f"{row_label:>10}", end="")
        for v in row_vals:
            print(f" {v:>10,}", end="")
        print(f" {row_total:>10,}")

    print(f"\nChi-squared: {ct['chi_squared']:,.2f} (df={ct['dof']})")
    print(f"p-value: {ct['p_value']:.2e}")
    print(f"Cramers V: {ct['cramers_v']:.4f}")

    print(f"\nSoft Assignment (Mean Posterior %):")
    print(f"{'Card Type':>10}", end="")
    for c in range(best_K):
        print(f" {'Class '+str(c+1):>10}", end="")
    print()
    for card_type, probs in ct['soft_assignment'].items():
        print(f"{card_type:>10}", end="")
        for p in probs:
            print(f" {p*100:>9.1f}%", end="")
        print()

    # ── 7. 프로파일링 ──
    print("\n" + "=" * 70)
    print("7. 클래스 프로파일링")
    print("=" * 70)

    profiles = profile_classes(betas_best, mean_pi)
    for key, prof in profiles.items():
        print(f"\n  {key}: {prof['name']} ({prof['weight']*100:.1f}%)")
        for var in VARNAMES:
            print(f"    {var}: {prof['betas'][var]:.4f}")

    # ── 8. 결과 저장 ──
    print("\n" + "=" * 70)
    print("8. 결과 저장")
    print("=" * 70)

    rho_sq = 1 - (best_ll / ll_null)

    mnl_path = RESULTS_DIR / "mnl_results.json"
    mnl_comparison = {}
    if mnl_path.exists():
        with open(mnl_path, 'r') as f:
            mnl_res = json.load(f)
        mnl_metrics = mnl_res['pooled']['metrics']
        mnl_comparison = {
            'rho_squared': {'mnl': mnl_metrics['rho_squared'], 'lc': rho_sq},
            'hit_rate': {'mnl': mnl_metrics['hit_rate'], 'lc': hit_train},
            'mean_choice_prob': {'mnl': mnl_metrics['mean_choice_prob'], 'lc': prob_train},
        }

    final_results = {
        'model_selection': model_selection,
        'best_model': {
            'K': best_K,
            'class_weights': mean_pi.tolist(),
            'membership_params': membership_results,
            'class_parameters': class_parameters,
            'class_profiles': profiles,
            'metrics': {
                'log_likelihood': float(best_ll),
                'null_log_likelihood': float(ll_null),
                'rho_squared': float(rho_sq),
                'AIC': float(model_selection['AIC'][best_idx]),
                'BIC': float(model_selection['BIC'][best_idx]),
                'n_parameters': int(model_selection['n_params'][best_idx]),
                'hit_rate_train': float(hit_train),
                'hit_rate_test': float(hit_test),
                'mean_prob_train': float(prob_train),
                'mean_prob_test': float(prob_test),
                'n_observations': int(N),
                'converged': bool(best_result.success)
            }
        },
        'cross_tabulation': ct,
        'mnl_comparison': mnl_comparison,
        'estimation_info': {
            'K_values_tested': K_VALUES,
            'n_random_starts': N_STARTS,
            'max_iter': MAX_ITER,
            'ftol': FTOL,
            'utility_vars': VARNAMES,
            'membership_covariates': COV_NAMES,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    }

    json_path = RESULTS_DIR / "latent_class_results.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)
    print(f"   JSON: {json_path}")

    md_content = generate_markdown_report(final_results)
    md_path = RESULTS_DIR / "PHASE3_RESULTS2_LC.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"   Markdown: {md_path}")

    print("\n" + "=" * 70)
    print("Latent Class 모델 추정 완료!")
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
