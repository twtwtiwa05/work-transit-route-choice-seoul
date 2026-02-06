# Phase 2: OTP 경로 매칭 및 유사도 분석 결과

## 연구 개요

본 문서는 TCD(교통카드 데이터) 관측 경로와 OTP(OpenTripPlanner) RAPTOR 알고리즘이 생성한 대안 경로 간의 유사도 분석 결과를 정리한다.

- **분석 대상**: 서울 수도권 대중교통 이용자
- **분석 기간**: 2025년 2월 20일 (평일 1일)
- **데이터 규모**: 1,320,030개 통행 체인, 4,936,864개 체인-대안 쌍

---

## 1. 데이터 구조

### 1.1 입력 데이터

| 파일 | 설명 | 규모 |
|------|------|------|
| `trip_attributes_matched.parquet` | TCD 관측 경로 (필터링됨) | 1,320,030 체인 |
| `otp_alternatives.parquet` | OTP 대안 경로 | 4,477,498 경로 |
| `tcd_leg_traversed_stops.parquet` | TCD 경유 정류장 (버스) | 1,179,285 레그 |
| `gtfs_tcd_stop_mapping.parquet` | 정류장 ID 매핑 | 46,859 매핑 |
| `gtfs_tcd_route_mapping.parquet` | 버스 노선 ID 매핑 | 2,058 매핑 |
| `subway_line_mapping.json` | 지하철 노선 ID 매핑 | 39 매핑 |

### 1.2 체인 구성

| 유형 | 체인 수 | 비율 |
|------|---------|------|
| 버스만 | 445,554 | 33.8% |
| 지하철만 | 720,692 | 54.6% |
| 버스+지하철 | 153,784 | 11.7% |
| **합계** | **1,320,030** | **100%** |

### 1.3 OTP 대안 통계

- 체인당 평균 대안 수: **3.74개**
- OTP Pareto-optimal 경로: 최대 10개/OD

---

## 2. 유사도 지표 체계

### 2.1 4-Level 계층적 유사도 프레임워크

본 연구는 단일 지표의 한계를 극복하기 위해 4개 레벨, 10개 세부 지표로 구성된 다층적 유사도 체계를 설계하였다.

```
Level 1: Exact Match (완전 일치)
    └── exact_match: 노선+수단+승하차 완전 일치 여부

Level 2: Structural Similarity (구조적 유사도)
    ├── sim_route_seq: 노선 시퀀스 LCS 유사도
    ├── sim_mode_seq: 수단 시퀀스 LCS 유사도
    └── transfer_match: 환승 횟수 일치 여부

Level 3: Stop-based Similarity (정류장 기반 유사도)
    ├── sim_jaccard_ba: 승하차 정류장 Jaccard Index
    ├── sim_jaccard_full: 경유 정류장 Jaccard Index
    ├── sim_lcs: 정류장 시퀀스 LCS 유사도
    └── sim_boarding_alighting: 승하차점 일치율

Level 4: Temporal Similarity (시간적 유사도)
    └── sim_time: 소요시간 유사도
```

### 2.2 지표별 계산 공식

#### Level 1: Exact Match

```
exact_match = 1  if (routes_match ∧ modes_match ∧ boarding_match ∧ alighting_match)
              0  otherwise
```

- `routes_match`: TCD 노선 시퀀스 = OTP 노선 시퀀스
- `modes_match`: TCD 수단 시퀀스 = OTP 수단 시퀀스
- `boarding_match`: TCD 승차 정류장 = OTP 승차 정류장
- `alighting_match`: TCD 하차 정류장 = OTP 하차 정류장

#### Level 2: Structural Similarity

**sim_route_seq (노선 시퀀스 유사도)**
```
sim_route_seq = 2 × LCS(R_tcd, R_otp) / (|R_tcd| + |R_otp|)
```
- LCS: Longest Common Subsequence (최장 공통 부분수열)
- R: 노선 ID 시퀀스

**sim_mode_seq (수단 시퀀스 유사도)**
```
sim_mode_seq = 2 × LCS(M_tcd, M_otp) / (|M_tcd| + |M_otp|)
```
- M: 수단 시퀀스 (BUS, SUBWAY)

**transfer_match (환승 횟수 일치)**
```
transfer_match = 1  if n_transfers_tcd = n_transfers_otp
                 0  otherwise
```

#### Level 3: Stop-based Similarity

**sim_jaccard_full (경유 정류장 Jaccard Index)**
```
sim_jaccard_full = |S_tcd ∩ S_otp| / |S_tcd ∪ S_otp|
```
- S: 경유 정류장 집합
- 버스: 전체 경유 정류장 사용
- 지하철: 승하차 정류장만 사용 (TCD 제한)

**sim_lcs (정류장 시퀀스 LCS 유사도)**
```
sim_lcs = 2 × LCS(S_tcd, S_otp) / (|S_tcd| + |S_otp|)
```
- 순서를 고려한 시퀀스 유사도
- 버스: 경유 정류장 시퀀스
- 지하철: 승하차 정류장 시퀀스

**sim_boarding_alighting (승하차점 일치율)**
```
sim_boarding_alighting = (Σ boarding_match + Σ alighting_match) / (2 × n_legs)
```

#### Level 4: Temporal Similarity

**sim_time (시간 유사도)**
```
time_diff = |T_tcd - T_otp|
baseline = max(T_tcd, T_otp)
sim_time = 1 - min(1, time_diff / baseline)
```

### 2.3 종합 유사도 (sim_total)

```
sim_total = 0.25 × sim_route_seq
          + 0.10 × sim_mode_seq
          + 0.20 × sim_jaccard_full
          + 0.25 × sim_lcs
          + 0.10 × sim_boarding_alighting
          + 0.10 × sim_time
```

**가중치 설계 근거:**

| 지표 | 가중치 | 근거 |
|------|--------|------|
| sim_route_seq | 0.25 | 경로 선택의 핵심 요소 (어떤 노선을 선택했는가) |
| sim_lcs | 0.25 | 경로 순서의 일치성 (경유지 순서 중요) |
| sim_jaccard_full | 0.20 | 공간적 중첩도 (어떤 정류장을 지나는가) |
| sim_mode_seq | 0.10 | 수단 구성 (버스/지하철 조합) |
| sim_boarding_alighting | 0.10 | 승하차 지점 일치 |
| sim_time | 0.10 | 시간 효율성 유사도 |

---

## 3. 분석 결과

### 3.1 전체 쌍 (All Pairs) vs 최선 매칭 (Best Match) 비교

분석은 두 가지 관점에서 수행하였다:
- **All Pairs**: 모든 TCD 체인과 OTP 대안 조합 (4,936,864쌍)
- **Best Match**: 각 TCD 체인에서 가장 유사한 OTP 대안 1개 (1,320,030쌍)

### 3.2 Level별 상세 결과

#### Level 1: Exact Match

| 구분 | All Pairs | Best Match |
|------|-----------|------------|
| 완전 일치 수 | 382,583 | 378,266 |
| 완전 일치율 | 7.75% | **28.66%** |

**환승 횟수별 Exact Match율 (Best Match):**

| 환승 횟수 | 체인 수 | Exact Match | 일치율 |
|-----------|---------|-------------|--------|
| 0회 (직통) | 792,878 | 361,531 | **45.60%** |
| 1회 | 444,614 | 16,576 | 3.73% |
| 2회 | 76,414 | 158 | 0.21% |
| 3회 | 5,859 | 1 | 0.02% |

→ 직통 경로의 경우 45.6%가 OTP 대안과 완전 일치하며, 환승이 증가할수록 일치율이 급감함.

#### Level 2: Structural Similarity

| 지표 | All Pairs ||| Best Match |||
|------|-----------|---------|---------|------------|---------|---------|
| | 평균 | 중앙값 | 표준편차 | 평균 | 중앙값 | 표준편차 |
| sim_route_seq | 0.1914 | 0.0000 | 0.3410 | **0.5095** | 0.6667 | 0.4472 |
| sim_mode_seq | 0.7103 | 0.6667 | 0.3281 | **0.8892** | 1.0000 | 0.1794 |
| transfer_match | 0.5567 | 1.0000 | 0.4968 | **0.7040** | 1.0000 | 0.4565 |

**해석:**
- `sim_route_seq`: All Pairs 평균 0.19 → Best Match 평균 0.51로 상승
- `sim_mode_seq`: Best Match에서 88.9%가 수단 구성 일치
- `transfer_match`: Best Match에서 70.4%가 환승 횟수 일치

#### Level 3: Stop-based Similarity

| 지표 | All Pairs ||| Best Match |||
|------|-----------|---------|---------|------------|---------|---------|
| | 평균 | 중앙값 | 표준편차 | 평균 | 중앙값 | 표준편차 |
| sim_jaccard_ba | 0.3769 | 0.2500 | 0.3614 | **0.6509** | 0.6000 | 0.3460 |
| sim_jaccard_full | 0.3489 | 0.2000 | 0.3522 | **0.5438** | 0.5000 | 0.3513 |
| sim_lcs | 0.4208 | 0.3333 | 0.3586 | **0.6276** | 0.6667 | 0.3279 |
| sim_boarding_alighting | 0.3580 | 0.2500 | 0.3741 | **0.6340** | 0.5000 | 0.3697 |

**해석:**
- `sim_jaccard_full`: 경유 정류장의 54.4%가 공통
- `sim_lcs`: 정류장 시퀀스 순서 유사도 62.8%
- `sim_boarding_alighting`: 승하차 정류장 63.4% 일치

#### Level 4: Temporal Similarity

| 지표 | All Pairs ||| Best Match |||
|------|-----------|---------|---------|------------|---------|---------|
| | 평균 | 중앙값 | 표준편차 | 평균 | 중앙값 | 표준편차 |
| sim_time | 0.7834 | 0.8261 | 0.1768 | **0.8044** | 0.8431 | 0.1601 |

**해석:**
- OTP 예측 소요시간과 TCD 실제 소요시간의 유사도가 평균 80.4%
- 중앙값 84.3%로 대부분의 경로에서 시간 예측이 정확함

### 3.3 종합 유사도 (sim_total)

| 구분 | All Pairs | Best Match |
|------|-----------|------------|
| 평균 | 0.4080 | **0.6258** |
| 중앙값 | 0.3493 | **0.6198** |
| 표준편차 | 0.2573 | 0.2571 |
| 최솟값 | 0.0000 | 0.0000 |
| 최댓값 | 1.0000 | 1.0000 |

### 3.4 Best Match 유사도 분포

| 구간 | 체인 수 | 비율 | 누적 비율 |
|------|---------|------|-----------|
| 95-100% | 225,434 | 17.08% | 17.08% |
| 90-95% | 80,105 | 6.07% | 23.15% |
| 80-90% | 114,505 | 8.67% | 31.82% |
| 70-80% | 140,769 | 10.66% | 42.48% |
| 60-70% | 154,619 | 11.71% | 54.19% |
| 50-60% | 67,017 | 5.08% | 59.27% |
| 30-50% | 390,973 | 29.62% | 88.89% |
| 0-30% | 146,608 | 11.11% | 100.00% |

**주요 발견:**
- **42.5%** 체인이 70% 이상 유사도를 보임
- **23.2%** 체인이 90% 이상 유사도를 보임 (거의 동일 경로)
- **17.1%** 체인이 95% 이상 유사도 (완전 일치에 가까움)

---

## 4. 버스 vs 지하철 특성 비교

### 4.1 데이터 가용성 차이

| 구분 | 버스 | 지하철 |
|------|------|--------|
| 노선 ID | O | O |
| 승차 정류장 | O | O |
| 하차 정류장 | O | O |
| 경유 정류장 시퀀스 | **O (66.1%)** | **X** |

### 4.2 지표 적용 차이

| 지표 | 버스 | 지하철 |
|------|------|--------|
| sim_jaccard_full | 경유 정류장 전체 | 승하차만 (fallback) |
| sim_lcs | 경유 정류장 시퀀스 | 승하차만 (fallback) |
| sim_route_seq | 노선 ID 비교 | 노선 ID 비교 |
| sim_boarding_alighting | 승하차 정류장 비교 | 승하차역 비교 |

### 4.3 지하철 노선 매핑

TCD 지하철 노선 ID를 GTFS 노선 ID로 매핑:

| TCD ID | 노선명 | GTFS ID |
|--------|--------|---------|
| 001 | 1호선 | RR_ACC1_S-1-01-1D |
| 002 | 2호선 | RR_ACC1_S-1-02-1I |
| 003 | 3호선 | RR_ACC1_S-1-03-1D |
| ... | ... | ... |
| 401 | 9호선 | RR_ACC1_S-1-09-1D |
| 403 | 신분당선 | RR_ACC1_S-1-SB-1D |

총 39개 지하철/경전철 노선 매핑 완료.

---

## 5. ID 매핑 처리

### 5.1 정류장 ID 체계 문제

GTFS 정류장 ID에 지역 코드 prefix가 다르게 부여되는 문제 발견:
- TCD 매핑: `BS_1100_116000008`
- OTP 사용: `BS_3100_116000008`

**해결책:** 정류장 고유 코드(뒤 9자리)만 추출하여 비교
```python
def extract_stop_code(gtfs_id):
    # "1:BS_3100_116000008" → "116000008"
    parts = gtfs_id.split('_')
    return parts[2] if len(parts) >= 3 else gtfs_id
```

### 5.2 최종 매핑 성공률

| 항목 | 매핑 수 | 성공률 |
|------|---------|--------|
| 정류장 | 46,859 | 97.1% (Phase 1) |
| 버스 노선 | 2,058 | 85.3% (Phase 1) |
| 지하철 노선 | 39 | 100% |
| **총 노선** | **2,097** | - |
| Step 5 매핑 | 4,936,864쌍 | **100%** |

---

## 6. 결론 및 시사점

### 6.1 주요 발견

1. **Exact Match율 28.66%**: 약 3분의 1 통행이 OTP 추천 경로와 완전 일치
2. **직통 경로 일치율 45.6%**: 환승 없는 경로는 알고리즘 예측력이 높음
3. **환승 경로 일치율 급감**: 1회 환승 3.7%, 2회 이상 0.2% 미만
4. **평균 유사도 62.6%**: Best Match 기준 합리적인 유사도 달성

### 6.2 기존 연구와 비교

| 연구 | 일치율 | 조건 |
|------|--------|------|
| 서울 선행연구 | 84% | 환승 0회 |
| 서울 선행연구 | 88% | 환승 1회 |
| 개선된 RAPTOR (K=1) | 58.8% | 페널티 적용 |
| 개선된 RAPTOR (K=5) | 91.4% | 페널티 적용 |
| **본 연구 (K=10)** | **28.66%** | Exact Match |
| **본 연구 (K=10)** | **42.5%** | sim_total ≥ 0.7 |

### 6.3 한계점

1. **지하철 경유역 정보 부재**: TCD 제한으로 지하철 중간역 비교 불가
2. **시간대별 분석 미수행**: 첨두/비첨두 구분 없이 전체 분석
3. **OTP 파라미터 고정**: 환승 페널티 등 보정 전 결과

### 6.4 향후 연구

1. **Phase 3**: 환승 페널티 보정을 통한 OTP 알고리즘 개선
2. **Phase 4**: Mixed Logit 모델을 통한 경로 선택 모형 추정
3. **반복 보정**: 추정된 파라미터로 OTP 재실행 → 유사도 향상 확인

---

## 7. 산출물

| 파일 | 설명 | 크기 |
|------|------|------|
| `similarity_results.parquet` | 전체 쌍 유사도 결과 | 124.1 MB |
| `similarity_summary.parquet` | 체인별 최선 매칭 요약 | 21.3 MB |

### 7.1 similarity_results.parquet 스키마

| 컬럼 | 타입 | 설명 |
|------|------|------|
| chain_id | int32 | TCD 체인 식별자 |
| od_id | int32 | OD 쌍 식별자 |
| alt_id | int8 | OTP 대안 번호 (0-9) |
| exact_match | int8 | Level 1: 완전 일치 |
| sim_route_seq | float32 | Level 2: 노선 시퀀스 |
| sim_mode_seq | float32 | Level 2: 수단 시퀀스 |
| transfer_match | int8 | Level 2: 환승 일치 |
| transfer_diff | int8 | 환승 횟수 차이 |
| sim_jaccard_ba | float32 | Level 3: 승하차 Jaccard |
| sim_jaccard_full | float32 | Level 3: 경유 Jaccard |
| sim_lcs | float32 | Level 3: 시퀀스 LCS |
| sim_boarding_alighting | float32 | Level 3: 승하차점 일치율 |
| sim_time | float32 | Level 4: 시간 유사도 |
| time_diff_sec | int32 | 시간 차이 (초) |
| sim_total | float32 | 종합 유사도 |
| otp_duration | int32 | OTP 예측 소요시간 |
| otp_n_transfers | int8 | OTP 환승 횟수 |
| otp_generalized_cost | int32 | OTP 일반화비용 |

---

## 부록: 실행 스크립트

```bash
# Step 5 실행
cd main
python scripts/matching/step5_calculate_similarity.py
```

**실행 환경:**
- Python 3.11
- pandas, numpy, tqdm
- 실행 시간: 약 30-40분 (1.32M 체인)

---

*문서 작성일: 2026-02-07*
*Phase 2 Step 5 완료*
