# Phase 3: 경로선택 모델 추정 계획서

## 개요

| 항목 | 내용 |
|------|------|
| **목적** | TCD 관측 경로와 OTP 대안 경로 간 유사도 기반 Choice Set 구성 후 이산선택모델 추정 |
| **입력** | Phase 2 결과 (similarity_results.parquet, otp_alternatives.parquet) |
| **출력** | 모델 추정 결과 (MNL, Mixed Logit, Latent Class, LightGBM) |
| **핵심 기여** | Mixed Logit으로 이용자 유형 내 이질성(heterogeneity) 포착 |

## 진행 현황 (2026-02-07 업데이트)

| Step | 작업 | 상태 | 비고 |
|------|------|------|------|
| Step 1 | Choice Set 생성 | ✅ 완료 | 560,844 체인 → threshold 0.70 |
| Step 2 | 대안 속성 추출 | ✅ 완료 | T_ride, T_walk, N_transfer 등 |
| Step 3 | 모델 입력 준비 | ✅ 완료 | 411,754 체인, Train/Test 분할 |
| Step 4 | MNL 추정 | ✅ 완료 | Pooled + 5개 유형별, ρ²=0.469 |
| Step 5 | Mixed Logit 추정 | 🔲 예정 | |
| Step 6 | Latent Class 추정 | 🔲 예정 | |
| Step 7 | LightGBM 벤치마크 | 🔲 예정 | |
| Step 8 | 모델 비교 | 🔲 예정 | |

---

## 1. Phase 2 결과 요약 (입력 데이터)

### 1.1 분석 규모

| 데이터 | 수량 | 설명 |
|--------|------|------|
| 분석 체인 | 1,320,030 | TCD에서 GTFS 매핑 성공한 체인 |
| OTP 대안 쌍 | 4,936,864 | (체인, OTP 대안) 쌍 |
| 체인당 대안 | 평균 3.74개 | 1~10개 범위 |

### 1.2 유사도 분포 (Best Match 기준)

| 기준 | 체인 수 | 비율 | 추정 샘플 적합성 |
|------|---------|------|-----------------|
| sim_total ≥ 0.90 | 305,254 | 23.1% | 고신뢰 샘플 |
| sim_total ≥ 0.85 | 378,419 | 28.7% | 권장 임계값 |
| sim_total ≥ 0.70 | 560,513 | 42.5% | **채택 임계값** |
| sim_total ≥ 0.50 | 844,820 | 64.0% | 확장 샘플 |
| Exact Match | 378,289 | 28.66% | 완전 일치 |

### 1.3 파일 위치

```
main/output/
├── similarity_results.parquet      # 4.94M쌍의 유사도 (6개 지표)
├── otp_alternatives.parquet        # 4.47M 경로 (legs 포함)
├── trip_attributes_filtered.parquet # 1.47M 체인 속성 (user_type 등)
└── od_pairs_filtered.csv           # 1.26M OD (좌표, 출발시간)
```

---

## 2. Choice Variable 생성 전략

### 2.1 핵심 질문

> "TCD 관측 경로와 가장 유사한 OTP 대안이 이용자의 '선택(choice)'인가?"

### 2.2 Choice 정의 방식

```
┌─────────────────────────────────────────────────────────────────┐
│  Best-Match with Threshold 방식 (채택)                           │
├─────────────────────────────────────────────────────────────────┤
│  1. 각 체인(n)별로 sim_total이 최대인 OTP 대안(j*) 찾기            │
│     j* = argmax_j sim_total(n, j)                               │
│                                                                 │
│  2. 신뢰도 필터링: sim_total(n, j*) ≥ τ (threshold)              │
│     - τ = 0.70 채택 → 42.5% 체인 포함 (560K)                     │
│     - τ < 0.70 체인은 추정에서 제외 (매칭 불확실)                   │
│                                                                 │
│  3. Choice 변수 생성:                                            │
│     - choice(n, j*) = 1  (best-match 대안)                       │
│     - choice(n, j≠j*) = 0  (나머지 대안들)                        │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Threshold 선택 근거

| Threshold | 체인 수 | 장점 | 단점 | 판단 |
|-----------|---------|------|------|------|
| **0.90** | 305K (23%) | 최고 신뢰도 | 어린이 샘플 부족 | 보수적 |
| **0.85** | 378K (29%) | Exact Match 수준 | 일부 유형 불균형 | 대안 |
| **0.70** | 560K (42%) | 균형잡힌 샘플 | 약간의 매칭 불확실성 | **채택** |
| **0.50** | 845K (64%) | 최대 샘플 | choice 정확도 우려 | 확장용 |

**채택: τ = 0.70**
- 모든 이용자 유형에서 충분한 샘플 확보
- 42.5%는 학술적으로 합리적인 매칭률
- 민감도 분석 시 0.85, 0.50도 비교 가능

### 2.4 실제 샘플 크기 (τ = 0.70, Step 4 결과)

| 이용자 유형 | Train 체인 | 비율 | ρ² | Hit Rate | 비고 |
|------------|-----------|------|-----|----------|------|
| 일반 (코드 1) | 271,843 | 82.5% | 0.459 | 62.1% | ✅ 기준선 |
| 고령자 (코드 4) | 24,132 | 7.3% | **0.582** | **78.5%** | ✅ 최고 적합도 |
| 청소년 (코드 3) | 19,725 | 6.0% | 0.486 | 63.8% | ✅ 충분 |
| 장애인 (코드 5) | 9,113 | 2.8% | 0.515 | 73.0% | ✅ 충분 |
| 어린이 (코드 2) | 4,590 | 1.4% | 0.487 | 65.2% | ⚠️ 최소 샘플 |
| **합계** | **329,403** | 100% | **0.469** | **62.9%** | |

**참고**: 전체 체인 411,754개 중 이상치 제거 후 329,403개 Train set 사용

---

## 3. 대안 속성 변수 정의

### 3.1 효용함수 사양 (2026-02-07 수정)

```
V_nj = β_ride × T_ride + β_walk × T_walk + β_transfer × N_transfer
     + β_subway × D_subway + β_peak_ride × (Peak × T_ride) + β_peak_xfer × (Peak × N_transfer)
```

**변경 이력**:
- T_wait 제거: 다중공선성 문제 (T_ride + T_walk + T_wait ≈ T_total), 양수 계수 발생
- D_peak 단독 → Peak 상호작용: chain 수준 변수는 ASC 없이 식별 불가

### 3.2 변수 정의 및 추출 방법

| 변수 | 정의 | 추출 소스 | 단위 | 기대 부호 | Step 4 결과 |
|------|------|----------|------|----------|-------------|
| **T_ride** | 차내 시간 | OTP legs (TRANSIT) | 분 | β < 0 | -0.0341*** |
| **T_walk** | 보행 시간 | OTP legs (WALK) | 분 | β < 0 | -0.7755*** |
| **N_transfer** | 환승 횟수 | OTP legs count - 1 | 정수 | β < 0 | -3.4130*** |
| **D_subway** | 지하철 포함 | any(mode==SUBWAY) | 0/1 | β > 0 | +2.3939*** |
| **Peak × T_ride** | 첨두×차내시간 | D_peak × T_ride | 분 | β < 0 | -0.0073** |
| **Peak × N_transfer** | 첨두×환승횟수 | D_peak × N_transfer | 회 | ± | +0.0837*** |
| ~~T_wait~~ | ~~대기 시간~~ | ~~(제거됨)~~ | - | - | - |
| **D_peak** | 첨두시간대 | 07-09, 18-20 | 0/1 | (상호작용만) | 29.0% |

### 3.3 OTP 결과에서 변수 추출 로직

```python
def extract_alternative_attributes(itinerary: dict) -> dict:
    """
    OTP itinerary에서 모델 변수 추출

    itinerary 구조:
    {
        "duration": 2400,  # 총 소요시간 (초)
        "walkTime": 300,   # 총 보행시간 (초)
        "waitingTime": 180, # 총 대기시간 (초)
        "transitTime": 1920, # 총 차내시간 (초)
        "transfers": 1,
        "legs": [
            {"mode": "WALK", "duration": 120, ...},
            {"mode": "BUS", "duration": 900, "routeId": "...", ...},
            {"mode": "WALK", "duration": 60, ...},
            {"mode": "SUBWAY", "duration": 720, ...},
            {"mode": "WALK", "duration": 120, ...}
        ]
    }
    """
    transit_legs = [leg for leg in itinerary['legs'] if leg['mode'] in ['BUS', 'SUBWAY', 'RAIL']]

    return {
        'T_ride': itinerary['transitTime'] / 60,  # 분 단위
        'T_walk': itinerary['walkTime'] / 60,
        'T_wait': itinerary['waitingTime'] / 60,
        'N_transfer': max(0, len(transit_legs) - 1),
        'D_subway': 1 if any(leg['mode'] == 'SUBWAY' for leg in transit_legs) else 0,
        'D_bus_only': 1 if all(leg['mode'] == 'BUS' for leg in transit_legs) else 0,
        'T_total': itinerary['duration'] / 60
    }
```

### 3.4 시간 변수 정규화

기존 논문(Table 8)에서 β_ride가 정규화 기준:

```
가중치 계산: Weight_walk = |β_walk / β_ride|

예시 (기존 논문):
  β_ride = -0.082, β_walk = -0.699
  Weight_walk = 0.699/0.082 = 8.52
  → "보행 1분 = 차내 8.52분"
```

---

## 4. 모델 입력 데이터 구조

### 4.1 Long Format (필수)

이산선택모델 패키지(xlogit, biogeme)는 Long Format 요구:

```
┌─────────┬────────┬────────┬────────┬────────┬───────────┬──────────┬───────────┬────────┐
│ trip_id │ alt_id │ choice │ T_ride │ T_walk │ N_transfer│ D_subway │ user_type │ D_peak │
├─────────┼────────┼────────┼────────┼────────┼───────────┼──────────┼───────────┼────────┤
│ 1       │ 1      │ 1      │ 25.3   │ 5.2    │ 0         │ 1        │ 1         │ 1      │
│ 1       │ 2      │ 0      │ 30.1   │ 3.8    │ 1         │ 1        │ 1         │ 1      │
│ 1       │ 3      │ 0      │ 22.7   │ 8.1    │ 1         │ 0        │ 1         │ 1      │
│ 2       │ 1      │ 0      │ 18.4   │ 4.2    │ 0         │ 1        │ 4         │ 0      │
│ 2       │ 2      │ 1      │ 20.0   │ 2.1    │ 0         │ 1        │ 4         │ 0      │
│ 2       │ 3      │ 0      │ 25.6   │ 1.8    │ 1         │ 1        │ 4         │ 0      │
│ ...     │ ...    │ ...    │ ...    │ ...    │ ...       │ ...      │ ...       │ ...    │
└─────────┴────────┴────────┴────────┴────────┴───────────┴──────────┴───────────┴────────┘
```

### 4.2 데이터 크기 예상

| 항목 | 수량 | 메모리 |
|------|------|-------|
| 체인 (trip_id) | 560K | - |
| 체인당 대안 | 평균 3.7개 | - |
| 총 행 수 | ~2.07M | - |
| 컬럼 수 | ~15개 | - |
| **예상 크기** | - | **~250MB** |

### 4.3 Train/Test 분할

```
전체 560K 체인
├── Train (80%): 448K 체인 → ~1.66M 행
└── Test (20%): 112K 체인 → ~0.41M 행

분할 기준: trip_id 수준 (같은 체인의 대안들이 분리되지 않도록)
층화 추출: user_type별 비율 유지
```

---

## 5. 모델 추정 계획

### 5.1 모델 계층 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                      Model Hierarchy                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Level 1: Pooled MNL (기준선)                                    │
│  ─────────────────────────────                                  │
│  - 전체 이용자, 고정 파라미터                                      │
│  - 기존 논문 Table 8 재현 확인                                    │
│                                                                 │
│  Level 2: Segmented MNL (기존 논문)                              │
│  ───────────────────────────────                                │
│  - 5개 유형별 개별 추정                                           │
│  - 기존 논문 Table 9 재현 확인                                    │
│                                                                 │
│  Level 3: Pooled Mixed Logit (신규 기여)                         │
│  ──────────────────────────────────────                         │
│  - 전체 이용자, 랜덤 파라미터 (μ, σ)                               │
│  - 이질성(heterogeneity) 분포 추정                                │
│                                                                 │
│  Level 4: Segmented Mixed Logit (핵심 기여)                      │
│  ────────────────────────────────────────                       │
│  - 5개 유형별 × 랜덤 파라미터                                     │
│  - "고령자 내에서도 다양한 선호 분포"                               │
│                                                                 │
│  Level 5: Latent Class Model (비교 분석)                         │
│  ──────────────────────────────────────                         │
│  - 데이터 기반 군집 발견                                          │
│  - 행정 유형 vs 행태 군집 비교                                    │
│                                                                 │
│  Level 6: LightGBM (벤치마크)                                    │
│  ─────────────────────────────                                  │
│  - 예측 정확도 상한 확인                                          │
│  - SHAP 특성 중요도                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Model A: MNL (Multinomial Logit)

#### 수학적 정의

```
선택 확률:
P(j | C_n) = exp(V_nj) / Σ_k∈C_n exp(V_nk)

효용함수:
V_nj = β_ride × T_ride_nj + β_walk × T_walk_nj + β_wait × T_wait_nj
     + β_transfer × N_transfer_nj + β_subway × D_subway_nj

로그우도:
LL = Σ_n Σ_j y_nj × log(P_nj)
   where y_nj = 1 if j is chosen, 0 otherwise
```

#### 추정 코드 (biogeme)

```python
from biogeme import biogeme, database, models
from biogeme.expressions import Variable, Beta

# 변수 정의
T_ride = Variable('T_ride')
T_walk = Variable('T_walk')
N_transfer = Variable('N_transfer')
D_subway = Variable('D_subway')

# 파라미터 정의 (초기값, 하한, 상한, 추정여부)
beta_ride = Beta('beta_ride', -0.08, None, 0, 0)      # 음수 제약
beta_walk = Beta('beta_walk', -0.7, None, 0, 0)
beta_transfer = Beta('beta_transfer', -4.0, None, 0, 0)
beta_subway = Beta('beta_subway', 2.0, None, None, 0)

# 효용함수
V = beta_ride * T_ride + beta_walk * T_walk + \
    beta_transfer * N_transfer + beta_subway * D_subway

# 모델 추정
model = models.logit(V, availability, choice)
results = biogeme.estimate(model)
```

#### 실제 결과 (Step 4 완료, 2026-02-07)

| 파라미터 | 추정치 | 표준오차 | t-stat | 유의수준 |
|----------|--------|---------|--------|----------|
| β_ride | -0.0341 | 0.0016 | -21.21 | *** |
| β_walk | -0.7755 | 0.0025 | -305.01 | *** |
| β_transfer | -3.4130 | 0.0153 | -222.65 | *** |
| β_subway | +2.3939 | 0.0171 | +140.30 | *** |
| β_peak_ride | -0.0073 | 0.0027 | -2.67 | ** |
| β_peak_xfer | +0.0837 | 0.0249 | +3.36 | *** |

**ρ² = 0.4686, Hit Rate = 62.92%**

상세 결과: `main/results/PHASE3_RESULTS1_MNL.md`

### 5.3 Model B: Mixed Logit (핵심 모델)

#### 이론적 배경

MNL의 한계:
- 모든 이용자가 **동일한 고정 β**를 가진다고 가정
- IIA (Independence of Irrelevant Alternatives) 가정

Mixed Logit의 개선:
- 파라미터가 **확률분포**를 따름: β_i ~ f(β | θ)
- 개인별 이질성 포착: "같은 고령자라도 다른 선호"
- IIA 가정 완화

#### 수학적 정의

```
조건부 선택확률 (given β_i):
L_ni(β_i) = exp(V_ni(β_i)) / Σ_k exp(V_nk(β_i))

비조건부 선택확률 (적분):
P_ni = ∫ L_ni(β) × f(β | θ) dβ

여기서 f(β | θ)는 파라미터 분포:
  - 정규분포: β ~ N(μ, σ)
  - 로그정규: β ~ LogN(μ, σ)  (음수 보장 필요 시)
  - 삼각분포: β ~ Triangular(a, b, c)

시뮬레이션 추정 (Monte Carlo):
P_ni ≈ (1/R) Σ_r L_ni(β^r)
       where β^r ~ f(β | θ), r = 1, ..., R
```

#### 랜덤 파라미터 선택

| 파라미터 | Random? | 분포 | 근거 |
|----------|---------|------|------|
| β_ride | **Fixed** | - | 정규화 기준, 안정적 |
| β_walk | **Random** | Normal | 유형간 8.2×~19.6× 큰 변이 |
| β_wait | Fixed | - | 데이터 불확실성 |
| β_transfer | **Random** | Normal | 고령자 47%↑ 등 차이 |
| β_subway | **Random** | Normal | 고령자 90%↑ 선호 차이 |

#### 추정 코드 (xlogit)

```python
from xlogit import MixedLogit
import numpy as np

# 데이터 준비
X = df[['T_ride', 'T_walk', 'N_transfer', 'D_subway']].values
y = df['choice'].values
ids = df['trip_id'].values
alts = df['alt_id'].values

# 모델 설정
model = MixedLogit()

# 추정
model.fit(
    X=X,
    y=y,
    varnames=['T_ride', 'T_walk', 'N_transfer', 'D_subway'],
    ids=ids,
    alts=alts,
    randvars={
        'T_walk': 'n',       # Normal(μ, σ)
        'N_transfer': 'n',   # Normal(μ, σ)
        'D_subway': 'n'      # Normal(μ, σ)
    },
    n_draws=1000,            # Monte Carlo draws
    halton=True,             # Halton sequence (효율적)
    optim_method='L-BFGS-B', # 최적화 방법
    verbose=1
)

# 결과 출력
print(model.summary())
```

#### 결과 해석 예시

```
Mixed Logit 추정 결과 (고령자):

┌────────────┬───────────┬──────────┬─────────┬────────────────────────┐
│ Parameter  │ Mean (μ)  │ Std (σ)  │ t-stat  │ 해석                    │
├────────────┼───────────┼──────────┼─────────┼────────────────────────┤
│ T_ride     │ -0.070    │ (fixed)  │ -12.3   │ 기준 파라미터            │
│ T_walk     │ -0.770    │ 0.250    │ -15.4   │ μ=-0.77, σ=0.25        │
│ N_transfer │ -5.940    │ 1.820    │ -8.2    │ μ=-5.94, σ=1.82        │
│ D_subway   │ +4.720    │ 1.350    │ +7.0    │ μ=+4.72, σ=1.35        │
└────────────┴───────────┴──────────┴─────────┴────────────────────────┘

β_walk 해석:
- 평균 가중치: |μ_walk/β_ride| = 0.770/0.070 = 11.0×
- 95% 신뢰구간: [(-0.77-1.96×0.25)/0.07, (-0.77+1.96×0.25)/0.07]
               = [(-1.26)/0.07, (-0.28)/0.07] = [18.0×, 4.0×]

→ "고령자 중 평균적으로 보행 1분 = 차내 11분
    95%의 고령자는 4~18배 사이에 분포"
```

### 5.4 Model C: Latent Class Model

#### 핵심 질문

> "교통카드의 5개 행정적 유형 = 실제 행태 군집인가?"

#### 모델 구조

```
이용자 i는 잠재 클래스 c ∈ {1, 2, ..., K}에 확률적으로 속함

클래스 소속 확률:
π_c = exp(γ_c) / Σ_k exp(γ_k)

클래스별 선택 확률:
P(j | i, c) = exp(V_j(β_c)) / Σ_k exp(V_k(β_c))

비조건부 선택 확률:
P(j | i) = Σ_c π_c × P(j | i, c)
```

#### 추정 계획

```python
# K = 2, 3, 4, 5, 6 클래스 비교
results = {}
for K in [2, 3, 4, 5, 6]:
    model = LatentClassModel(n_classes=K)
    model.fit(X, y, ids)
    results[K] = {
        'LL': model.log_likelihood,
        'AIC': model.aic,
        'BIC': model.bic,
        'params': model.get_params()
    }

# 최적 K 선택 (BIC 최소)
best_K = min(results, key=lambda k: results[k]['BIC'])
```

#### 교차분석 계획

```
발견된 잠재 클래스 vs 교통카드 유형 교차표:

                 클래스1      클래스2      클래스3
                 (시간민감)   (편의추구)   (보행회피)
일반(82.8%)        60%         30%         10%
고령자(8.6%)       10%         75%         15%
장애인(3.1%)       15%         20%         65%
청소년(4.5%)       55%         35%         10%
어린이(1.0%)       40%         45%         15%

→ 카이제곱 검정으로 독립성 검정
→ "행정 유형 ≠ 행태 군집"이면 새로운 학술적 발견
```

### 5.5 Model D: LightGBM (벤치마크)

#### 목적

- 이산선택모델의 예측력 상한 확인
- SHAP으로 변수 중요도 교차검증

#### 코드

```python
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import shap

# 특성 (대안 속성 + 개인 속성)
features = ['T_ride', 'T_walk', 'N_transfer', 'D_subway',
            'D_peak', 'user_type', 'n_alternatives']

X_train, X_test, y_train, y_test = train_test_split(
    df[features], df['choice'], test_size=0.2,
    stratify=df['trip_id'].map(lambda x: x % 100)  # 체인 수준 분할
)

# 모델 학습
model = lgb.LGBMClassifier(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    num_leaves=31,
    class_weight='balanced'
)
model.fit(X_train, y_train)

# 예측 및 평가
y_pred = model.predict(X_test)
hit_rate = (y_pred == y_test).mean()

# SHAP 분석
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)
shap.summary_plot(shap_values, X_test, feature_names=features)
```

#### 기대 결과

```
모델 비교 (예상):

┌─────────────┬───────────┬──────────┬─────────────────────────┐
│ Model       │ Hit Rate  │ ρ²       │ 비고                     │
├─────────────┼───────────┼──────────┼─────────────────────────┤
│ MNL         │ 68%       │ 0.059    │ 기준선                   │
│ Mixed Logit │ 72%       │ 0.085    │ +4%p (이질성 포착)        │
│ Latent Class│ 70%       │ 0.072    │ 군집 기반                 │
│ LightGBM    │ 78%       │ N/A      │ 예측 상한 (해석 불가)      │
└─────────────┴───────────┴──────────┴─────────────────────────┘

해석: "ML이 LightGBM 대비 6%p 낮지만,
       경제학적 해석력(가중치, 지불의사)을 제공"
```

---

## 6. 평가 지표

### 6.1 적합도 지표

| 지표 | 수식 | 의미 | 목표 |
|------|------|------|------|
| **Log-Likelihood (LL)** | Σ y·log(P) | 모델 적합도 | 높을수록 좋음 |
| **ρ² (Rho-squared)** | 1 - LL/LL_0 | 설명력 (0~1) | > 0.1 양호 |
| **Adjusted ρ²** | 1 - (LL-K)/LL_0 | 파라미터 보정 | 모델 비교용 |
| **AIC** | -2LL + 2K | 정보기준 | 낮을수록 좋음 |
| **BIC** | -2LL + K·ln(N) | 정보기준 (엄격) | 낮을수록 좋음 |

### 6.2 예측 지표

| 지표 | 정의 | 계산 |
|------|------|------|
| **Hit Rate** | 선택 정확히 예측 비율 | Σ I(argmax P = choice) / N |
| **Mean Choice Probability** | 선택된 대안의 평균 확률 | Σ P_chosen / N |
| **Top-K Accuracy** | 상위 K개 안에 정답 포함 | 대안 많을 때 유용 |

### 6.3 통계적 검정

| 검정 | 용도 | 귀무가설 |
|------|------|----------|
| **t-test** | 개별 파라미터 유의성 | β = 0 |
| **우도비 검정 (LRT)** | 모델 비교 (nested) | 제약 모델 = 비제약 모델 |
| **Wald 검정** | 파라미터 제약 검정 | 제약 조건 성립 |
| **Hausman 검정** | IIA 가정 검정 | IIA 성립 |

---

## 7. 스크립트 구조

### 7.1 파일 구조

```
main/scripts/models/
├── step1_create_choice_set.py       # Choice variable 생성
├── step2_extract_attributes.py      # OTP 대안별 속성 추출
├── step3_prepare_model_input.py     # 모델 입력 데이터 병합
├── step4_estimate_mnl.py            # MNL 추정
├── step5_estimate_mixed_logit.py    # Mixed Logit 추정
├── step6_estimate_latent_class.py   # Latent Class 추정
├── step7_lightgbm_benchmark.py      # LightGBM + SHAP
├── step8_compare_models.py          # 모델 비교표 생성
└── utils/
    ├── data_loader.py               # 공통 데이터 로드
    └── evaluation_metrics.py        # 평가 지표 계산
```

### 7.2 각 스크립트 입출력

| Step | 입력 | 출력 | 예상 시간 | 상태 |
|------|------|------|----------|------|
| 1 | similarity_results.parquet | choice_set.parquet | ~2분 | ✅ 완료 |
| 2 | otp_alternatives.parquet | alternative_attributes.parquet | ~3분 | ✅ 완료 |
| 3 | step1,2 + trip_attributes | model_input.parquet | ~2분 | ✅ 완료 |
| 4 | model_input.parquet | mnl_results.json | ~5분 | ✅ 완료 |
| 5 | model_input.parquet | mixed_logit_results.json | 30분+ | 🔲 예정 |
| 6 | model_input.parquet | latent_class_results.json | 20분 | 🔲 예정 |
| 7 | model_input.parquet | lightgbm_results.json | 5분 | 🔲 예정 |
| 8 | 모든 결과 | comparison_table.csv, figures/ | 5분 | 🔲 예정 |

---

## 8. 상세 구현 계획

### 8.1 Step 1: Choice Set 생성

```python
"""
step1_create_choice_set.py

입력:
- similarity_results.parquet (4.94M pairs)

출력:
- choice_set.parquet
  - od_id: OD 식별자
  - chain_id: 체인 식별자
  - otp_alt_id: OTP 대안 번호 (0-9)
  - choice: 1 if best-match, 0 otherwise
  - sim_total: 종합 유사도
  - is_exact_match: exact match 여부
  - best_sim: 해당 체인의 최고 sim_total

로직:
1. similarity_results 로드
2. chain_id별 groupby
3. 각 그룹에서 sim_total 최대 대안 찾기
4. best_sim ≥ 0.70 필터링
5. choice 변수 생성
"""

THRESHOLD = 0.70

def create_choice_set(sim_df: pd.DataFrame) -> pd.DataFrame:
    # 체인별 best match 찾기
    best_match = sim_df.groupby('chain_id')['sim_total'].idxmax()

    # best_sim 계산
    sim_df['best_sim'] = sim_df.groupby('chain_id')['sim_total'].transform('max')

    # 필터링
    valid_chains = sim_df[sim_df['best_sim'] >= THRESHOLD]['chain_id'].unique()
    filtered_df = sim_df[sim_df['chain_id'].isin(valid_chains)].copy()

    # choice 변수
    filtered_df['choice'] = 0
    filtered_df.loc[best_match[best_match.index.isin(valid_chains)], 'choice'] = 1

    return filtered_df
```

### 8.2 Step 2: 대안 속성 추출

```python
"""
step2_extract_attributes.py

입력:
- otp_alternatives.parquet (4.47M 경로)

출력:
- alternative_attributes.parquet
  - od_id, alt_id
  - T_ride, T_walk, T_wait (분)
  - N_transfer
  - D_subway, D_bus_only
  - T_total
  - modes (JSON: ["BUS", "SUBWAY"])

로직:
1. otp_alternatives 로드
2. 각 경로의 legs 파싱
3. 변수 계산
"""

def extract_attributes(row: pd.Series) -> dict:
    legs = json.loads(row['legs']) if isinstance(row['legs'], str) else row['legs']

    transit_legs = [l for l in legs if l['mode'] in ['BUS', 'SUBWAY', 'RAIL']]
    walk_legs = [l for l in legs if l['mode'] == 'WALK']

    T_ride = sum(l['duration'] for l in transit_legs) / 60
    T_walk = sum(l['duration'] for l in walk_legs) / 60
    T_wait = row.get('waitingTime', 0) / 60

    N_transfer = max(0, len(transit_legs) - 1)
    D_subway = 1 if any(l['mode'] == 'SUBWAY' for l in transit_legs) else 0
    D_bus_only = 1 if all(l['mode'] == 'BUS' for l in transit_legs) else 0

    modes = [l['mode'] for l in transit_legs]

    return {
        'T_ride': T_ride,
        'T_walk': T_walk,
        'T_wait': T_wait,
        'N_transfer': N_transfer,
        'D_subway': D_subway,
        'D_bus_only': D_bus_only,
        'T_total': row['duration'] / 60,
        'modes': json.dumps(modes)
    }
```

### 8.3 Step 3: 모델 입력 병합

```python
"""
step3_prepare_model_input.py

입력:
- choice_set.parquet (from step1)
- alternative_attributes.parquet (from step2)
- trip_attributes_filtered.parquet (user_type, departure_time)

출력:
- model_input.parquet (Long format, ~2M rows)
- model_input_train.parquet (80%)
- model_input_test.parquet (20%)

로직:
1. 세 파일 조인 (od_id, alt_id 기준)
2. D_peak 계산
3. Train/Test 분할 (체인 수준)
"""

def prepare_model_input():
    choice_df = pd.read_parquet('choice_set.parquet')
    attr_df = pd.read_parquet('alternative_attributes.parquet')
    trip_df = pd.read_parquet('trip_attributes_filtered.parquet')

    # 조인
    merged = choice_df.merge(attr_df, on=['od_id', 'alt_id'])
    merged = merged.merge(trip_df[['chain_id', 'user_type', 'departure_time']], on='chain_id')

    # D_peak 계산 (07-09, 18-20)
    merged['hour'] = pd.to_datetime(merged['departure_time']).dt.hour
    merged['D_peak'] = ((merged['hour'] >= 7) & (merged['hour'] < 9) |
                        (merged['hour'] >= 18) & (merged['hour'] < 20)).astype(int)

    # Train/Test 분할
    unique_chains = merged['chain_id'].unique()
    train_chains, test_chains = train_test_split(
        unique_chains, test_size=0.2, random_state=42
    )

    train_df = merged[merged['chain_id'].isin(train_chains)]
    test_df = merged[merged['chain_id'].isin(test_chains)]

    return train_df, test_df
```

### 8.4 Step 5: Mixed Logit 추정 (핵심)

```python
"""
step5_estimate_mixed_logit.py

입력:
- model_input_train.parquet

출력:
- mixed_logit_results.json
  - pooled: 전체 이용자 결과
  - by_type: 유형별 결과 (5개)
  - comparison: MNL vs ML 비교

로직:
1. Pooled Mixed Logit 추정
2. 유형별 Mixed Logit 추정 (5개)
3. 결과 저장 및 시각화
"""

from xlogit import MixedLogit
import json

def estimate_mixed_logit(df: pd.DataFrame, user_type: int = None) -> dict:
    if user_type is not None:
        df = df[df['user_type'] == user_type]

    X = df[['T_ride', 'T_walk', 'N_transfer', 'D_subway']].values
    y = df['choice'].values
    ids = df['chain_id'].values
    alts = df['alt_id'].values

    model = MixedLogit()
    model.fit(
        X=X, y=y,
        varnames=['T_ride', 'T_walk', 'N_transfer', 'D_subway'],
        ids=ids, alts=alts,
        randvars={
            'T_walk': 'n',
            'N_transfer': 'n',
            'D_subway': 'n'
        },
        n_draws=1000,
        halton=True
    )

    # 결과 정리
    results = {
        'coefficients': {
            'T_ride': {'mean': model.coeff_['T_ride'], 'se': model.stderr_['T_ride']},
            'T_walk': {
                'mean': model.coeff_['T_walk'],
                'std': model.coeff_['sd.T_walk'],
                'se_mean': model.stderr_['T_walk'],
                'se_std': model.stderr_['sd.T_walk']
            },
            # ... 다른 파라미터들
        },
        'log_likelihood': model.loglikelihood,
        'aic': model.aic,
        'bic': model.bic,
        'n_obs': len(df),
        'n_trips': df['chain_id'].nunique()
    }

    # 가중치 계산
    beta_ride = abs(model.coeff_['T_ride'])
    results['weights'] = {
        'walk': abs(model.coeff_['T_walk']) / beta_ride,
        'transfer_minutes': abs(model.coeff_['N_transfer']) / beta_ride,
    }

    return results

def main():
    train_df = pd.read_parquet('model_input_train.parquet')

    # Pooled
    pooled_results = estimate_mixed_logit(train_df)

    # By user type
    by_type_results = {}
    for user_type in [1, 2, 3, 4, 5]:
        type_df = train_df[train_df['user_type'] == user_type]
        if len(type_df) >= 1000:  # 최소 샘플
            by_type_results[user_type] = estimate_mixed_logit(type_df)

    # 저장
    with open('mixed_logit_results.json', 'w') as f:
        json.dump({
            'pooled': pooled_results,
            'by_type': by_type_results
        }, f, indent=2)
```

---

## 9. 출력물 명세

### 9.1 결과 파일

| 파일 | 내용 | 형식 |
|------|------|------|
| choice_set.parquet | Choice variable 포함 데이터 | Parquet |
| alternative_attributes.parquet | 대안별 속성 | Parquet |
| model_input.parquet | 최종 모델 입력 | Parquet |
| mnl_results.json | MNL 추정 결과 | JSON |
| mixed_logit_results.json | ML 추정 결과 | JSON |
| latent_class_results.json | LC 추정 결과 | JSON |
| lightgbm_results.json | LightGBM 결과 | JSON |
| model_comparison.csv | 모델 비교표 | CSV |

### 9.2 논문용 테이블

| Table | 내용 | 위치 |
|-------|------|------|
| Table 8 (갱신) | Pooled MNL/ML 파라미터 | results/tables/ |
| Table 9 (갱신) | 유형별 ML 파라미터 (μ, σ) | results/tables/ |
| Table 10 (신규) | Latent Class 프로필 | results/tables/ |
| Table 11 (신규) | LC vs Card Type 교차표 | results/tables/ |
| Table 12 (신규) | 모델 비교 (ρ², AIC, Hit Rate) | results/tables/ |

### 9.3 그래프

| Figure | 내용 | 파일 |
|--------|------|------|
| Fig 5 (갱신) | 유형별 가중치 비교 (bar chart) | results/figures/ |
| Fig 6 (신규) | ML 파라미터 분포 (density plot) | results/figures/ |
| Fig 7 (신규) | SHAP 특성 중요도 | results/figures/ |
| Fig 8 (신규) | LC 클래스 프로필 (radar chart) | results/figures/ |

---

## 10. 필요 패키지

```
# requirements.txt (Phase 3 추가)

# 기존 (Phase 1-2)
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=14.0.0
tqdm>=4.65.0
scipy>=1.11.0

# 이산선택모델
xlogit>=0.2.7            # Mixed Logit (GPU 지원)
biogeme>=3.2.13          # MNL, Nested Logit, Latent Class

# 머신러닝
lightgbm>=4.0.0          # 벤치마크
shap>=0.43.0             # 특성 중요도
scikit-learn>=1.3.0      # 전처리, 분할

# 시각화
matplotlib>=3.7.0
seaborn>=0.13.0
plotly>=5.18.0           # 인터랙티브 (선택)

# 통계
statsmodels>=0.14.0      # 검정
```

---

## 11. 실행 순서 및 의존성

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phase 3 실행 DAG                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Phase 2 출력]                                                  │
│       │                                                         │
│       ├── similarity_results.parquet                            │
│       ├── otp_alternatives.parquet                              │
│       └── trip_attributes_filtered.parquet                      │
│               │                                                 │
│               ▼                                                 │
│  ┌─────────────────┐    ┌─────────────────────┐                │
│  │ Step 1: Choice  │    │ Step 2: Attributes  │                │
│  │ Set 생성        │    │ 추출                 │                │
│  └────────┬────────┘    └──────────┬──────────┘                │
│           │                        │                            │
│           └──────────┬─────────────┘                            │
│                      ▼                                          │
│           ┌─────────────────────┐                               │
│           │ Step 3: Model Input │                               │
│           │ 병합                 │                               │
│           └──────────┬──────────┘                               │
│                      │                                          │
│      ┌───────────────┼───────────────┬───────────────┐          │
│      ▼               ▼               ▼               ▼          │
│  ┌───────┐     ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │Step 4 │     │ Step 5   │    │ Step 6   │    │ Step 7   │   │
│  │ MNL   │     │Mixed Logit│   │Latent Cls│    │LightGBM  │   │
│  └───┬───┘     └────┬─────┘    └────┬─────┘    └────┬─────┘   │
│      │              │               │               │          │
│      └──────────────┴───────────────┴───────────────┘          │
│                             │                                   │
│                             ▼                                   │
│                   ┌─────────────────────┐                       │
│                   │ Step 8: 모델 비교   │                       │
│                   └─────────────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12. 검증 체크리스트

### 12.1 데이터 검증

- [x] choice_set: 각 체인당 정확히 1개의 choice=1 ✅
- [x] choice_set: best_sim ≥ 0.70 필터링 정확 ✅
- [x] model_input: 모든 체인이 2개 이상 대안 보유 ✅ (단일대안 제거)
- [x] model_input: user_type 분포가 TCD와 일치 ✅
- [x] Train/Test: 분포 균형 확인 ✅ (층화추출)

### 12.2 모델 검증

- [x] MNL: 기본 변수 부호 이론 일치 ✅ (Elderly/Disabled T_ride 제외)
- [x] MNL: 모든 기본 파라미터 유의 ✅ (p < 0.001)
- [ ] Mixed Logit: σ > 0 (이질성 존재) 🔲
- [ ] Mixed Logit: ρ² > MNL ρ² 🔲
- [ ] Latent Class: 최적 K의 BIC가 인접 K보다 낮음 🔲
- [ ] LightGBM: Hit Rate > MNL Hit Rate 🔲

### 12.3 결과 검증 (Step 4 완료)

- [x] 지하철 선호: 고령자(4.64) > 장애인(2.71) > 일반(2.16) ✅
- [x] 환승 페널티: 장애인(130분) > 고령자(40분) > 일반(73분) ⚠️ 고령자 낮음
- [x] 보행 가중치: 장애인(30×) > 일반(17×) > 고령자(7×) ⚠️ 예상과 다름
- [x] Peak 효과: 시간민감도↑, 환승페널티↓ (첨두시간대 배차간격 효과) ✅

**주요 발견**: 고령자는 보행보다 환승/지하철에 더 민감, 장애인은 보행에 가장 민감

---

## 13. 예상 결과

### 13.1 MNL vs Mixed Logit 비교

```
┌─────────────────────────────────────────────────────────────────┐
│                    Pooled Model Comparison                       │
├──────────────┬─────────────────┬─────────────────────────────────┤
│ Parameter    │ MNL             │ Mixed Logit                     │
│              │ β (t-stat)      │ μ (t-stat)    σ (t-stat)        │
├──────────────┼─────────────────┼─────────────────────────────────┤
│ T_ride       │ -0.082 (-14.2)  │ -0.082 (-14.2) (fixed)          │
│ T_walk       │ -0.699 (-22.5)  │ -0.712 (-18.3) 0.215 (8.4)      │
│ N_transfer   │ -4.194 (-16.8)  │ -4.350 (-12.1) 1.520 (6.2)      │
│ D_subway     │ +2.493 (+11.4)  │ +2.580 (+9.5)  0.890 (4.8)      │
├──────────────┼─────────────────┼─────────────────────────────────┤
│ LL           │ -234,567        │ -228,123                        │
│ ρ²           │ 0.059           │ 0.085                           │
│ AIC          │ 469,142         │ 456,260                         │
│ Hit Rate     │ 68.2%           │ 72.4%                           │
└──────────────┴─────────────────┴─────────────────────────────────┘

해석:
- Mixed Logit이 ρ² 0.026 개선 (44% 상대 개선)
- σ > 0: 이용자 간 선호 이질성 존재 증명
- LRT = 2×(LL_ML - LL_MNL) = 12,888, p < 0.001
```

### 13.2 유형별 Mixed Logit 가중치

```
┌─────────────────────────────────────────────────────────────────┐
│           Walk Weight (β_walk / β_ride) by User Type             │
├───────────┬────────────┬────────────┬────────────────────────────┤
│ Type      │ MNL        │ ML Mean    │ ML 95% CI                  │
├───────────┼────────────┼────────────┼────────────────────────────┤
│ General   │ 8.2×       │ 8.4×       │ [4.1×, 12.7×]              │
│ Elderly   │ 11.0×      │ 11.5×      │ [5.2×, 17.8×]              │
│ Youth     │ 10.3×      │ 10.1×      │ [5.5×, 14.7×]              │
│ Disabled  │ 11.2×      │ 12.0×      │ [6.1×, 17.9×]              │
│ Children  │ 19.6×      │ 18.2×      │ [8.4×, 28.0×]              │
└───────────┴────────────┴────────────┴────────────────────────────┘

핵심 발견:
- 어린이의 보행 가중치 분산이 가장 큼 (보호자 동반 여부?)
- 고령자/장애인의 95% CI가 겹침 → 유사한 이질성 패턴
```

---

## 14. Phase 4 (반복 보정) 연결

Phase 3 완료 후 Mixed Logit 결과를 Phase 4 (반복 보정)에 연결:

```
Phase 3 출력 → Phase 4 입력

β_walk / β_ride = 8.5 → WALK_RELUCTANCE = 8.5
β_transfer / β_ride × 60 = 3068초 → TRANSFER_COST = min(600, 3068) = 600초

→ OTP 파라미터 업데이트 → 재실행 → 재매칭 → 재추정 → 수렴까지
```

---

## 15. 일정

| 일차 | 작업 | 산출물 | 상태 |
|------|------|--------|------|
| Day 1 | Step 1-3: 데이터 준비 | model_input.parquet | ✅ 완료 |
| Day 1 | Step 4: MNL 추정 + 검증 | mnl_results.json | ✅ 완료 |
| Day 2 | Step 5: Mixed Logit (Pooled + 유형별) | mixed_logit_results.json | 🔲 예정 |
| Day 3 | Step 6: Latent Class | latent_class_results.json | 🔲 예정 |
| Day 4 | Step 7-8: LightGBM + 비교 | 최종 결과 | 🔲 예정 |

**진행 상황**: Step 1-4 완료 (2026-02-07), Step 5 대기 중
