# Phase 4: 반복 보정 (Iterative Calibration) 실행 계획

*작성일: 2026-02-08 (수정: 2026-02-11)*
*ITS World Congress 2026 (강릉)*

---

## 1. 목적 및 배경

### 1.1 핵심 목표

Phase 3에서 추정된 행태 파라미터(β)를 OTP 라우팅 엔진의 비용함수에 반영하여 **자기일관적(self-consistent) 파라미터**를 도출한다. 나아가, θ 최적화의 구조적 한계를 발견하고 **MNL 재순위(re-ranking)**를 통한 대안적 개선 방법을 제시한다.

```
문제 상황:
  OTP: walkReluctance=1.0, transferCost=120초 (기본값)
  MNL: 보행 가중치 22.7×, 환승 페널티 ~100분
  → OTP 가정과 실제 행태 사이에 큰 괴리

해결 시도:
  1. β → θ 변환 (접근법 A, B, E) → 개선 상한 ~+1%p 확인
  2. MNL β 기반 재순위 → +1.89%p 개선 (θ 최적화의 2배)
```

### 1.2 접근법 요약

| 접근법 | 설명 | 평가 기준 | 결과 | 상태 |
|--------|------|-----------|------|------|
| 전통적 반복 | β→θ→OTP 재실행→β 재추정 | - | Exact Match 붕괴 | ❌ 실패 |
| A. Pooled MSA | 단일 θ (MNL β 비율 기반) | Best Match | +1.02%p | ✅ 완료 |
| B. 유형별 θ | 5유형별 MNL 비율 기반 θ | Best Match | +4.3%p | ✅ 완료 |
| E. 확률적 RSM (IPW) | LHS+RSM, MNL 확률 가중, IPW | F₁ (확률적) | 경계 수렴 | ✅ 완료 |
| **MNL 재순위** | **MNL β로 OTP 대안 재순위** | **OTP 1순위** | **+1.89%p** | **✅ 핵심 기여** |

---

## 2. 접근법 A: Choice Set 고정 보정 (완료)

### 2.1 방법론

**β → θ 매핑**:
```
walkReluctance = |β_walk / β_ride|
transferCostSeconds = |β_transfer / β_ride| × 60
```

**MSA (Method of Successive Averages)**:
```
α_k = min(0.3, 1/(k+1))
θ_k = θ_{k-1} + α_k × (θ_target − θ_{k-1})
```

파라미터 상한: walkReluctance ≤ 6.0, transferCostSeconds ≤ 300

### 2.2 결과

| 파라미터 | 초기값 | 보정값 |
|----------|--------|--------|
| walkReluctance | 2.0 | **5.47** |
| transferCostSeconds | 120 | **276** |

검증 (50K 서브샘플, Best Match 기준):
- Exact Match: 28.66% → **29.68%** (+1.02%p)
- sim_total: 0.626 → **0.641** (+0.015)

---

## 3. 접근법 B: 유형별 θ 적용 (완료)

### 3.1 유형별 θ

Pooled θ × (유형별 가중치 / Pooled 가중치)

| 유형 | walkReluctance | transferCostSec |
|------|----------------|-----------------|
| GENERAL | 4.07 | 202 |
| CHILDREN | 2.97 | 145 |
| YOUTH | 2.71 | 139 |
| ELDERLY | 1.75 | 109 |
| DISABLED | 7.28 | 358 |

### 3.2 결과

| 방법 | Exact Match (Best Match 기준) |
|------|------|
| Baseline | 28.66% |
| A. Pooled θ | 29.68% (+1.0%p) |
| **B. 유형별 θ** | **33.0%** (+4.3%p) |

---

## 4. 평가 지표의 진화: Best Match → OTP 1순위 → 확률적 F₁ → MNL 재순위

### 4.1 3단계 발전

| 단계 | 평가 방식 | 목적함수 특성 | 한계 |
|------|-----------|--------------|------|
| 1단계 | Best Match (sim max) | 파라미터 변화에 둔감 | 보정 효과 희석 |
| 2단계 | OTP 1순위 (cost min) | 계단형 (0 or 1) | 최적화 불가 |
| 3단계 | MNL 확률 가중 (F₁) | 연속, 매끄러움 | θ 경계 수렴 |
| **4단계** | **MNL 재순위** | **β 기반 직접 순위** | **핵심 기여** |

### 4.2 OTP 1순위 vs MNL 1순위 (전체 데이터)

| 순위 방식 | Exact Match | sim_total |
|-----------|-------------|-----------|
| OTP 1순위 | 20.34% | 0.5372 |
| **MNL 1순위** | **22.23%** | **0.5713** |
| Best Match (상한) | 28.62% | 0.6260 |

→ MNL β가 OTP generalized_cost보다 행태를 더 정확히 반영

---

## 5. 접근법 E: 확률 기반 LHS + RSM 최적화 (완료)

### 5.1 수학적 프레임워크

```
F₁(θ) = Σᵢ wᵢ^IPW × Σⱼ P(j|i,θ) × sim(i,j) / Σᵢ wᵢ^IPW

P(j|i,θ) = exp(V_ij) / Σ_{k∈C_i(θ)} exp(V_ik)
V_ij = β_ride × T_ride + β_walk × T_walk + β_transfer × N_transfer + β_subway × D_subway
```

### 5.2 GENERAL 결과

| 항목 | 값 |
|------|-----|
| LHS 포인트 | 22개 |
| 총 평가 | 28회 |
| RSM R² | **0.9802** |
| 소요 시간 | 125.7분 |

**최적 θ (경계 수렴)**:
| 파라미터 | 범위 | 최적값 |
|----------|------|--------|
| walkReluctance | [2.0, 40.0] | **40.0** (상한) |
| transferCostSeconds | [15, 500] | **17** (하한 근처) |
| subwayReluctance | [0.2, 3.0] | **3.0** (상한) |

**성과 분석**:
| 지표 | Baseline | 접근법 E | 변화 |
|------|----------|----------|------|
| det_exact (OTP 1순위) | 19.84% | 20.79% | **+0.95%p** |
| mnl_exact (MNL 1순위) | 21.84% | **30.66%** | **+8.82%p** |

→ det_exact(+0.95%p)과 mnl_exact(+8.82%p)의 극적 괴리 = F₁ 개선의 대부분이 **MNL 재순위 효과**

### 5.3 구조적 한계

F₁ 목적함수가 경계로 수렴하는 이유:
1. 극단적 θ → 다양한 Choice Set → MNL 재순위 여지 ↑ → F₁ ↑
2. θ 자체의 개선이 아닌 MNL "재료" 풍부화 효과
3. 범위를 합리적으로 제한해도 동일 현상 반복 (v1, v2 모두)

→ **θ 최적화의 상한은 ~+1%p** (det_exact 기준)

---

## 6. MNL 재순위 분석 (핵심 기여)

### 6.1 방법

기존 Phase 2 OTP 대안에 MNL β를 적용하여 재순위. OTP 재실행 불필요.

### 6.2 핵심 결과

- **전체**: OTP 20.34% → MNL 22.23% (+1.89%p)
- **불일치 시 MNL:OTP 승률 = 10.4:1** (Exact Match 기준)
- **대안 많을수록 MNL 개선폭 증가**: 1개 0%p → 5개+ **+3.17%p** (단조 증가)
- **시간대 무관**: 피크 +1.84%p, 비피크 +1.91%p (안정적)

### 6.3 선택 경로 특성: MNL은 보행↓ 환승↓ 지하철↑

| 특성 | OTP 1순위 | MNL 1순위 | 차이 |
|------|-----------|-----------|------|
| 보행시간 | 3.2분 | 2.6분 | -0.5분 |
| 환승 횟수 | 0.50 | 0.40 | -0.10 |
| 지하철 비율 | 61.5% | 63.5% | +2.0%p |
| 차내시간 | 18.8분 | 19.9분 | +1.1분 |

→ Phase 3 β 계수와 완벽히 일관된 경로 프로파일

상세 결과: `results/PHASE4_RESULTS.md` Section 7

---

## 7. 코드 구조

| 파일 | 역할 | 상태 |
|------|------|------|
| `scripts/calibration/fixed_choice_calibration.py` | β→θ 매핑 + MSA 수렴 (접근법 A) | ✅ 완료 |
| `scripts/calibration/usertype_calibration.py` | 유형별 θ 적용 (접근법 B) | ✅ 완료 |
| `scripts/calibration/probabilistic_rsm_calibration.py` | 확률적 RSM + IPW (접근법 E) | ✅ 완료 |
| `scripts/calibration/mnl_reranking_analysis.py` | **MNL 재순위 상세 분석** | ✅ 완료 |
| `scripts/calibration/test_mnl_probability_ranking.py` | MNL 순위 사전 검증 | ✅ 완료 |
| `scripts/calibration/full_baseline_analysis.py` | 전체 데이터 베이스라인 분석 | ✅ 완료 |

---

## 8. 완료된 작업

- [x] 전통적 반복 보정 실패 확인
- [x] 접근법 A: Choice Set 고정 보정 (+1.02%p)
- [x] 접근법 B: 유형별 θ 적용 (+4.3%p)
- [x] 평가 지표 수정 (Best Match → OTP 1순위 → 확률적 F₁)
- [x] 전체 데이터 베이스라인 산출 (OTP 1순위 기준)
- [x] MNL 순위 사전 검증 (MNL > OTP, +1.89%p)
- [x] 접근법 E-IPW v2 (GENERAL 완료, 경계 수렴 확인)
- [x] **MNL 재순위 상세 분석** (유형별·환승별·시간대별·대안수별·일치도·확률분포·경로특성)

---

## 9. 참고 문헌

- McFadden, D. (1974). Conditional logit analysis of qualitative choice behavior.
- Ben-Akiva, M., & Lerman, S. R. (1985). *Discrete Choice Analysis*.
- Sheffi, Y. (1985). *Urban Transportation Networks*.
- Prato, C. G. (2009). Route choice modeling: past, present and future research directions.
- Frejinger, E., Bierlaire, M., & Ben-Akiva, M. (2009). Sampling of alternatives for route choice modeling.
- Cascetta, E. (2009). Transportation Systems Analysis (Ch. 10: Assignment-Consistent Models).
- Train, K. (2009). Discrete Choice Methods with Simulation (Ch. 3: Logit).

---

*최종 수정: 2026-02-11 — Phase 4 완료 (접근법 E 구조적 한계 확인, MNL 재순위 핵심 기여)*
