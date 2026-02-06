# Korean Raptor 기술 아키텍처 문서

**한국 전국 대중교통 경로탐색 엔진 - 시스템 설계 및 구현 상세**

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [OTP Raptor 알고리즘 이해](#3-otp-raptor-알고리즘-이해)
4. [GTFS 데이터 통합](#4-gtfs-데이터-통합)
5. [SPI 구현체 설계](#5-spi-구현체-설계)
6. [OSM 도보 경로 시스템](#6-osm-도보-경로-시스템)
7. [성능 최적화](#7-성능-최적화)
8. [데이터 흐름](#8-데이터-흐름)
9. [핵심 알고리즘 상세](#9-핵심-알고리즘-상세)
10. [결론](#10-결론)

---

## 1. 프로젝트 개요

### 1.1 목표

본 프로젝트는 **OpenTripPlanner(OTP)의 Raptor 모듈**을 활용하여 한국 전국 대중교통 경로탐색을 수행하는 고성능 CLI 엔진을 개발하는 것을 목표로 합니다.

**핵심 목표:**
- 출발/도착 좌표 입력 → **0.5초 이내** 경로 결과 출력
- OTP Raptor JAR를 **수정 없이** 그대로 사용
- SPI(Service Provider Interface)만 구현하여 한국 GTFS 데이터 연결
- OSM 기반 **실제 도보 경로** 거리 계산 지원

### 1.2 달성 성과

| 항목 | 값 |
|------|-----|
| 정류장 | 212,105개 |
| 노선(패턴) | 32,229개 |
| 트립 | 349,509개 |
| 환승 | 2,027,380개 |
| OSM 노드 | 15,711,249개 |
| **초기화 시간** | ~60초 |
| **검색 시간** | **~0.35초** |

### 1.3 지원 교통수단

- 시내버스, 광역버스, 마을버스
- 지하철, 도시철도
- KTX, SRT (고속철도)
- 일반철도 (무궁화, 새마을, ITX)

---

## 2. 시스템 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Korean Raptor Engine                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────────────┐ │
│  │   사용자 입력    │    │   CLI / Main   │    │      결과 출력          │ │
│  │ (좌표, 시간)    │───▶│    진입점      │───▶│   (경로, 시간표)        │ │
│  └────────────────┘    └───────┬────────┘    └────────────────────────┘ │
│                                │                                         │
│                    ┌───────────▼───────────┐                             │
│                    │    KoreanRaptor       │                             │
│                    │    (메인 엔진)         │                             │
│                    └───────────┬───────────┘                             │
│                                │                                         │
│         ┌──────────────────────┼──────────────────────┐                  │
│         │                      │                      │                  │
│         ▼                      ▼                      ▼                  │
│  ┌──────────────┐    ┌─────────────────┐    ┌─────────────────────────┐ │
│  │AccessEgress  │    │   TransitData   │    │  KoreanTransitData      │ │
│  │   Finder     │    │   (정류장/노선)  │    │     Provider (SPI)      │ │
│  └──────┬───────┘    └────────┬────────┘    └───────────┬─────────────┘ │
│         │                     │                         │                │
│         ▼                     │                         ▼                │
│  ┌──────────────┐             │              ╔═════════════════════════╗ │
│  │WalkingRouter │             │              ║                         ║ │
│  │  (A* 알고리즘) │            │              ║   OTP Raptor JAR        ║ │
│  └──────┬───────┘             │              ║   (외부 라이브러리)       ║ │
│         │                     │              ║                         ║ │
│         ▼                     │              ╚════════════╤════════════╝ │
│  ┌──────────────┐             │                          │               │
│  │StreetNetwork │             │                          ▼               │
│  │ (15M 노드)   │             │              ┌───────────────────────┐   │
│  └──────┬───────┘             │              │   RaptorPath 결과     │   │
│         │                     │              │   (경로 목록)         │   │
│         ▼                     ▼              └───────────────────────┘   │
│  ┌──────────────┐    ┌─────────────────┐                                 │
│  │  OsmLoader   │    │TransitDataBuilder│                                │
│  │ (PBF 파서)   │    │  (GTFS 변환)    │                                 │
│  └──────┬───────┘    └────────┬────────┘                                 │
│         │                     │                                          │
│         ▼                     ▼                                          │
│  ┌──────────────┐    ┌─────────────────┐                                 │
│  │south-korea   │    │   GtfsLoader    │                                 │
│  │  .osm.pbf    │    │  (CSV 파서)     │                                 │
│  └──────────────┘    └────────┬────────┘                                 │
│                               │                                          │
│                               ▼                                          │
│                      ┌─────────────────┐                                 │
│                      │   GTFS 파일들    │                                 │
│                      │ (stops, routes,  │                                 │
│                      │  trips, ...)    │                                 │
│                      └─────────────────┘                                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 계층 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│                    (Main.java - CLI)                         │
├─────────────────────────────────────────────────────────────┤
│                     Core Layer                               │
│            (KoreanRaptor, AccessEgressFinder)                │
├─────────────────────────────────────────────────────────────┤
│                      SPI Layer                               │
│    (KoreanTransitDataProvider, KoreanTripSchedule, ...)     │
├─────────────────────────────────────────────────────────────┤
│                     Data Layer                               │
│        (TransitData, TransitDataBuilder, GtfsBundle)        │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                       │
│     (GtfsLoader, OsmLoader, StreetNetwork, WalkingRouter)   │
├─────────────────────────────────────────────────────────────┤
│                   External Libraries                         │
│         (OTP Raptor JAR, osm4j, OpenCSV, SLF4J)             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 모듈 구성

```
korean-otp/
├── src/main/java/kr/otp/
│   │
│   ├── Main.java                    # CLI 진입점
│   │
│   ├── core/                        # 핵심 엔진
│   │   ├── KoreanRaptor.java        # Raptor 래퍼 (메인 엔진)
│   │   └── AccessEgressFinder.java  # 좌표→정류장 검색
│   │
│   ├── gtfs/                        # GTFS 데이터 처리
│   │   ├── model/                   # 데이터 모델
│   │   │   ├── GtfsStop.java
│   │   │   ├── GtfsRoute.java
│   │   │   ├── GtfsTrip.java
│   │   │   └── GtfsStopTime.java
│   │   ├── loader/
│   │   │   └── GtfsLoader.java      # CSV 파서
│   │   └── GtfsBundle.java          # GTFS 데이터 컨테이너
│   │
│   ├── raptor/
│   │   ├── data/                    # Raptor용 데이터 구조
│   │   │   ├── TransitData.java     # 정류장/노선/환승 저장
│   │   │   └── TransitDataBuilder.java  # GTFS → TransitData 변환
│   │   │
│   │   └── spi/                     # ★ OTP SPI 구현체
│   │       ├── KoreanTransitDataProvider.java  # 최상위 Provider
│   │       ├── KoreanTripSchedule.java         # 트립 시간표
│   │       ├── KoreanTripPattern.java          # 정류장 패턴
│   │       ├── KoreanRoute.java                # 노선 정보
│   │       ├── KoreanTimeTable.java            # 시간표
│   │       ├── KoreanTransfer.java             # 환승 정보
│   │       ├── KoreanAccessEgress.java         # 출발/도착 연결
│   │       └── ...
│   │
│   └── osm/                         # OSM 도보 경로
│       ├── OsmLoader.java           # PBF 파서 (2-pass)
│       ├── StreetNetwork.java       # 도로망 그래프
│       ├── StreetNode.java          # 노드 (교차점)
│       ├── StreetEdge.java          # 엣지 (도로)
│       └── WalkingRouter.java       # A* 경로 탐색
│
├── libs/                            # 외부 라이브러리
│   ├── raptor-2.9.0-SNAPSHOT.jar    # OTP Raptor 모듈
│   └── utils-2.9.0-SNAPSHOT.jar     # OTP Utils 모듈
│
└── data/
    ├── gtfs/                        # GTFS 데이터
    └── osm/                         # OSM 데이터
```

---

## 3. OTP Raptor 알고리즘 이해

### 3.1 Raptor 알고리즘 개요

**RAPTOR (Round-bAsed Public Transit Optimized Router)**는 Microsoft Research에서 2012년 발표한 대중교통 경로탐색 알고리즘입니다.

**핵심 특징:**
- **Round-based**: 환승 횟수(round)별로 탐색
- **배열 기반**: Dijkstra의 그래프 탐색 대신 배열 스캔
- **Pareto 최적**: 시간-환승 횟수 다중 목표 최적화

### 3.2 알고리즘 동작 원리

```
Round 0: 출발지에서 도보로 도달 가능한 정류장 초기화
         τ₀[p] = 도보 시간 (access stop)

Round k (k = 1, 2, ...):
  1. 이전 라운드에서 갱신된 정류장을 지나는 모든 노선 수집
  2. 각 노선에서 가장 빠른 트립 탑승 → 모든 정류장 하차 시간 계산
  3. 하차 정류장에서 환승 가능한 정류장으로 도보 이동
  4. 목적지에 도달했는지 확인

종료: 더 이상 갱신되는 정류장이 없을 때
```

### 3.3 OTP Raptor SPI 구조

OpenTripPlanner의 Raptor 모듈은 **SPI(Service Provider Interface)** 패턴을 사용합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    OTP Raptor Core                           │
│              (알고리즘 구현 - 수정 불가)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   RaptorService.route(request, provider)                     │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────────────────────────────────────────────┐   │
│   │        RaptorTransitDataProvider<T>                 │   │
│   │              (SPI 인터페이스)                         │   │
│   │                                                      │   │
│   │   + numberOfStops(): int                            │   │
│   │   + getTransfersFromStop(stop): Iterator<Transfer>  │   │
│   │   + routeIndexIterator(stops): IntIterator          │   │
│   │   + getRouteForIndex(idx): RaptorRoute<T>           │   │
│   │   + slackProvider(): RaptorSlackProvider            │   │
│   │   + multiCriteriaCostCalculator(): CostCalculator   │   │
│   └─────────────────────────────────────────────────────┘   │
│                           ▲                                  │
│                           │ 구현                             │
│                           │                                  │
└───────────────────────────┼─────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            │    KoreanTransitDataProvider   │
            │        (우리의 구현체)           │
            └────────────────────────────────┘
```

**핵심 인터페이스:**

| 인터페이스 | 역할 |
|-----------|------|
| `RaptorTransitDataProvider<T>` | 최상위 데이터 제공자 |
| `RaptorRoute<T>` | 노선 (패턴 + 시간표) |
| `RaptorTripPattern` | 정류장 순서 패턴 |
| `RaptorTripSchedule` | 트립 시간표 |
| `RaptorTimeTable` | 시간표 검색 |
| `RaptorTransfer` | 환승 정보 |
| `RaptorAccessEgress` | 출발/도착 연결 |

---

## 4. GTFS 데이터 통합

### 4.1 GTFS 개요

**GTFS (General Transit Feed Specification)**는 대중교통 시간표 데이터의 표준 형식입니다.

**필수 파일:**

| 파일 | 내용 | 한국 데이터 규모 |
|------|------|-----------------|
| `stops.txt` | 정류장 정보 | 212,105개 |
| `routes.txt` | 노선 정보 | 27,138개 |
| `trips.txt` | 운행 정보 | 349,580개 |
| `stop_times.txt` | 정차 시간 | 20,871,237개 |
| `calendar.txt` | 운행 요일 | - |

### 4.2 GTFS 모델 클래스

```java
// GtfsStop.java - 정류장 정보
public record GtfsStop(
    String stopId,      // 정류장 고유 ID
    String stopName,    // 정류장 이름
    double lat,         // 위도
    double lon          // 경도
) {}

// GtfsRoute.java - 노선 정보
public record GtfsRoute(
    String routeId,         // 노선 고유 ID
    String routeShortName,  // 노선 번호 (예: "750B")
    String routeLongName,   // 노선 이름
    int routeType           // 교통수단 (0=트램, 1=지하철, 2=철도, 3=버스)
) {}

// GtfsTrip.java - 운행 정보
public record GtfsTrip(
    String routeId,     // 노선 ID
    String serviceId,   // 운행 요일 ID
    String tripId,      // 트립 고유 ID
    String tripHeadsign // 행선지
) {}

// GtfsStopTime.java - 정차 시간
public record GtfsStopTime(
    String tripId,      // 트립 ID
    int arrivalTime,    // 도착 시간 (초)
    int departureTime,  // 출발 시간 (초)
    String stopId,      // 정류장 ID
    int stopSequence    // 정차 순서
) {}
```

### 4.3 GtfsLoader 구현

```java
public class GtfsLoader {
    private final Path gtfsDir;

    public GtfsBundle load() throws IOException {
        // 1. stops.txt 파싱
        Map<String, GtfsStop> stops = loadStops();

        // 2. routes.txt 파싱
        Map<String, GtfsRoute> routes = loadRoutes();

        // 3. trips.txt 파싱
        Map<String, GtfsTrip> trips = loadTrips();

        // 4. stop_times.txt 파싱 (가장 큰 파일)
        Map<String, List<GtfsStopTime>> stopTimesByTrip = loadStopTimes();

        // 5. calendar.txt 파싱
        Set<String> activeServices = loadCalendar();

        return new GtfsBundle(stops, routes, trips, stopTimesByTrip, activeServices);
    }
}
```

### 4.4 TransitDataBuilder - GTFS to Raptor 변환

**변환 과정:**

```
┌─────────────────────────────────────────────────────────────┐
│                    TransitDataBuilder                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: 정류장 인덱스 매핑                                    │
│  ─────────────────────────────                               │
│  stopId (문자열) → stopIndex (정수)                           │
│  예: "100000001" → 0, "100000002" → 1, ...                   │
│                                                              │
│  Step 2: 트립 패턴 그룹화                                      │
│  ─────────────────────────                                   │
│  동일한 정류장 순서를 가진 트립들을 하나의 패턴으로 그룹화          │
│                                                              │
│  예: 750B 노선의 트립들                                        │
│  Trip A: 서울역 → 숙대입구 → 남영 (09:00 출발)                  │
│  Trip B: 서울역 → 숙대입구 → 남영 (09:30 출발)                  │
│  → 같은 패턴 "750B:서울역,숙대입구,남영"으로 그룹화               │
│                                                              │
│  Step 3: 노선(Route) 생성                                     │
│  ─────────────────────                                       │
│  각 패턴에 대해:                                               │
│  - KoreanTripPattern: 정류장 인덱스 배열                       │
│  - KoreanTimeTable: 해당 패턴의 모든 트립 시간표                 │
│  - KoreanRoute: 패턴 + 시간표 + 메타데이터                      │
│                                                              │
│  Step 4: 정류장별 노선 인덱스 생성                               │
│  ─────────────────────────────                               │
│  routesByStop[stopIndex] = [경유하는 노선 인덱스들]             │
│                                                              │
│  Step 5: 환승 정보 생성                                        │
│  ─────────────────────                                       │
│  500m 이내 정류장 쌍에 대해 환승 정보 생성                       │
│  transfersFromStop[stopIndex] = [환승 가능 정류장들]            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**패턴 그룹화 핵심 코드:**

```java
private void buildRoutesFromPatterns() {
    // 패턴 키 → 트립 리스트
    Map<String, List<TripWithStopTimes>> patternGroups = new LinkedHashMap<>();

    for (GtfsTrip trip : gtfs.getAllTrips()) {
        List<GtfsStopTime> stopTimes = gtfs.getStopTimes(trip.tripId());

        // 패턴 키 생성: routeId + 정류장 순서
        // 예: "750B:100000001,100000002,100000003"
        String patternKey = buildPatternKey(trip.routeId(), stopTimes);

        patternGroups.computeIfAbsent(patternKey, k -> new ArrayList<>())
            .add(new TripWithStopTimes(trip, stopTimes));
    }

    // 각 패턴 그룹에서 Route 생성
    for (List<TripWithStopTimes> trips : patternGroups.values()) {
        KoreanRoute route = buildRoute(patternIndex++, trips);
        routes.add(route);
    }
}
```

---

## 5. SPI 구현체 설계

### 5.1 구현 클래스 목록

| 클래스 | OTP 인터페이스 | 역할 |
|--------|--------------|------|
| `KoreanTransitDataProvider` | `RaptorTransitDataProvider<T>` | 최상위 데이터 제공자 |
| `KoreanRoute` | `RaptorRoute<T>` | 노선 (패턴 + 시간표) |
| `KoreanTripPattern` | `RaptorTripPattern` | 정류장 순서 패턴 |
| `KoreanTripSchedule` | `RaptorTripSchedule` | 트립 시간표 |
| `KoreanTimeTable` | `RaptorTimeTable<T>` | 시간표 검색 |
| `KoreanTransfer` | `RaptorTransfer` | 환승 정보 |
| `KoreanAccessEgress` | `RaptorAccessEgress` | 출발/도착 연결 |
| `KoreanCostCalculator` | `RaptorCostCalculator<T>` | 비용 계산 |
| `KoreanSlackProvider` | `RaptorSlackProvider` | 여유 시간 |

### 5.2 KoreanTransitDataProvider (최상위)

```java
/**
 * Raptor SPI의 최상위 인터페이스 구현
 *
 * Raptor 알고리즘이 경로 탐색에 필요한 모든 데이터를 제공:
 * - 정류장 수, 정류장 이름
 * - 환승 정보 (정류장 간)
 * - 노선 정보 (패턴 + 시간표)
 */
public class KoreanTransitDataProvider
    implements RaptorTransitDataProvider<KoreanTripSchedule> {

    private final TransitData data;

    // ═══════════════════════════════════════════════════════════
    // 필수 구현: 정류장
    // ═══════════════════════════════════════════════════════════

    @Override
    public int numberOfStops() {
        return data.getStopCount();  // 212,105개
    }

    // ═══════════════════════════════════════════════════════════
    // 필수 구현: 환승
    // ═══════════════════════════════════════════════════════════

    @Override
    public Iterator<? extends RaptorTransfer> getTransfersFromStop(int fromStop) {
        return data.getTransfersFrom(fromStop);
    }

    // ═══════════════════════════════════════════════════════════
    // 필수 구현: 노선
    // ═══════════════════════════════════════════════════════════

    @Override
    public IntIterator routeIndexIterator(IntIterator stops) {
        // 주어진 정류장들을 지나는 모든 노선 인덱스 반환
        BitSet activeRoutes = new BitSet();
        while (stops.hasNext()) {
            int stopIndex = stops.next();
            for (int routeIdx : data.getRoutesByStop(stopIndex)) {
                activeRoutes.set(routeIdx);
            }
        }
        return new BitSetIntIterator(activeRoutes);
    }

    @Override
    public RaptorRoute<KoreanTripSchedule> getRouteForIndex(int routeIndex) {
        return data.getRoute(routeIndex);
    }
}
```

### 5.3 KoreanTripPattern (정류장 패턴)

```java
/**
 * 트립 패턴: 노선이 경유하는 정류장 순서
 *
 * 예: 750B 노선
 * stopIndexes = [0, 15, 28, 42, ...]  (서울역, 숙대입구, 남영, ...)
 */
public class KoreanTripPattern implements RaptorTripPattern {

    private final int patternIndex;
    private final int[] stopIndexes;    // 정류장 인덱스 배열
    private final int slackIndex;       // 환승 여유 시간 인덱스
    private final String debugInfo;

    @Override
    public int numberOfStopsInPattern() {
        return stopIndexes.length;
    }

    @Override
    public int stopIndex(int stopPositionInPattern) {
        return stopIndexes[stopPositionInPattern];
    }

    @Override
    public int findStopPositionAfter(int stopIndex, int startPosition) {
        // 특정 정류장이 이 패턴에서 몇 번째인지 검색
        for (int i = startPosition; i < stopIndexes.length; i++) {
            if (stopIndexes[i] == stopIndex) {
                return i;
            }
        }
        return -1;
    }
}
```

### 5.4 KoreanTripSchedule (트립 시간표)

```java
/**
 * 개별 트립의 시간표
 *
 * 예: 750B 노선 09:00 출발 트립
 * arrivalTimes   = [32400, 32700, 33000, ...]  (09:00, 09:05, 09:10)
 * departureTimes = [32400, 32700, 33000, ...]
 */
public class KoreanTripSchedule implements RaptorTripSchedule {

    private final int tripSortIndex;      // 정렬용 인덱스 (첫 출발 시간)
    private final int[] arrivalTimes;     // 각 정류장 도착 시간 (초)
    private final int[] departureTimes;   // 각 정류장 출발 시간 (초)
    private final KoreanTripPattern pattern;
    private final String tripId;
    private final String routeShortName;

    @Override
    public int tripSortIndex() {
        return tripSortIndex;
    }

    @Override
    public int arrival(int stopPosInPattern) {
        return arrivalTimes[stopPosInPattern];
    }

    @Override
    public int departure(int stopPosInPattern) {
        return departureTimes[stopPosInPattern];
    }
}
```

### 5.5 KoreanTimeTable (시간표 검색)

```java
/**
 * 특정 패턴의 시간표 검색
 *
 * Raptor가 "정류장 X에서 시간 T 이후 탑승 가능한 트립"을 찾을 때 사용
 */
public class KoreanTimeTable implements RaptorTimeTable<KoreanTripSchedule> {

    private final KoreanTripSchedule[] schedules;  // 출발시간순 정렬됨

    @Override
    public int numberOfTripSchedules() {
        return schedules.length;
    }

    @Override
    public KoreanTripSchedule getTripSchedule(int index) {
        return schedules[index];
    }

    @Override
    public RaptorTripScheduleSearch<KoreanTripSchedule> tripSearch(SearchDirection direction) {
        return new KoreanTripScheduleSearch(this, direction);
    }
}
```

### 5.6 KoreanTripScheduleSearch (트립 이진 검색)

```java
/**
 * 특정 시간 이후 탑승 가능한 트립을 이진 검색으로 찾음
 *
 * 핵심 최적화: O(N) → O(log N)
 */
public class KoreanTripScheduleSearch
    implements RaptorTripScheduleSearch<KoreanTripSchedule> {

    @Override
    public RaptorBoardOrAlightEvent<KoreanTripSchedule> search(
        int earliestBoardTime,
        int stopPositionInPattern,
        int tripIndexLimit
    ) {
        // 이진 검색으로 earliestBoardTime 이후 출발하는 첫 트립 찾기
        int lo = 0, hi = schedules.length - 1;
        int result = -1;

        while (lo <= hi) {
            int mid = (lo + hi) / 2;
            int departureTime = schedules[mid].departure(stopPositionInPattern);

            if (departureTime >= earliestBoardTime) {
                result = mid;
                hi = mid - 1;
            } else {
                lo = mid + 1;
            }
        }

        return result >= 0 ? createBoardEvent(result, stopPositionInPattern) : null;
    }
}
```

---

## 6. OSM 도보 경로 시스템

### 6.1 개요

기존 Raptor 시스템은 정류장 간 도보 거리를 **직선 거리(Haversine)**로 계산합니다.
본 프로젝트는 **OSM(OpenStreetMap) 도로망**을 활용하여 **실제 도보 경로** 거리를 계산합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                 직선 거리 vs 실제 도보 거리                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  직선 거리 (Haversine):                                       │
│                                                              │
│    A ─────────────────────── B                               │
│         (300m - 직선)                                         │
│                                                              │
│  실제 도보 거리 (OSM A*):                                      │
│                                                              │
│    A ────┐                                                   │
│          │  (건물)                                            │
│          │                                                   │
│          └────────────────── B                               │
│         (450m - 실제 도로)                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 OSM 데이터 로딩 (2-Pass 방식)

OSM PBF 파일은 크기가 크므로 (한국: ~254MB, 15M 노드) 효율적인 로딩이 필요합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    OsmLoader 2-Pass 로딩                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Pass 1: Way 분석                                            │
│  ─────────────────                                           │
│  - 모든 Way 스캔                                              │
│  - 도보 가능한 도로 유형만 필터링                               │
│    (footway, pedestrian, residential, ...)                   │
│  - 필요한 노드 ID 수집                                        │
│  - Way 정보 임시 저장 (nodeIds, highway type)                 │
│                                                              │
│  Pass 2: 노드 좌표 수집                                       │
│  ──────────────────                                          │
│  - 모든 Node 스캔                                             │
│  - Pass 1에서 수집한 노드 ID만 좌표 저장                        │
│  - 불필요한 노드는 스킵 (메모리 절약)                           │
│                                                              │
│  그래프 구축:                                                  │
│  ───────────                                                 │
│  - 각 Way를 Node 시퀀스로 변환                                 │
│  - 인접 Node 쌍에 Edge 생성                                    │
│  - 양방향 Edge (일방통행 제외)                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**OsmLoader 핵심 코드:**

```java
public class OsmLoader {

    // 도보 가능한 도로 유형
    private static final Set<String> WALKABLE_HIGHWAYS = Set.of(
        "footway",      // 보행자 전용
        "pedestrian",   // 보행자 구역
        "path",         // 오솔길
        "steps",        // 계단
        "residential",  // 주거지역
        "tertiary",     // 3차 도로
        "secondary",    // 2차 도로
        "primary",      // 1차 도로
        "service"       // 서비스 도로
    );

    public StreetNetwork load() throws IOException {
        // Pass 1: Way에서 사용하는 노드 ID 수집
        Set<Long> neededNodeIds = new HashSet<>();
        collectWaysAndNodeIds(neededNodeIds);
        // 결과: walkableWays 1,601,155개, neededNodeIds 15,711,249개

        // Pass 2: 필요한 노드의 좌표 수집
        collectNodeCoordinates(neededNodeIds);

        // 도로망 구축
        return buildNetwork();
    }
}
```

### 6.3 StreetNetwork (도로망 그래프)

```java
/**
 * 도로망 그래프
 * - 노드: 15,711,249개 (교차점, 도로 끝점)
 * - 엣지: 3,547,892개 (도로 세그먼트)
 * - 공간 인덱스: 격자 기반 (~100m 셀)
 */
public class StreetNetwork {

    // 노드 저장 (OSM ID → Node)
    private final Map<Long, StreetNode> nodes = new HashMap<>();

    // 공간 인덱스 (격자 기반)
    private static final double GRID_SIZE = 0.001;  // 약 100m
    private final Map<String, List<StreetNode>> spatialIndex = new HashMap<>();

    /**
     * 주어진 좌표에서 가장 가까운 노드 찾기
     *
     * 공간 인덱스 활용으로 O(N) → O(1) 수준으로 최적화
     */
    public StreetNode findNearestNode(double lat, double lon, double maxDistance) {
        // 주변 그리드 셀만 검색
        int gridRadius = (int) Math.ceil(maxDistance / 111000.0 / GRID_SIZE) + 1;

        String centerKey = getGridKey(lat, lon);
        // centerKey 주변 셀들만 검색...
    }

    private String getGridKey(double lat, double lon) {
        int x = (int) Math.floor(lat / GRID_SIZE);
        int y = (int) Math.floor(lon / GRID_SIZE);
        return x + "," + y;
    }
}
```

### 6.4 WalkingRouter (A* 알고리즘)

```java
/**
 * A* 알고리즘 기반 도보 경로 탐색
 *
 * ★ 핵심 최적화: HashMap 기반 상태 관리
 *
 * 문제: 15M 노드의 상태(gScore, fScore, parent)를 매 검색마다 초기화하면
 *       O(15,000,000) 연산 필요 → 검색당 수 초 소요
 *
 * 해결: HashMap으로 방문한 노드만 상태 저장
 *       O(방문 노드 수) ≈ O(수백~수천) 연산
 */
public class WalkingRouter {

    private static final double MAX_SEARCH_DISTANCE = 500.0;  // 최대 탐색 거리
    private static final int MAX_ITERATIONS = 15000;          // 최대 반복

    /**
     * A* 알고리즘 (HashMap 최적화 버전)
     */
    private WalkingPath aStarSearch(StreetNode start, StreetNode goal) {
        // ★ HashMap 기반 상태 관리 (노드 초기화 불필요!)
        Map<Long, Double> gScores = new HashMap<>();  // 시작점에서의 실제 거리
        Map<Long, Double> fScores = new HashMap<>();  // g + h (휴리스틱)
        Map<Long, StreetNode> parents = new HashMap<>();  // 경로 역추적용

        // 우선순위 큐 (f-score 기준)
        PriorityQueue<StreetNode> openSet = new PriorityQueue<>(
            Comparator.comparingDouble(n -> fScores.getOrDefault(n.getOsmId(), Double.MAX_VALUE))
        );

        Set<Long> closedSet = new HashSet<>();

        // 시작 노드 초기화
        gScores.put(start.getOsmId(), 0.0);
        fScores.put(start.getOsmId(), heuristic(start, goal));
        openSet.add(start);

        int iterations = 0;

        while (!openSet.isEmpty() && iterations < MAX_ITERATIONS) {
            iterations++;

            StreetNode current = openSet.poll();
            long currentId = current.getOsmId();

            // 목표 도달
            if (current.equals(goal)) {
                return reconstructPath(goal, parents, gScores.get(currentId));
            }

            // 이미 처리됨
            if (closedSet.contains(currentId)) continue;
            closedSet.add(currentId);

            double currentGScore = gScores.get(currentId);

            // 최대 거리 초과 체크
            if (currentGScore > MAX_SEARCH_DISTANCE) continue;

            // 인접 노드 탐색
            for (StreetEdge edge : current.getOutgoingEdges()) {
                StreetNode neighbor = edge.getToNode();
                long neighborId = neighbor.getOsmId();

                if (closedSet.contains(neighborId)) continue;

                double tentativeGScore = currentGScore + edge.getLengthMeters();
                double neighborGScore = gScores.getOrDefault(neighborId, Double.MAX_VALUE);

                if (tentativeGScore < neighborGScore) {
                    // 더 좋은 경로 발견
                    parents.put(neighborId, current);
                    gScores.put(neighborId, tentativeGScore);
                    fScores.put(neighborId, tentativeGScore + heuristic(neighbor, goal));
                    openSet.add(neighbor);
                }
            }
        }

        return null;  // 경로 없음
    }

    /**
     * 휴리스틱 함수: 직선 거리 (Admissible)
     */
    private double heuristic(StreetNode from, StreetNode to) {
        return StreetNetwork.haversineDistance(
            from.getLat(), from.getLon(),
            to.getLat(), to.getLon()
        );
    }
}
```

### 6.5 AccessEgressFinder와 OSM 통합

```java
/**
 * 좌표에서 가까운 정류장을 찾아 Access/Egress 경로 생성
 *
 * OSM 모드: 실제 도보 거리 (A* 병렬 실행)
 * Fallback: 직선 거리 × 1.3 (도로 우회 계수)
 */
public class AccessEgressFinder {

    private WalkingRouter walkingRouter;
    private StreetNetwork streetNetwork;
    private StreetNode[] stopNearestNodes;  // 정류장별 가장 가까운 도로 노드 (사전 계산)
    private ExecutorService executor;        // 병렬 A* 실행용

    /**
     * 정류장별 가장 가까운 도로 노드 사전 계산
     *
     * 초기화 시 1회 실행 → 검색 시 findNearestNode() 호출 생략
     */
    private void precomputeStopNearestNodes() {
        stopNearestNodes = new StreetNode[stopCount];

        for (int i = 0; i < stopCount; i++) {
            stopNearestNodes[i] = streetNetwork.findNearestNode(
                stopLats[i], stopLons[i], 300
            );
        }
    }

    /**
     * 근처 정류장 찾기 (병렬 A* 실행)
     */
    private List<RaptorAccessEgress> findNearbyStops(double lat, double lon, double maxDistance) {
        // 1. 직선 거리로 후보 필터링
        List<StopDistance> candidates = filterByHaversine(lat, lon, maxDistance * 1.5);

        // 2. 출발지 도로 노드 검색
        StreetNode originNode = streetNetwork.findNearestNode(lat, lon, 300);

        // 3. 상위 30개 후보에 대해 병렬 A* 실행 (지하철역 포함 위해 증가)
        List<Future<StopDistance>> futures = new ArrayList<>();

        for (int i = 0; i < Math.min(candidates.size(), 30); i++) {
            StopDistance sd = candidates.get(i);

            futures.add(executor.submit(() -> {
                StreetNode stopNode = stopNearestNodes[sd.stopIndex];

                if (stopNode == null) {
                    // 도로망에 연결 안됨 → 직선 거리 × 1.3
                    return new StopDistance(sd.stopIndex, sd.straightDistance * 1.3);
                }

                // A* 실행
                double walkDistance = walkingRouter.getWalkingDistanceBetweenNodes(
                    originNode, stopNode
                );

                return new StopDistance(sd.stopIndex, walkDistance);
            }));
        }

        // 4. 결과 수집
        List<RaptorAccessEgress> result = new ArrayList<>();
        for (Future<StopDistance> future : futures) {
            StopDistance sd = future.get(2000, TimeUnit.MILLISECONDS);
            if (sd != null && sd.walkDistance <= maxDistance) {
                int duration = (int) Math.ceil(sd.walkDistance / WALK_SPEED_MPS);
                result.add(new KoreanAccessEgress(sd.stopIndex, duration, sd.walkDistance));
            }
        }

        return result;
    }
}
```

---

## 7. 성능 최적화

### 7.1 최적화 히스토리

| 버전 | 검색 시간 | 주요 변경 |
|------|----------|----------|
| v0 (초기) | ~14초 | MULTI_CRITERIA, 2시간 윈도우 |
| v1 | ~5초 | STANDARD 프로파일 |
| v2 | ~0.3초 | 15분 윈도우, 정류장 5개 제한 |
| v3 (OSM) | ~26초 | OSM A* 추가 (순차, 노드 초기화) |
| v4 | ~3초 | A* HashMap 최적화 |
| v5 | ~0.5초 | 병렬 A* + 사전 매핑 |
| **v6** | **~0.35초** | **MULTI_CRITERIA 최적화 (relaxC1 비활성화)** |

### 7.2 Raptor 프로파일 선택

두 가지 프로파일 모두 ~0.35초 이내 검색 가능:

```java
// STANDARD 모드 (시간 기준 최적)
builder.profile(RaptorProfile.STANDARD);

// MULTI_CRITERIA 모드 (파레토 최적, 최적화 적용)
builder.profile(RaptorProfile.MULTI_CRITERIA);
builder.enableOptimization(Optimization.PARETO_CHECK_AGAINST_DESTINATION);
// relaxC1 비활성화 → 엄격한 파레토 지배
```

**프로파일 비교:**

| 프로파일 | 검색 시간 | 경로 수 | 특징 |
|----------|----------|--------|------|
| `STANDARD` | ~0.35초 | 4개 | 시간 기준 최적 경로 |
| `MULTI_CRITERIA` | ~0.35초 | **11개** | 시간+환승+비용 파레토 최적화 |

### 7.2.1 MULTI_CRITERIA 최적화 상세

기존 MULTI_CRITERIA는 ~14초가 걸렸으나, 다음 최적화로 **40배 개선**:

```java
// KoreanRaptor.java의 buildMultiCriteriaRequest()
private static final int MC_SEARCH_WINDOW_SECONDS = 900;   // 15분 (STANDARD와 동일)
private static final int MC_ADDITIONAL_TRANSFERS = 3;       // 3회 (STANDARD와 동일)
private static final double MC_RELAX_RATIO = 1.0;           // relaxC1 비활성화 (핵심!)
private static final int MC_RELAX_SLACK = 0;                // relaxC1 비활성화

builder
    .profile(RaptorProfile.MULTI_CRITERIA)
    .enableOptimization(Optimization.PARETO_CHECK_AGAINST_DESTINATION)
    .searchParams()
        .searchWindowInSeconds(MC_SEARCH_WINDOW_SECONDS)
        .numberOfAdditionalTransfers(MC_ADDITIONAL_TRANSFERS);

// relaxC1 비활성화: ratio=1.0, slack=0 → 엄격한 파레토 지배
```

**핵심 발견 - relaxC1 비활성화:**

| 설정 | 효과 |
|------|------|
| relaxC1 활성화 (ratio>1.0) | 파레토 지배 조건 완화 → 더 많은 해 생존 → **느려짐** |
| **relaxC1 비활성화 (ratio=1.0)** | **엄격한 파레토 지배 → 불필요한 해 빠르게 제거 → 빨라짐** |
| `PARETO_CHECK_AGAINST_DESTINATION` | 목적지 기준 조기 가지치기 → 불필요한 경로 제거 |

**결과:** MC가 STD와 동일한 속도(~0.35초)로 **2.75배 더 많은 경로**(11개 vs 4개) 제공!

### 7.3 검색 윈도우 최적화

```java
// 느림: 2시간 윈도우
builder.searchParams().searchWindowInSeconds(7200);  // 많은 트립 탐색

// 빠름: 15분 윈도우
builder.searchParams().searchWindowInSeconds(900);   // 필요한 트립만 탐색
```

### 7.4 A* HashMap 최적화 (핵심)

**문제:**
```java
// 매 검색마다 15M 노드 초기화 필요
public void resetSearchStates() {
    for (StreetNode node : nodes.values()) {  // 15,000,000번 반복
        node.gScore = Double.MAX_VALUE;
        node.fScore = Double.MAX_VALUE;
        node.parent = null;
    }
}
// O(15,000,000) → 수 초 소요
```

**해결:**
```java
// HashMap으로 방문한 노드만 상태 저장
Map<Long, Double> gScores = new HashMap<>();
Map<Long, Double> fScores = new HashMap<>();
Map<Long, StreetNode> parents = new HashMap<>();

// 방문한 노드만 HashMap에 추가
gScores.put(nodeId, distance);
// O(방문 노드 수) ≈ O(수백~수천) → 수 밀리초 소요
```

### 7.5 병렬 A* 실행

```java
// CPU 코어 수만큼 스레드 풀 생성
int cores = Runtime.getRuntime().availableProcessors();  // 8
ExecutorService executor = Executors.newFixedThreadPool(cores);

// 30개 정류장에 대해 A* 병렬 실행 (지하철역 포함 위해 증가)
List<Future<StopDistance>> futures = new ArrayList<>();
for (int i = 0; i < 30; i++) {
    futures.add(executor.submit(() -> {
        // 각 스레드에서 독립적으로 A* 실행
        return walkingRouter.getWalkingDistanceBetweenNodes(origin, stop);
    }));
}

// 모든 결과 수집 (병렬 실행으로 총 시간 단축)
for (Future<StopDistance> future : futures) {
    result.add(future.get());
}
```

### 7.6 정류장-노드 사전 매핑

```java
// 초기화 시 1회 실행
private void precomputeStopNearestNodes() {
    stopNearestNodes = new StreetNode[stopCount];  // 212,105개

    for (int i = 0; i < stopCount; i++) {
        stopNearestNodes[i] = streetNetwork.findNearestNode(
            stopLats[i], stopLons[i], 300
        );
    }
}

// 검색 시: findNearestNode() 호출 생략
StreetNode stopNode = stopNearestNodes[stopIndex];  // O(1)
```

### 7.7 최적화 효과 요약

```
┌─────────────────────────────────────────────────────────────┐
│                    성능 최적화 요약                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Raptor 프로파일: MULTI_CRITERIA → STANDARD               │
│     효과: 14초 → 5초 (64% 단축)                              │
│                                                              │
│  2. 검색 윈도우: 2시간 → 15분                                 │
│     효과: 5초 → 0.3초 (94% 단축)                             │
│                                                              │
│  3. A* HashMap 최적화                                        │
│     효과: 26초 → 3초 (88% 단축)                              │
│     원리: O(15M) 초기화 제거 → O(방문 노드)                   │
│                                                              │
│  4. 정류장-노드 사전 매핑                                     │
│     효과: 검색당 findNearestNode() 호출 생략                  │
│     원리: 초기화 시 212K 정류장 매핑                          │
│                                                              │
│  5. 병렬 A* 실행                                             │
│     효과: 3초 → 0.5초 (83% 단축)                             │
│     원리: 8코어 스레드 풀, 30개 A* 동시 실행                   │
│                                                              │
│  6. Access/Egress 후보 확대                                  │
│     효과: 불필요한 환승 제거                                  │
│     원리: 5개 → 30개로 확대하여 지하철역 포함 보장            │
│                                                              │
│  ─────────────────────────────────────────────               │
│  총 효과: 26초 → 0.3초 (99% 단축) + 불필요한 환승 제거       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. 데이터 흐름

### 8.1 초기화 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                      초기화 흐름 (~60초)                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [1/4] GTFS 로드 (8초)                                       │
│  ─────────────────                                           │
│  data/gtfs/*.txt                                             │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                            │
│  │  GtfsLoader  │ ─── CSV 파싱                               │
│  └──────┬───────┘                                            │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                            │
│  │  GtfsBundle  │ ─── 212K 정류장, 350K 트립                  │
│  └──────────────┘                                            │
│                                                              │
│  [2/4] TransitData 빌드 (4초)                                │
│  ───────────────────────                                     │
│  ┌──────────────────┐                                        │
│  │TransitDataBuilder│ ─── 패턴 그룹화, 환승 생성              │
│  └────────┬─────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────┐                                            │
│  │ TransitData  │ ─── 32K 패턴, 2M 환승                       │
│  └──────────────┘                                            │
│                                                              │
│  [3/4] OSM 로드 (45초)                                       │
│  ─────────────────                                           │
│  south-korea.osm.pbf (254MB)                                 │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                            │
│  │  OsmLoader   │ ─── 2-pass 로딩                            │
│  └──────┬───────┘                                            │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                            │
│  │StreetNetwork │ ─── 15M 노드, 3.5M 엣지                    │
│  └──────────────┘                                            │
│                                                              │
│  [4/4] 엔진 초기화 (3초)                                      │
│  ─────────────────                                           │
│  ┌──────────────┐                                            │
│  │ KoreanRaptor │ ─── 정류장-노드 매핑                        │
│  └──────────────┘                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 검색 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                      검색 흐름 (~0.35초)                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  입력: (37.5547, 126.9707) → (37.4979, 127.0276) @ 09:00    │
│        서울역 좌표              강남역 좌표                    │
│                                                              │
│  Step 1: Access 정류장 검색 (~100ms)                         │
│  ──────────────────────────                                  │
│  ┌──────────────────┐                                        │
│  │AccessEgressFinder│                                        │
│  └────────┬─────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  출발지 근처 정류장 30개 (병렬 A* 거리 계산)                    │
│  - 서울역버스환승센터 (도보 3분)                               │
│  - 서울역 지하철 (도보 5분)                                    │
│  - ...                                                       │
│                                                              │
│  Step 2: Egress 정류장 검색 (~100ms)                         │
│  ─────────────────────────                                   │
│  도착지 근처 정류장 30개 (지하철역 포함 위해 증가)              │
│  - 강남역 (도보 2분)                                          │
│  - 신논현역 (도보 8분)                                        │
│  - ...                                                       │
│                                                              │
│  Step 3: Raptor 실행 (~300ms)                                │
│  ────────────────────                                        │
│  ┌──────────────────────────────────────────────────┐        │
│  │              OTP Raptor JAR                       │        │
│  │                                                   │        │
│  │  Round 0: Access 정류장 초기화                     │        │
│  │  Round 1: 환승 0회 경로 탐색                       │        │
│  │  Round 2: 환승 1회 경로 탐색                       │        │
│  │  Round 3: 환승 2회 경로 탐색                       │        │
│  │  ...                                              │        │
│  └──────────────────────────────────────────────────┘        │
│                                                              │
│  Step 4: 결과 필터링 & 정렬                                   │
│  ────────────────────────                                    │
│  - 요청 시간 이후 출발 경로만 필터링                           │
│  - 출발 시간순 정렬                                           │
│                                                              │
│  출력: 5개 경로                                               │
│  ───────────                                                 │
│  경로 1: 09:03 출발 → 09:45 도착 (42분, 환승 2회)             │
│    1. 도보 3분 → 서울역버스환승센터                            │
│    2. [750B] 서울역버스환승센터 09:10 → 숙대입구역 09:13       │
│    3. 환승 도보 1분                                           │
│    4. [4호선] 숙대입구 09:18 → 사당 09:32                     │
│    5. [2호선] 사당 09:36 → 강남 09:45                         │
│    6. 도보 2분 → 목적지                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 핵심 알고리즘 상세

### 9.1 Raptor 알고리즘 의사코드

```
RAPTOR(출발정류장들, 도착정류장들, 출발시간):

    // 초기화
    τ[k][p] = ∞ for all k, p  // k번 환승 후 정류장 p 최소 도착 시간
    τ*[p] = ∞ for all p       // 정류장 p 최소 도착 시간 (환승 무관)

    // Round 0: Access 정류장 초기화
    for each (정류장 p, 도보시간 t) in 출발정류장들:
        τ[0][p] = 출발시간 + t
        τ*[p] = τ[0][p]
        mark p

    // Round 반복 (k = 1, 2, ...)
    for k = 1 to MAX_ROUNDS:
        // 1. 갱신된 정류장을 지나는 노선 수집
        Q = {} // 탐색할 (노선, 탑승위치) 쌍
        for each marked stop p:
            for each route r passing through p:
                if r not in Q:
                    Q.add(r, position of p in r)
                else:
                    update position to earliest

        unmark all stops

        // 2. 각 노선에서 트립 탑승 & 하차
        for each (route r, boarding_pos) in Q:
            t = null // 현재 탑승 중인 트립

            for i = boarding_pos to last_stop(r):
                p = stop_at_position(r, i)

                // 현재 트립으로 하차
                if t != null:
                    arrival = arrival_time(t, i)
                    if arrival < τ*[p]:
                        τ[k][p] = arrival
                        τ*[p] = arrival
                        mark p

                // 더 빠른 트립으로 갈아탐
                if τ[k-1][p] < τ*[p]:
                    t' = earliest_trip(r, i, τ[k-1][p])
                    if t' != null and (t == null or t' departs earlier):
                        t = t'

        // 3. 환승 (도보 이동)
        for each marked stop p:
            for each transfer from p to p':
                arrival = τ[k][p] + transfer_time
                if arrival < τ*[p']:
                    τ[k][p'] = arrival
                    τ*[p'] = arrival
                    mark p'

        // 4. 종료 조건
        if no stops marked:
            break

    // 결과: 도착정류장들 중 최소 도착 시간
    return min(τ*[p] + egress_time[p]) for p in 도착정류장들
```

### 9.2 A* 알고리즘 의사코드

```
A*(시작노드, 목표노드):

    gScore[시작노드] = 0
    fScore[시작노드] = heuristic(시작노드, 목표노드)

    openSet = 우선순위큐 (fScore 기준)
    openSet.add(시작노드)

    closedSet = {}
    parents = {}

    while openSet is not empty:
        current = openSet.poll()  // fScore 최소 노드

        if current == 목표노드:
            return reconstruct_path(parents, current)

        if current in closedSet:
            continue

        closedSet.add(current)

        // 최대 거리 체크
        if gScore[current] > MAX_DISTANCE:
            continue

        for each edge from current to neighbor:
            if neighbor in closedSet:
                continue

            tentative_g = gScore[current] + edge.distance

            if tentative_g < gScore[neighbor]:
                parents[neighbor] = current
                gScore[neighbor] = tentative_g
                fScore[neighbor] = tentative_g + heuristic(neighbor, 목표노드)
                openSet.add(neighbor)

    return null  // 경로 없음

heuristic(from, to):
    return haversine_distance(from.lat, from.lon, to.lat, to.lon)
```

### 9.3 Haversine 거리 공식

```
haversine(lat1, lon1, lat2, lon2):
    R = 6,371,000  // 지구 반지름 (미터)

    φ1 = radians(lat1)
    φ2 = radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)

    a = sin²(Δφ/2) + cos(φ1) × cos(φ2) × sin²(Δλ/2)
    c = 2 × atan2(√a, √(1-a))

    return R × c
```

---

## 10. 결론

### 10.1 프로젝트 성과

본 프로젝트는 다음을 성공적으로 달성했습니다:

1. **OTP Raptor 모듈 통합**: JAR 수정 없이 SPI 구현만으로 한국 GTFS 연결
2. **고성능 경로탐색**: 21만 정류장, 35만 트립에서 0.5초 이내 검색
3. **실제 도보 경로**: 15M 노드 OSM 그래프에서 A* 알고리즘 적용
4. **다양한 최적화**: HashMap A*, 병렬 실행, 사전 매핑 등

### 10.2 기술적 기여

| 항목 | 기여 |
|------|------|
| SPI 구현 패턴 | OTP Raptor를 외부 데이터와 연결하는 방법 제시 |
| A* HashMap 최적화 | 대규모 그래프에서 상태 초기화 문제 해결 |
| 병렬 A* 실행 | 다중 목적지 경로 탐색 성능 개선 |
| 2-Pass OSM 로딩 | 메모리 효율적인 대용량 PBF 파싱 |

### 10.3 향후 개선 방향

1. **공간 인덱스 개선**: 정류장 검색에 R-tree 적용
2. **실시간 데이터**: GTFS-RT 연동
3. **API 서버화**: REST API 제공
4. **멀티모달**: 자전거, 킥보드 등 추가

---

## 참고 문헌

1. Delling, D., Pajor, T., & Werneck, R. F. (2012). **Round-based public transit routing**. *Transportation Science*.
2. OpenTripPlanner Documentation. https://docs.opentripplanner.org/
3. GTFS Specification. https://gtfs.org/schedule/reference/
4. OpenStreetMap Wiki. https://wiki.openstreetmap.org/

---

**작성자**: 김태우 (가천대학교 CAMMUS 연구원)
**이메일**: twdaniel@gachon.ac.kr
**최종 수정**: 2026-01
