# Transit Route Similarity Metrics Framework
# 대중교통 경로 유사도 평가 프레임워크

## 1. 연구 배경 및 목적

### 1.1 기존 연구의 한계
- 단일 지표(완전 일치율) 의존
- 부분 일치 경로에 대한 정량적 평가 부재
- 버스/지하철 데이터 특성 차이 미고려

### 1.2 본 연구의 기여
1. **다층적 유사도 체계**: 4개 레벨, 10개 세부 지표
2. **데이터 특성 반영**: 버스(시퀀스)/지하철(포인트) 차별화
3. **학술적 엄밀성**: 수학적 정의 + 통계적 검증
4. **재현성**: 오픈소스 구현 + 상세 문서화

---

## 2. 데이터 구조

### 2.1 TCD 관측 경로 (Observed Path)
```
P_obs = {
    chain_id: 고유 식별자,
    legs: [
        {
            mode: BUS | SUBWAY,
            route_id: 노선 ID (TCD),
            boarding_stop: 승차 정류장 ID,
            alighting_stop: 하차 정류장 ID,
            traversed_stops: [정류장 시퀀스] (버스만, 66.1%)
        },
        ...
    ]
}
```

### 2.2 OTP 대안 경로 (Alternative Path)
```
P_alt = {
    od_id: OD 쌍 식별자,
    alt_id: 대안 번호 (1~10),
    route_ids: [노선 ID 시퀀스] (GTFS),
    modes: [수단 시퀀스],
    stop_sequence: [전체 정류장 시퀀스] (GTFS ID),
    boarding_stops: [승차 정류장 시퀀스],
    alighting_stops: [하차 정류장 시퀀스],
    n_transfers: 환승 횟수,
    total_duration: 총 소요시간 (초),
    ride_time_sec: 차내 시간,
    walk_time_sec: 도보 시간
}
```

### 2.3 ID 매핑
- TCD 정류장 ID ↔ GTFS 정류장 ID: 좌표 기반 KD-Tree 매핑 (버스 50m, 지하철 100m)
- TCD 노선 ID ↔ GTFS 노선 ID: 노선명 기반 매핑 (버스 85.3%, 지하철 100%)

---

## 3. 유사도 지표 정의

### Level 1: Exact Match Rate (EMR)

**정의**: 관측 경로와 대안 경로가 완전히 일치하는 비율

```
EMR = (완전 일치 OD 수) / (전체 OD 수)
```

**완전 일치 조건**:
1. 노선 시퀀스 동일: routes(P_obs) = routes(P_alt)
2. 수단 시퀀스 동일: modes(P_obs) = modes(P_alt)
3. 승하차 정류장 동일: boarding/alighting stops 일치

**K-경로 확장**:
```
EMR@K = (K개 대안 중 하나라도 일치하는 OD 수) / (전체 OD 수)
```

**참고 문헌 비교**:
- 서울 연구 (환승 0회): 84%
- 서울 연구 (환승 1회): 88%
- 개선된 RAPTOR (K=5): 91.4%

---

### Level 2: Structural Similarity (SS)

#### 2a. Route Sequence Similarity (RSS)

**정의**: 노선 시퀀스의 LCS 기반 유사도

```
RSS(P_obs, P_alt) = 2 × LCS(R_obs, R_alt) / (|R_obs| + |R_alt|)
```

여기서:
- R_obs = [r1, r2, ...]: 관측 경로의 노선 시퀀스
- R_alt = [r1, r2, ...]: 대안 경로의 노선 시퀀스
- LCS: Longest Common Subsequence 길이

**범위**: [0, 1], 1이면 완전 일치

#### 2b. Mode Sequence Similarity (MSS)

**정의**: 수단 시퀀스의 일치율

```
MSS(P_obs, P_alt) = 2 × LCS(M_obs, M_alt) / (|M_obs| + |M_alt|)
```

여기서:
- M_obs = [BUS, SUBWAY, ...]: 관측 경로의 수단 시퀀스
- M_alt = [BUS, SUBWAY, ...]: 대안 경로의 수단 시퀀스

#### 2c. Transfer Count Similarity (TCS)

**정의**: 환승 횟수 일치 여부 (이진)

```
TCS(P_obs, P_alt) = 1 if n_transfers(P_obs) = n_transfers(P_alt) else 0
```

**확장**: 환승 횟수 차이 기반 연속 지표
```
TCS_cont(P_obs, P_alt) = 1 / (1 + |n_obs - n_alt|)
```

---

### Level 3: Stop-based Similarity

#### 3a. Jaccard Index (JI)

**정의**: 정류장 집합의 교집합/합집합 비율

```
JI(P_obs, P_alt) = |S_obs ∩ S_alt| / |S_obs ∪ S_alt|
```

여기서:
- S_obs = {s1, s2, ...}: 관측 경로의 정류장 집합
- S_alt = {s1, s2, ...}: 대안 경로의 정류장 집합

**특징**:
- 순서 무시
- 범위: [0, 1]
- 버스 + 지하철 모두 적용 가능 (승하차 정류장만으로도 계산)

#### 3b. LCS Ratio (LCSR)

**정의**: 정류장 시퀀스의 LCS 기반 유사도

```
LCSR(P_obs, P_alt) = 2 × LCS(S_obs, S_alt) / (|S_obs| + |S_alt|)
```

**특징**:
- 순서 고려 (시퀀스 유사도)
- 범위: [0, 1]
- **버스 전용**: 지하철은 경유 정류장 시퀀스 없음

#### 3c. LCSWT (LCS with Tolerance)

**정의**: 공간적 근접성을 허용하는 LCS 변형

기존 LCS는 정확한 ID 일치만 인정하지만, LCSWT는 근접 정류장(예: 300m 이내)도 부분 매칭으로 인정

```python
def lcswt_match(stop1, stop2, threshold=300):
    """
    두 정류장이 매칭되는지 확인
    - 동일 ID: 1.0점
    - threshold 이내 거리: 거리에 반비례하는 점수
    """
    if stop1 == stop2:
        return 1.0
    dist = haversine(coord(stop1), coord(stop2))
    if dist <= threshold:
        return 1.0 - (dist / threshold)  # 거리에 따른 감쇠
    return 0.0
```

**LCSWT 알고리즘**:
```python
def lcswt(seq1, seq2, threshold=300):
    n, m = len(seq1), len(seq2)
    dp = [[0.0] * (m+1) for _ in range(n+1)]

    for i in range(1, n+1):
        for j in range(1, m+1):
            match_score = lcswt_match(seq1[i-1], seq2[j-1], threshold)
            dp[i][j] = max(
                dp[i-1][j],      # skip seq1[i]
                dp[i][j-1],      # skip seq2[j]
                dp[i-1][j-1] + match_score  # match with score
            )

    return dp[n][m]
```

**정규화**:
```
LCSWT_sim(P_obs, P_alt) = 2 × LCSWT(S_obs, S_alt) / (|S_obs| + |S_alt|)
```

**특징**:
- 근접 정류장 부분 매칭 허용
- samplet.MD에서 제안된 공간적 근접성 고려
- **버스 전용**

#### 3d. Boarding/Alighting Match Rate (BAMR)

**정의**: 승하차 정류장 일치율

```
BAMR(P_obs, P_alt) = Σ(match_score) / (2 × n_legs)
```

여기서:
- n_legs: 레그 수
- match_score: 각 레그의 승차점 + 하차점 일치 여부 (0 또는 1)

**근접 매칭 확장**:
```
BAMR_tol(P_obs, P_alt) = Σ(proximity_score) / (2 × n_legs)
```
- proximity_score: 300m 이내면 거리에 반비례하는 점수

**특징**:
- 버스 + 지하철 모두 적용 가능
- 경유 정류장 없이도 계산 가능

---

### Level 4: Temporal Similarity

#### 4a. Total Time Difference (TTD)

**정의**: 총 소요시간 차이

```
TTD(P_obs, P_alt) = |T_obs - T_alt|
```

**정규화 (유사도로 변환)**:
```
TTS(P_obs, P_alt) = 1 / (1 + TTD / baseline)
```
- baseline: 평균 통행시간 (예: 30분 = 1800초)

**참고**: TCD에는 실제 소요시간이 있고, OTP는 예측 소요시간 제공

#### 4b. In-Vehicle Time Difference (IVTD)

**정의**: 차내 시간 차이

```
IVTD(P_obs, P_alt) = |IVT_obs - IVT_alt|
```

#### 4c. Walk Time Difference (WTD)

**정의**: 도보 시간 차이

```
WTD(P_obs, P_alt) = |WT_obs - WT_alt|
```

**참고**: TCD에는 도보 시간 정보 없음 → OTP 대안 간 비교에만 사용

---

## 4. 종합 유사도 지표

### 4.1 가중 평균 유사도 (Weighted Average Similarity)

```
SIM_total = w1×EMR + w2×RSS + w3×MSS + w4×JI + w5×LCSR + w6×BAMR + w7×TTS
```

가중치 예시 (경험적 설정):
- w1 = 0.15 (완전 일치)
- w2 = 0.20 (노선 시퀀스)
- w3 = 0.10 (수단 시퀀스)
- w4 = 0.15 (정류장 집합)
- w5 = 0.20 (정류장 시퀀스 - 버스만)
- w6 = 0.10 (승하차점)
- w7 = 0.10 (시간)

### 4.2 계층적 유사도 (Hierarchical Similarity)

단계별 필터링 접근:
1. Level 1 통과 → 완전 일치
2. Level 2 통과 (RSS ≥ 0.8) → 구조적 유사
3. Level 3 통과 (JI ≥ 0.5) → 정류장 유사
4. Level 4 통과 (TTS ≥ 0.8) → 시간적 유사

### 4.3 버스/지하철 차별화 지표

**버스 레그**: 모든 지표 적용 가능
```
SIM_bus = 0.2×RSS + 0.3×LCSWT + 0.2×JI + 0.2×BAMR + 0.1×TTS
```

**지하철 레그**: LCSR/LCSWT 제외
```
SIM_subway = 0.3×RSS + 0.3×JI + 0.3×BAMR + 0.1×TTS
```

**혼합 경로**: 레그별 가중 평균
```
SIM_mixed = (Σ SIM_leg × leg_weight) / (Σ leg_weight)
```
- leg_weight: 해당 레그의 차내시간 비율

---

## 5. 통계적 검증 방법

### 5.1 지표 간 상관분석
- Pearson/Spearman 상관계수로 지표 간 중복성 확인
- 다중공선성 진단

### 5.2 Sensitivity Analysis
- 파라미터 변화에 따른 유사도 변화 분석
- threshold (300m), 가중치 등

### 5.3 Bootstrap Confidence Interval
- 각 지표의 95% 신뢰구간 산출
- 샘플 크기: 1.26M OD → 충분한 통계적 검정력

### 5.4 Comparison with Baseline
- 개선 전/후 RAPTOR 비교
- 환승 페널티 적용 효과

---

## 6. 구현 전략

### 6.1 Step 5a: ID 매핑 적용
- TCD 정류장 ID → GTFS 정류장 ID 변환
- TCD 노선 ID → GTFS 노선 ID 변환
- 매핑 실패 레코드 제외 (이미 Step 6에서 필터링됨)

### 6.2 Step 5b: 레그 단위 유사도 계산
- 각 TCD 레그 vs OTP 대안의 해당 레그 비교
- 버스/지하철 구분하여 적용 가능한 지표만 계산

### 6.3 Step 5c: 경로 단위 유사도 집계
- 레그별 유사도를 경로 전체로 집계
- 가중 평균 (차내시간 기준)

### 6.4 Step 5d: OD 단위 대안 순위화
- 각 OD의 K개 대안을 유사도 순으로 정렬
- Best match 선정

### 6.5 출력 파일
```
similarity_results.parquet:
- od_id
- chain_id
- alt_id
- sim_exact_match (Level 1)
- sim_route_seq (Level 2a)
- sim_mode_seq (Level 2b)
- sim_transfer_count (Level 2c)
- sim_jaccard (Level 3a)
- sim_lcs (Level 3b)
- sim_lcswt (Level 3c)
- sim_boarding_alighting (Level 3d)
- sim_time (Level 4a)
- sim_total (가중 평균)
- is_best_match (이 대안이 최고 유사도인지)
```

---

## 7. 예상 결과 및 학술적 기여

### 7.1 예상 결과
- EMR@1: 50-60% (단일 최적 경로)
- EMR@10: 80-90% (Pareto 최적 경로 집합)
- 평균 유사도: 0.7-0.8 (가중 평균)

### 7.2 학술적 기여
1. **다층적 유사도 체계**: 단일 지표의 한계 극복
2. **LCSWT 적용**: 공간적 근접성을 고려한 시퀀스 유사도
3. **대규모 검증**: 126만 OD, 450만 대안 경로
4. **버스/지하철 차별화**: 데이터 특성에 맞는 지표 적용
5. **재현성**: 오픈소스 코드 + 상세 문서

### 7.3 한계 및 향후 연구
- 지하철 경유역 정보 부재 → 네트워크 기반 추정 가능
- 시간대별 변동 미반영 → 피크/비피크 구분 분석
- 선호 이질성 미반영 → Mixed Logit으로 확장 (Phase 4)

---

## 8. 참고문헌 요약

| 지표 | 출처 | 특징 |
|------|------|------|
| Exact Match | 서울 연구 (84-88%) | 가장 엄격한 기준 |
| Jaccard Index | 경로 유사성 연구 | 집합 기반, 순서 무시 |
| LCS | 편집거리 기반 | 순서 고려 |
| LCSWT | samplet.MD | 공간적 근접성 허용 |
| CSI | 벡터 공간 모델 | 확률 기반 |
| MAE/RMSE | MDPI 연구 | 시간 차이 평가 |
| 동적 페널티 | 개선된 RAPTOR | 환승 페널티 효과 (48.5%→58.8%) |

---

## 부록: 수학적 표기 정리

| 기호 | 의미 |
|------|------|
| P_obs | 관측 경로 (TCD) |
| P_alt | 대안 경로 (OTP) |
| S | 정류장 시퀀스 |
| R | 노선 시퀀스 |
| M | 수단 시퀀스 |
| LCS(X, Y) | X, Y의 최장 공통 부분수열 길이 |
| LCSWT(X, Y) | 공간적 근접성 허용 LCS 점수 |
| JI(X, Y) | Jaccard Index = |X∩Y| / |X∪Y| |
| δ(X, Y) | 불일치도 = 1 - 2×LCS/(|X|+|Y|) |
