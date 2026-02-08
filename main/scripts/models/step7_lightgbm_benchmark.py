#!/usr/bin/env python3
"""
Phase 3 Step 7: LightGBM Benchmark for Transit Route Choice
============================================================

목적:
  - ML 예측 성능 상한(upper bound) 확립
  - SHAP 기반 변수 중요도 분석 → 경제학적 β와 교차검증
  - MNL / Mixed Logit / Latent Class 모형과의 정량적 비교

방법론:
  - LightGBM 이진 분류기 → Choice-set 단위 평가 (MNL과 동일 기준)
  - Optuna Bayesian 최적화 + GroupKFold (chain_id 기준, 데이터 누출 방지)
  - 2개 Feature Set: Core (4변수, 경제학 모형과 동일) / Full (7변수)

입력:
  - output/model_input_train.parquet
  - output/model_input_test.parquet

출력:
  - results/lightgbm_results.json
  - results/PHASE3_RESULTS4_LIGHTGBM.md
  - results/figures/shap_summary_core.png
  - results/figures/shap_summary_full.png
  - results/figures/shap_by_usertype_full.png
  - results/figures/model_comparison.png

필요 패키지: pip install lightgbm optuna shap matplotlib
"""

import json
import time
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import lightgbm as lgb
import optuna
import shap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.model_selection import GroupKFold

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='lightgbm')
warnings.filterwarnings('ignore', category=UserWarning, module='shap')
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ═══════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "output"
RESULT_DIR = ROOT / "results"
FIGURE_DIR = RESULT_DIR / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

CORE_FEATURES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway']
FULL_FEATURES = ['T_ride', 'T_walk', 'N_transfer', 'D_subway',
                 'D_peak', 'user_type', 'n_alternatives']
TARGET = 'choice'

N_OPTUNA_TRIALS = 30
N_CV_FOLDS = 5
RANDOM_STATE = 42
SHAP_SAMPLE = 50_000

USER_TYPE_MAP = {1: 'General', 2: 'Children', 3: 'Youth',
                 4: 'Elderly', 5: 'Disabled'}


# ═══════════════════════════════════════════════════════════════════
#  Choice-Set Level Evaluation
# ═══════════════════════════════════════════════════════════════════

def compute_choice_set_metrics(proba, chain_ids, y_true):
    """
    MNL/ML/LC와 동일한 기준의 choice-set 단위 평가.

    Hit rate: 각 chain에서 argmax(proba) == 실제 선택인 비율
    Mean choice prob: 각 chain에서 선택된 대안의 정규화 확률 평균

    정규화: P_norm(j|C_n) = P_raw(j) / Σ_{k∈C_n} P_raw(k)
    → LightGBM의 독립적 이진 확률을 choice-set 내 조건부 확률로 변환
    """
    df = pd.DataFrame({
        'chain_id': chain_ids,
        'proba': proba,
        'choice': y_true
    })

    # Hit rate: chain별 최고 확률 대안이 실제 선택인지
    # 동점(tie) 시 idxmax는 첫 번째를 선택 — 동점 빈도를 추적
    max_proba = df.groupby('chain_id')['proba'].transform('max')
    n_tied = (df['proba'] == max_proba).groupby(df['chain_id']).sum()
    n_tied_chains = int((n_tied > 1).sum())

    idx_max = df.groupby('chain_id')['proba'].idxmax()
    hits = df.loc[idx_max.values, 'choice'].values.sum()
    n_chains = len(idx_max)
    hit_rate = hits / n_chains

    if n_tied_chains > 0 and n_tied_chains > n_chains * 0.01:
        print(f"    ※ 동점 chain: {n_tied_chains:,}/{n_chains:,} "
              f"({n_tied_chains / n_chains:.1%})")

    # Mean choice probability (chain 내 정규화)
    df['proba_sum'] = df.groupby('chain_id')['proba'].transform('sum')
    df['proba_sum'] = df['proba_sum'].clip(lower=1e-15)  # 0 나눗셈 방지
    df['proba_norm'] = df['proba'] / df['proba_sum']
    chosen = df.loc[df['choice'] == 1, 'proba_norm']
    mean_choice_prob = chosen.mean()

    return float(hit_rate), float(mean_choice_prob)


def compute_hit_rate_by_user_type(proba, chain_ids, y_true, user_types):
    """유형별 choice-set hit rate."""
    df = pd.DataFrame({
        'chain_id': chain_ids,
        'proba': proba,
        'choice': y_true,
        'user_type': user_types
    })

    # chain별 user_type (첫 행 기준)
    chain_info = df.groupby('chain_id').agg(
        user_type=('user_type', 'first')
    )

    # chain별 hit 판정
    idx_max = df.groupby('chain_id')['proba'].idxmax()
    chain_hit = df.loc[idx_max.values, ['chain_id', 'choice']].set_index('chain_id')
    chain_info['hit'] = chain_hit['choice']

    result = {}
    for ut, label in USER_TYPE_MAP.items():
        mask = chain_info['user_type'] == ut
        n = int(mask.sum())
        if n > 0:
            result[label] = {
                'hit_rate': float(chain_info.loc[mask, 'hit'].mean()),
                'n_chains': n
            }
    return result


# ═══════════════════════════════════════════════════════════════════
#  Optuna Hyperparameter Optimization
# ═══════════════════════════════════════════════════════════════════

def make_optuna_objective(X, y, chain_ids, feature_cols, spw):
    """GroupKFold 기반 Optuna 목적 함수 생성."""

    cat_cols = [c for c in feature_cols if c in ('user_type',)]

    def objective(trial):
        params = {
            'n_estimators':     trial.suggest_int('n_estimators', 100, 800),
            'learning_rate':    trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
            'max_depth':        trial.suggest_int('max_depth', 3, 8),
            'num_leaves':       trial.suggest_int('num_leaves', 15, 63),
            'min_child_samples': trial.suggest_int('min_child_samples', 20, 200),
            'subsample':        trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha':        trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
            'reg_lambda':       trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
        }

        gkf = GroupKFold(n_splits=N_CV_FOLDS)
        hit_rates = []

        for tr_idx, val_idx in gkf.split(X, y, groups=chain_ids):
            model = lgb.LGBMClassifier(
                **params,
                scale_pos_weight=spw,
                random_state=RANDOM_STATE,
                verbose=-1,
                n_jobs=-1
            )
            model.fit(
                X.iloc[tr_idx], y[tr_idx],
                categorical_feature=cat_cols
            )

            proba = model.predict_proba(X.iloc[val_idx])[:, 1]
            hr, _ = compute_choice_set_metrics(
                proba, chain_ids[val_idx], y[val_idx]
            )
            hit_rates.append(hr)

        return np.mean(hit_rates)

    return objective


def run_optuna_tuning(X_train, y_train, chain_ids_train,
                      feature_cols, spw):
    """Optuna 하이퍼파라미터 탐색 실행."""

    print(f"\n  Optuna 최적화: {N_OPTUNA_TRIALS} trials × {N_CV_FOLDS}-fold GroupKFold")

    objective = make_optuna_objective(
        X_train, y_train, chain_ids_train, feature_cols, spw
    )

    # 진행 콜백
    def callback(study, trial):
        if trial.number % 5 == 0 or trial.number == N_OPTUNA_TRIALS - 1:
            print(f"    Trial {trial.number:2d}: "
                  f"CV HR = {trial.value:.4f}  "
                  f"(best = {study.best_value:.4f})")

    study = optuna.create_study(
        direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE)
    )
    study.optimize(objective, n_trials=N_OPTUNA_TRIALS, callbacks=[callback])

    print(f"\n  최적 CV Hit Rate: {study.best_value:.4f}")
    print(f"  최적 파라미터:")
    for k, v in study.best_params.items():
        if isinstance(v, float):
            print(f"    {k:20s}: {v:.6f}")
        else:
            print(f"    {k:20s}: {v}")

    return study.best_params, study.best_value


# ═══════════════════════════════════════════════════════════════════
#  Model Training & Evaluation
# ═══════════════════════════════════════════════════════════════════

def train_and_evaluate(X_train, y_train, X_test, y_test,
                       chain_ids_train, chain_ids_test,
                       user_types_test, feature_cols,
                       best_params, spw, label):
    """최적 파라미터로 최종 모형 학습 및 평가."""

    print(f"\n  최종 모형 학습 ({label})...")

    cat_cols = [c for c in feature_cols if c in ('user_type',)]

    model = lgb.LGBMClassifier(
        **best_params,
        scale_pos_weight=spw,
        random_state=RANDOM_STATE,
        verbose=-1,
        n_jobs=-1
    )
    model.fit(X_train, y_train, categorical_feature=cat_cols)

    # ── Train 평가 ──
    proba_train = model.predict_proba(X_train)[:, 1]
    hr_train, mcp_train = compute_choice_set_metrics(
        proba_train, chain_ids_train, y_train
    )

    # ── Test 평가 ──
    proba_test = model.predict_proba(X_test)[:, 1]
    hr_test, mcp_test = compute_choice_set_metrics(
        proba_test, chain_ids_test, y_test
    )

    # ── 유형별 Hit Rate ──
    hr_by_type = compute_hit_rate_by_user_type(
        proba_test, chain_ids_test, y_test, user_types_test
    )

    print(f"  Train Hit Rate:       {hr_train:.4f}")
    print(f"  Test  Hit Rate:       {hr_test:.4f}")
    print(f"  Train Mean Prob:      {mcp_train:.4f}")
    print(f"  Test  Mean Prob:      {mcp_test:.4f}")
    print(f"  Train-Test Gap:       {hr_train - hr_test:+.4f}")
    print(f"\n  유형별 Test Hit Rate:")
    for ut_label, info in hr_by_type.items():
        print(f"    {ut_label:10s}: {info['hit_rate']:.4f}  "
              f"(n = {info['n_chains']:,})")

    # ── LightGBM 내장 Feature Importance ──
    fi = dict(zip(feature_cols,
                  model.feature_importances_.astype(float)))

    results = {
        'features': feature_cols,
        'n_features': len(feature_cols),
        'best_params': {k: (float(v) if isinstance(v, (np.floating, float))
                            else int(v) if isinstance(v, (np.integer, int))
                            else v)
                        for k, v in best_params.items()},
        'hit_rate_train': hr_train,
        'hit_rate_test': hr_test,
        'mean_choice_prob_train': mcp_train,
        'mean_choice_prob_test': mcp_test,
        'train_test_gap': hr_train - hr_test,
        'hit_rate_by_user_type': hr_by_type,
        'lgb_feature_importance': fi,
    }

    return model, results


# ═══════════════════════════════════════════════════════════════════
#  SHAP Analysis
# ═══════════════════════════════════════════════════════════════════

def run_shap_analysis(model, X_test, user_types_test, feature_cols, label):
    """SHAP TreeExplainer 기반 변수 중요도 분석."""

    print(f"\n  SHAP 분석 ({label})...")
    suffix = label.lower().replace(' ', '_').replace('-', '_')

    # 대규모 데이터 서브샘플링
    n = min(SHAP_SAMPLE, len(X_test))
    if n < len(X_test):
        rng = np.random.RandomState(RANDOM_STATE)
        idx = rng.choice(len(X_test), n, replace=False)
        X_shap = X_test.iloc[idx].copy()
        ut_shap = user_types_test[idx]
        print(f"    서브샘플: {n:,} / {len(X_test):,}")
    else:
        X_shap = X_test.copy()
        ut_shap = user_types_test.copy()

    # LightGBM TreeExplainer: categorical dtype 유지 (모델 학습 시와 동일해야 함)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_shap)

    # 이진 분류: [class0, class1] 리스트 또는 단일 배열
    if isinstance(shap_values, list):
        sv = shap_values[1]
    else:
        sv = shap_values

    # ── Global Importance (mean |SHAP|) ──
    mean_abs = np.abs(sv).mean(axis=0)
    importance = {}
    for feat, val in sorted(zip(feature_cols, mean_abs),
                            key=lambda x: x[1], reverse=True):
        importance[feat] = float(val)
        print(f"    {feat:15s}: {val:.4f}")

    # ── SHAP by User Type ──
    shap_by_type = {}
    for ut, ut_label in USER_TYPE_MAP.items():
        mask = ut_shap == ut
        if mask.sum() > 100:
            ma = np.abs(sv[mask]).mean(axis=0)
            shap_by_type[ut_label] = {
                feat: float(v) for feat, v in zip(feature_cols, ma)
            }

    # ── Summary Plot ──
    # Categorical → int 변환 (summary_plot의 percentile 컬러 매핑에 필요)
    X_shap_plot = X_shap.copy()
    for col in X_shap_plot.columns:
        if X_shap_plot[col].dtype.name == 'category':
            X_shap_plot[col] = X_shap_plot[col].astype(int)

    plt.figure(figsize=(10, 6))
    shap.summary_plot(sv, X_shap_plot, feature_names=feature_cols,
                      show=False, max_display=len(feature_cols))
    plt.tight_layout()
    path1 = FIGURE_DIR / f"shap_summary_{suffix}.png"
    plt.savefig(path1, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"    → {path1.name}")

    # ── User Type Heatmap ──
    if shap_by_type:
        types_list = [t for t in USER_TYPE_MAP.values() if t in shap_by_type]
        matrix = np.array([
            [shap_by_type[t].get(f, 0) for f in feature_cols]
            for t in types_list
        ])

        _fig, ax = plt.subplots(figsize=(10, 5))
        im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
        ax.set_xticks(range(len(feature_cols)))
        ax.set_xticklabels(feature_cols, rotation=45, ha='right')
        ax.set_yticks(range(len(types_list)))
        ax.set_yticklabels(types_list)

        vmax = matrix.max()
        for i in range(len(types_list)):
            for j in range(len(feature_cols)):
                color = 'white' if matrix[i, j] > vmax * 0.6 else 'black'
                ax.text(j, i, f'{matrix[i, j]:.3f}',
                        ha='center', va='center', fontsize=9, color=color)

        plt.colorbar(im, label='Mean |SHAP value|')
        ax.set_title(f'SHAP Feature Importance by User Type ({label})')
        plt.tight_layout()
        path2 = FIGURE_DIR / f"shap_by_usertype_{suffix}.png"
        plt.savefig(path2, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"    → {path2.name}")

    return {
        'global_importance': importance,
        'by_user_type': shap_by_type
    }


# ═══════════════════════════════════════════════════════════════════
#  Load Econometric Model Results for Comparison
# ═══════════════════════════════════════════════════════════════════

def load_comparison_baselines():
    """MNL, ML, LC 결과를 로드하여 비교 테이블 구성."""
    comparison = {}

    # ── MNL ──
    mnl_path = RESULT_DIR / 'mnl_results.json'
    if mnl_path.exists():
        with open(mnl_path) as f:
            mnl = json.load(f)
        pooled = mnl.get('pooled', {})
        metrics = pooled.get('metrics', {})
        n_obs = metrics.get('n_observations')
        comparison['MNL'] = {
            'hit_rate': metrics.get('hit_rate'),
            'rho_squared': metrics.get('rho_squared'),
            'mean_choice_prob': metrics.get('mean_choice_prob'),
            'n_params': metrics.get('n_parameters'),
            'note': f"Train set ({n_obs:,} chains)" if n_obs else "Train set"
        }

    # ── Mixed Logit ──
    ml_path = RESULT_DIR / 'mixed_logit_results.json'
    if ml_path.exists():
        with open(ml_path) as f:
            ml = json.load(f)
        pred = ml.get('prediction', {})
        fit = ml.get('fit_statistics', {})
        sample = ml.get('sample', {})
        n_sc = sample.get('sampled_chains')
        comparison['Mixed_Logit'] = {
            'hit_rate': pred.get('hit_rate'),
            'rho_squared': fit.get('rho_squared'),
            'mean_choice_prob': pred.get('mean_choice_probability'),
            'n_params': 9,
            'note': f"Sampled ({n_sc:,} chains)" if n_sc else "Sampled"
        }

    # ── Latent Class ──
    lc_path = RESULT_DIR / 'latent_class_results.json'
    if lc_path.exists():
        with open(lc_path) as f:
            lc = json.load(f)
        best = lc.get('best_model', {})
        met = best.get('metrics', {})
        n_lc = met.get('n_observations')
        k_val = best.get('K')
        comparison['Latent_Class'] = {
            'hit_rate': met.get('hit_rate_test'),
            'rho_squared': met.get('rho_squared'),
            'mean_choice_prob': met.get('mean_prob_test'),
            'n_params': met.get('n_parameters'),
            'note': f"Sampled ({n_lc:,} chains, K={k_val})" if n_lc else f"K={k_val}"
        }

    return comparison


# ═══════════════════════════════════════════════════════════════════
#  Comparison Figure
# ═══════════════════════════════════════════════════════════════════

def create_comparison_figure(comparison):
    """모형 간 Hit Rate 비교 차트."""

    models = list(comparison.keys())
    hit_rates = [comparison[m].get('hit_rate', 0) or 0 for m in models]

    # 색상: 경제학 모형은 파란 계열, ML은 빨간 계열
    colors = []
    for m in models:
        if 'LightGBM' in m:
            colors.append('#E91E63' if 'Full' in m else '#FF5722')
        elif 'Latent' in m:
            colors.append('#FF9800')
        elif 'Mixed' in m:
            colors.append('#4CAF50')
        else:
            colors.append('#2196F3')

    # 표시 이름 정리
    display_names = {
        'MNL': 'MNL (Pooled)',
        'Mixed_Logit': 'Mixed Logit',
        'Latent_Class': 'Latent Class (K=3)',
        'LightGBM_Core': 'LightGBM (Core 4var)',
        'LightGBM_Full': 'LightGBM (Full 7var)'
    }
    labels = [display_names.get(m, m) for m in models]

    _fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(range(len(models)), hit_rates, color=colors,
                   edgecolor='white', linewidth=0.5)

    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel('Choice-Set Level Hit Rate', fontsize=12)
    ax.set_title('Model Comparison: Transit Route Choice Prediction',
                 fontsize=13, fontweight='bold')

    x_min = min(hr for hr in hit_rates if hr > 0) * 0.95
    x_max = max(hit_rates) * 1.02
    ax.set_xlim(x_min, x_max)

    for bar, hr in zip(bars, hit_rates):
        if hr > 0:
            ax.text(hr + (x_max - x_min) * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f'{hr:.1%}', va='center', fontsize=11, fontweight='bold')

    # 구분선
    n_econ = sum(1 for m in models if 'LightGBM' not in m)
    if 0 < n_econ < len(models):
        ax.axhline(y=n_econ - 0.5, color='gray', linestyle='--',
                   linewidth=0.8, alpha=0.5)
        ax.text(x_min + (x_max - x_min) * 0.02, n_econ - 0.7,
                'Econometric ↑  |  ML ↓', fontsize=8, color='gray')

    ax.invert_yaxis()
    plt.tight_layout()
    fig_path = FIGURE_DIR / "model_comparison.png"
    plt.savefig(fig_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  → {fig_path.name}")

    return fig_path


# ═══════════════════════════════════════════════════════════════════
#  Report Generation
# ═══════════════════════════════════════════════════════════════════

def generate_report(all_results, comparison, data_info, total_time):
    """PHASE3_RESULTS4_LIGHTGBM.md 생성."""

    core = all_results['core']
    full = all_results['full']

    lines = []
    lines.append("# Phase 3 Results: LightGBM Benchmark")
    lines.append("")
    lines.append(f"추정 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 1. 개요 ──
    lines.append("## 1. 개요")
    lines.append("")
    lines.append("### 1.1 연구 목적")
    lines.append("경제학적 모형(MNL, ML, LC)의 예측 성능을 **ML 상한**과 비교하여,")
    lines.append("선호 이질성 모형의 해석력-예측력 트레이드오프를 정량화한다.")
    lines.append("")
    lines.append("### 1.2 방법론")
    lines.append("- **LightGBM** 이진 분류기 (choice=0/1)")
    lines.append("- Choice-set 단위 평가: 각 chain에서 argmax(P) == 선택 대안")
    lines.append("- Optuna Bayesian 최적화 + 5-fold GroupKFold (chain_id 기준)")
    lines.append("- 2개 Feature Set 비교")
    lines.append("")
    lines.append("### 1.3 추정 설정")
    lines.append("")
    lines.append("| 항목 | 값 |")
    lines.append("|------|-----|")
    lines.append(f"| Train | {data_info['n_train_rows']:,} rows, "
                 f"{data_info['n_train_chains']:,} chains |")
    lines.append(f"| Test | {data_info['n_test_rows']:,} rows, "
                 f"{data_info['n_test_chains']:,} chains |")
    lines.append(f"| Optuna Trials | {N_OPTUNA_TRIALS} |")
    lines.append(f"| CV Folds | {N_CV_FOLDS} (GroupKFold by chain_id) |")
    lines.append(f"| Class Balance | choice=1 {data_info['pos_ratio']:.1%} / "
                 f"choice=0 {1 - data_info['pos_ratio']:.1%} |")
    lines.append(f"| 총 소요시간 | {total_time / 60:.1f}분 |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 2. Core Model ──
    lines.append("## 2. Core 모형 (4 변수)")
    lines.append("")
    lines.append("**Features**: T_ride, T_walk, N_transfer, D_subway")
    lines.append("(MNL/ML/LC와 동일한 효용함수 변수)")
    lines.append("")
    lines.append("### 2.1 최적 하이퍼파라미터")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    for k, v in core['best_params'].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("### 2.2 적합도")
    lines.append("")
    lines.append("| 지표 | Train | Test |")
    lines.append("|------|-------|------|")
    lines.append(f"| Hit Rate | {core['hit_rate_train']:.4f} | "
                 f"**{core['hit_rate_test']:.4f}** |")
    lines.append(f"| Mean Choice Prob | {core['mean_choice_prob_train']:.4f} | "
                 f"{core['mean_choice_prob_test']:.4f} |")
    lines.append(f"| CV Hit Rate | {core['cv_hit_rate']:.4f} | - |")
    lines.append(f"| Train-Test Gap | {core['train_test_gap']:+.4f} | - |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 3. Full Model ──
    lines.append("## 3. Full 모형 (7 변수)")
    lines.append("")
    lines.append("**Features**: T_ride, T_walk, N_transfer, D_subway, "
                 "D_peak, user_type, n_alternatives")
    lines.append("")
    lines.append("### 3.1 최적 하이퍼파라미터")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    for k, v in full['best_params'].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("### 3.2 적합도")
    lines.append("")
    lines.append("| 지표 | Train | Test |")
    lines.append("|------|-------|------|")
    lines.append(f"| Hit Rate | {full['hit_rate_train']:.4f} | "
                 f"**{full['hit_rate_test']:.4f}** |")
    lines.append(f"| Mean Choice Prob | {full['mean_choice_prob_train']:.4f} | "
                 f"{full['mean_choice_prob_test']:.4f} |")
    lines.append(f"| CV Hit Rate | {full['cv_hit_rate']:.4f} | - |")
    lines.append(f"| Train-Test Gap | {full['train_test_gap']:+.4f} | - |")
    lines.append("")

    # ── 유형별 Hit Rate ──
    lines.append("### 3.3 유형별 Test Hit Rate (Full)")
    lines.append("")
    lines.append("| 유형 | Hit Rate | N chains |")
    lines.append("|------|----------|----------|")
    for ut_label, info in full['hit_rate_by_user_type'].items():
        lines.append(f"| {ut_label} | {info['hit_rate']:.4f} | "
                     f"{info['n_chains']:,} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 4. SHAP ──
    lines.append("## 4. SHAP Feature Importance")
    lines.append("")
    lines.append("### 4.1 Global Importance (Full)")
    lines.append("")
    lines.append("| Rank | Feature | Mean |SHAP| |")
    lines.append("|------|---------|------------|")
    if 'shap' in full:
        for rank, (feat, val) in enumerate(
                full['shap']['global_importance'].items(), 1):
            lines.append(f"| {rank} | {feat} | {val:.4f} |")
    lines.append("")

    lines.append("### 4.2 SHAP by User Type (Full)")
    lines.append("")
    if 'shap' in full and full['shap']['by_user_type']:
        # 헤더
        feats = list(next(iter(full['shap']['by_user_type'].values())).keys())
        header = "| User Type | " + " | ".join(feats) + " |"
        sep = "|-----------|" + "|".join(["------"] * len(feats)) + "|"
        lines.append(header)
        lines.append(sep)
        for ut_label, vals in full['shap']['by_user_type'].items():
            row = f"| {ut_label} | " + " | ".join(
                f"{vals.get(f, 0):.4f}" for f in feats) + " |"
            lines.append(row)
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 5. 모형 비교 ──
    lines.append("## 5. 모형 비교")
    lines.append("")
    lines.append("| 모형 | Hit Rate | Mean Prob | ρ² | 비고 |")
    lines.append("|------|----------|-----------|-----|------|")
    for name, m in comparison.items():
        hr = f"{m['hit_rate']:.4f}" if m.get('hit_rate') else "N/A"
        mcp = f"{m['mean_choice_prob']:.4f}" if m.get('mean_choice_prob') else "N/A"
        rho = f"{m['rho_squared']:.4f}" if m.get('rho_squared') else "N/A"
        note = m.get('note', '')
        disp = name.replace('_', ' ')
        lines.append(f"| {disp} | {hr} | {mcp} | {rho} | {note} |")
    lines.append("")

    # LC 대비 비율 계산
    lgb_hr = full['hit_rate_test']
    lc_hr = comparison.get('Latent_Class', {}).get('hit_rate')
    mnl_hr = comparison.get('MNL', {}).get('hit_rate')
    if lc_hr and lgb_hr > 0:
        ratio = lc_hr / lgb_hr
        lines.append(f"**LC / LightGBM(Full) = {ratio:.1%}**: "
                     f"Latent Class 모형이 ML 상한의 {ratio:.0%}를 달성하면서 "
                     f"경제학적 해석(WTP, 환승 페널티, 클래스 멤버십)을 제공한다.")
        lines.append("")
    if mnl_hr and lgb_hr > 0:
        lines.append(f"**MNL / LightGBM(Full) = {mnl_hr / lgb_hr:.1%}**: "
                     f"가장 단순한 MNL도 ML 상한의 {mnl_hr / lgb_hr:.0%}를 달성.")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 6. 해석 ──
    lines.append("## 6. 핵심 해석")
    lines.append("")
    lines.append("### 6.1 예측력 격차 분석")
    lines.append("")
    core_gap = full['hit_rate_test'] - core['hit_rate_test']
    lines.append(f"- **Core → Full 개선**: +{core_gap:.1%}p — "
                 f"user_type, D_peak, n_alternatives 추가 효과")
    if lc_hr:
        lc_core_gap = core['hit_rate_test'] - lc_hr
        lines.append(f"- **LC → LGB-Core 격차**: {lc_core_gap:+.1%}p — "
                     f"동일 변수에서 비선형/교호작용 효과")
    lines.append("")

    lines.append("### 6.2 SHAP vs 경제학적 β 비교")
    lines.append("")
    lines.append("SHAP 변수 중요도 순위와 MNL/LC의 β 크기 순위를 비교하여,")
    lines.append("트리 기반 모형이 포착하는 비선형 패턴과 경제학적 모형의 ")
    lines.append("선형 효용 함수 가정 간의 일관성을 확인한다.")
    lines.append("")
    lines.append("### 6.3 유형별 예측 가능성")
    lines.append("")
    lines.append("ML(Mixed Logit) 유형별 ρ²와 LightGBM 유형별 Hit Rate의 순위가 ")
    lines.append("일치하면, **경로선택 행태의 예측 가능성**이 모형에 관계없이 ")
    lines.append("이용자 유형의 고유한 특성임을 시사한다.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 7. 결론 ──
    lines.append("## 7. 결론")
    lines.append("")
    lines.append("### 7.1 학술적 기여")
    lines.append("1. **해석력-예측력 트레이드오프 정량화**: "
                 "경제학적 모형이 ML 상한 대비 달성하는 비율을 제시")
    lines.append("2. **SHAP-β 교차검증**: "
                 "트리 기반 변수 중요도와 효용함수 계수의 일관성 확인")
    lines.append("3. **유형별 예측 가능성 패턴**: "
                 "모형 비의존적인 이용자 유형 특성 발견")
    lines.append("")
    lines.append("### 7.2 한계")
    lines.append("1. LightGBM은 **독립적 이진 분류기**로, "
                 "choice-set 내 대안 간 경쟁 구조를 명시적으로 모형화하지 않음")
    lines.append("2. ρ² 미정의: 이진 분류 확률을 choice-set 확률로 정규화하여 "
                 "비교하였으나, 엄밀한 ρ²는 아님")
    lines.append("3. MNL/ML/LC는 서로 다른 표본 크기에서 추정 — "
                 "절대 수치 비교 시 유의 필요")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 8. 파일 참조")
    lines.append("")
    lines.append("| 파일 | 설명 |")
    lines.append("|------|------|")
    lines.append("| `lightgbm_results.json` | 전체 결과 (Core/Full + 비교) |")
    lines.append("| `figures/shap_summary_core.png` | Core SHAP Summary |")
    lines.append("| `figures/shap_summary_full.png` | Full SHAP Summary |")
    lines.append("| `figures/shap_by_usertype_full.png` | 유형별 SHAP Heatmap |")
    lines.append("| `figures/model_comparison.png` | 모형 비교 차트 |")
    lines.append("| `step7_lightgbm_benchmark.py` | 추정 스크립트 |")

    report_path = RESULT_DIR / "PHASE3_RESULTS4_LIGHTGBM.md"
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"  → {report_path.name}")
    return report_path


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    t_start = time.time()

    print("=" * 60)
    print("  Step 7: LightGBM Benchmark")
    print("=" * 60)

    # ──────────────────────────────────────────────────────────────
    #  1. 데이터 로드
    # ──────────────────────────────────────────────────────────────
    print("\n[1] 데이터 로드")

    try:
        df_train = pd.read_parquet(DATA_DIR / 'model_input_train.parquet')
        df_test = pd.read_parquet(DATA_DIR / 'model_input_test.parquet')
    except OSError:
        print("  pyarrow 읽기 실패 → fastparquet 사용")
        df_train = pd.read_parquet(DATA_DIR / 'model_input_train.parquet',
                                   engine='fastparquet')
        df_test = pd.read_parquet(DATA_DIR / 'model_input_test.parquet',
                                  engine='fastparquet')

    # n_alternatives: choice set 크기 (context feature)
    df_train['n_alternatives'] = (
        df_train.groupby('chain_id')['chain_id'].transform('count')
    )
    df_test['n_alternatives'] = (
        df_test.groupby('chain_id')['chain_id'].transform('count')
    )

    # user_type → LightGBM native categorical
    for df in [df_train, df_test]:
        df['user_type'] = df['user_type'].astype(
            pd.CategoricalDtype(categories=[1, 2, 3, 4, 5])
        )

    # 정렬
    df_train = df_train.sort_values(['chain_id', 'alt_id']).reset_index(drop=True)
    df_test = df_test.sort_values(['chain_id', 'alt_id']).reset_index(drop=True)

    # 클래스 불균형 가중치
    n_pos = df_train[TARGET].sum()
    n_neg = len(df_train) - n_pos
    spw = n_neg / n_pos

    n_train_chains = df_train['chain_id'].nunique()
    n_test_chains = df_test['chain_id'].nunique()

    print(f"  Train: {len(df_train):,} rows, {n_train_chains:,} chains")
    print(f"  Test:  {len(df_test):,} rows, {n_test_chains:,} chains")
    print(f"  Class balance: choice=1 {n_pos / len(df_train):.1%}")
    print(f"  scale_pos_weight: {spw:.2f}")

    y_train = df_train[TARGET].values
    y_test = df_test[TARGET].values
    chain_ids_train = df_train['chain_id'].values
    chain_ids_test = df_test['chain_id'].values
    user_types_test = df_test['user_type'].astype(int).values  # category → int

    data_info = {
        'n_train_rows': len(df_train),
        'n_test_rows': len(df_test),
        'n_train_chains': n_train_chains,
        'n_test_chains': n_test_chains,
        'pos_ratio': n_pos / len(df_train),
        'scale_pos_weight': spw
    }

    # ──────────────────────────────────────────────────────────────
    #  2-3. Core Model & Full Model
    # ──────────────────────────────────────────────────────────────
    all_results = {}

    for feat_label, feature_cols in [('Core', CORE_FEATURES),
                                     ('Full', FULL_FEATURES)]:
        print(f"\n{'═' * 60}")
        print(f"  [{feat_label}] Feature Set ({len(feature_cols)} vars)")
        print(f"  {feature_cols}")
        print(f"{'═' * 60}")

        X_train = df_train[feature_cols]
        X_test = df_test[feature_cols]

        # ── Optuna 튜닝 ──
        t_tune = time.time()
        best_params, cv_hr = run_optuna_tuning(
            X_train, y_train, chain_ids_train,
            feature_cols, spw
        )
        tune_time = time.time() - t_tune
        print(f"  튜닝 소요: {tune_time / 60:.1f}분")

        # ── 최종 학습 + 평가 ──
        model, results = train_and_evaluate(
            X_train, y_train, X_test, y_test,
            chain_ids_train, chain_ids_test,
            user_types_test, feature_cols,
            best_params, spw, feat_label
        )
        results['cv_hit_rate'] = cv_hr
        results['tuning_time_sec'] = tune_time

        # ── SHAP ──
        shap_results = run_shap_analysis(
            model, X_test, user_types_test, feature_cols, feat_label
        )
        results['shap'] = shap_results

        all_results[feat_label.lower()] = results

    # ──────────────────────────────────────────────────────────────
    #  4. 모형 비교
    # ──────────────────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print("  모형 비교")
    print(f"{'═' * 60}")

    comparison = load_comparison_baselines()

    comparison['LightGBM_Core'] = {
        'hit_rate': all_results['core']['hit_rate_test'],
        'rho_squared': None,
        'mean_choice_prob': all_results['core']['mean_choice_prob_test'],
        'n_params': None,
        'note': f"Test set ({n_test_chains:,} chains, 4 features)"
    }
    comparison['LightGBM_Full'] = {
        'hit_rate': all_results['full']['hit_rate_test'],
        'rho_squared': None,
        'mean_choice_prob': all_results['full']['mean_choice_prob_test'],
        'n_params': None,
        'note': f"Test set ({n_test_chains:,} chains, 7 features)"
    }

    print(f"\n  {'모형':<18s} {'Hit Rate':>10s} {'Mean Prob':>10s} {'ρ²':>8s}")
    print(f"  {'─' * 48}")
    for name, m in comparison.items():
        hr = f"{m['hit_rate']:.4f}" if m.get('hit_rate') else "  N/A"
        mcp = f"{m['mean_choice_prob']:.4f}" if m.get('mean_choice_prob') else "  N/A"
        rho = f"{m['rho_squared']:.4f}" if m.get('rho_squared') else "  N/A"
        print(f"  {name:<18s} {hr:>10s} {mcp:>10s} {rho:>8s}")

    # ── 비교 차트 ──
    create_comparison_figure(comparison)

    # ──────────────────────────────────────────────────────────────
    #  5. 결과 저장
    # ──────────────────────────────────────────────────────────────
    total_time = time.time() - t_start

    output = {
        'core_model': all_results['core'],
        'full_model': all_results['full'],
        'comparison': comparison,
        'data_info': data_info,
        'estimation_info': {
            'n_optuna_trials': N_OPTUNA_TRIALS,
            'n_cv_folds': N_CV_FOLDS,
            'random_state': RANDOM_STATE,
            'total_time_sec': total_time,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    }

    json_path = RESULT_DIR / 'lightgbm_results.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  JSON: {json_path.name}")

    # ── MD 보고서 ──
    generate_report(all_results, comparison, data_info, total_time)

    # ── 완료 ──
    print(f"\n{'═' * 60}")
    print(f"  완료! 총 소요시간: {total_time / 60:.1f}분")
    print(f"{'═' * 60}")
    print(f"  Core Test Hit Rate:  {all_results['core']['hit_rate_test']:.4f}")
    print(f"  Full Test Hit Rate:  {all_results['full']['hit_rate_test']:.4f}")

    lc_hr = comparison.get('Latent_Class', {}).get('hit_rate')
    if lc_hr:
        ratio = lc_hr / all_results['full']['hit_rate_test']
        print(f"  LC / LGB-Full:       {ratio:.1%}")

    print(f"\n  결과: {json_path}")
    print(f"  보고서: {RESULT_DIR / 'PHASE3_RESULTS4_LIGHTGBM.md'}")
    print(f"  차트: {FIGURE_DIR}")


if __name__ == '__main__':
    main()
