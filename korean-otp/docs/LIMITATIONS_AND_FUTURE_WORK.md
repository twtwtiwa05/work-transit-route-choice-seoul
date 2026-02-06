# 한계점 및 향후 개선사항

본 문서는 Korean Raptor 프로젝트의 현재 한계점과 향후 개선 방향을 정리합니다.

---

## 목차

1. [현재 한계점](#1-현재-한계점)
2. [향후 개선사항](#2-향후-개선사항)
3. [기술적 부채](#3-기술적-부채)

---

## 1. 현재 한계점

### 1.1 Raptor 프로파일 ✅ 해결됨

#### 현재 상태

두 가지 검색 모드 모두 ~0.35초 이내 검색 가능:

| 프로파일 | 검색 시간 | 경로 수 | 결과 특성 |
|----------|----------|--------|----------|
| STANDARD | ~0.35초 | 4개 | 시간 기준 최적 경로 |
| MULTI_CRITERIA | **~0.35초** | **11개** | 파레토 최적 경로 (시간/환승/비용 다양) |

#### 최적화 적용 내용

기존 MULTI_CRITERIA는 ~14초가 걸렸으나, 다음 최적화로 **40배 개선** (~0.35초):

```java
// KoreanRaptor.java에 적용된 최적화 설정
MC_SEARCH_WINDOW_SECONDS = 900    // STANDARD와 동일 (15분)
MC_ADDITIONAL_TRANSFERS = 3        // STANDARD와 동일 (3회)
MC_RELAX_RATIO = 1.0               // relaxC1 비활성화 (핵심!)
MC_RELAX_SLACK = 0                 // relaxC1 비활성화

// 적용된 OTP 기능
Optimization.PARETO_CHECK_AGAINST_DESTINATION  // 목적지 조기 가지치기
```

#### 핵심 발견

**relaxC1 비활성화가 성능 향상의 핵심:**
- relaxC1 활성화: 파레토 지배 조건 완화 → 더 많은 해 생존 → 느려짐
- relaxC1 비활성화: 엄격한 파레토 지배 → 불필요한 해 제거 → 빨라짐

**결과:** MC가 STD와 동일한 속도(~0.35초)로 **2.75배 더 많은 경로**(11개 vs 4개) 제공!

#### CLI 사용법

```
[STD, n=5] > mc                    # MULTI_CRITERIA 모드 전환
[MC, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00
검색 [MULTI_CRITERIA]: ... (0.350초)
■ 경로 1: 09:00 출발 → 09:40 도착 (39분, 환승 2회)  ← 시간 최적
■ 경로 2: 09:02 출발 → 09:48 도착 (45분, 환승 1회)  ← 환승 최적
```

### 1.2 불필요한 환승 버그 ✅ 해결됨

#### 문제점

지하철 직행 경로가 표시되지 않고, 불필요한 버스 환승이 추가되는 버그:

```
예: 서울역 → 홍대입구 (공항철도 직행 가능)
문제: 공항철도 → 환승 도보 → 버스 → 목적지 (환승 1회)
기대: 공항철도 → 도보 → 목적지 (환승 0회)
```

#### 원인

Access/Egress 후보 수가 너무 적어서(5개) 버스 정류장만 선택되고 지하철역이 제외됨.

#### 해결

```java
// AccessEgressFinder.java
MAX_STOPS = 30              // 10 → 30
osmCandidateLimit = 30      // 5 → 30

// KoreanRaptor.java
MAX_ACCESS_STOPS = 30       // 10 → 30
MAX_EGRESS_STOPS = 30       // 10 → 30
```

#### 결과

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 환승 | 1회 | **0회** |
| 소요시간 | 22분 | **16분** |
| 검색시간 | 0.487초 | **0.314초** |

### 1.3 OSM 메모리 사용량

#### 문제점

OSM 기반 도보 경로 사용 시 **40GB+ RAM**이 필요합니다.

| 모드 | 메모리 | 정확도 |
|------|--------|--------|
| Haversine (직선) | 8GB | 보통 |
| OSM (실제 도로) | 40GB+ | 높음 |

#### 원인

```
한국 OSM 데이터:
- 노드: 15,711,249개
- 엣지: 3,547,892개
- 각 노드: ~100 bytes (좌표, 엣지 리스트)
- 공간 인덱스: ~500MB

총 메모리: ~15GB (그래프) + ~10GB (JVM 오버헤드) + ~10GB (여유)
```

### 1.4 초기화 시간

#### 문제점

서버 시작 시 **~60초**의 초기화 시간이 필요합니다.

| 단계 | 시간 | 내용 |
|------|------|------|
| GTFS 로드 | ~8초 | 21만 정류장, 35만 트립 |
| TransitData 빌드 | ~4초 | 패턴 그룹화, 환승 생성 |
| OSM 로드 | ~45초 | 15M 노드 그래프 구축 |
| 엔진 초기화 | ~3초 | 정류장-노드 매핑 |

### 1.5 실시간 데이터 미지원

현재 **정적 GTFS**만 지원하며, 실시간 정보(GTFS-RT)는 지원하지 않습니다.

- 실시간 도착 정보 미반영
- 지연/운휴 정보 미반영
- 실시간 혼잡도 미반영

### 1.6 경로 품질 제한

#### 도보 경로 정확도

- A* 탐색 거리 제한: 500m
- 최대 반복 횟수: 15,000
- 제한 초과 시 직선 거리 × 1.3 사용

#### 환승 정보

- 거리 기반 환승만 지원 (500m 이내)
- 실제 환승 통로/시간 미반영
- 동일 역사 내 환승 최적화 없음

---

## 2. 향후 개선사항

### 2.1 MULTI_CRITERIA 성능 개선 ✅ 완료

OTP 외부 설정만으로 14초 → 0.35초 (**40배 개선**) 달성.

적용된 최적화:
- **relaxC1 비활성화**: 엄격한 파레토 지배 → 불필요한 해 빠르게 제거 (핵심!)
- **PARETO_CHECK_AGAINST_DESTINATION**: 목적지 기준 조기 가지치기
- **STANDARD와 동일 조건**: 15분 윈도우, 3회 환승 (탐색 공간 동일)

**결과:** MC가 STD와 동일 속도(~0.35초)로 2.75배 더 많은 경로(11개 vs 4개) 제공!

자세한 내용은 [1.1 Raptor 프로파일](#11-raptor-프로파일--해결됨) 참조.

### 2.2 불필요한 환승 버그 수정 ✅ 완료

Access/Egress 후보 수를 30개로 확대하여 지하철역이 누락되는 문제 해결.

자세한 내용은 [1.2 불필요한 환승 버그](#12-불필요한-환승-버그--해결됨) 참조.

### 2.3 메모리 최적화 (우선순위: 중간)

#### 방안 1: OSM 그래프 압축

```java
// 현재: HashMap<Long, StreetNode>
// 개선: 배열 기반 저장 (메모리 50% 절감)
long[] nodeIds;
double[] lats;
double[] lons;
int[][] adjacencyList;
```

#### 방안 2: 지역별 분할 로딩

```java
// 서울/경기만 로드
OsmLoader loader = new OsmLoader(osmPath)
    .withBoundingBox(37.0, 126.5, 38.0, 127.5);
```

#### 방안 3: 메모리 맵 파일 (mmap)

```java
// 디스크 기반 그래프 (느리지만 메모리 절약)
MappedByteBuffer graphBuffer = fileChannel.map(...);
```

### 2.4 실시간 데이터 지원 (우선순위: 중간)

#### GTFS-RT 연동

```java
// 실시간 업데이트
GtfsRealtimeLoader rtLoader = new GtfsRealtimeLoader(rtUrl);
rtLoader.onUpdate(update -> {
    transitData.applyRealtimeUpdate(update);
});
```

#### 지원 예정 기능

- TripUpdate: 지연/운휴 정보
- VehiclePosition: 차량 위치
- Alert: 서비스 알림

### 2.5 API 서버화 (우선순위: 중간)

#### REST API

```
GET /api/v1/route?
    from=37.5547,126.9707&
    to=37.4979,127.0276&
    time=09:00&
    date=2026-01-12
```

#### 응답 형식

```json
{
  "routes": [
    {
      "departureTime": "09:03",
      "arrivalTime": "09:45",
      "duration": 42,
      "transfers": 2,
      "legs": [...]
    }
  ],
  "searchTime": 0.487
}
```

### 2.6 정류장 검색 최적화 (우선순위: 낮음)

#### R-tree 공간 인덱스

```java
// 현재: 선형 검색 O(N)
for (int i = 0; i < stopCount; i++) {
    if (distance(lat, lon, stopLats[i], stopLons[i]) < maxDistance) {
        candidates.add(i);
    }
}

// 개선: R-tree O(log N)
RTree<Integer> stopIndex = RTree.create();
List<Integer> candidates = stopIndex.search(
    Geometries.circle(lat, lon, maxDistance)
);
```

### 2.7 멀티모달 지원 (우선순위: 낮음)

#### 추가 교통수단

- 공유 자전거 (따릉이 등)
- 전동 킥보드
- 택시/카풀

---

## 3. 기술적 부채

### 3.1 테스트 부족

- 단위 테스트 미작성
- 통합 테스트 미작성
- 성능 벤치마크 미구축

### 3.2 에러 처리

- GTFS 파일 형식 오류 시 상세 메시지 부족
- OSM 파일 손상 시 복구 로직 없음
- 검색 실패 시 대안 경로 제안 없음

### 3.3 로깅/모니터링

- 검색 성능 메트릭 수집 없음
- 오류 추적 시스템 미연동
- 사용 통계 수집 없음

### 3.4 문서화

- API 문서 (Javadoc) 부족
- 코드 주석 일부 누락
- 아키텍처 결정 기록(ADR) 없음

---

## 개선 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| Phase 1 | MULTI_CRITERIA 최적화 | ✅ **완료** (14초 → 0.35초, 40배 개선) |
| Phase 1.5 | 불필요한 환승 버그 수정 | ✅ **완료** (Access/Egress 30개 확대) |
| Phase 2 | API 서버화 (Spring Boot) | ⏳ 예정 |
| Phase 3 | GTFS-RT 연동 | ⏳ 예정 |
| Phase 4 | 메모리 최적화 | ⏳ 예정 |
| Phase 5 | 테스트 코드 작성 | ⏳ 예정 |

---

## 참고

- [OTP Raptor 소스코드](https://github.com/opentripplanner/OpenTripPlanner/tree/dev-2.x/raptor)
- [GTFS-RT Specification](https://gtfs.org/realtime/)
- [R-tree 라이브러리](https://github.com/davidmoten/rtree)

---

**작성일**: 2026-01
**작성자**: 김태우 (가천대학교 CAMMUS 연구원)
