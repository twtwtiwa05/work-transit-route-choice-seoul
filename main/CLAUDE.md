# CLAUDE.md

Claude Code 작업 가이드 - 대중교통 경로선택 모형 연구

## Project Overview

**프로젝트명**: Transit Route Choice Modeling with Smart Card Data
**목표 학회**: ITS World Congress 2026 (강릉)
**연구 범위**: 서울시 대중교통 (버스 + 지하철)

### 연구 목적

교통카드(TCD) 빅데이터와 OTP 경로탐색을 결합하여 대중교통 경로선택 행태를 분석하고, 기존 연구의 한계를 극복한 Mixed Logit 모형을 추정한다.

---

## 현재 상태 (빠른 파악용)

```
Phase 1: 데이터 전처리     ✅ 완료
Phase 2: OTP 매칭 + 유사도  ✅ 완료
Phase 3: 모형 추정         ✅ 완료 (MNL → ML → LC → LightGBM → 비교분석)
Phase 4: 반복 보정         ✅ 완료 (θ 최적화 한계 실증 + MNL 재순위)
```

### 모든 Phase 완료 — 논문 작성 단계

**Phase 4 핵심 결론**:
- θ 최적화(OTP 파라미터 보정)의 개선 상한: ~+1%p
- MNL 재순위(β로 대안 재순위): +1.89%p (OTP 재실행 불필요)
- 불일치 시 MNL:OTP 승률 = 10.4:1

다음 단계:
- 최종 논문 작성

---

## Phase 3 모형 추정 상세

### 진행 현황

| Step | 내용 | 상태 | 산출물 |
|------|------|------|--------|
| 1 | Choice Set 생성 | ✅ | `choice_set.parquet` |
| 2 | 대안 속성 추출 | ✅ | `alternative_attributes.parquet` |
| 3 | 모델 입력 준비 | ✅ | `model_input_train/test.parquet` |
| 4 | MNL 추정 | ✅ | `results/mnl_results.json` |
| 5 | Mixed Logit | ✅ | `results/mixed_logit_results.json` |
| 6 | Latent Class (K=3) | ✅ | `results/latent_class_results.json` |
| 7 | LightGBM Benchmark | ✅ | `results/lightgbm_results.json` |
| 8 | 통합 모형 비교 | ✅ | `results/PHASE3_RESULTS5_COMPARISON.md` |

### 효용함수 (Utility Function)

```
V_j = β_ride × T_ride_j
    + β_walk × T_walk_j
    + β_transfer × N_transfer_j
    + β_subway × D_subway_j
    + β_peak_ride × (D_peak × T_ride_j)
    + β_peak_transfer × (D_peak × N_transfer_j)
```

| 변수 | 설명 | 단위 |
|------|------|------|
| T_ride | 차내시간 | 분 |
| T_walk | 보행시간 (접근+환승+이탈) | 분 |
| N_transfer | 환승횟수 | 회 |
| D_subway | 지하철 포함 더미 | 0/1 |
| D_peak | 출발시간 피크 더미 (7-9시, 18-20시) | 0/1 |

**주의**: T_wait(대기시간)은 T_ride와 다중공선성 문제로 제외됨

### MNL 추정 결과 요약 (Step 4 완료)

| 지표 | Pooled | Elderly | Disabled |
|------|--------|---------|----------|
| ρ² (rho-squared) | 0.469 | 0.582 | 0.515 |
| Hit Rate (테스트셋) | 66.0% | — | — |
| Hit Rate (학습셋) | 62.9% | 78.5% | 73.0% |
| 보행 가중치 (T_walk/T_ride) | 22.7× | 7.3× | 30.2× |

**상세 결과**: `results/PHASE3_RESULTS1_MNL.md`

### Mixed Logit 추정 결과 (Step 5 완료)

| 파라미터 | 평균(μ) | 표준편차(σ) | 해석 |
|----------|---------|-------------|------|
| T_walk | -0.860*** | 0.194*** | 보행 가중치 14×~36× |
| N_transfer | -3.614*** | 0.777*** | 환승 페널티 61~150분 |
| D_subway | 2.585*** | 0.483*** | 지하철 선호 개인차 |

- ρ² = 0.4636, Hit Rate (테스트셋) = 65.9%, Hit Rate (샘플) = 62.3%
- **모든 σ 유의** → 이용자 간 선호 이질성 확인됨
- Peak 상호작용 효과 비유의 (개인 이질성에 흡수됨)

**상세 결과**: `results/PHASE3_RESULTS2_MIXED_LOGIT.md`

### Latent Class 추정 결과 (Step 6 완료)

| 클래스 | 비율 | 특성 | 핵심 파라미터 |
|--------|------|------|-------------|
| Class 1 (접근성) | 8.7% | 고령자 61%, 환승 극기피 | β_ride=+0.25, β_transfer=-10.0, β_subway=+8.12 |
| Class 2 (일반) | 77.2% | 합리적 트레이드오프 | β_ride=-0.077, β_walk=-0.730, β_transfer=-3.27 |
| Class 3 (극단) | 14.0% | 지하철 충성, 극단값 | 모든 β 경계값 |

- ρ² = 0.474, Hit Rate (테스트셋) = 67.4%, χ²(교차분석) = 46,861***
- Concomitant variables: D_elderly → Class 1 오즈비 22배
- **상세 결과**: `results/PHASE3_RESULTS3_LC.md`

### LightGBM Benchmark 결과 (Step 7 완료)

| 모형 | Hit Rate | 비고 |
|------|----------|------|
| LightGBM Core (4변수) | 65.75% | MNL과 동일 변수 |
| LightGBM Full (7변수) | 66.22% | context 변수 추가 |

- **LC(67.4%) > LightGBM(66.2%)**: 경제학 모형이 ML 상한 +1.2%p 초과
- MNL / LightGBM = 99.7%: 6개 파라미터 선형모형이 상한의 99.7% 달성
- SHAP 순위 = MNL β 순위 (완벽 일치) → 효용함수 사양 타당성 확인
- D_peak SHAP ≈ 0 → 네 모형 일관 비유의
- **상세 결과**: `results/PHASE3_RESULTS4_LIGHTGBM.md`

### Mixed Logit 설정 (참고)

```python
RANDOM_VARS = ['T_walk', 'N_transfer', 'D_subway']  # Normal distribution
FIXED_VARS = ['T_ride', 'Peak_T_ride', 'Peak_N_transfer']
N_DRAWS = 500  # Halton sequence
SAMPLE_SIZE = 30000  # Stratified by user_type
```

---

## 데이터 파일

### GitHub에 포함된 파일 (다른 컴퓨터에서 이어서 작업 가능)

| 파일 | 크기 | 용도 |
|------|------|------|
| `output/model_input_train.parquet` | 26MB | 학습 데이터 (329K 체인) |
| `output/model_input_test.parquet` | 6.6MB | 테스트 데이터 (82K 체인) |
| `results/mnl_results.json` | - | MNL 추정 결과 |
| `scripts/models/*.py` | - | 모델 추정 스크립트 |

### model_input 스키마

```
chain_id      : 체인 고유 ID
alt_idx       : 대안 인덱스 (0=관측, 1~N=OTP 생성)
chosen        : 선택 여부 (1=관측 경로, 0=비선택)
T_ride        : 차내시간 (분)
T_walk        : 보행시간 (분)
N_transfer    : 환승횟수
D_subway      : 지하철 포함 여부
D_peak        : 피크시간 출발 여부
user_type     : 이용자 유형 (general/elderly/disabled)
```

---

## 디렉토리 구조

```
main/
├── CLAUDE.md                ← 이 파일 (작업 가이드)
├── README.md                ← 프로젝트 개요
├── .gitignore               ← 대용량 파일 제외
│
├── scripts/
│   ├── data/                ← Phase 1 전처리
│   ├── matching/            ← Phase 2 OTP 매칭
│   ├── models/              ← Phase 3 모형 추정
│   │   ├── step1_build_choice_set.py       ✅
│   │   ├── step2_extract_attributes.py     ✅
│   │   ├── step3_prepare_model_input.py    ✅
│   │   ├── step4_estimate_mnl.py           ✅
│   │   ├── step5_estimate_mixed_logit.py   ✅
│   │   ├── step6_estimate_latent_class.py  ✅
│   │   ├── step7_lightgbm_benchmark.py     ✅
│   │   └── step8_model_comparison.py       ✅
│   └── calibration/         ← Phase 4 반복 보정
│       ├── fixed_choice_calibration.py     ✅ 접근법 A
│       ├── usertype_calibration.py         ✅ 접근법 B
│       ├── probabilistic_rsm_calibration.py ✅ 접근법 E
│       └── mnl_reranking_analysis.py       ✅ MNL 재순위 (핵심)
│
├── output/
│   ├── model_input_train.parquet  ✅ GitHub 포함
│   ├── model_input_test.parquet   ✅ GitHub 포함
│   └── (기타 대용량 파일은 .gitignore로 제외)
│
├── results/
│   ├── mnl_results.json           ✅ MNL 추정 결과
│   ├── mixed_logit_results.json   ✅ Mixed Logit 결과
│   ├── latent_class_results.json  ✅ Latent Class 결과
│   ├── lightgbm_results.json      ✅ LightGBM 결과
│   ├── PHASE3_RESULTS1_MNL.md     ✅ MNL 결과 문서
│   ├── PHASE3_RESULTS2_MIXED_LOGIT.md  ✅ ML 결과 문서
│   ├── PHASE3_RESULTS3_LC.md      ✅ LC 결과 문서
│   ├── PHASE3_RESULTS4_LIGHTGBM.md ✅ LightGBM 결과 문서
│   ├── PHASE3_RESULTS5_COMPARISON.md ✅ 통합 비교 분석
│   ├── PHASE4_RESULTS.md          ✅ 반복 보정 + MNL 재순위 결과
│   ├── mnl_reranking_analysis.json ✅ MNL 재순위 상세 데이터
│   ├── probabilistic_rsm_log.json ✅ RSM 최적화 로그
│   └── figures/                   ✅ SHAP, 비교 차트
│
└── docs/
    ├── PHASE3_MODEL_ESTIMATION_PLAN.md  ← 모형 추정 계획
    ├── PHASE4_ITERATIVE_CALIBRATION_PLAN.md ← 반복 보정 계획
    ├── SIMILARITY_METRICS_FRAMEWORK.md
    └── ...
```

---

## 핵심 발견사항

### TCD 데이터

- **수단 구분**: `교통수단코드` 200~289 = SUBWAY, 그 외 = BUS
- **체인 구조**: 각 행 = 1 레그, `환승건수` = 누적값 (0이면 새 체인 시작)
- **ID 체계**: TCD ID (7~8자리) ≠ GTFS ID (9자리) → 좌표 기반 매칭

### 유사도 매칭 결과 (Phase 2)

- **분석 규모**: 1,320,030 체인
- **Exact Match**: 28.66% (경로 완전 일치)
- **sim_total ≥ 70%**: 42.5% 체인
- **sim_total ≥ 90%**: 23.1% 체인

### Peak × N_transfer 양의 계수

피크시간대 이용자가 오히려 환승을 더 많이 하는 이유:
- 피크시간 평균 환승: 0.206회
- 비피크 평균 환승: 0.155회
- 해석: 피크시간 배차간격이 짧아 환승 부담이 감소

---

## 빌드 및 실행

### Python 환경

```bash
pip install pandas pyarrow numpy scipy tqdm
```

### Step 5 Mixed Logit 실행

```bash
cd main
python scripts/models/step5_estimate_mixed_logit.py
```

**설정 변경** (step5_estimate_mixed_logit.py 내):
- `N_DRAWS = 500` - 시뮬레이션 draws 수
- `SAMPLE_SIZE = 30000` - 샘플링 체인 수

---

## 주요 참조 문서

| 파일 | 설명 |
|------|------|
| `docs/PHASE3_MODEL_ESTIMATION_PLAN.md` | Phase 3 상세 계획 |
| `docs/PHASE4_ITERATIVE_CALIBRATION_PLAN.md` | Phase 4 반복 보정 계획 |
| `results/PHASE3_RESULTS1_MNL.md` | MNL 결과 상세 |
| `results/PHASE3_RESULTS2_MIXED_LOGIT.md` | Mixed Logit 결과 상세 |
| `results/PHASE3_RESULTS3_LC.md` | Latent Class 결과 상세 |
| `results/PHASE3_RESULTS4_LIGHTGBM.md` | LightGBM 벤치마크 결과 |
| `results/PHASE3_RESULTS5_COMPARISON.md` | 통합 모형 비교 분석 |
| `results/PHASE4_RESULTS.md` | **Phase 4 반복 보정 + MNL 재순위 결과** |
| `docs/SIMILARITY_METRICS_FRAMEWORK.md` | 유사도 지표 정의 |

---

## 다음 단계

1. ~~**Phase 3**: 모형 추정~~ ✅ 완료 (MNL → ML → LC → LightGBM → 비교분석)
2. ~~**Phase 4**: 반복 보정~~ ✅ 완료 (θ 최적화 한계 + MNL 재순위)
3. **논문 작성**

### Phase 3 핵심 결과 요약

```
Hit Rate 순위 (테스트셋 82,351 체인):
  LC (K=3)         67.4%  ← 경제학 모형이 1위
  LightGBM Full    66.2%
  MNL (Pooled)     66.0%
  Mixed Logit      65.9%
  LightGBM Core    65.8%
```

### Phase 4 핵심 결과 요약

```
θ 최적화 (OTP 파라미터 보정):
  접근법 A (Pooled MSA):    +1.02%p (Best Match 기준)
  접근법 B (유형별 θ):      +4.3%p  (Best Match 기준)
  접근법 E (확률적 RSM):    +0.95%p (OTP 1순위 기준, 경계 수렴)

MNL 재순위 (핵심 기여):
  OTP 1순위 → MNL 1순위:   +1.89%p (OTP 재실행 불필요)
  불일치 시 MNL:OTP 승률:  10.4:1 (Exact Match)
  대안 5개+:              +3.17%p (최대 개선)
  MNL 선택 경로:          보행↓0.5분, 환승↓0.10, 지하철↑2.0%p
```

---

*최종 수정: 2026-02-11 (Phase 4 완료 — θ 최적화 한계 실증, MNL 재순위 핵심 기여)*
