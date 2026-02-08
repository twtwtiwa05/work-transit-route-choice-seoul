# Phase 4: 반복 보정 (Iterative Calibration) 실행 계획

*작성일: 2026-02-08*
*ITS World Congress 2026 (강릉)*

---

## 1. 목적 및 배경

### 1.1 핵심 목표

Phase 3에서 추정된 행태 파라미터(β)를 OTP 라우팅 엔진의 비용함수에 반영하고, 반복적으로 경로 대안을 재생성하여 **자기일관적(self-consistent) 파라미터**로 수렴시킨다.

```
현재 상태 (Iteration 0):
  OTP: walkReluctance=1.0, transferCost=120초 (기본값)
  → 보행 페널티 거의 없이 경로 생성
  → 추정된 β_walk/β_ride = 9.5× (LC Class 2)
  → OTP 가정과 실제 행태 사이에 9.5배 괴리

목표 상태 (수렴):
  OTP: walkReluctance≈8.0, transferCost≈420초
  → 실제 이용자 선호를 반영한 경로 생성
  → 매칭률: 42.5% → 55%+ (분석 가능 표본 30% 확대)
  → β-θ 일관성 달성
```

### 1.2 전 논문과의 차별점

| 항목 | 전 논문 (ITSWC 2026 초안) | 현 연구 (Phase 4) |
|------|-------------------------|-------------------|
| 데이터 | 187,010 체인 (exact match만) | 411,754 체인 (sim≥0.70) |
| 모형 | MNL 1개 | MNL + ML + LC + LightGBM 4개 |
| OTP 파라미터 | 기본값 1회 사용 | **반복 보정으로 수렴** |
| 이질성 | 유형별 MNL (5개) | LC 잠재 군집 + ML 연속 분포 |
| 확률 표시 | OD별 유형별 확률 3개 테스트 | **전체 OD에 유형별 확률 배정** |

### 1.3 이론적 기반: 이중 수준 최적화

```
상위 수준 (OTP 비용함수 보정):
  min_θ  D(P_observed, P_predicted(θ))

하위 수준 (경로선택 모형 추정):
  max_β  LL(β | C(θ))

핵심 결합: 선택지 집합 C(θ)가 OTP 파라미터 θ에 의존하고,
          추정된 β가 다음 θ를 결정
→ Method of Successive Averages (MSA)로 풀이
```

---

## 2. 현재 시스템 현황

### 2.1 OTP Java 엔진 (이미 파라미터화 완료)

Java 코드는 Phase 2에서 이미 `CalibrationConfig` 기반으로 수정 완료. **Java 수정 불필요.**

| 파라미터 | JSON 키 | 현재값 | 사용처 |
|---------|---------|--------|-------|
| walkReluctance | `walkReluctance` | **1.0** | `KoreanAccessEgress.c1()`: 보행비용 = 초 × 100 × walkReluctance |
| transferCostSeconds | `transferCostSeconds` | **120** | `KoreanCostCalculator`: 환승비용 = sec × 100 |
| firstBoardCostSeconds | `firstBoardCostSeconds` | **60** | 최초 탑승 비용 |
| waitReluctance | `waitReluctance` | **1.0** | 대기시간 가중치 |
| searchWindowSeconds | `searchWindowSeconds` | **1800** | RAPTOR 탐색 시간창 |

**설정 파일**: `korean-otp/calibration_config.json`

```json
{
  "transferCostSeconds": 120,
  "firstBoardCostSeconds": 60,
  "waitReluctance": 1.0,
  "walkReluctance": 1.0,
  "searchWindowSeconds": 1800
}
```

### 2.2 비용 계산 구조 (centi-seconds)

```
OTP 내부 비용 단위: centi-seconds (1초 = 100 단위)

보행 비용 = durationSec × 100 × walkReluctance
         현재: 5분 보행 = 300 × 100 × 1.0 = 30,000
         목표: 5분 보행 = 300 × 100 × 8.5 = 255,000 (8.5배 증가)

환승 비용 = transferCostSec × 100
         현재: 120 × 100 = 12,000 (2분 등가)
         목표: 420 × 100 = 42,000 (7분 등가)

차내시간 비용 = transitTimeSec × 100 (기본, 가중치 없음)
→ walkReluctance=8.5는 "보행 1초 = 차내시간 8.5초"를 의미
```

### 2.3 Phase 3 추정 파라미터 (β → θ 매핑 입력)

#### LC Class 2 (77.2%, 다수 이용자) — 기본 OTP 파라미터 후보

| 파라미터 | 추정치 | 매핑 | OTP 목표값 |
|---------|--------|------|-----------|
| β_ride | -0.077 | (기준) | 1.0 |
| β_walk | -0.730 | \|−0.730 / −0.077\| | **walkReluctance = 9.5** |
| β_transfer | -3.272 | \|−3.272 / −0.077\| × 60초 | **transferCost = 2,552초 → cap 600초** |
| β_subway | +2.022 | (OTP에 직접 매핑 불가) | — |

#### MNL 유형별 β → OTP θ 매핑

| 유형 | β_ride | β_walk | β_transfer | Walk Reluctance | Transfer Penalty (분) |
|------|--------|--------|------------|----------------|---------------------|
| **General** | -0.045 | -0.767 | -3.322 | 16.9× | 73.3분 |
| **Children** | -0.077 | -0.947 | -4.042 | 12.3× | 52.6분 |
| **Youth** | -0.078 | -0.880 | -3.941 | 11.2× | 50.3분 |
| **Elderly** | +0.108 | -0.785 | -4.290 | 7.3× | 39.6분 |
| **Disabled** | +0.028 | -0.840 | -3.600 | 30.2× | 129.6분 |
| **가중평균** | — | — | — | **~13.5×** | **~66분** |

> **주의**: Elderly/Disabled는 β_ride > 0 (양수). 환승 회피와 지하철 선호가 너무 강해 차내시간 증가를 감수하는 행태. OTP 파라미터 매핑 시 |β_walk / β_ride| 대신 β_walk 자체의 상대적 크기를 활용해야 함.

---

## 3. 반복 보정 전략

### 3.1 핵심 설계 결정

#### 결정 1: OTP는 1회만 실행, 유형별 차이는 β로 표현

```
[이유]
- OTP 배치 실행 1회 = ~8시간 (1.26M OD)
- 5유형 × 8시간 = 40시간 → 비현실적
- Pareto-optimal 탐색은 다양한 선호 프로파일의 경로를 포괄함
- 유형별 차이는 동일 대안에 대해 다른 MNL β를 적용하여 반영

[구조]
OTP(θ_avg) → 대안 5~11개/OD → 유형별 V_j 계산 → 유형별 P(j) 산출
```

#### 결정 2: LC Class 2 파라미터를 기본 OTP θ로 사용

```
[이유]
- 77.2%의 다수 이용자 대표
- MNL pooled (walk=22.7×)보다 안정적 (walk=9.5×)
- 전 논문 권장값 (8.0~9.0)과 일치
- Elderly/Disabled의 양수 β_ride 문제 회피

[대안 검토]
- MNL pooled 22.7× → 너무 극단적, 보행 경로 완전 소멸 위험
- 유형별 가중평균 13.5× → 중간값이나 이론적 근거 약함
- LC Class 2 9.5× → ✓ 이론+실증 기반, 안정적
```

#### 결정 3: TRANSFER_COST 상한 설정

```
Raw 계산: |β_transfer / β_ride| × 60 = 2,552초 (42.5분)
→ 너무 높으면 다환승 경로가 Pareto 탐색에서 소멸

상한: transferCostSeconds ≤ 600 (10분)
→ 나머지 환승 기피는 MNL β_transfer가 모형 수준에서 포착
→ OTP 역할은 "대안 생성", 행태적 극단성은 β가 담당
```

### 3.2 반복 알고리즘 흐름

```
┌──────────────────────────────────────────────────────────────────┐
│                     반복 보정 루프 (Phase 4)                        │
│                                                                  │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│  │ θ 설정   │──→│ OTP 배치  │──→│ 유사도    │──→│ Choice Set│    │
│  │ config   │    │ Java실행  │    │ 매칭     │    │ 구성      │    │
│  └─────────┘    └──────────┘    └──────────┘    └──────────┘    │
│       ↑                                              │          │
│       │                                              ↓          │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│  │ MSA감쇠  │←──│ β→θ 매핑  │←──│ MNL추정   │←──│ 속성추출  │    │
│  │ θ 업데이트│    │          │    │ (Pooled)  │    │          │    │
│  └─────────┘    └──────────┘    └──────────┘    └──────────┘    │
│                                                                  │
│  수렴 시: 최종 MNL(Pooled+유형별) + ML + LC 재추정                    │
│         + 유형별 확률 배정 모듈 실행                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 상세 알고리즘

```
입력:
  od_pairs_filtered.csv (1,263,225 OD pairs)
  TCD 관측 데이터 (tcd_chains)
  θ_0 = {walkReluctance: 1.0, transferCostSeconds: 120}  ← iter0 (이미 완료)
  β_0 = Phase 3 MNL pooled 추정치
  ε = 0.01 (수렴 허용 오차)
  K_max = 10

절차:
  k ← 0

  REPEAT:
    k ← k + 1

    === STEP 1: β → θ 목표값 계산 ===
    θ_target.walkReluctance ← |β_{k-1}.walk / β_{k-1}.ride|
    θ_target.transferCost ← min(600, |β_{k-1}.transfer / β_{k-1}.ride| × 60)

    === STEP 2: MSA 감쇠 업데이트 ===
    α_k ← min(0.5, 1/k)
    θ_k ← θ_{k-1} + α_k × (θ_target − θ_{k-1})

    === STEP 3: calibration_config.json 업데이트 ===
    write_config(θ_k)

    === STEP 4: OTP 배치 실행 (Java) ===
    run_batch_router → batch_result_iter{k}.ndjson

    === STEP 5: 파싱 + 유사도 매칭 + Choice Set 구성 ===
    parse_otp_results → otp_alternatives_iter{k}.parquet
    calculate_similarity → similarity_iter{k}.parquet
    create_choice_set (threshold=0.70) → choice_set_iter{k}.parquet

    === STEP 6: 속성 추출 + MNL 추정 (Pooled only) ===
    extract_attributes → model_input_iter{k}.parquet
    estimate_mnl_pooled → β_k

    === STEP 7: 수렴 검사 ===
    Δ_β ← max|β_k − β_{k-1}| / max|β_{k-1}|
    Δ_θ ← max|θ_k − θ_{k-1}| / max|θ_{k-1}|
    match_rate_k ← |choice_set| / |total_chains|

    converged ← (Δ_β < ε) AND (Δ_θ < ε)

  UNTIL converged OR k ≥ K_max

  === STEP 8: 최종 모형 추정 (수렴 파라미터 기반) ===
  MNL pooled + 5유형별
  Mixed Logit (pooled)
  Latent Class (K=3)
  LightGBM (Core + Full)

  === STEP 9: 유형별 확률 배정 모듈 ===
  for each OD pair:
    for each alternative j:
      for each user_type g:
        P(j | g) = exp(V_j^g) / Σ exp(V_k^g)
    → 경로별 유형별 선택확률(%) 출력
```

---

## 4. 유형별 확률적 경로 배정

### 4.1 개념

논문의 SYSTEM IMPLEMENTATION을 확장하여, 수렴된 파라미터 기반으로 **모든 OD에 대해 유형별 경로 선택확률을 산출**한다.

```
입력: OTP 대안 경로 (속성 포함)
       + MNL β 파라미터 (유형별 5세트)

처리:
  Route 1: T_ride=29.5, T_walk=1.8, N_transfer=1, D_subway=1
  Route 2: T_ride=35.6, T_walk=3.7, N_transfer=0, D_subway=0

  V_1^General = -0.045×29.5 - 0.767×1.8 - 3.322×1 + 2.161×1 = -3.56
  V_2^General = -0.045×35.6 - 0.767×3.7 - 3.322×0 + 2.161×0 = -4.44

  P(1|General) = exp(-3.56) / (exp(-3.56) + exp(-4.44)) = 70.8%
  P(2|General) = 29.2%

  V_1^Elderly = +0.108×29.5 - 0.785×1.8 - 4.290×1 + 4.641×1 = +2.12
  V_2^Elderly = +0.108×35.6 - 0.785×3.7 - 4.290×0 + 4.641×0 = +0.94

  P(1|Elderly) = 76.7%
  P(2|Elderly) = 23.3%

출력 (경로별 퍼센트):
  ┌─────────────────────────────────────────────────┐
  │  명동 → 역삼 (09:00)                             │
  ├───────────┬───────┬───────┬────────┬────────────┤
  │ Route     │ 시간   │ 환승  │ General │ Elderly    │
  ├───────────┼───────┼───────┼────────┼────────────┤
  │ 4호선→2호선│ 29.5분 │ 1회   │ 70.8%  │ 76.7%     │
  │ 463번 직행 │ 35.6분 │ 0회   │ 29.2%  │ 23.3%     │
  └───────────┴───────┴───────┴────────┴────────────┘
```

### 4.2 확률 배정 모듈 설계

```python
# scripts/calibration/probabilistic_router.py

class ProbabilisticRouter:
    """유형별 MNL 확률 계산기"""

    def __init__(self, mnl_params: dict):
        """
        mnl_params = {
            'General': {'T_ride': -0.045, 'T_walk': -0.767, ...},
            'Elderly': {'T_ride': +0.108, 'T_walk': -0.785, ...},
            ...
        }
        """
        self.params = mnl_params

    def compute_probabilities(self, alternatives: list[dict]) -> dict:
        """
        alternatives = [
            {'T_ride': 29.5, 'T_walk': 1.8, 'N_transfer': 1, 'D_subway': 1},
            {'T_ride': 35.6, 'T_walk': 3.7, 'N_transfer': 0, 'D_subway': 0},
        ]

        returns = {
            'General':  [0.708, 0.292],
            'Elderly':  [0.767, 0.233],
            'Disabled': [0.621, 0.379],
            ...
        }
        """
        result = {}
        for user_type, beta in self.params.items():
            utilities = []
            for alt in alternatives:
                V = (beta['T_ride'] * alt['T_ride']
                   + beta['T_walk'] * alt['T_walk']
                   + beta['N_transfer'] * alt['N_transfer']
                   + beta['D_subway'] * alt['D_subway'])
                utilities.append(V)

            # Max-normalization for numerical stability
            V_max = max(utilities)
            exp_V = [math.exp(v - V_max) for v in utilities]
            sum_exp = sum(exp_V)
            probs = [e / sum_exp for e in exp_V]
            result[user_type] = probs

        return result
```

### 4.3 출력 형식 (JSON)

```json
{
  "od_pair": {"from": "명동역", "to": "역삼역", "departure": "09:00"},
  "alternatives": [
    {
      "route_name": "4호선 → 2호선",
      "ride_min": 29.5,
      "walk_min": 1.8,
      "transfers": 1,
      "has_subway": true,
      "probabilities": {
        "General": "70.8%",
        "Children": "65.2%",
        "Youth": "68.4%",
        "Elderly": "76.7%",
        "Disabled": "62.1%"
      }
    },
    {
      "route_name": "463번 직행",
      "ride_min": 35.6,
      "walk_min": 3.7,
      "transfers": 0,
      "has_subway": false,
      "probabilities": {
        "General": "29.2%",
        "Children": "34.8%",
        "Youth": "31.6%",
        "Elderly": "23.3%",
        "Disabled": "37.9%"
      }
    }
  ]
}
```

---

## 5. 실행 단계 (Step-by-Step)

### Step 4-1: 파라미터 매핑 모듈 구현

**스크립트**: `scripts/calibration/param_mapper.py`

```
입력: results/mnl_results.json (또는 latent_class_results.json)
처리: β → θ 매핑 + MSA 감쇠
출력: korean-otp/calibration_config.json (업데이트)

매핑 규칙:
  walkReluctance = |β_walk / β_ride|  (단, β_ride < 0인 경우만)
  transferCostSeconds = min(600, |β_transfer / β_ride| × 60)
  firstBoardCostSeconds = 60 (고정)
  waitReluctance = 1.0 (고정, 추정 대상 아님)

MSA 감쇠:
  α_k = min(0.5, 1/k)
  θ_k = θ_{k-1} + α_k × (θ_target − θ_{k-1})
```

**Iteration 1 예측값 (LC Class 2 기반)**:
```
θ_target = {walkReluctance: 9.5, transferCostSeconds: 600}
α_1 = min(0.5, 1/1) = 0.5

walkReluctance: 1.0 + 0.5 × (9.5 − 1.0) = 5.25
transferCostSeconds: 120 + 0.5 × (600 − 120) = 360
```

### Step 4-2: OTP 배치 재실행

**실행**: Java BatchRouter

```bash
cd korean-otp
java -jar target/korean-otp.jar \
  --input od_pairs_filtered.csv \
  --output batch_result_iter1.ndjson \
  --config calibration_config.json
```

| 항목 | 값 |
|------|-----|
| OD 수 | 1,263,225 |
| 예상 시간 | ~8시간 (16 스레드) |
| 출력 크기 | ~30GB (NDJSON) |
| 대안 수 | 5~11개/OD (Multi-criteria Pareto) |

> **개발 시**: 10,000 OD 서브샘플로 ~5분/반복 (빠른 디버깅)

### Step 4-3: 재파싱 + 유사도 재계산

기존 Phase 2 파이프라인을 iteration 변수와 함께 재실행:

```
step4_parse_otp_results.py → otp_alternatives_iter{k}.parquet
step5_calculate_similarity.py → similarity_iter{k}.parquet
```

> **주의**: `step4_parse_otp_results.py`의 NDJSON 경로가 하드코딩되어 있음 → 파라미터화 필요

### Step 4-4: Choice Set 재구성

```
step1_create_choice_set.py (threshold=0.70)
→ choice_set_iter{k}.parquet

모니터링:
  - 매칭률 (42.5% → ? 목표 55%+)
  - OD당 평균 대안 수 (3.7개 → ?)
  - 유형별 체인 수 (최소 1,000개 유지 확인)
```

### Step 4-5: MNL Pooled 재추정

```
step4_estimate_mnl.py (pooled only, 빠른 추정)
→ β_k (수렴 비교용)
```

> **보정 루프에서는 MNL Pooled만 사용** (5분 이내).
> ML/LC는 수렴 후 최종 1회만 추정 (ML: 6시간, LC: 1시간).

### Step 4-6: 수렴 검사

| 기준 | 수식 | 임계값 | 의미 |
|------|------|--------|------|
| β 안정성 | max\|β_k − β_{k-1}\| / max\|β_{k-1}\| | < 0.01 | 파라미터 수렴 |
| θ 안정성 | max\|θ_k − θ_{k-1}\| / max\|θ_{k-1}\| | < 0.01 | OTP 파라미터 수렴 |
| 매칭률 변화 | \|match_k − match_{k-1}\| | < 0.5%p | 매칭률 안정 |
| 최대 반복 | k | ≤ 10 | 안전 장치 |

### Step 4-7: (수렴 후) 최종 모형 재추정

수렴된 choice set으로 **4개 모형 전체 재추정**:

| 모형 | 예상 소요시간 | 비고 |
|------|------------|------|
| MNL Pooled + 5유형 | ~30분 | 유형별 β 확보 (확률 배정용) |
| Mixed Logit | ~6시간 | σ 재추정 (이질성 구조 변화 확인) |
| Latent Class (K=3) | ~1시간 | 클래스 구성 변화 확인 |
| LightGBM Core + Full | ~30분 | 벤치마크 업데이트 |

### Step 4-8: 유형별 확률 배정

```
scripts/calibration/probabilistic_router.py

입력:
  - 수렴된 OTP 대안 (otp_alternatives_final.parquet)
  - 유형별 MNL β (mnl_results_final.json)

출력:
  - route_probabilities.json (전체 OD × 유형별 확률)
  - 논문용 테스트 케이스 3~5개 (Table + 시각화)
```

### Step 4-9: 결과 보고서 + 시각화

| 산출물 | 내용 |
|--------|------|
| `PHASE4_RESULTS.md` | 수렴 과정, iter0 vs 최종 비교, 매칭률 변화 |
| `fig_convergence.png` | θ, β, 매칭률 반복별 궤적 |
| `fig_match_rate.png` | 매칭률 향상 그래프 |
| `fig_probability_cases.png` | 테스트 케이스 유형별 확률 비교 |
| `table_before_after.md` | OTP 기본값 vs 보정값 비교표 |

---

## 6. 예상 수렴 과정

```
Iter 0 (현재, 이미 완료):
  θ: walk=1.0, transfer=120s
  매칭률: 42.5% (560,844 / 1,320,030 체인)
  β: MNL pooled walk/ride=22.7×, LC C2 walk/ride=9.5×

Iter 1:
  θ: walk=5.25, transfer=360s  (MSA α=0.5)
  → 보행 적은 경로 위주 생성
  매칭률: ~47% (+4.5%p)
  β: walk/ride ≈ 10~12×

Iter 2:
  θ: walk=6.9, transfer=400s  (MSA α=0.33)
  매칭률: ~51% (+4%p)
  β: walk/ride ≈ 9~10×

Iter 3:
  θ: walk=7.5, transfer=420s  (MSA α=0.25)
  매칭률: ~54% (+3%p)
  β 변화 < 3%

Iter 4-5:
  θ: walk=7.8~8.0, transfer=430~450s
  매칭률: ~55-57%
  Δβ < 1% → 수렴!

최종:
  θ*: walkReluctance ≈ 8.0, transferCostSeconds ≈ 430
  매칭률: 55%+ (42.5% 대비 +12.5%p 개선)
  분석 가능 체인: ~726,000개 (560,844 대비 29% 증가)
```

---

## 7. 위험 관리

### 7.1 Pareto 표면 변화

**위험**: walkReluctance가 1→5.25으로 급변하면 Pareto frontier가 근본적으로 변함.
일부 OD에서 대안이 1~2개로 축소될 수 있음.

**대응**:
- Iteration 1 후 OD당 대안 수 분포 모니터링
- 평균 대안 수 < 2.5이면 MC_RELAX_RATIO를 1.0 → 1.1로 완화 검토
- TRANSFER_COST 상한 600초 유지하여 다환승 경로 보존

### 7.2 경로 세트 붕괴 (Alternative Set Collapse)

**위험**: 극단적 walkReluctance로 보행 경로가 모두 제거되어 선택지가 단일화.

**모니터링**:
```python
# 반복마다 체크
mean_alts = choice_set.groupby('chain_id')['alt_idx'].count().mean()
pct_single = (choice_set.groupby('chain_id')['alt_idx'].count() == 1).mean()

assert mean_alts >= 2.5, "대안 수 부족"
assert pct_single <= 0.30, "단일 대안 체인 30% 초과"
```

### 7.3 계산 시간

| 시나리오 | OD 수 | 반복당 | 총 예상 |
|---------|-------|--------|--------|
| **개발 (서브샘플)** | 10,000 | ~15분 | ~1시간 (4회) |
| **전체 실행** | 1,263,225 | ~10시간 | ~50시간 (5회) |
| **하이브리드** | 서브샘플 수렴 → 전체 1회 | ~15시간 | 권장 |

**권장 전략**: 10K 서브샘플로 θ 수렴 확인 후, 수렴된 θ로 전체 OD 1회 배치 실행.

### 7.4 양수 β_ride 문제 (Elderly/Disabled)

**현상**: MNL 유형별 추정에서 Elderly(β_ride=+0.108)와 Disabled(β_ride=+0.028)의 차내시간 계수가 양수.

**해석**: 지하철 선호(β_subway=+4.64)와 환승 기피(β_transfer=-4.29)가 극도로 강해, 환승 없는 지하철 직통 노선을 위해 차내시간 증가를 감수. β_ride가 양수인 것은 이 행태의 통계적 반영.

**OTP 매핑 대응**:
- 유형별 OTP 파라미터 매핑 시 β_ride > 0인 유형은 walk_reluctance = |β_walk| / median(|β_ride|) 사용
- 또는 LC Class 2 파라미터를 모든 유형의 기본 OTP 파라미터로 사용하고, 유형 차이는 β 확률 계산에서만 반영

---

## 8. 구현 파일 목록

### 새로 생성할 스크립트 (scripts/calibration/)

| # | 파일 | 역할 | 입출력 |
|---|------|------|-------|
| 1 | `param_mapper.py` | β→θ 매핑 + MSA 감쇠 | mnl_results.json → calibration_config.json |
| 2 | `calibration_orchestrator.py` | 반복 루프 자동화 | Java 호출 + Python 파이프라인 조율 |
| 3 | `convergence_checker.py` | 수렴 진단 + 시각화 | 반복별 β, θ, match_rate → 그래프 |
| 4 | `probabilistic_router.py` | 유형별 확률 배정 | OTP 대안 + β → 유형별 P(j) |
| 5 | `run_subsample.py` | 서브샘플 빠른 실행 | 10K OD로 빠른 반복 검증 |

### 수정할 기존 스크립트

| 파일 | 수정 내용 |
|------|---------|
| `scripts/matching/step4_parse_otp_results.py` | NDJSON 경로 파라미터화 (iter0 → iterN 지원) |
| `scripts/matching/step5_calculate_similarity.py` | iteration별 입출력 경로 지원 |
| `scripts/models/step1_create_choice_set.py` | iteration별 입출력 경로 지원 |

### Java (수정 불필요)

`CalibrationConfig.java`, `KoreanCostCalculator.java`, `KoreanAccessEgress.java`, `BatchRouter.java`
→ 이미 Phase 2에서 파라미터화 완료. `calibration_config.json`만 업데이트하면 됨.

---

## 9. 디렉토리 구조

```
main/
├── scripts/
│   ├── calibration/              ← 새로 생성
│   │   ├── param_mapper.py
│   │   ├── calibration_orchestrator.py
│   │   ├── convergence_checker.py
│   │   ├── probabilistic_router.py
│   │   └── run_subsample.py
│   ├── matching/                 ← 일부 수정
│   │   ├── step4_parse_otp_results.py  (경로 파라미터화)
│   │   └── step5_calculate_similarity.py
│   └── models/                   ← 재사용
│       ├── step1_create_choice_set.py
│       ├── step2_extract_attributes.py
│       ├── step3_prepare_model_input.py
│       └── step4_estimate_mnl.py
│
├── output/
│   ├── iter0/                    ← 현재 데이터 (이동)
│   │   ├── otp_alternatives.parquet
│   │   ├── similarity_results.parquet
│   │   └── choice_set.parquet
│   ├── iter1/
│   │   ├── batch_result_iter1.ndjson
│   │   ├── otp_alternatives_iter1.parquet
│   │   └── ...
│   └── final/                    ← 수렴 후 최종
│
├── results/
│   ├── calibration_log.json      ← 반복별 θ, β, match_rate 기록
│   ├── route_probabilities.json  ← 유형별 확률 배정 결과
│   ├── PHASE4_RESULTS.md         ← 결과 보고서
│   └── figures/
│       ├── fig_convergence.png
│       ├── fig_match_rate.png
│       └── fig_probability_cases.png
│
└── korean-otp/
    └── calibration_config.json   ← 반복마다 업데이트
```

---

## 10. 논문 기여도 (Phase 4 완료 시)

| # | 기여 | 설명 |
|---|------|------|
| 1 | **자기일관적 보정** | OTP-행태모형 간 피드백 루프를 통한 일관적 파라미터 수렴 |
| 2 | **매칭률 개선** | 42.5% → 55%+ (분석 가능 표본 ~30% 확대) |
| 3 | **OTP 파라미터 권장** | WALK_RELUCTANCE 기본값 1.0 → 실증 기반 8.0 제안 |
| 4 | **유형별 확률 경로 배정** | 동일 OD에서 유형별로 다른 경로 선택확률 시스템 구현 |
| 5 | **수렴 진단 프레임워크** | MSA 감쇠 + 4중 수렴 기준의 방법론적 기여 |

### 전 논문 Table 17 업데이트 목표

| Parameter | Default | 전 논문 권장 | **Phase 4 수렴값** |
|-----------|---------|------------|-------------------|
| WALK_RELUCTANCE | 1.0 | 8.0~9.0 | **~8.0** (수렴) |
| TRANSFER_COST | 120초 | "Increase" | **~430초** (수렴) |

---

## 11. 실행 일정

| 단계 | 내용 | 소요 | 산출물 |
|------|------|------|--------|
| Day 1 | param_mapper.py + run_subsample.py 구현 | 3시간 | θ 매핑 + 10K 서브샘플 준비 |
| Day 1 | step4 경로 파라미터화 수정 | 1시간 | iterN 지원 |
| Day 2 | calibration_orchestrator.py 구현 | 4시간 | 반복 루프 자동화 |
| Day 2 | 10K 서브샘플 4~5회 반복 테스트 | 2시간 | θ 수렴 확인 |
| Day 3 | 전체 OD 최종 OTP 배치 실행 | 8시간 | batch_result_final.ndjson |
| Day 4 | 재매칭 + 4개 모형 재추정 | 8시간 | 최종 모형 결과 |
| Day 5 | probabilistic_router.py + 시각화 | 4시간 | 유형별 확률 + 그래프 |
| Day 5 | PHASE4_RESULTS.md 작성 | 3시간 | 결과 보고서 |

**총 예상: 5일 (하이브리드 전략 기준)**

---

*이 계획은 RESEARCH_PLAN.md Section 5의 설계를 기반으로 하되, Phase 3 결과를 반영하여 구체화한 실행 계획입니다.*
