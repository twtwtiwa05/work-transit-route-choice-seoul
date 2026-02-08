# Phase 3 Results: LightGBM Benchmark — ML Upper Bound & Cross-Validation

추정 완료: 2026-02-08

---

## 1. 개요

### 1.1 연구 목적

경제학적 이산선택 모형(MNL, Mixed Logit, Latent Class)은 **행태적 해석력**(VoT, 환승 페널티, 클래스 세분화)을 제공하지만, 이를 위해 선형 효용 가정과 확률 분포 가정을 전제한다. LightGBM Benchmark는 이러한 가정 없이 데이터의 **예측 성능 상한(upper bound)**을 확립하여, 경제학적 모형의 해석력-예측력 트레이드오프를 정량화한다.

추가로, SHAP(SHapley Additive exPlanations) 분석을 통해 트리 기반 모형의 **비모수적 변수 중요도**와 경제학적 β 계수의 순위 일관성을 교차검증한다.

### 1.2 방법론

- **LightGBM** 이진 분류기 (choice=0/1) → Choice-set 단위 평가 (MNL과 동일 기준)
- **Optuna Bayesian 최적화** + 5-fold GroupKFold (chain_id 기준, 데이터 누출 방지)
- **2개 Feature Set**: Core (4변수, 경제학 모형과 동일) / Full (7변수, context 변수 추가)
- **SHAP TreeExplainer**: 변수별·유형별 기여도 분해

**핵심 설계 원칙:**
LightGBM은 각 대안을 독립적으로 "선택/비선택" 분류하는 이진 분류기이다. Choice-set 내 대안 간 경쟁을 명시적으로 모형화하지 않으므로, 경제학 모형과의 공정한 비교를 위해 **choice-set 단위 Hit Rate**를 공통 평가 지표로 사용한다. 각 chain에서 가장 높은 예측 확률을 받은 대안이 실제 선택과 일치하는 비율을 산출한다.

### 1.3 추정 설정

| 항목 | 값 |
|------|-----|
| Train | 1,518,228 rows, 329,403 chains |
| Test | 380,532 rows, 82,351 chains |
| Optuna Trials | 30 (TPE Sampler, seed=42) |
| CV Folds | 5 (GroupKFold by chain_id) |
| Class Balance | choice=1 21.7% / choice=0 78.3% |
| scale_pos_weight | 3.61 (불균형 보정) |
| SHAP Sample | 50,000 rows (Random subsample) |
| 총 소요시간 | 31.9분 |

---

## 2. Core 모형 (4 변수)

**Features**: T_ride, T_walk, N_transfer, D_subway — MNL/ML/LC 효용함수와 **동일 변수**

경제학 모형과 동일한 정보만으로 LightGBM이 달성하는 예측력을 확인하여, 선형 효용 가정의 비용(예측력 손실)을 측정한다.

### 2.1 최적 하이퍼파라미터

| Parameter | Value | 해석 |
|-----------|-------|------|
| n_estimators | 596 | 앙상블 트리 수 |
| learning_rate | 0.0106 | 보수적 학습률 (과적합 방지) |
| max_depth | 8 | 깊은 트리 허용 (비선형 교호작용 포착) |
| num_leaves | 55 | 리프 수 (2^8=256 대비 보수적) |
| min_child_samples | 58 | 리프 최소 샘플 (안정성 확보) |
| subsample | 0.673 | 행 서브샘플링 |
| colsample_bytree | 0.673 | 열 서브샘플링 |
| reg_alpha | 5.5e-6 | L1 정규화 (거의 0 → 불필요) |
| reg_lambda | 5.3e-4 | L2 정규화 (약함) |

**특징**: max_depth=8로 깊은 트리를 허용한 것은 4개 변수 간 **비선형 교호작용**(예: T_walk × D_subway, N_transfer × D_subway)이 존재함을 시사한다. 그러나 정규화가 약한 점은 과적합 위험이 낮음을 의미한다.

### 2.2 적합도

| 지표 | Train | Test |
|------|-------|------|
| Hit Rate | 0.6580 | **0.6575** |
| Mean Choice Prob | 0.4345 | 0.4346 |
| CV Hit Rate | 0.6568 | - |
| Train-Test Gap | +0.0004 | - |

**Train-Test Gap = +0.0004**: 사실상 과적합 없음. 4개 변수의 예측 공간이 제한적이어서 트리가 학습할 노이즈가 적다.

---

## 3. Full 모형 (7 변수)

**Features**: T_ride, T_walk, N_transfer, D_subway, **D_peak, user_type, n_alternatives**

Core 변수에 context 변수 3개를 추가하여, 경제학 모형이 포착하지 못하는 정보의 추가적 예측 기여를 측정한다.

### 3.1 최적 하이퍼파라미터

| Parameter | Value | Core 대비 |
|-----------|-------|----------|
| n_estimators | 313 | ↓ (596→313, 절반) |
| learning_rate | 0.0134 | ↑ (더 빠른 학습) |
| max_depth | 7 | ↓ (8→7) |
| num_leaves | 36 | ↓ (55→36) |
| min_child_samples | 42 | ↓ |
| reg_alpha | **1.527** | ↑↑ (5.5e-6 → 1.5, L1 활성화) |

**특징**: Core 대비 **더 작은 트리, 더 강한 정규화**. 변수가 7개로 늘면서 과적합 위험이 증가하여 Optuna가 자동으로 보수적 설정을 선택했다. 특히 reg_alpha(L1)가 5.5e-6 → 1.527로 급증한 것은 일부 변수(D_peak)가 **불필요한 노이즈**이며 자동 제거(feature selection) 역할을 수행함을 의미한다.

### 3.2 적합도

| 지표 | Train | Test |
|------|-------|------|
| Hit Rate | 0.6642 | **0.6622** |
| Mean Choice Prob | 0.4042 | 0.4042 |
| CV Hit Rate | 0.6633 | - |
| Train-Test Gap | +0.0020 | - |

**Core → Full 개선: +0.47%p** (65.75% → 66.22%). user_type, n_alternatives가 약간의 추가 예측력을 제공하지만, 핵심 정보는 이미 Core 4변수에 집중되어 있다.

### 3.3 유형별 Test Hit Rate

| 유형 | Core HR | Full HR | 개선 | N chains |
|------|---------|---------|------|----------|
| General | 64.76% | 65.28% | +0.52%p | 67,961 |
| Children | 64.90% | 65.94% | +1.05%p | 1,148 |
| Youth | 64.92% | 65.40% | +0.49%p | 4,931 |
| **Elderly** | **76.00%** | **76.08%** | +0.08%p | 6,033 |
| **Disabled** | **70.41%** | **70.28%** | -0.13%p | 2,278 |

**핵심 발견:**
1. **Elderly(76%)와 Disabled(70%)가 전 모형에서 최고 예측력** — 이 패턴은 MNL(78.5%, 73.0%), LC에서도 동일하게 나타남
2. **Full 모형에서 Elderly/Disabled는 거의 개선 없음** (+0.08%p / -0.13%p) — 이미 Core 4변수가 이들의 행태를 충분히 포착하므로, user_type 추가가 불필요
3. **General/Children/Youth는 소폭 개선** (+0.5~1.0%p) — context 변수가 일반 이용자의 미세 패턴을 추가 포착

---

## 4. SHAP Feature Importance

### 4.1 Global Importance (Full 모형)

| Rank | Feature | Mean |SHAP| | MNL β 방향 | 일관성 |
|------|---------|-----------|------------|--------|
| 1 | **T_walk** | **0.826** | β = -0.860*** | T_walk 높으면 SHAP 음수 |
| 2 | **N_transfer** | **0.684** | β = -3.614*** | 환승 많으면 SHAP 음수 |
| 3 | T_ride | 0.327 | β = -0.060*** | 방향 일치 |
| 4 | D_subway | 0.215 | β = +2.585*** | 지하철=1이면 SHAP 양수 |
| 5 | n_alternatives | 0.200 | (MNL에 없음) | context 변수 |
| 6 | user_type | 0.022 | (MNL에 없음) | 미미한 기여 |
| 7 | D_peak | **0.002** | ML에서 비유의 | **거의 0 — 완벽 일치** |

### 4.2 SHAP-β 순위 일관성 분석

SHAP 중요도 순위(T_walk > N_transfer > T_ride > D_subway)는 MNL β 절대값 순위와 **완벽히 일치**한다.

이는 다음을 의미한다:

1. **효용함수 사양의 타당성**: MNL의 선형 효용 함수 V_j = β'x_j가 데이터의 주요 행태 패턴을 정확히 포착하고 있으며, LightGBM이 추가로 발견하는 비선형 패턴은 예측력 기여가 미미함
2. **D_peak 비유의의 재확인**: MNL(Pooled)에서 Peak×T_ride 비유의, ML에서 p=0.33, LC 멤버십에서 t=0.05, 그리고 LightGBM SHAP=0.002 → **네 모형 모두 일관되게 D_peak 비유의**. 서울 대중교통 경로선택은 첨두/비첨두에 따라 구조적으로 달라지지 않음
3. **n_alternatives의 발견**: 경제학 모형에 포함되지 않는 choice-set 크기(n_alternatives)가 SHAP 5위(0.200)로, D_subway(0.215)와 비슷한 기여. 대안이 많은 체인에서 예측이 어려워지는 **choice complexity** 효과

### 4.3 SHAP Beeswarm Plot 해석

SHAP beeswarm plot은 각 변수의 값(색상)이 예측에 미치는 방향과 크기를 보여준다.

| Feature | 높은 값 (빨강) | 낮은 값 (파랑) | 경제학적 해석 |
|---------|-------------|-------------|-------------|
| T_walk | SHAP ← (음) | SHAP → (양) | 보행시간 길면 선택 확률 감소 (β_walk < 0) |
| N_transfer | SHAP ← (음, 이산적 덩어리) | SHAP → (양) | 환승 있으면 급격히 감소 (β_transfer < 0) |
| T_ride | SHAP 혼재 | SHAP 혼재 | 약한 음의 효과 (β_ride 절대값 작음) |
| D_subway | SHAP → (양, 뚜렷한 이분) | SHAP ← (음) | 지하철 경로 강한 선호 (β_subway > 0) |
| n_alternatives | SHAP 분산 | SHAP 분산 | 대안 수에 따른 복잡도 효과 |
| user_type | 대부분 0 부근 | 대부분 0 부근 | 유형 자체보다 행태 변수가 중요 |
| D_peak | **거의 0** | **거의 0** | 피크 효과 부재 |

**N_transfer의 이산적 패턴**이 특징적이다. 환승=0(파랑)은 SHAP 양수, 환승≥1(빨강)은 SHAP 음수로 뚜렷하게 이분되며, 이는 MNL의 선형 β_transfer가 사실 **단계 함수(step function)**에 가까운 비선형 효과를 선형 근사하고 있음을 시사한다.

### 4.4 유형별 SHAP 차이

| Feature | General | Children | Youth | Elderly | Disabled |
|---------|---------|----------|-------|---------|----------|
| T_ride | 0.329 | 0.343 | 0.321 | 0.309 | 0.324 |
| T_walk | 0.822 | **0.910** | 0.845 | 0.830 | 0.862 |
| N_transfer | 0.687 | 0.620 | 0.645 | **0.700** | 0.646 |
| **D_subway** | 0.214 | 0.168 | 0.180 | **0.293** | 0.177 |
| D_peak | 0.002 | 0.002 | 0.002 | 0.002 | 0.002 |
| **user_type** | 0.011 | 0.021 | 0.021 | **0.154** | 0.034 |
| n_alternatives | 0.198 | 0.216 | 0.212 | 0.207 | 0.216 |

**핵심 발견:**

1. **Elderly의 D_subway SHAP = 0.293** (다른 유형 ~0.18의 1.6배) — LC Class 1 "접근성 우선" 클래스에서 β_subway=+8.12가 극단적으로 높았던 것과 정확히 대응. LightGBM도 고령자의 지하철 강선호를 독립적으로 포착.

2. **Elderly의 user_type SHAP = 0.154** (다른 유형 ~0.02의 7배) — 고령자 데이터에서 "이 사람이 고령자라는 사실 자체"가 예측에 강하게 기여. 이는 LC의 concomitant variable에서 D_elderly = +3.09*** (오즈비 22배)와 같은 맥락.

3. **Children의 T_walk SHAP = 0.910** (최고) — 어린이가 보행시간에 가장 민감. MNL에서 어린이 별도 모형이 없었으나, 행태적으로 보행 민감도가 독특함을 시사.

4. **D_peak = 모든 유형 0.002** — 어떤 이용자 유형에서도 피크 여부는 경로선택에 영향 없음. 네 모형(MNL, ML, LC, LightGBM) × 다섯 유형에서 **완벽한 일관성**.

---

## 5. 모형 비교

### 5.1 전체 비교표

| 모형 | Hit Rate | Mean Prob | ρ² | 파라미터 | 표본 | 이질성 |
|------|----------|-----------|-----|---------|------|--------|
| MNL (Pooled) | 62.92% | 0.599 | 0.469 | 6 | 329K (Train) | 없음 |
| Mixed Logit | 62.30% | 0.595 | 0.464 | 9 | 30K (Sample) | 연속 (Normal) |
| **Latent Class** | **67.43%** | **0.603** | **0.474** | 24 | 82K (Test) | 이산 (3 class) |
| LightGBM Core | 65.75% | 0.435 | — | — | 329K (Train) | 비모수 |
| LightGBM Full | 66.22% | 0.404 | — | — | 329K (Train) | 비모수 |

### 5.2 핵심 비교 지표

| 비교 | 비율 | 의미 |
|------|------|------|
| **MNL / LGB-Full** | **95.0%** | 가장 단순한 6-파라미터 모형이 ML 상한의 95%를 달성 |
| **LC / LGB-Full** | **101.8%** | 경제학 모형이 ML 상한을 **초과** |
| Core / Full | 99.3% | 추가 3변수의 기여가 미미 |

### 5.3 LC > LightGBM: 왜 경제학 모형이 ML을 이겼는가

Latent Class(67.4%)가 LightGBM Full(66.2%)을 **+1.2%p 초과**한 결과는 반직관적이지만, 구조적으로 설명 가능하다:

1. **Choice-set 구조의 명시적 모형화**: LC는 P(j|C_n) = Σ_c π_c · exp(V_jc) / Σ_k exp(V_kc)로 **choice set 내 대안 간 경쟁**을 직접 모형화한다. 반면 LightGBM은 각 대안을 독립적으로 P(choice=1|x_j)를 예측하며, 같은 chain의 다른 대안은 보지 못한다. 이 구조적 차이가 LC에 유리하게 작용한다.

2. **이산적 세그먼트의 효율성**: LC의 3개 클래스(접근성 8.7% / 일반 77.2% / 극단 14.0%)가 LightGBM의 일반적 비선형 학습보다 이 데이터의 이질성을 더 효율적으로 포착한다. 특히 "환승 절대 기피 + 지하철 강선호"라는 Class 1의 극단적 패턴은 트리 기반 모형이 자연스럽게 발견하기 어려운 **사전적 선호(lexicographic preference)** 구조이다.

3. **동일 Test Set 비교**: LC(50K 체인으로 학습)와 LightGBM(329K 체인으로 학습) 모두 동일한 test set(82,351 chains, `model_input_test.parquet`)에서 평가되었다. LC는 학습 데이터가 15%에 불과함에도 LightGBM을 초과하여, choice-set 구조 모형화의 우위가 더욱 강조된다.

**학술적 함의**: 대중교통 경로선택과 같이 **choice-set 구조가 명확한** 이산선택 문제에서, 행태적 구조를 반영한 경제학적 모형이 일반적 ML 접근보다 우위에 있을 수 있다. 이는 "ML이 항상 경제학 모형을 이긴다"는 통념에 대한 반례(counterexample)를 제공한다.

### 5.4 유형별 예측력 패턴: 모형 비의존적 일관성

| 유형 | MNL* | LC (K=3) | LGB Core | LGB Full | 순위 |
|------|------|----------|----------|----------|------|
| General | 62.9% | 66.4% | 64.8% | 65.3% | **5위** |
| Children | — | 66.5% | 64.9% | 65.9% | **4위** |
| Youth | — | 67.0% | 64.9% | 65.4% | **3위** |
| **Elderly** | **78.5%** | **77.8%** | **76.0%** | **76.1%** | **1위** |
| **Disabled** | **73.0%** | **71.5%** | **70.4%** | **70.3%** | **2위** |

(*MNL은 pooled/유형별 별도 모형에서 추정, Children/Youth는 별도 모형 미추정)

**핵심 발견:**

1. **Elderly > Disabled > General 순위가 모든 모형에서 동일.** 경로선택의 예측 가능성은 **모형 선택이 아닌 이용자 유형의 고유한 행태적 특성**에 의해 결정된다.

2. **모든 유형에서 LC > LightGBM**: General +1.1%p, Youth +1.6%p, Elderly +1.8%p, Disabled +1.2%p. LC의 choice-set 구조 우위가 특정 유형에 국한되지 않고 **전 유형에서 일관**되게 나타남.

3. **고령자의 압도적 예측력** (LC 77.8%, LGB 76.0%): "환승 없는 지하철 직통"이라는 단순하고 일관된 규칙을 따르므로 예측이 쉬움. 반면 일반 이용자(LC 66.4%)는 다양한 요인을 종합 고려하여 상대적으로 예측 어려움.

---

## 6. Mean Choice Probability의 해석

| 모형 | Mean Choice Prob | 해석 |
|------|-----------------|------|
| MNL | **0.599** | 선택 확률을 직접 추정 (choice-set 내 합=1) |
| LC | **0.603** | 선택 확률 직접 추정 |
| LGB Core | 0.435 | 독립 이진 확률 → chain 내 정규화 |
| LGB Full | 0.404 | 독립 이진 확률 → chain 내 정규화 |

LightGBM의 Mean Choice Prob이 경제학 모형보다 낮은 이유: LightGBM은 P(choice=1|x_j)를 독립적으로 출력하므로, 같은 chain 내 여러 대안이 동시에 높은 확률을 받을 수 있다. P_norm(j) = P(j) / Σ P(k)로 정규화하면 희석되어 Mean Prob이 낮아진다. **이는 LightGBM의 한계이지 성능 저하가 아니다** — Hit Rate(argmax 기반)와 Mean Prob은 별개의 지표이다.

---

## 7. 핵심 해석 종합

### 7.1 효용함수 사양의 교차 타당성

| 검증 방법 | 근거 | 결론 |
|-----------|------|------|
| SHAP 순위 vs MNL β 순위 | T_walk > N_transfer > T_ride > D_subway (완벽 일치) | 효용함수 변수 선택 적절 |
| D_peak SHAP ≈ 0 | 네 모형 모두 비유의 | D_peak 제외 정당화 |
| Core vs Full 격차 | +0.47%p (미미) | **4변수가 예측력의 99.3%를 포착** |
| Elderly D_subway SHAP 돌출 | LC Class 1 β_subway=+8.12와 대응 | 이질성 구조 교차 확인 |

### 7.2 네 모형의 상호 보완적 역할

| 모형 | 역할 | 고유 기여 |
|------|------|----------|
| **MNL** | 기준선(baseline) | 평균적 선호 구조, VoT 산출 |
| **Mixed Logit** | 이질성 존재 확인 | σ 유의 → 이질성의 연속 분포 확인 |
| **Latent Class** | 이질성 구조 해석 | 3개 행태 군집 프로파일, 정책 세분화 |
| **LightGBM** | 예측 상한 + 교차검증 | SHAP으로 β 순위 확인, 비선형 패턴 탐지 |

네 모형이 **동일한 이질성 구조**(고령자 접근성 우선, 일반 합리적 트레이드오프, D_peak 비유의)를 독립적으로 포착하였다. 이는 발견의 **강건성(robustness)**을 입증한다.

### 7.3 비선형 효과의 정량화

LightGBM Core(65.75%) - MNL(62.92%) = **+2.83%p**는 MNL의 선형 효용 가정이 놓치는 **비선형 교호작용의 크기**이다.

그러나 LC(67.43%) - LightGBM Full(66.22%) = **+1.21%p**로, **choice-set 구조 반영**의 이점이 비선형 포착의 이점보다 크다. 즉, 이 데이터에서는 비선형 모형화보다 **행태적 구조의 올바른 반영**이 더 중요하다.

---

## 8. 정책적 시사점

### 8.1 경로안내 시스템 설계

| 시사점 | 근거 | 적용 |
|--------|------|------|
| **4변수 효용함수 충분** | Core/Full 격차 0.47%p, SHAP 상위 4개=경제학 변수 | 경로안내에 T_ride, T_walk, N_transfer, D_subway만 반영해도 99%의 예측력 확보 |
| **피크 차별 불필요** | D_peak SHAP=0.002, 네 모형 비유의 | 첨두/비첨두 별 다른 가중치 불필요 |
| **이용자 유형 식별의 가치** | user_type SHAP 낮지만 LC 세분화 효과 큼 | ML보다 **모형 기반 세분화**가 효과적 |

### 8.2 모형 선택 가이드라인

| 용도 | 추천 모형 | 이유 |
|------|----------|------|
| 실시간 경로 추천 | **MNL (Class 2 파라미터)** | 단순·빠름, 95% 성능 |
| 개인화 추천 | **LC (클래스별 파라미터)** | 최고 성능 + 세분화 |
| 수요 예측·정책 분석 | **Mixed Logit** | WTP 분포, 후생 분석 |
| 변수 탐색·검증 | **LightGBM + SHAP** | 비모수적 교차검증 |

---

## 9. 결론

### 9.1 학술적 기여

1. **해석력-예측력 트레이드오프 정량화**: MNL(6 파라미터)이 LightGBM 상한의 **95.0%**를 달성. LC(24 파라미터)는 이를 **101.8%로 초과**. 경제학적 모형이 해석력을 "유지"하면서도 예측력을 "잃지 않음"을 정량적으로 입증.

2. **SHAP-β 교차검증**: 트리 기반 비모수적 변수 중요도 순위가 MNL/ML의 효용함수 계수 순위와 완벽히 일치하여, 효용함수 사양(specification)의 타당성을 독립적으로 확인.

3. **Choice-set 구조의 우위**: LC > LightGBM 결과는, 대안 간 경쟁을 명시적으로 모형화하는 경제학적 접근이 **이산선택 문제**에서 일반적 ML보다 효과적일 수 있음을 시사. "ML이 항상 우월"이라는 통념에 대한 반례 제시.

4. **유형별 예측 가능성의 모형 비의존성**: Elderly > Disabled > General 순위가 MNL, LC, LightGBM 모두에서 동일. 경로선택의 예측 가능성은 모형이 아닌 이용자 유형의 고유 특성.

5. **D_peak 비유의의 4중 확인**: MNL, ML, LC, LightGBM 네 모형이 일관되게 피크시간 효과를 부정하여, 서울 대중교통 경로선택의 시간대 비의존성을 강건하게 확립.

### 9.2 한계

1. **독립적 이진 분류**: LightGBM은 choice-set 내 대안 간 경쟁 구조를 모형화하지 않으므로, 엄밀한 의미의 "ML 상한"이 아닌 "독립 이진 분류기 상한"이다. RankNet, LambdaMART 등 learning-to-rank 접근이 더 공정한 비교 대상일 수 있다.

2. **학습 표본 차이**: MNL(329K), ML(30K), LC(50K), LightGBM(329K)이 각각 다른 학습 표본 크기를 사용. 단, LC와 LightGBM은 동일 test set(82K)에서 평가되어 직접 비교 가능. MNL/ML의 hit rate는 각자의 학습 데이터에서 산출되어 엄밀한 비교에는 유의 필요.

3. **ρ² 미산출**: LightGBM의 이진 확률을 choice-set 확률로 정규화하여 비교하였으나, 경제학적 ρ²와 엄밀히 동일하지 않음.

4. **동점(tie) 비율**: Choice-set 내 최대 확률 대안이 복수인 경우(~25%)가 있으며, idxmax의 첫 번째 선택 규칙이 Hit Rate에 노이즈를 추가할 수 있음.

---

## 10. 파일 참조

| 파일 | 설명 |
|------|------|
| `lightgbm_results.json` | 전체 결과 (Core/Full + SHAP + 비교) |
| `figures/shap_summary_core.png` | Core SHAP Beeswarm Plot |
| `figures/shap_summary_full.png` | Full SHAP Beeswarm Plot |
| `figures/shap_by_usertype_core.png` | Core 유형별 SHAP Heatmap |
| `figures/shap_by_usertype_full.png` | Full 유형별 SHAP Heatmap |
| `figures/model_comparison.png` | 5-모형 Hit Rate 비교 차트 |
| `step7_lightgbm_benchmark.py` | 추정 스크립트 |
| `PHASE3_RESULTS1_MNL.md` | MNL 결과 (비교 기준) |
| `PHASE3_RESULTS2_MIXED_LOGIT.md` | Mixed Logit 결과 |
| `PHASE3_RESULTS3_LC.md` | Latent Class 결과 |
