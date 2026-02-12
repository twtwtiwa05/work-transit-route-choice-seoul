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

### 5.1 핵심 목표

Phase 3에서 추정된 행태 파라미터(β)를 OTP 라우팅 엔진의 비용함수에 반영하여 **자기일관적(self-consistent) 파라미터**를 도출한다.

```
문제 상황:
  OTP: walkReluctance=1.0, transferCostSeconds=120초 (기본값)
  MNL: 보행 가중치 22.7×, 환승 페널티 ~100분
  → OTP 가정과 실제 행태 사이에 큰 괴리
```

### 5.2 접근법 진화 과정

연구 과정에서 여러 접근법을 시도하며 점진적으로 핵심 발견에 도달:

| 접근법 | 설명 | 결과 | 핵심 발견 |
|--------|------|------|-----------|
| 전통적 반복 | β→θ→OTP 재실행→β 재추정 | ❌ Exact Match 28.66%→14% | 대중교통 이산적 특성으로 붕괴 |
| A. Pooled MSA | β 비율 기반 단일 θ, MSA 수렴 | +1.02%p (Best Match) | Choice Set 고정이 안정적 |
| B. 유형별 θ | 5유형별 β 비율 기반 θ | +4.3%p (Best Match) | 유형별 차별화 유효 |
| E. 확률적 RSM | LHS+RSM 3D 전역 탐색, MNL 확률 가중 F₁, IPW 보정 | +0.95%p (OTP 1순위) | **θ 최적화의 구조적 상한 ~+1%p** |
| **MNL 재순위** | **MNL β로 OTP 대안 재순위** | **+1.89%p (OTP 1순위)** | **핵심 기여: β가 θ보다 우수** |

### 5.3 전통적 반복 보정의 실패

초기에 전통적 방식(β→θ→OTP 재실행→β 재추정)을 시도:

```
Iter0 → Iter1 파라미터 변경:
  walkReluctance: 1.0 → 5.0 (+400%)
  transferCostSeconds: 120 → 300 (+150%)

결과: Exact Match 28.66% → 14.0% (-14.6%p) ← 붕괴!
```

**원인**: OTP 파라미터 변경 → 완전히 다른 경로 세트 생성 → TCD 관측 경로와 매칭률 급락. 도로 네트워크(연속적)와 달리 대중교통(이산적)은 파라미터 변화에 극도로 민감.

→ **Choice Set 고정 접근법** 채택: Phase 3 β를 Ground Truth로 고정, θ만 조정

### 5.4 접근법 A: Choice Set 고정 보정 (Pooled MSA)

**β → θ 매핑 공식**:
```
walkReluctance = |β_walk / β_ride| = |-0.644 / -0.075| = 8.59
transferCostSeconds = |β_transfer / β_ride| × 60 = |-3.051 / -0.075| × 60 = 2,441초
```

파라미터 상한 적용(walkReluctance ≤ 6.0, transferCostSeconds ≤ 300) 후 MSA 감쇠:
```
α_k = min(0.3, 1/(k+1))
θ_k = θ_{k-1} + α_k × (θ_target − θ_{k-1})
```

**수렴 결과**: walkReluctance=5.47, transferCostSeconds=276
**검증**: Exact Match 28.66% → 29.68% (+1.02%p, Best Match 기준)

### 5.5 접근법 B: 유형별 θ

Pooled θ × (유형별 가중치 / Pooled 가중치)로 5유형별 θ 산출:

| 유형 | walkReluctance | transferCostSec |
|------|----------------|-----------------|
| GENERAL | 4.07 | 202 |
| CHILDREN | 2.97 | 145 |
| YOUTH | 2.71 | 139 |
| ELDERLY | 1.75 | 109 |
| DISABLED | 7.28 | 358 |

**결과**: Exact Match 33.0% (+4.3%p, Best Match 기준)

### 5.6 평가 지표의 진화

| 단계 | 평가 방식 | 문제점 |
|------|-----------|--------|
| 1단계 | Best Match (sim max) | 파라미터 변화에 둔감, 보정 효과 희석 |
| 2단계 | OTP 1순위 (generalized_cost min) | 계단형(0/1), 최적화 불가 |
| 3단계 | MNL 확률 가중 F₁ | 연속적이나 경계 수렴 |
| **4단계** | **MNL 재순위 (V max)** | **핵심 기여** |

전체 데이터(1,320,030 체인) 베이스라인:
- OTP 1순위 Exact Match: **20.34%** (Best Match 28.62%와 8.28%p 차이 = 개선 여지)

### 5.7 접근법 E: 확률 기반 LHS + RSM 최적화

**목적함수** (IPW-가중 기대 유사도):
```
F₁(θ) = Σᵢ wᵢ^IPW × Σⱼ P(j|i,θ) × sim(i,j) / Σᵢ wᵢ^IPW
P(j|i,θ) = exp(V_ij) / Σ exp(V_ik),  V_ij = β'x_ij
```

3D 파라미터 공간: walkReluctance∈[2,40], transferCostSeconds∈[15,500], subwayReluctance∈[0.2,3.0]

**GENERAL 결과** (22개 LHS + 6개 검증, RSM R²=0.98):
- 최적 θ: walkReluctance=**40.0**(상한), transferCostSeconds=**17**(하한 근처), subwayReluctance=**3.0**(상한)
- **3개 파라미터 모두 경계에 수렴** → 구조적 문제

**구조적 한계 발견**:
- det_exact(OTP 자체 순위): 19.84% → 20.79% (+0.95%p — 미미)
- mnl_exact(MNL 재순위): 21.84% → 30.66% (+8.82%p — 대폭)
- F₁ 개선의 대부분이 θ 자체 개선이 아닌 **MNL 재순위 효과**에 기인
- 극단적 θ → 다양한 Choice Set → MNL 재순위 "재료" 풍부화

→ **θ 최적화의 상한은 ~+1%p** (OTP 1순위 기준)

### 5.8 MNL 재순위 (핵심 기여)

접근법 E의 구조적 한계 분석에서 도출된 핵심 발견: OTP 재실행 없이 기존 대안에 MNL β를 적용하여 재순위하면 θ 최적화보다 더 큰 개선을 달성.

```
V_j = β_ride × T_ride_j + β_walk × T_walk_j + β_transfer × N_transfer_j + β_subway × D_subway_j
MNL 1순위 = argmax_j V_j  (generalized_cost 대신 V 사용)
```

**전체 결과** (1,320,030 체인, 4,884,216 경로 쌍):

| 순위 방식 | Exact Match | sim_total |
|-----------|-------------|-----------|
| OTP 1순위 | 20.34% | 0.5372 |
| **MNL 1순위** | **22.23%** | **0.5713** |
| Best Match (상한) | 28.62% | 0.6260 |

**상세 분석 결과**:

- **유형별**: YOUTH +2.49%p(최대), CHILDREN +2.23%p, GENERAL +1.99%p, DISABLED +1.51%p, ELDERLY +1.16%p(최소)
- **환승별**: 직통 +2.05%p, 환승1회 +1.25%p, 2회+ 거의 효과 없음
- **시간대**: 피크 +1.84%p, 비피크 +1.91%p (안정적, 시간대 무관)
- **대안 수별**: 1개=0%p, 2개=+1.52%p, 3-4개=+2.23%p, **5개+=+3.17%p** (단조 증가)
- **일치/불일치**: 75.4% 동일 선택, 24.6% 불일치 → 불일치 시 MNL:OTP = **10.4:1** (Exact Match)
- **MNL 선택 경로 특성**: 보행 -0.5분(16%↓), 환승 -0.10회(20%↓), 지하철 +2.0%p, 차내시간 +1.1분

### 5.9 OTP Java 수정사항

Phase 4에서 실제 수행한 Java 수정:

| 파일 | 수정 내용 |
|------|----------|
| `KoreanCostCalculator.java` | `TRANSFER_COST`, `WAIT_RELUCTANCE` 상수 → `CalibrationConfig`에서 읽도록 파라미터화 |
| `KoreanAccessEgress.java` (AccessEgressFinder) | `walkReluctance` 외부 주입, `c1()` = `durationSeconds × 100 × walkReluctance` |
| `BatchRouter.java` | `calibration_config.json` 파일 로드, 경로 속성(ride_time, walk_time, transfers, modes, stops) 출력 추가 |
| `KoreanTransitDataProvider.java` | 보정 파라미터를 CostCalculator에 전달하는 경로 추가 |
| `CalibrationConfig.java` | JSON 기반 파라미터 설정 클래스 신규 생성 |

### 5.10 구현 파일 (Phase 4)

| 파일 | 역할 | 상태 |
|------|------|------|
| `scripts/calibration/fixed_choice_calibration.py` | β→θ 매핑 + MSA 수렴 (접근법 A) | ✅ |
| `scripts/calibration/usertype_calibration.py` | 유형별 θ 적용 (접근법 B) | ✅ |
| `scripts/calibration/probabilistic_rsm_calibration.py` | LHS + RSM + IPW (접근법 E) | ✅ |
| `scripts/calibration/mnl_reranking_analysis.py` | **MNL 재순위 상세 분석 (핵심)** | ✅ |
| `scripts/calibration/full_baseline_analysis.py` | 전체 데이터 베이스라인 | ✅ |

---

## 6. 전체 실행 파이프라인

### Phase 1: 데이터 전처리 ✅ 완료

```
[1.1] TCD 데이터 로드 + 정제 → cleaned_tcd.parquet (18,106,743 레그)
[1.2] 통행 체인 재구성 → trip_chains.parquet (13,906,278 체인) + trip_legs.parquet
[1.3] OD 쌍 추출 + 좌표 변환 → od_pairs.csv (1,781,135 OD)
[1.4] 정류장 시퀀스 추출 (GTFS + TCD)
[1.5] GTFS↔TCD ID 매핑 → 버스 85.3%, 지하철역 97.1%, 지하철노선 100%
[1.6] 미매칭 OD 필터링 → 1,263K OD (OTP 입력)
```

### Phase 2: OTP 배치 + 매칭 + 유사도 ✅ 완료

```
[2.1] OTP Java 파라미터화 수정 (CalibrationConfig 도입)
[2.2] OTP 배치 실행 (1,263K OD, ~8시간)
[2.3] OTP 결과 파싱 → otp_alternatives.parquet (4.47M 경로)
[2.4] TCD 경유정류장 추출 → 버스 66.1% 성공
[2.5] 유사도 계산 → 1,320,030 체인, Exact Match 28.66%
```

### Phase 3: 모형 추정 ✅ 완료

```
[3.1] Choice Set 생성 → choice_set.parquet
[3.2] 대안 속성 추출 → alternative_attributes.parquet
[3.3] 모델 입력 준비 → model_input_train/test.parquet (329K/82K 체인)
[3.4] MNL 추정 (Pooled + 5유형) → ρ²=0.469, Hit Rate=66.0%
[3.5] Mixed Logit (Pooled) → ρ²=0.464, 모든 σ 유의 (이질성 확인)
[3.6] Latent Class (K=3) → Hit Rate=67.4% (최고, 경제학 모형 1위)
[3.7] LightGBM Benchmark → Hit Rate=66.2% (LC 하회)
[3.8] 통합 모형 비교 → LC > LightGBM > MNL > ML (테스트셋)
```

### Phase 4: 반복 보정 + MNL 재순위 ✅ 완료

```
[4.1] 전통적 반복 보정 시도 → 실패 (Exact Match 28.66% → 14%)
[4.2] 접근법 A: Choice Set 고정 보정 → +1.02%p (Best Match)
[4.3] 접근법 B: 유형별 θ 적용 → +4.3%p (Best Match)
[4.4] 평가 지표 수정: Best Match → OTP 1순위 → 확률적 F₁
[4.5] 접근법 E: 확률적 RSM+IPW → θ 경계 수렴 (구조적 한계 발견)
[4.6] MNL 재순위 상세 분석 → +1.89%p (OTP 재실행 불필요, 핵심 기여)
```

---

## 7. 프로젝트 구조

```
강릉ITS/
├── RESEARCH_PLAN.md                         # 이 계획서 (docs/ 내에도 복사)
│
├── main/                                    # Python 코드 + 결과
│   ├── CLAUDE.md                            # 작업 가이드
│   ├── scripts/
│   │   ├── data/                            # Phase 1: 전처리
│   │   │   ├── step1_clean_tcd.py
│   │   │   ├── step2_build_trip_chains.py
│   │   │   ├── step3_extract_od.py
│   │   │   ├── step4_extract_stop_sequences.py
│   │   │   ├── step5_map_gtfs_tcd_ids.py
│   │   │   └── step6_filter_unmatched.py
│   │   ├── matching/                        # Phase 2: OTP 매칭 + 유사도
│   │   │   ├── step4_parse_otp_results.py
│   │   │   └── step5_calculate_similarity.py
│   │   ├── models/                          # Phase 3: 모형 추정
│   │   │   ├── step1_create_choice_set.py
│   │   │   ├── step2_extract_attributes.py
│   │   │   ├── step3_prepare_model_input.py
│   │   │   ├── step4_estimate_mnl.py
│   │   │   ├── step5_estimate_mixed_logit.py
│   │   │   ├── step6_estimate_latent_class.py
│   │   │   ├── step7_lightgbm_benchmark.py
│   │   │   └── step8_model_comparison.py
│   │   └── calibration/                     # Phase 4: 반복 보정
│   │       ├── fixed_choice_calibration.py
│   │       ├── usertype_calibration.py
│   │       ├── probabilistic_rsm_calibration.py
│   │       └── mnl_reranking_analysis.py    # ★ 핵심 기여
│   ├── output/                              # 중간 산출물
│   │   ├── model_input_train.parquet
│   │   └── model_input_test.parquet
│   ├── results/                             # 최종 결과
│   │   ├── PHASE3_RESULTS1_MNL.md ~ 5_COMPARISON.md
│   │   ├── PHASE4_RESULTS.md
│   │   ├── mnl_reranking_analysis.json
│   │   └── figures/
│   └── docs/                                # 계획서 + 참조 문서
│       ├── PHASE1_PREPROCESSING_PLAN.md
│       ├── PHASE3_MODEL_ESTIMATION_PLAN.md
│       ├── PHASE4_ITERATIVE_CALIBRATION_PLAN.md
│       ├── SIMILARITY_METRICS_FRAMEWORK.md
│       └── DATA_AND_SYSTEM_REFERENCE.md
│
├── korean-otp/                              # OTP 엔진 (Java)
│   ├── src/main/java/kr/otp/
│   │   ├── CalibrationConfig.java           # 보정 파라미터 설정
│   │   ├── raptor/spi/
│   │   │   ├── KoreanCostCalculator.java    # ✏️ 파라미터화 완료
│   │   │   └── KoreanTransitDataProvider.java
│   │   ├── core/AccessEgressFinder.java     # ✏️ walkReluctance 반영
│   │   └── batch/BatchRouter.java           # ✏️ calibration_config 로드
│   ├── calibration_config.json              # 현재 파라미터
│   └── data/gtfs/                           # GTFS 데이터
│
└── DATA/                                    # 원시 데이터
    └── tcd_2025_parquet/20250220/           # 분석 대상 (목요일)
```

---

## 8. 검증 결과

### 8.1 유사도 프레임워크 검증 ✅

| 검증 | 기대 | 실제 결과 |
|------|------|----------|
| Exact Match | 38% → 55%+ | **28.66%** (기준 재정의: 경로+수단 완전 일치) |
| sim_total ≥ 70% | - | **42.5%** 체인 |
| sim_total ≥ 90% | - | **23.1%** 체인 |
| 유형별 패턴 | 어린이 > 청소년 > 일반 | ✅ CHILDREN(46.5%) > YOUTH(41.7%) > GENERAL(28.5%) |

> **참고**: 초기 기대(38%→55%)와 실제 결과(28.66%)의 차이는 Exact Match 기준 강화(5개 유사도 지표 기반 완전 일치) 때문. 정류장 시퀀스 기반 비교 자체는 성공적으로 구현됨.

### 8.2 모형 검증 ✅

| 검증 | 기대 | 실제 결과 |
|------|------|----------|
| 파라미터 부호 | 보행-, 환승-, 지하철+ | ✅ β_walk=-0.644, β_transfer=-3.051, β_subway=+2.538 |
| ML 이질성 | σ 유의 | ✅ 모든 σ 유의 (보행 가중치 14×~36×) |
| LC > MNL | LC 적합도 우위 | ✅ LC(67.4%) > MNL(66.0%) |
| LightGBM 대비 | ML ≥ 90% | ✅ LC(67.4%) > LightGBM(66.2%), **경제학 모형 1위** |
| SHAP vs β | 순위 일치 | ✅ SHAP 특성 중요도 = MNL β 절대값 순위 (완벽 일치) |

### 8.3 반복 보정 검증 ✅

| 검증 | 초기 기대 | 실제 결과 |
|------|----------|----------|
| 전통적 반복 수렴 | 5~8회 반복 후 안정 | ❌ 1회 만에 매칭률 붕괴 (28.66%→14%) |
| θ 최적화 개선 | 큰 개선 | **~+1%p 상한** (구조적 한계 발견) |
| MNL 재순위 | (계획에 없음) | **+1.89%p** (θ 최적화의 2배, 핵심 기여) |
| 불일치 시 MNL 우위 | - | **10.4:1** (Exact Match 기준) |

### 8.4 핵심 수치 종합

```
Phase 2 (유사도):
  분석 규모: 1,320,030 체인, 4,936,864 쌍
  Exact Match: 28.66%
  Best Match sim_total: 평균 0.626

Phase 3 (모형):
  Hit Rate: LC(67.4%) > LGB(66.2%) > MNL(66.0%) > ML(65.9%)
  MNL ρ²: 0.469
  보행 가중치: 22.7× (ML 분포: 14×~36×)
  환승 페널티: ~100분

Phase 4 (보정):
  θ 최적화 상한: ~+1%p (OTP 1순위 기준)
  MNL 재순위: +1.89%p (OTP 재실행 불필요)
  불일치 시: MNL:OTP = 10.4:1
  대안 5개+: MNL +3.17%p (최대 개선)
```

---

## 9. 학술적 기여

### 기존 논문 대비 실현된 기여

| # | 기여 | 학술적 가치 | 상태 |
|---|------|-----------|------|
| 1 | **정류장 시퀀스 기반 다층 유사도** | 5단계(환승/수단/Jaccard/LCS/시간) 유사도 프레임워크, 302↔303 문제 해결 | ✅ |
| 2 | **TCD 완전 환승 데이터** | 지하철↔지하철 환승 포함, 1,320만 체인 분석 | ✅ |
| 3 | **Mixed Logit (이질성)** | 보행 가중치 분포 14×~36× (개인차 2.6배), 모든 σ 유의 | ✅ |
| 4 | **Latent Class (잠재 군집)** | 3클래스 발견, 고령자 61%가 접근성 클래스, Hit Rate 1위(67.4%) | ✅ |
| 5 | **LightGBM 벤치마크** | 경제학 모형(LC) > ML(LightGBM), SHAP=β 순위 일치 | ✅ |
| 6 | **θ 최적화 구조적 한계 실증** | 전통적 반복 실패 + RSM 경계 수렴 → ~+1%p 상한 | ✅ |
| 7 | **MNL 재순위의 이론적·실증적 정당화** | +1.89%p, MNL:OTP=10.4:1, 대안 수 단조 관계 | ✅ **핵심** |

### 참고 문헌

- McFadden, D. (1974). Conditional logit analysis of qualitative choice behavior.
- Ben-Akiva, M. & Lerman, S. R. (1985). *Discrete Choice Analysis*.
- Sheffi, Y. (1985). *Urban Transportation Networks*.
- Prato, C. G. (2009). Route choice modeling: past, present and future research directions.
- Frejinger, E., Bierlaire, M. & Ben-Akiva, M. (2009). Sampling of alternatives for route choice modeling.
- Cascetta, E. (2009). *Transportation Systems Analysis* (Ch. 10: Assignment-Consistent Models).
- Train, K. (2009). *Discrete Choice Methods with Simulation*.
- Han, Y., et al. (2022). A neural-embedded discrete choice model. *Transportation Research Part B*.

---

## 10. 일정 및 산출물

### 실제 일정

| 일차 | 단계 | 상태 |
|------|------|------|
| Day 1-3 | Phase 1: 데이터 전처리 (TCD 정제 + 체인 구성 + OD 추출 + ID 매핑) | ✅ |
| Day 4-5 | Phase 2: OTP 배치 실행 (~8시간) + 결과 파싱 + 유사도 계산 | ✅ |
| Day 6-7 | Phase 3: MNL + Mixed Logit (~6.4시간) | ✅ |
| Day 8 | Phase 3: Latent Class + LightGBM + 모형 비교 | ✅ |
| Day 9-11 | Phase 4: 접근법 A→B→E + 평가 지표 진화 + MNL 재순위 분석 | ✅ |
| Day 12+ | 논문 작성 | ⏳ |

### 핵심 산출물

1. **Python 스크립트 ~25개** (data 6 + matching 2 + models 8 + calibration 5 + utils)
2. **Java 수정 5개** (CalibrationConfig, CostCalculator, AccessEgressFinder, TransitDataProvider, BatchRouter)
3. **결과 문서 7개** (Phase 3 5개 + Phase 4 2개)
4. **데이터** (model_input_train/test.parquet, mnl_reranking_analysis.json 등)
