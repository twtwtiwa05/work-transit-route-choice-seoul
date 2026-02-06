# 연구 재수행 종합 계획서
## Transit Route Choice with User-Type-Specific Probabilistic Assignment
### ITS World Congress 2026 (강릉, 2026.10.19-23)

**저자**: Tae Woo Kim, Minsu Kim, Jiho Yeo (가천대), Sungtaek Choi (한양대)
**기반 논문**: Kim_TransitRouteChoice_ITSWC2026.pdf
**작성일**: 2026-02-05

---

## 목차

1. [연구 배경 및 수정 동기](#1-연구-배경-및-수정-동기)
2. [수정사항 1: 경로 유사도 프레임워크](#2-수정사항-1-경로-유사도-프레임워크)
3. [수정사항 2: TCD 데이터 전처리](#3-수정사항-2-tcd-데이터-전처리)
4. [수정사항 3: 모델 개선 (Mixed Logit 중심)](#4-수정사항-3-모델-개선)
5. [수정사항 4: 반복 보정 프레임워크](#5-수정사항-4-반복-보정-프레임워크)
6. [전체 실행 파이프라인](#6-전체-실행-파이프라인)
7. [프로젝트 구조](#7-프로젝트-구조)
8. [검증 계획](#8-검증-계획)
9. [학술적 기여](#9-학술적-기여)
10. [일정 및 산출물](#10-일정-및-산출물)

---

## 1. 연구 배경 및 수정 동기

### 1.1 기존 논문 요약

기존 논문은 서울 교통카드(TCN) 빅데이터 187,010통행을 활용하여:
- MNL 모델로 5개 이용자 유형(일반/고령자/청소년/장애인/어린이)별 경로선택 파라미터 추정
- 보행시간 가중치 8.5배, 고령자 환승기피 47%, 지하철선호 90% 등 핵심 발견
- OTP와 통합된 확률적 경로배정 모듈 개발

### 1.2 수정이 필요한 4가지 사항

| # | 수정사항 | 기존 한계 | 개선 방향 |
|---|---------|----------|----------|
| 1 | **경로 유사도 지표** | 노선 ID 기반 Jaccard (302번≠303번) | 정류장 시퀀스 기반 비교 |
| 2 | **데이터** | TCN (지하철 환승 미기록) | TCD (환승 완전 기록) |
| 3 | **모델** | MNL (고정 파라미터) | Mixed Logit (랜덤 파라미터) + Latent Class + LightGBM |
| 4 | **새로운 섹션** | 1회 추정으로 종료 | 반복 보정으로 자기일관적 파라미터 수렴 |

---

## 2. 수정사항 1: 경로 유사도 프레임워크

### 2.1 문제 정의: "302번 vs 303번" 문제

현재 경로 유사도는 **노선 ID(route_id)**로 비교합니다:
```
실제 경로: [Bus 302] 강남역 → 양재역 → 수서역
OTP 추천:  [Bus 303] 강남역 → 양재역 → 수서역
Route Jaccard = |{302} ∩ {303}| / |{302} ∪ {303}| = 0/2 = 0.0  ← 문제!
```

302번과 303번은 같은 정류장을 경유하는데 유사도가 0입니다. 이는 **기능적으로 동일한 경로**를 "불일치"로 분류하는 근본적 오류입니다.

### 2.2 해결 원칙: 정류장 시퀀스 기반 비교

노선 ID 대신 **실제 경유 정류장의 순서**로 비교합니다:
```
실제 경로: [강남역 → 양재역 → 수서역]  (정류장 시퀀스)
OTP 추천:  [강남역 → 양재역 → 수서역]  (정류장 시퀀스)
Stop Jaccard = |{강남,양재,수서} ∩ {강남,양재,수서}| / |{강남,양재,수서} ∪ {강남,양재,수서}| = 3/3 = 1.0  ← 정확!
```

### 2.3 학술적 근거

정류장 시퀀스 기반 유사도는 다음 학술 전통에 기반합니다:

1. **집합론적 유사도** (Jaccard, 1912; Dice, 1945): 정보검색, 생물정보학에서 표준적으로 사용되는 집합 비교 지표
2. **시퀀스 정렬** (Needleman-Wunsch, 1970; Smith-Waterman, 1981): 생물정보학의 LCS(Longest Common Subsequence) 알고리즘을 교통 경로 비교에 적용
3. **Path Size Logit** (Ben-Akiva & Bierlaire, 1999; Frejinger & Bierlaire, 2007): 경로 중첩도(overlap)가 선택 모형에 미치는 영향 — 정류장 시퀀스 유사도는 PSL 보정 계수의 기반
4. **공간 유사도** (Fréchet, 1906; Hausdorff): 곡선 유사도 지표를 경로 비교에 적용

### 2.4 새로운 5개 유사도 지표

#### 지표 1: S_xfer (환승 구조 유사도)

**목적**: 두 통행의 환승 횟수가 유사한지 측정

**수학적 정의**:
```
S_xfer = 1 - |N_transfer_actual - N_transfer_otp| / max(N_transfer_actual, N_transfer_otp, 1)
```

**예시**:
- 실제 0환승, OTP 0환승: S_xfer = 1 - 0/1 = 1.0
- 실제 1환승, OTP 0환승: S_xfer = 1 - 1/1 = 0.0
- 실제 2환승, OTP 3환승: S_xfer = 1 - 1/3 = 0.667

**기존 Transfer Diff 대비 개선점**: 정수 → [0,1] 정규화, 다른 지표와 비교 가능

---

#### 지표 2: S_mode (수단 구조 유사도)

**목적**: 두 통행이 같은 교통수단 순서를 사용하는지 측정

**수단 대체 비용 행렬**:
```
         BUS    SUBWAY   RAIL
BUS      0.0    0.7      0.8
SUBWAY   0.7    0.0      0.3
RAIL     0.8    0.3      0.0
```

**수학적 정의** (가중 편집 거리):
```
S_mode = 1 - WeightedEditDistance(M_actual, M_otp) / max(|M_actual|, |M_otp|)
```

여기서 `M_actual = [BUS, SUBWAY]`, `M_otp = [SUBWAY]` 등 수단 시퀀스

**예시**:
- 실제 [BUS→SUBWAY], OTP [BUS→SUBWAY]: S_mode = 1.0
- 실제 [BUS], OTP [SUBWAY]: S_mode = 1 - 0.7/1 = 0.3
- 실제 [BUS→SUBWAY], OTP [SUBWAY]: S_mode = 1 - 1.0/2 = 0.5 (삽입 비용 1.0)

**기존 Modal Match 대비 개선점**: 이진(0/1) → 연속값 [0,1], 부분 유사성 포착

---

#### 지표 3: S_jaccard (정류장 집합 유사도) — **핵심 혁신**

**목적**: 두 통행이 같은 정류장들을 경유하는지 측정 (순서 무관)

**수학적 정의**:
```
S_jaccard = |Stops_actual ∩ Stops_otp| / |Stops_actual ∪ Stops_otp|
```

여기서 `Stops_actual`과 `Stops_otp`는 각 통행이 경유하는 **정류장 ID 집합**

**정류장 시퀀스 추출 방법**:
1. 교통카드 데이터에서 승차 정류장, 하차 정류장, 환승 정류장 식별
2. GTFS `stop_times.txt`에서 해당 노선의 전체 정류장 시퀀스 조회
3. 승차~하차 사이의 중간 정류장 추출

```
예: Bus 302 전체 시퀀스: [A, B, C, D, E, F, G, H, I, J]
    승차: C, 하차: G
    경유 정류장: {C, D, E, F, G}

    Bus 303 전체 시퀀스: [A, B, C, D, E, F, G, K, L]
    승차: C, 하차: G
    경유 정류장: {C, D, E, F, G}

    S_jaccard = |{C,D,E,F,G} ∩ {C,D,E,F,G}| / |{C,D,E,F,G} ∪ {C,D,E,F,G}| = 5/5 = 1.0
```

**이것이 302번 vs 303번 문제를 해결합니다.**

**다중 레그 통행 처리**:
다환승 통행의 경우 각 레그별 정류장을 합집합으로 결합:
```
Stops_actual = Stops_leg1 ∪ Stops_leg2 ∪ ... ∪ Stops_legK
```

---

#### 지표 4: S_lcs (정류장 순서 유사도)

**목적**: 두 통행의 정류장 방문 **순서**가 유사한지 측정

**수학적 정의** (Longest Common Subsequence):
```
S_lcs = |LCS(Seq_actual, Seq_otp)| / max(|Seq_actual|, |Seq_otp|)
```

**LCS 알고리즘** (동적 프로그래밍, O(n×m)):
```python
def lcs_length(seq_a, seq_b):
    n, m = len(seq_a), len(seq_b)
    dp = [[0] * (m+1) for _ in range(n+1)]
    for i in range(1, n+1):
        for j in range(1, m+1):
            if seq_a[i-1] == seq_b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[n][m]
```

**왜 S_jaccard와 별도로 필요한가?**:
```
경로 A: [강남 → 역삼 → 선릉 → 삼성]  (정방향)
경로 B: [삼성 → 선릉 → 역삼 → 강남]  (역방향)

S_jaccard = 4/4 = 1.0  (같은 정류장 집합)
S_lcs = 1/4 = 0.25     (공통 부분수열 길이 1)
```
순서가 다르면 유사도가 낮아야 합니다 — S_lcs가 이를 포착합니다.

**서울 버스 노선의 일반적 길이**: 20~60 정류장 → LCS 계산 O(60×60) = O(3,600), 매우 빠름

---

#### 지표 5: S_cost (비용 유사도)

**목적**: 두 통행의 통행시간이 유사한지 측정

**수학적 정의**:
```
S_cost = 1 - |T_actual - T_otp| / max(T_actual, T_otp)
```

**세부 분해** (선택적):
```
S_cost = w_ride × S_ride + w_walk × S_walk + w_wait × S_wait
S_ride = 1 - |T_ride_actual - T_ride_otp| / max(T_ride_actual, T_ride_otp)
S_walk = 1 - |T_walk_actual - T_walk_otp| / max(T_walk_actual, T_walk_otp)
```

**기존 Time Ratio 대비 개선점**: 비대칭(T_otp/T_actual) → 대칭, 유계 [0,1]

---

### 2.5 종합 유사도 (Composite Trip Similarity)

**가중 산술 평균**:
```
S_trip = 0.10 × S_xfer + 0.15 × S_mode + 0.30 × S_jaccard + 0.30 × S_lcs + 0.15 × S_cost
```

**가중치 설정 근거**:
- S_jaccard + S_lcs = 0.60 (전체의 60%): 정류장 수준 비교가 **핵심 혁신**이므로 가장 큰 비중
- S_mode = 0.15: 수단 구조도 중요하지만 부차적
- S_cost = 0.15: 시간 유사성은 보조 지표
- S_xfer = 0.10: 환승 구조는 S_mode와 부분 중복

### 2.6 매칭 분류 기준

| 범주 | 기준 | 해석 | 기존 대비 |
|------|------|------|----------|
| **Exact Match** | S_trip ≥ 0.85 | 사실상 동일한 경로 | 기존 Jaccard=1.0 대체 |
| **Partial Match** | 0.40 ≤ S_trip < 0.85 | 같은 회랑, 약간 다른 경로 | 기존에는 No Match 처리됨 |
| **No Match** | S_trip < 0.40 | 근본적으로 다른 경로 | |

**기대 효과**: Exact Match 비율 38% → 55%+ 개선 (302↔303 등 기능적 동등 경로 포함)

### 2.7 노선 동등성 인덱스 (Route Equivalence Index)

계산 효율화를 위해 노선 쌍 유사도를 **사전 계산**:

```python
# 모든 노선 쌍에 대해 정류장 집합 Jaccard 사전 계산
for route_i in all_routes:
    for route_j in routes_sharing_stops(route_i):  # 공통 정류장 있는 쌍만
        stops_i = get_stop_set(route_i)
        stops_j = get_stop_set(route_j)
        equiv_score = len(stops_i & stops_j) / len(stops_i | stops_j)
        if equiv_score >= 0.7:
            route_equiv_index[(route_i, route_j)] = equiv_score
```

이를 통해 "302번 ↔ 303번 = 0.92" 같은 사전 조회가 가능하여, 통행 수준 유사도 계산 속도 대폭 향상.

### 2.8 구현 파일

| 파일 | 역할 | 주요 함수 |
|------|------|----------|
| `scripts/similarity/stop_sequence_extractor.py` | GTFS에서 노선별 정류장 시퀀스 추출 | `extract_stop_sequences()`, `get_subsequence(route_id, board_stop, alight_stop)` |
| `scripts/similarity/route_similarity.py` | 5개 유사도 지표 계산 | `compute_s_xfer()`, `compute_s_mode()`, `compute_s_jaccard()`, `compute_s_lcs()`, `compute_s_cost()`, `compute_s_trip()` |
| `scripts/similarity/route_equivalence_index.py` | 노선 쌍 유사도 사전 계산 | `build_equivalence_index()`, `lookup_equivalence(route_a, route_b)` |

### 2.9 핵심 데이터 의존성

```
GTFS stop_times.txt (20,871,237 레코드)
    → trip_id, stop_id, stop_sequence, arrival_time, departure_time
    → trip_id를 통해 routes.txt와 조인 → route_id별 정류장 시퀀스

ROUTESTTN_20250220.parquet (257,579 레코드)
    → 노선코드, 정류장ID, 정류장명, X좌표, Y좌표, 순번, 누적거리
    → TCD 데이터의 운영사코드 기반 정류장 매핑

tcn_to_gtfs_route_mapping.csv (288,879 레코드)
    → tcn_route_id → gtfs_route_id 변환
    → 교통카드 노선코드를 GTFS 정류장 시퀀스로 연결하는 핵심 브릿지
```

---

## 3. 수정사항 2: TCD 데이터 전처리

### 3.1 TCN vs TCD 비교

| 항목 | TCN (기존) | TCD (개선) |
|------|-----------|-----------|
| 지하철 환승 기록 | **미기록** | **완전 기록** |
| 환승 정류장 | 미제공 | 환승역1, 환승역2 제공 |
| 환승 유형 | 미구분 | 0~5단계 구분 |
| 데이터 날짜 | 2024.11.14 (1일) | 2025.02.17~23 (7일) |
| 분석 대상 | 전체 | **2025.02.20 (목)** 선택 |

### 3.2 TCD 데이터 구조 (27개 컬럼)

**분석에 사용하는 핵심 컬럼**:

```
┌──────────────────────────────────────────────────────────────────┐
│ TCD_20250220.parquet (~20M 레코드, ~740MB)                        │
├──────────────────────────────────────────────────────────────────┤
│ 날짜             int64   분석일 (20250220)                         │
│ 운영사 ID        int64   수단 구분 (3=지하철, 8=버스, 11=기타)        │
│ 조회일번호        int64   동일 카드의 일일 통행 순번 (1~47)            │
│ 카드카드번호      object  스마트카드 고유번호 (~7.15M 고유값)          │
│ 승차ID(운영사코드) float64 출발 정류장 (null 47%)                    │
│ 하차ID(운영사코드) object  도착 정류장 (null 0%)                     │
│ 승차시간          float64 탑승 시간 (YYYYMMDDHHMISS)                │
│ 하차시간          int64   하차 시간 (YYYYMMDDHHMISS)                │
│ 환승역1ID(운영사코드) int64 환승 정류장 1                             │
│ 환승역2ID(운영사코드) float64 환승 정류장 2 (null 1%)                 │
│ 환승구분          int64   환승 횟수 (0=무환승, 1~5=환승)              │
│ 사용자유형코드     int64   이용자 유형 (1~7)                          │
│ 거리/시간         int64   통행 거리/시간 (초)                         │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 이용자 유형 매핑

TCD의 `사용자유형코드`를 논문의 5개 유형으로 매핑:

| 코드 | 유형 | 논문 코드 | 비율 (추정) |
|------|------|----------|-----------|
| 1 | 일반 (General) | 01 | ~83% |
| 2 | 어린이 (Children) | 02 | ~1% |
| 3 | 청소년 (Youth) | 03 | ~4.5% |
| 4 | 고령자 (Elderly) | 04 | ~8.6% |
| 5 | 장애인 (Disabled) | 05 | ~3.1% |
| 6-7 | 기타 | - | 제외 또는 일반에 포함 |

> **확인 필요**: TCD `사용자유형코드` 1~7의 정확한 매핑. 데이터 탐색 시 확인할 것.

### 3.4 환승 데이터 구조 (TCD의 핵심 장점)

```
[무환승 통행] 환승구분=0 (77.2%)
  승차 정류장 ──(노선)──→ 하차 정류장

[1회 환승 통행] 환승구분=1 (19.6%)
  승차 정류장 ──(노선1)──→ 환승역1 ──(노선2)──→ 하차 정류장

[2회 환승 통행] 환승구분=2 (3.0%)
  승차 정류장 ──(노선1)──→ 환승역1 ──(노선2)──→ 환승역2 ──(노선3)──→ 하차 정류장

[3회+ 환승] 환승구분=3~5 (0.2%)
  더 복잡한 체인...
```

**TCN에서는 지하철↔지하철 환승이 기록되지 않았으나, TCD에서는 완전히 기록됩니다.**

### 3.5 전처리 파이프라인

```
Step 1: TCD 파케 로드
        ├── TCD_20250220.parquet 읽기
        ├── ROUTE_20250220.parquet 읽기 (노선 마스터)
        ├── STTN_20250220.parquet 읽기 (정류장 마스터)
        └── ROUTESTTN_20250220.parquet 읽기 (노선-정류장 매핑)

Step 2: 데이터 정제
        ├── 사용자유형코드 6,7 제외 (또는 일반에 포함)
        ├── 승차시간 null 제거 (~47% → 유효 레코드만)
        ├── 비정상 통행 제거 (거리/시간 > 86,400초 등)
        └── 수단 구분 (운영사ID: 3=지하철, 8=버스)

Step 3: 통행 체인 재구성
        ├── 환승구분=0: 단일 레그 (출발→도착)
        ├── 환승구분=1: 2레그 (출발→환승1→도착)
        ├── 환승구분=2: 3레그 (출발→환승1→환승2→도착)
        └── 각 레그의 수단 식별 (운영사ID로 판단)

Step 4: OD 쌍 추출
        ├── 출발 정류장 → 좌표 변환 (STTN 테이블 조인)
        ├── 도착 정류장 → 좌표 변환
        ├── 출발 시간 파싱 (HHMM → seconds from midnight)
        └── OD CSV 출력: [od_id, origin_lat, origin_lon, dest_lat, dest_lon, departure_time, user_type]

Step 5: 중복 경로 제거
        ├── 동일 OD쌍 + 동일 경유 정류장 시퀀스 = 중복
        ├── 중복 제거 후 고유 통행만 보존
        └── 예상: ~20M → ~200K-300K 고유 통행
```

### 3.6 구현 파일

| 파일 | 역할 | 입력 | 출력 |
|------|------|------|------|
| `scripts/data/tcd_preprocessor.py` | TCD 로드 + 정제 | TCD/ROUTE/STTN/ROUTESTTN parquet | cleaned_tcd.parquet |
| `scripts/data/trip_chain_builder.py` | 통행 체인 재구성 | cleaned_tcd.parquet | trip_chains.parquet |
| `scripts/data/od_extractor.py` | OD 쌍 추출 + 좌표 | trip_chains.parquet + STTN | od_pairs.csv, trip_attributes.parquet |

---

## 4. 수정사항 3: 모델 개선

### 4.1 모델 선택 근거

10개 후보 모델을 7개 기준으로 평가한 결과:

| 모델 | 해석력 | 정확도↑ | 학술 신규성 | 구현성 | 이질성 | OTP 통합 | **결정** |
|------|-------|--------|-----------|-------|-------|---------|---------|
| **Mixed Logit** | 5/5 | 3/5 | 3/5 | 5/5 | 5/5 | 5/5 | **주력** |
| **Latent Class** | 5/5 | 3/5 | 4/5 | 5/5 | 4/5 | 4/5 | **비교** |
| **LightGBM** | 2/5 | 5/5 | 1/5 | 5/5 | 3/5 | 2/5 | **벤치마크** |
| Nested Logit | 4/5 | 1/5 | 1/5 | 5/5 | 1/5 | 4/5 | 건강성 체크 |
| TasteNet-MNL | 4/5 | 3/5 | 5/5 | 3/5 | 5/5 | 4/5 | 향후 연구 |
| ResLogit | 3/5 | 3/5 | 4/5 | 3/5 | 3/5 | 2/5 | 건너뜀 |
| DNN | 1/5 | 2/5 | 2/5 | 4/5 | 2/5 | 1/5 | 건너뜀 |
| IRL | 2/5 | ?/5 | 5/5 | 2/5 | 3/5 | 1/5 | 별도 논문 |
| Transformer | 1/5 | 1/5 | 3/5 | 3/5 | 2/5 | 1/5 | 건너뜀 |
| Cross-Nested | 3/5 | 2/5 | 2/5 | 3/5 | 1/5 | 3/5 | 건너뜀 |

### 4.2 Model A: Mixed Logit (주력 모델)

#### 이론적 배경

MNL은 모든 이용자가 **동일한 고정 파라미터**를 가진다고 가정합니다:
```
MNL:  V_j = β_ride × T_ride + β_walk × T_walk + ...   (β는 고정)
```

Mixed Logit은 파라미터가 **확률분포**를 따른다고 가정합니다:
```
ML:   V_j = β_ride_i × T_ride + β_walk_i × T_walk + ...
      β_walk_i ~ Normal(μ_walk, σ_walk)     ← 개인 i마다 다른 β
      β_transfer_i ~ Normal(μ_transfer, σ_transfer)
```

이를 통해 **같은 "고령자" 그룹 내에서도** 보행 부담을 크게 느끼는 사람과 적게 느끼는 사람의 분포를 파악할 수 있습니다.

#### 모델 사양

```python
from xlogit import MixedLogit

model = MixedLogit()
model.fit(
    X=route_attributes,     # [T_ride, T_walk, N_transfer, D_subway, D_sp, D_tp]
    y=chosen_alternative,   # 선택된 경로 인덱스
    varnames=['T_ride', 'T_walk', 'N_transfer', 'D_subway', 'D_sp', 'D_tp'],
    alts=alternative_ids,   # 대안 경로 ID
    ids=trip_ids,           # 통행 ID
    panels=card_ids,        # 동일인 반복 관측 (선택적)
    randvars={
        'T_walk': 'n',      # 보행시간 ~ Normal(μ, σ) ← 핵심 이질성 변수
        'N_transfer': 'n',  # 환승횟수 ~ Normal(μ, σ)
        'D_subway': 'n',    # 지하철포함 ~ Normal(μ, σ)
    },
    n_draws=1000,           # 몬테카를로 추출 수
    halton=True,            # Halton 시퀀스 (효율적 추출)
)
```

**랜덤 파라미터 선택 근거**:
- `T_walk`: Table 9에서 이용자 유형간 가장 큰 변이 (8.2× ~ 19.6×)
- `N_transfer`: 고령자 환승기피 47%↑ 등 큰 차이
- `D_subway`: 고령자 지하철선호 90%↑
- `T_ride`: 고정 파라미터 (정규화 속성, 모든 유형에서 비교적 안정)

#### 추정 계층

1. **풀링 MNL** (기준선) — 전체 이용자, 고정 파라미터
2. **유형별 MNL** (기존 논문) — 5개 유형 × 고정 파라미터
3. **풀링 Mixed Logit** — 전체 이용자, 랜덤 파라미터
4. **유형별 Mixed Logit** (최종) — 5개 유형 × 랜덤 파라미터

#### 결과 해석 예시

```
고령자 Mixed Logit 결과:
  β_walk ~ N(μ=-0.77, σ=0.25)
  → 평균 보행 가중치: |μ_walk/β_ride| = 11.0×
  → 95% 신뢰구간: [(-0.77-1.96×0.25)/β_ride, (-0.77+1.96×0.25)/β_ride] = [3.7×, 18.1×]
  → 해석: "고령자 중 97.5%가 보행을 차내시간의 3.7배 이상으로 느끼며,
           평균적으로 11.0배, 가장 민감한 2.5%는 18.1배 이상으로 인식"
```

#### xlogit의 장점
- **GPU 가속**: Biogeme 대비 43배 빠른 추정
- **대규모 데이터**: 187K+ 관측치를 1분 이내 추정
- **패널 데이터**: 동일 카드번호의 반복 통행 활용 가능

### 4.3 Model B: Latent Class Model (비교 모델)

#### 핵심 질문
"교통카드의 5개 행정적 유형(일반/고령/청소년/장애/어린이) = 실제 행태 군집인가?"

#### 모델 구조

```
이용자 i는 잠재 클래스 c ∈ {1, 2, ..., K}에 확률적으로 속함
각 클래스 c는 고유한 파라미터 벡터 β_c를 가짐

P(j | i) = Σ_c π_c × P(j | β_c)

π_c = 클래스 c에 속할 확률 (EM 알고리즘으로 추정)
β_c = 클래스 c의 MNL 파라미터
```

#### 추정 계획

```python
# K = 2, 3, 4, 5, 6 클래스 모델 추정
# AIC/BIC 기준 최적 K 선택
for K in [2, 3, 4, 5, 6]:
    model_K = LatentClassModel(n_classes=K)
    model_K.fit(X, y)
    print(f"K={K}: AIC={model_K.aic}, BIC={model_K.bic}")
```

#### 기대 결과

발견될 수 있는 잠재 클래스 예시:
- **클래스 1**: "시간 민감형" — 환승 기피 낮음, 총 시간 중시
- **클래스 2**: "편의 추구형" — 환승 강하게 기피, 지하철 선호
- **클래스 3**: "보행 회피형" — 보행 가중치 매우 높음

→ 이 클래스들과 교통카드 유형의 교차표를 만들면:
```
              클래스1(시간민감) 클래스2(편의추구) 클래스3(보행회피)
일반(82.8%)     60%              30%              10%
고령자(8.6%)    10%              75%              15%
장애인(3.1%)    15%              20%              65%
```

이런 결과가 나오면: "고령자의 75%가 편의추구형이지만, 일반 이용자의 30%도 편의추구형 — 교통카드 유형만으로는 행태 이질성을 완전히 설명할 수 없다"는 **새로운 학술적 발견**.

### 4.4 Model C: LightGBM (벤치마크)

#### 목적
이산선택모델의 예측 정확도가 머신러닝 대비 어떤지 확인

```python
import lightgbm as lgb
import shap

# 특성: 경로 속성 + 이용자 유형 + OD 특성
features = ['T_ride', 'T_walk', 'N_transfer', 'D_subway', 'D_peak',
            'user_type', 'distance_km', 'n_alternatives']

model = lgb.LGBMClassifier(n_estimators=500, learning_rate=0.05)
model.fit(X_train, y_train)

# SHAP 분석
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)
shap.summary_plot(shap_values, X_test)
```

#### 기대 역할
- Mixed Logit Hit Rate 75% vs LightGBM Hit Rate 80% → "ML이 5% 더 높지만, 정책 해석 불가"
- SHAP 특성 중요도가 MNL/ML의 β 절대값 순위와 일치하는지 검증
- 이산선택모델의 행동경제학적 해석력이 5% 정확도 손실을 정당화

### 4.5 구현 파일

| 파일 | 역할 | 패키지 | 출력 |
|------|------|-------|------|
| `scripts/models/data_formatter.py` | 모델 입력 데이터 포맷팅 | pandas | model_input.parquet |
| `scripts/models/mixed_logit_estimator.py` | Mixed Logit 추정 | xlogit | ml_results.json |
| `scripts/models/latent_class_estimator.py` | Latent Class 추정 | biogeme | lc_results.json |
| `scripts/models/lightgbm_benchmark.py` | LightGBM + SHAP | lightgbm, shap | lgb_results.json |
| `scripts/models/model_comparison.py` | 3모델 비교표 | pandas | comparison_table.csv |

### 4.6 필요 Python 패키지

```
xlogit>=0.2.7          # GPU 가속 Mixed Logit
biogeme>=3.2.13        # Latent Class Model
lightgbm>=4.0.0        # 예측 벤치마크
shap>=0.43.0           # 특성 중요도
pandas>=2.0.0          # 데이터 처리
numpy>=1.24.0          # 수치 계산
pyarrow>=14.0.0        # Parquet 읽기
scipy>=1.11.0          # 통계 검정
matplotlib>=3.7.0      # 시각화
seaborn>=0.13.0        # 시각화
```

---

## 5. 수정사항 4: 반복 보정 프레임워크

### 5.1 핵심 아이디어

```
┌───────────────────────────────────────────────────────────┐
│                    반복 보정 루프                            │
│                                                           │
│   OTP 파라미터 θ ──→ 경로 대안 생성 ──→ 교통카드 매칭        │
│        ↑                                    │             │
│        │                                    ↓             │
│   β→θ 매핑          ←── Mixed Logit 추정 ←── 유사도 계산    │
│   (MSA 감쇠)              (β 파라미터)                      │
│                                                           │
│   수렴 시: 최적 θ* + 최적 β* = 자기일관적 시스템              │
└───────────────────────────────────────────────────────────┘
```

### 5.2 이론적 분류: 이중 수준 최적화 (Bilevel Optimization)

**상위 수준** (OTP 파라미터 보정):
```
min_θ  D(P_observed, P_predicted(θ))
```

**하위 수준** (경로선택 모델 추정):
```
max_β  LL(β | C(θ))
```

여기서 `C(θ)`는 OTP 파라미터 θ하에서 생성된 선택지 집합.

핵심 결합: **선택지 집합 C(θ)가 OTP 파라미터에 의존**하고, **추정된 β가 다음 OTP 파라미터를 결정**.

**유사 방법론**:
- 확률적 이용자 균형 (Stochastic User Equilibrium, Sheffi 1985)
- Method of Successive Averages (MSA)
- 교통 배정 반복법 (Frank-Wolfe algorithm)

### 5.3 이용자 유형별 Generalized Cost 전략

**사용자 제안 반영**: OTP는 1회만 실행하되, 유형별로 다른 Generalized Cost를 적용

```
[Step 1] OTP 실행 (가중평균 파라미터)
         → 각 OD쌍에 대해 5~11개 Pareto-optimal 대안 생성
         → 각 대안의 속성 추출: (T_ride, T_walk, N_transfer, D_subway)

[Step 2] 유형별 효용 계산 (같은 대안, 다른 β)

  일반 이용자:
    V_j = -0.084×T_ride - 0.685×T_walk - 4.04×N_transfer + 2.49×D_subway

  고령자:
    V_j = -0.070×T_ride - 0.770×T_walk - 5.94×N_transfer + 4.72×D_subway

  장애인:
    V_j = -0.072×T_ride - 0.807×T_walk - 4.62×N_transfer + 2.93×D_subway

[Step 3] 유형별 선택확률
    P(j | 일반) = exp(V_j^일반) / Σ exp(V_k^일반)
    P(j | 고령) = exp(V_j^고령) / Σ exp(V_k^고령)

    → 같은 대안이라도 유형별로 다른 확률!
```

**이 구조의 장점**:
- OTP 1회 실행 = 계산 비용 1/5
- 유형별 차이는 β 파라미터 수준에서 반영 (더 유연)
- Pareto-optimal 대안은 다양한 유형의 선호를 포괄할 수 있음

### 5.4 파라미터 매핑 함수: β → OTP θ

#### WALK_RELUCTANCE 매핑

OTP에서 보행 비용은:
```java
// KoreanAccessEgress.java
public int c1() {
    return durationSeconds * 100;  // 현재: 1초 = 100 비용단위
}
```

수정 후:
```java
public int c1() {
    return (int)(durationSeconds * 100 * WALK_RELUCTANCE);
    // WALK_RELUCTANCE=8.5 → 1초 보행 = 850 비용단위 = 8.5초 차내시간
}
```

**매핑 공식**:
```
WALK_RELUCTANCE = |β_walk_pooled / β_ride_pooled|

현재 β 추정치 (Table 8):
  β_walk = -0.699, β_ride = -0.082
  → WALK_RELUCTANCE = 0.699/0.082 = 8.5

유형별 가중평균 (반복 보정용):
  WALK_RELUCTANCE = Σ(w_g × |β_walk_g / β_ride_g|)
  = 0.828×8.2 + 0.086×11.0 + 0.045×10.3 + 0.031×11.2 + 0.010×19.6
  ≈ 8.74
```

#### TRANSFER_COST 매핑

OTP에서 환승 비용은:
```java
// KoreanCostCalculator.java
private static final int TRANSFER_COST = 120 * 100;  // 120초 = 2분
```

**매핑 공식**:
```
TRANSFER_COST(초) = |β_transfer / β_ride| × 60

현재 β 추정치:
  β_transfer = -4.194, β_ride = -0.082
  → TRANSFER_COST = 4.194/0.082 × 60 = 3,068초 ≈ 51분

⚠️ 주의: 3,068초는 너무 큼 → Pareto 탐색에서 다환승 경로가 사라질 수 있음
→ 상한 설정: TRANSFER_COST ≤ 600초 (10분)
→ 나머지는 MNL β 수준에서 반영 (행태 모델이 환승 기피를 포착)
```

**핵심 인사이트**: OTP 파라미터는 **대안 생성** 역할이므로 극단적 값은 피해야 합니다. 행태적 선호의 극단성은 **MNL β 파라미터**에서 포착하는 것이 적절합니다. OTP의 TRANSFER_COST는 "다환승 경로도 대안에 포함되게 하되, 어느 정도 페널티는 주는" 수준으로 설정.

### 5.5 반복 알고리즘 (의사코드)

```
알고리즘: IterativeCalibration

입력:
  S = {(n, y_n, user_type_n)} : 교통카드 관측 데이터
  θ_0 = (WALK_RELUCTANCE=1.0, TRANSFER_COST=120초) : 초기 OTP 파라미터
  ε = 0.01 : 수렴 허용 오차
  K_max = 15 : 최대 반복 횟수

출력:
  θ* : 수렴된 OTP 파라미터
  β* : 수렴된 Mixed Logit 파라미터 (유형별)
  C*(θ*) : 최종 선택지 집합

절차:
  k ← 0
  θ ← θ_0

  REPEAT:
    k ← k + 1
    print(f"=== Iteration {k} ===")

    // STEP 1: OTP 배치 실행 (Java)
    write_config(θ, "calibration_config.json")
    run_java_batch("BatchRouter", od_pairs, "batch_result_k.json")
    C_k ← load_batch_results("batch_result_k.json")
    // 각 OD에 대해 5~11개 Pareto-optimal 대안 + 속성

    // STEP 2: 경로 매칭 (Python)
    for each 관측 n:
      for each 대안 j in C_k(n):
        S_trip(y_n, j) ← compute_similarity(y_n, j)  // 5개 유사도 지표
      best_match ← argmax_j S_trip(y_n, j)
      if S_trip(y_n, best_match) ≥ 0.85:  // Exact Match
        include n in estimation_sample

    match_rate_k ← |estimation_sample| / N
    print(f"Match rate: {match_rate_k:.1%}")

    // STEP 3: 속성 추출 (Python)
    for each n in estimation_sample:
      for each j in C_k(n):
        extract (T_ride_nj, T_walk_nj, N_transfer_nj, D_subway_nj)

    // STEP 4: Mixed Logit 추정 (Python - xlogit)
    β_k ← estimate_mixed_logit(estimation_sample)
    // 유형별 5개 모델도 별도 추정

    // STEP 5: 목표 OTP 파라미터 계산
    θ_target.WALK_RELUCTANCE ← |β_k.walk / β_k.ride|
    θ_target.TRANSFER_COST ← min(600, |β_k.transfer / β_k.ride| × 60)

    // STEP 6: MSA 감쇠 업데이트
    α_k ← min(0.5, 1/k)  // 감쇠 계수
    θ_k ← θ_{k-1} + α_k × (θ_target - θ_{k-1})

    // STEP 7: 수렴 검사
    Δ_β ← max(|β_k - β_{k-1}|) / max(|β_{k-1}|)
    Δ_θ ← max(|θ_k - θ_{k-1}|) / max(|θ_{k-1}|)
    route_stability ← mean(Jaccard(C_k(n), C_{k-1}(n)) for all n)
    Δ_LL ← |LL_k - LL_{k-1}| / |LL_{k-1}|

    print(f"Δβ={Δ_β:.4f}, Δθ={Δ_θ:.4f}, RouteStab={route_stability:.4f}, ΔLL={Δ_LL:.6f}")

    converged ← (Δ_β < ε) AND (route_stability > 0.95) AND (Δ_LL < 0.001)

  UNTIL converged OR k ≥ K_max

  print(f"Converged at iteration {k}")
  print(f"Final θ: WALK_RELUCTANCE={θ_k.wr:.2f}, TRANSFER_COST={θ_k.tc:.0f}s")
  print(f"Final match rate: {match_rate_k:.1%}")

  RETURN θ_k, β_k, C_k
```

### 5.6 수렴 기준 (4가지 동시 충족)

| 기준 | 수식 | 임계값 | 의미 |
|------|------|--------|------|
| 파라미터 안정성 | `max|βₖ - βₖ₋₁| / |βₖ₋₁|` | < 0.01 (1%) | β가 거의 변하지 않음 |
| 경로집합 안정성 | `mean(Jaccard(Cₖ, Cₖ₋₁))` | > 0.95 | 대안 경로가 거의 동일 |
| 로그우도 안정성 | `|LLₖ - LLₖ₋₁| / |LLₖ₋₁|` | < 0.001 | 모델 적합도 안정 |
| 최대 반복 | k | ≤ 15 | 안전 장치 |

### 5.7 예상 수렴 과정

```
Iteration 0 (기준선):
  θ: WALK_RELUCTANCE=1.0, TRANSFER_COST=120s
  → OTP가 보행 많은 경로도 추천 (보행 거의 페널티 없음)
  → 매칭률: ~38% (기존 논문과 동일)
  → β: walk_weight=8.5×, transfer=-4.2

Iteration 1:
  θ: WALK_RELUCTANCE=3.75 (1.0+0.5×(8.5-1.0)), TRANSFER_COST=240s
  → 보행 적은 경로 위주 추천
  → 매칭률: ~43% (+5%)
  → β 약간 변화

Iteration 2:
  θ: WALK_RELUCTANCE=5.6, TRANSFER_COST=300s
  → 매칭률: ~48% (+5%)
  → 경로집합 안정화 시작

Iteration 3-4:
  θ: WALK_RELUCTANCE=6.8-7.5, TRANSFER_COST=350-400s
  → 매칭률: ~52-55%
  → Δβ < 0.05 (미세 조정 단계)

Iteration 5-6:
  θ: WALK_RELUCTANCE=7.5-8.0, TRANSFER_COST=400-450s
  → 매칭률: ~55-58%
  → Δβ < 0.01 → 수렴!

최종 결과:
  θ*: WALK_RELUCTANCE ≈ 8.0, TRANSFER_COST ≈ 420s
  매칭률: 38% → 55%+ (17%p 개선)
  β*: 보다 정확한 행태 파라미터 (일관된 선택지 집합 기반)
```

### 5.8 비수렴 대응 방안

| 위험 | 확률 | 대응 |
|------|------|------|
| **진동** (두 상태 왔다갔다) | 중간 | MSA 감쇠 계수 αₖ = 1/(k+1) 적용 → 보장됨 |
| **선택지 붕괴** (다환승 경로 소멸) | 낮음 | TRANSFER_COST 상한 600초, Pareto 탐색이 다양성 유지 |
| **파라미터 발산** | 낮음 | β 비율(β_walk/β_ride)은 본질적으로 안정적 |
| **계산시간 초과** | 중간 | 10K 서브샘플로 반복, 최종만 전체 실행 |

### 5.9 OTP Java 측 수정사항 (상세)

#### 수정 1: KoreanCostCalculator.java

**위치**: `korean-otp/src/main/java/kr/otp/raptor/spi/KoreanCostCalculator.java`

**현재 코드**:
```java
private static final int FIRST_BOARD_COST = 60 * 100;
private static final int TRANSFER_COST = 120 * 100;
```

**수정 후**:
```java
private final int firstBoardCost;
private final int transferCost;
private final double waitReluctance;

public KoreanCostCalculator(int firstBoardCostSec, int transferCostSec, double waitReluctance) {
    this.firstBoardCost = firstBoardCostSec * 100;
    this.transferCost = transferCostSec * 100;
    this.waitReluctance = waitReluctance;
}
```

#### 수정 2: KoreanAccessEgress.java

**위치**: `korean-otp/src/main/java/kr/otp/raptor/spi/KoreanAccessEgress.java`

**현재 코드**:
```java
public int c1() {
    return durationSeconds * 100;
}
```

**수정 후**:
```java
private final double walkReluctance;

public KoreanAccessEgress(int stopIndex, int durationSeconds, double walkReluctance) {
    this.stopIndex = stopIndex;
    this.durationSeconds = durationSeconds;
    this.walkReluctance = walkReluctance;
}

public int c1() {
    return (int)(durationSeconds * 100 * walkReluctance);
}
```

#### 수정 3: BatchRouter.java

**위치**: `korean-otp/src/main/java/kr/otp/batch/BatchRouter.java`

**추가 기능**:
1. `calibration_config.json` 파일 읽기
2. 파라미터를 KoreanRaptor → KoreanTransitDataProvider → KoreanCostCalculator로 전달
3. 출력 JSON에 경로 속성 추가:

```json
{
  "paths": [
    {
      "departure": "09:00",
      "arrival": "09:40",
      "duration": 40,
      "transfers": 1,
      "legs": [...],
      "route_attributes": {
        "ride_time_min": 29.5,
        "walk_time_min": 1.8,
        "n_transfers": 1,
        "has_subway": true,
        "modes": ["SUBWAY", "BUS"],
        "stops": ["100001", "100002", "100003", ...]
      }
    }
  ]
}
```

#### 수정 4: KoreanTransitDataProvider.java

**위치**: `korean-otp/src/main/java/kr/otp/raptor/spi/KoreanTransitDataProvider.java`

**변경**: 생성자에서 보정 파라미터를 받아 CostCalculator에 전달

### 5.10 구현 파일

| 파일 | 역할 | 입출력 |
|------|------|-------|
| `scripts/calibration/calibration_orchestrator.py` | 메인 반복 루프 | config → Java 호출 → Python 분석 → 수렴 검사 |
| `scripts/calibration/param_mapper.py` | β → OTP θ 매핑 + MSA 감쇠 | β_estimates.json → calibration_config.json |
| `scripts/calibration/convergence_checker.py` | 수렴 진단 + 시각화 | 반복별 β, θ, LL → 수렴 그래프 |
| `scripts/calibration/route_matcher.py` | 교통카드 ↔ OTP 경로 매칭 | tcd + batch_result → matched_data.parquet |

### 5.11 계산 예산

| 단계 | 반복당 소요시간 | 비고 |
|------|-------------|------|
| OTP 배치 실행 | ~72분 | 187K OD @ 43.4 req/s |
| 경로 매칭 | ~10분 | Pandas 조인 + 유사도 계산 |
| Mixed Logit 추정 | ~5분 | xlogit GPU |
| 파라미터 매핑 | <1분 | 단순 연산 |
| **반복당 합계** | **~88분** | |
| **5회 반복 (예상)** | **~7.3시간** | |
| **개발 시 10K 서브샘플** | **~5분/반복** | 빠른 디버깅 |

---

## 6. 전체 실행 파이프라인

### Phase 1: 데이터 전처리 (Day 1-2)

```
[1.1] TCD 파케 데이터 로드
      입력: DATA/tcd_2025_parquet/20250220/TCD_20250220.parquet
      출력: cleaned_tcd.parquet (~10M 유효 레코드)
      스크립트: scripts/data/tcd_preprocessor.py

[1.2] 통행 체인 재구성
      입력: cleaned_tcd.parquet
      출력: trip_chains.parquet (승차→환승→하차 완전 체인)
      스크립트: scripts/data/trip_chain_builder.py

[1.3] OD 쌍 추출 + 좌표 변환
      입력: trip_chains.parquet + STTN_20250220.parquet
      출력: od_pairs.csv, trip_attributes.parquet
      스크립트: scripts/data/od_extractor.py

[1.4] GTFS 정류장 시퀀스 추출
      입력: GTFS stop_times.txt + routes.txt + trips.txt
      출력: route_stop_sequences.parquet (노선별 정류장 순서)
      스크립트: scripts/similarity/stop_sequence_extractor.py

[1.5] 노선 동등성 인덱스 구축
      입력: route_stop_sequences.parquet
      출력: route_equivalence_index.parquet (노선쌍 유사도)
      스크립트: scripts/similarity/route_equivalence_index.py
```

### Phase 2: 초기 OTP 배치 + 매칭 (Day 3-4)

```
[2.1] OTP Java 파라미터화 수정
      수정 파일: KoreanCostCalculator.java, KoreanAccessEgress.java,
                BatchRouter.java, KoreanTransitDataProvider.java
      테스트: 소수 OD로 기능 검증

[2.2] 초기 OTP 배치 실행
      입력: od_pairs.csv + calibration_config.json (기본 파라미터)
      출력: batch_result_iter0.json
      실행: Java BatchRouter (187K OD, ~72분)

[2.3] 경로 유사도 계산
      입력: trip_chains.parquet + batch_result_iter0.json + route_stop_sequences.parquet
      출력: similarity_results.parquet (5개 지표 + S_trip)
      스크립트: scripts/similarity/route_similarity.py

[2.4] 매칭 결과 분석
      - 기존 Route Jaccard(노선ID) vs 새 S_trip(정류장) 분포 비교
      - Exact Match 비율: 38% → ?%
      - 유형별 매칭률 비교표
```

### Phase 3: 모델 추정 (Day 5-7)

```
[3.1] 모델 입력 데이터 포맷팅
      입력: similarity_results.parquet + batch_result_iter0.json
      출력: model_input.parquet (wide format: trip × alternatives)
      스크립트: scripts/models/data_formatter.py

[3.2] MNL 추정 (기준선)
      - 풀링 MNL: 전체 이용자
      - 유형별 MNL: 5개 모델
      → 기존 논문 결과 재현 확인

[3.3] Mixed Logit 추정 (주력)
      - 풀링 ML: 랜덤 파라미터 (μ, σ)
      - 유형별 ML: 5개 × (μ, σ)
      → ρ² 개선 확인
      스크립트: scripts/models/mixed_logit_estimator.py

[3.4] Latent Class 추정 (비교)
      - K=2,3,4,5,6 클래스 비교
      - 최적 K 선택 (AIC/BIC)
      - 잠재 클래스 vs 교통카드 유형 교차분석
      스크립트: scripts/models/latent_class_estimator.py

[3.5] LightGBM 벤치마크
      - 80/20 split
      - Hit Rate, SHAP 분석
      스크립트: scripts/models/lightgbm_benchmark.py

[3.6] 모델 비교
      - MNL vs ML vs LC vs LightGBM
      - ρ², Hit Rate, AIC/BIC 비교표
      스크립트: scripts/models/model_comparison.py
```

### Phase 4: 반복 보정 (Day 8-10)

```
[4.1] β → OTP 파라미터 매핑 (Iteration 1)
      β_0 → θ_1 (MSA 감쇠 적용)
      스크립트: scripts/calibration/param_mapper.py

[4.2] OTP 재실행 (Iteration 1)
      batch_result_iter1.json 생성

[4.3] 재매칭 + 재추정 (Iteration 1)
      새 유사도 → 새 β_1

[4.4] 반복 (Iteration 2~6)
      수렴까지 [4.1]~[4.3] 반복
      스크립트: scripts/calibration/calibration_orchestrator.py

[4.5] 수렴 진단
      - 반복별 파라미터 궤적 그래프
      - 매칭률 변화 그래프
      - 로그우도 수렴 그래프
      스크립트: scripts/calibration/convergence_checker.py
```

### Phase 5: 검증 + 결과 정리 (Day 11-12)

```
[5.1] Hold-out 검증
      - 80/20 split
      - Train vs Test: Hit Rate, ρ², Mean Choice Probability
      - 과적합 여부 확인

[5.2] 테스트 케이스
      - 명동→역삼 (지하철 vs 버스)
      - 구로디지털단지→종로 (0환승 vs 1환승)
      - 합정→선릉 (직통 vs 환승)
      - 각 케이스: 유형별 선택확률 비교

[5.3] 반복 전/후 비교
      - 매칭률: 38% → ?%
      - ρ²: 0.059 → ?
      - OTP 파라미터: WALK_RELUCTANCE 1.0 → ?
      - 경로 추천 차이 시각화

[5.4] 결과 테이블 생성
      - 논문용 테이블 (Table 7~14 대체)
      - 새로운 테이블: 유사도 분포, ML 파라미터, 잠재 클래스, 수렴 과정
```

---

## 7. 프로젝트 구조

```
강릉ITS/
├── Kim_TransitRouteChoice_ITSWC2026.pdf    # 기존 논문
├── RESEARCH_PLAN.md                        # 이 계획서
│
├── scripts/                                 # 🆕 신규 Python 코드
│   ├── requirements.txt                     # 패키지 의존성
│   │
│   ├── data/                               # Phase 1: 데이터 전처리
│   │   ├── tcd_preprocessor.py             # TCD 파케 로드+정제
│   │   ├── trip_chain_builder.py           # 통행 체인 재구성
│   │   └── od_extractor.py                 # OD 추출+좌표변환
│   │
│   ├── similarity/                         # 수정사항 1: 유사도
│   │   ├── stop_sequence_extractor.py      # GTFS 정류장 시퀀스
│   │   ├── route_similarity.py             # 5개 유사도 지표
│   │   └── route_equivalence_index.py      # 노선쌍 사전계산
│   │
│   ├── models/                             # 수정사항 3: 모델
│   │   ├── data_formatter.py               # 모델 입력 포맷
│   │   ├── mixed_logit_estimator.py        # Mixed Logit (xlogit)
│   │   ├── latent_class_estimator.py       # Latent Class (Biogeme)
│   │   ├── lightgbm_benchmark.py           # LightGBM + SHAP
│   │   └── model_comparison.py             # 3모델 비교
│   │
│   └── calibration/                        # 수정사항 4: 반복보정
│       ├── calibration_orchestrator.py     # 메인 반복 루프
│       ├── param_mapper.py                 # β→OTP 매핑+MSA
│       ├── convergence_checker.py          # 수렴 진단+시각화
│       └── route_matcher.py               # 경로 매칭
│
├── korean-otp/                             # 기존 OTP 엔진 (Java 수정)
│   ├── src/main/java/kr/otp/
│   │   ├── raptor/spi/
│   │   │   ├── KoreanCostCalculator.java   # ✏️ 파라미터화
│   │   │   ├── KoreanAccessEgress.java     # ✏️ WALK_RELUCTANCE
│   │   │   └── KoreanTransitDataProvider.java # ✏️ 파라미터 전달
│   │   └── batch/
│   │       └── BatchRouter.java            # ✏️ 설정읽기+속성출력
│   └── data/gtfs/                          # GTFS 데이터
│
├── DATA/                                   # 데이터
│   ├── tcd_2025_parquet/
│   │   └── 20250220/                       # 📌 분석 대상 (목요일)
│   │       ├── TCD_20250220.parquet
│   │       ├── ROUTE_20250220.parquet
│   │       ├── STTN_20250220.parquet
│   │       └── ROUTESTTN_20250220.parquet
│   ├── tcn_route_mapping_complete.csv
│   └── tcn_to_gtfs_route_mapping.csv
│
└── results/                                # 🆕 결과 출력
    ├── iteration_logs/                     # 반복보정 로그
    ├── model_results/                      # 모델 추정 결과
    ├── figures/                            # 그래프
    └── tables/                             # 논문용 테이블
```

---

## 8. 검증 계획

### 8.1 유사도 프레임워크 검증

| 검증 | 방법 | 기대 결과 |
|------|------|----------|
| 302↔303 문제 해결 | 기존 Route Jaccard vs 새 S_jaccard 비교 | S_jaccard가 0.85+ (기존 0.0) |
| Exact Match 개선 | S_trip 기준 매칭률 | 38% → 55%+ |
| 유형별 패턴 | 어린이 > 고령자 > 일반 순 매칭률 | 기존 패턴 유지 확인 |

### 8.2 모델 검증

| 검증 | 방법 | 기대 결과 |
|------|------|----------|
| Hold-out | 80/20 split, Train vs Test | ML: Hit Rate 차이 < 1% (과적합 없음) |
| 모델 비교 | ρ², AIC, BIC | ML > MNL > LC (적합도 순) |
| LightGBM 대비 | Hit Rate 비교 | ML Hit Rate는 LightGBM의 90-95% |
| 파라미터 부호 | β 추정치 부호 | 이론 일치 (보행-, 환승-, 지하철+) |
| 우도비 검정 | 유형별 vs 풀링 | p < 0.001 (유형별 차이 유의) |

### 8.3 반복 보정 검증

| 검증 | 방법 | 기대 결과 |
|------|------|----------|
| 수렴 | 파라미터 궤적 그래프 | 5~8회 반복 후 안정 |
| 매칭률 개선 | 반복별 매칭률 | 38% → 55%+ 단조 증가 |
| OTP 파라미터 | 보정 전 vs 후 | WALK_RELUCTANCE: 1.0 → ~8.0 |
| 경로 추천 변화 | 동일 OD의 추천 경로 비교 | 보행 적은 경로로 전환 |

### 8.4 테스트 케이스 (논문 재현)

| OD | 비교 | 기대 패턴 |
|-----|------|----------|
| 명동→역삼 | 지하철(환승) vs 버스(직통) | 고령자: 지하철 67%+, 어린이: 버스 52%+ |
| 구로→종로 | 0환승 vs 1환승 | 고령자: 0환승 86%+, 일반: 1환승 38%+ |
| 합정→선릉 | 직통 vs 환승 | 고령자: 직통 97%+, 일반: 직통 85%+ |

---

## 9. 학술적 기여

### 기존 논문 대비 추가 기여

| # | 기여 | 학술적 가치 |
|---|------|-----------|
| 1 | **정류장 시퀀스 기반 유사도** | 노선 ID 한계 극복, 기능적 경로 동등성의 학술적 정의 제시 |
| 2 | **TCD 완전 환승 데이터** | 지하철 환승까지 포착한 보다 정확한 통행 체인 분석 |
| 3 | **Mixed Logit** | MNL → ML 확장으로 이용자 유형 내 이질성까지 포착 (μ+σ 보고) |
| 4 | **Latent Class** | 교통카드 유형 ≠ 행태 군집 여부 실증 검증 |
| 5 | **LightGBM 벤치마크** | 이산선택모델의 예측력을 ML 대비 정량 평가 |
| 6 | **반복 보정** | 라우팅 엔진-행태 모델의 자기일관적(self-consistent) 보정 프레임워크 |
| 7 | **매칭률 개선** | 38% → 55%+로 분석 가능 표본 대폭 확대 |

### 참고 문헌 (추가 필요)

- Han, Y., et al. (2022). "A neural-embedded discrete choice model..." Transportation Research Part B
- Wong, M. & Farooq, B. (2021). "ResLogit: A residual neural network logit model..." Transportation Research Part C
- Arriagada, J., et al. (2025). "An experiential learning-based transit route choice model..." Transportation
- xlogit documentation: https://xlogit.readthedocs.io/
- Frejinger, E. & Bierlaire, M. (2007). "Capturing correlation with subnetworks..." Transportation Research Part B
- Sheffi, Y. (1985). Urban Transportation Networks. Prentice-Hall.

---

## 10. 일정 및 산출물

### 일정 (12일)

| 일차 | 단계 | 산출물 |
|------|------|--------|
| Day 1-2 | 데이터 전처리 | cleaned_tcd.parquet, trip_chains.parquet, od_pairs.csv |
| Day 3-4 | OTP 수정 + 배치 + 매칭 | batch_result_iter0.json, similarity_results.parquet |
| Day 5-6 | Mixed Logit + MNL 추정 | ml_results.json, mnl_results.json |
| Day 7 | Latent Class + LightGBM | lc_results.json, lgb_results.json |
| Day 8-9 | 반복 보정 (5~8회) | iteration_logs/, converged_params.json |
| Day 10 | 최종 모델 추정 | final_ml_results.json (수렴 파라미터 기반) |
| Day 11 | Hold-out 검증 + 테스트 케이스 | validation_results.json |
| Day 12 | 결과 정리 + 테이블/그래프 | tables/, figures/ |

### 핵심 산출물

1. **Python 스크립트 16개** (data 3 + similarity 3 + models 5 + calibration 4 + requirements 1)
2. **Java 수정 4개** (KoreanCostCalculator, KoreanAccessEgress, BatchRouter, KoreanTransitDataProvider)
3. **결과 테이블** (유사도 분포, Mixed Logit 파라미터, Latent Class 교차표, 수렴 과정, 모델 비교)
4. **그래프** (유사도 히스토그램, 파라미터 비교 바차트, 수렴 궤적, SHAP 요약)
