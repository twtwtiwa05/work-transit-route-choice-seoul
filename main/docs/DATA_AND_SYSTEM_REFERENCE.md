# 데이터 및 시스템 참조 문서
## Transit Route Choice 연구 — 데이터·OTP·매핑 통합 가이드

**작성일**: 2026-02-06
**목적**: RESEARCH_PLAN.md 실행 전 데이터 구조, OTP 엔진, ID 매핑 체계를 정확히 파악
**대상 데이터**: 서울 대중교통 (2025.02.20 목요일)

---

## 목차

1. [Korean OTP (RAPTOR 엔진) 구조](#1-korean-otp-raptor-엔진-구조)
2. [TCD 데이터 구조](#2-tcd-데이터-구조)
3. [보조 데이터 (STTN, ROUTE, ROUTESTTN)](#3-보조-데이터)
4. [GTFS 데이터 구조](#4-gtfs-데이터-구조)
5. [ID 매핑 체계: TCD ↔ GTFS 연결](#5-id-매핑-체계)
6. [매핑 CSV 분석: 어떤 파일을 사용할 것인가](#6-매핑-csv-분석)
7. [RESEARCH_PLAN.md 정정사항](#7-research_planmd-정정사항)
8. [데이터 흐름도](#8-데이터-흐름도)
9. [파일 인벤토리](#9-파일-인벤토리)

---

## 1. Korean OTP (RAPTOR 엔진) 구조

### 1.1 시스템 개요

Korean OTP는 OTP(OpenTripPlanner)의 **RAPTOR 모듈(JAR)**을 그대로 사용하되,
SPI(Service Provider Interface)만 한국 GTFS에 맞게 구현한 **CLI 기반 대중교통 경로탐색 엔진**이다.

```
좌표 입력 (lat, lon)
    ↓
AccessEgressFinder: 근처 정류장 검색 (800m 반경, 최대 30개)
    ↓
KoreanRaptor: RAPTOR 알고리즘 실행
    ↓
Pareto-optimal 경로 반환 (최대 11개, MC 모드)
```

### 1.2 성능 현황

| 항목 | 값 |
|------|-----|
| 정류장 | 212,105개 |
| 노선(패턴) | 32,229개 |
| 트립 | 349,509개 |
| 단일 검색 (MC) | ~0.365초 |
| 배치 처리량 (16스레드) | 43.4 req/s |
| 1000 OD 처리 | 23초 |
| 성공률 | 96.7% |

### 1.3 핵심 Java 클래스

#### KoreanCostCalculator.java
**위치**: `korean-otp/src/main/java/kr/otp/raptor/spi/KoreanCostCalculator.java`

Multi-Criteria 탐색에서 경로의 "비용"을 계산하는 핵심 클래스.

```java
// 현재 하드코딩된 상수값 (수정 대상)
private static final int FIRST_BOARD_COST = 60 * 100;     // 첫 승차: 1분 = 6,000 centi-seconds
private static final int TRANSFER_COST = 120 * 100;       // 환승: 2분 = 12,000 centi-seconds
private static final double WAIT_RELUCTANCE = 1.0;        // 대기 시간 가중치
```

**비용 단위**: centi-seconds (1초 = 100)

**비용 구성**:
- `boardingCost()`: 첫 승차 = 6,000cs (1분) / 환승 = 12,000cs (2분) + 대기시간×100
- `transitArrivalCost()`: 승차비용 + 탑승시간×100
- `costEgress()`: `KoreanAccessEgress.c1()` 그대로 반환
- `calculateRemainingMinCost()`: 남은 최소 시간×100 + 남은 환승×TRANSFER_COST (A* 휴리스틱)

**반복 보정 시 수정할 부분**:
- `TRANSFER_COST` → 생성자 파라미터로 변경
- `WAIT_RELUCTANCE` → 생성자 파라미터로 변경

#### KoreanAccessEgress.java
**위치**: `korean-otp/src/main/java/kr/otp/raptor/spi/KoreanAccessEgress.java`

출발지→첫 정류장(Access), 마지막 정류장→목적지(Egress) 도보 경로.

```java
// 핵심: 보행 비용 계산
this.cost = durationSeconds * 100;    // 1초 보행 = 100 centi-seconds

// 도보 속도
public static KoreanAccessEgress fromDistance(int stopIndex, double distanceMeters) {
    int duration = (int) Math.ceil(distanceMeters / 1.2);  // 1.2 m/s 가정
    return new KoreanAccessEgress(stopIndex, duration, distanceMeters);
}
```

**반복 보정 시 수정할 부분**:
- `c1()`: `durationSeconds * 100` → `(int)(durationSeconds * 100 * walkReluctance)`
- `walkReluctance` 파라미터 추가 (기본값 1.0, 보정 후 ~8.5)

**현재 문제**: WALK_RELUCTANCE=1.0이므로 보행 1초 = 차내 1초로 취급.
논문 결과(8.5×)를 반영하면 보행 1초 = 차내 8.5초로 비용 계산해야 함.

#### KoreanTransitDataProvider.java
**위치**: `korean-otp/src/main/java/kr/otp/raptor/spi/KoreanTransitDataProvider.java`

RAPTOR SPI의 최상위 인터페이스. TransitData를 래핑하여 RAPTOR에 제공.

```java
public KoreanTransitDataProvider(TransitData data) {
    this.data = data;
    this.costCalculator = new KoreanCostCalculator();  // ← 여기서 생성
    this.slackProvider = new KoreanSlackProvider();
}
```

**반복 보정 시 수정할 부분**:
- 생성자에서 보정 파라미터를 받아 `KoreanCostCalculator`에 전달

#### KoreanRaptor.java
**위치**: `korean-otp/src/main/java/kr/otp/core/KoreanRaptor.java`

메인 엔진. 좌표 기반 경로 탐색 수행.

```java
// STANDARD 모드 설정
MAX_ACCESS_WALK_METERS = 800.0    // 도보 반경
SEARCH_WINDOW_SECONDS = 1800      // 30분 검색 윈도우
MAX_ACCESS_STOPS = 30             // 최대 접근 정류장

// MULTI_CRITERIA 모드 설정 (Pareto-optimal)
MC_SEARCH_WINDOW_SECONDS = 1800   // 30분
MC_ADDITIONAL_TRANSFERS = 3       // 최대 추가 환승
MC_RELAX_RATIO = 1.0              // relaxC1 비활성화 (엄격한 Pareto)
MC_RELAX_SLACK = 0
```

**두 가지 검색 모드**:
- `route()`: STANDARD 모드 — 최단 시간 기준, 4개 경로
- `routeMultiCriteria()`: MC 모드 — Pareto 최적, **11개** 경로 (시간/환승/비용 트레이드오프)

#### BatchRouter.java
**위치**: `korean-otp/src/main/java/kr/otp/batch/BatchRouter.java`

대량 OD 배치 처리. CSV 입력 → JSON 출력.

```
입력 CSV: from_lat, from_lon, to_lat, to_lon, departure_time
출력 JSON: itineraries[] → legs[] → {mode, from, to, route, trip, duration, ...}
```

**배치 출력 JSON 구조**:
```json
{
  "id": 0,
  "searchTimeMs": 365,
  "data": {
    "plan": {
      "itineraries": [
        {
          "startTime": 1768892400000,
          "endTime": 1768894800000,
          "duration": 2400,
          "walkDistance": 480.00,
          "generalizedCost": 240000,
          "legs": [
            {
              "mode": "WALK",        // 도보
              "duration": 180.0,
              "from": { "name": "Origin", "lat": 37.5547, "lon": 126.9707 },
              "to": { "name": "서울역", "stop": { "gtfsId": "1:BS_3100_..." } }
            },
            {
              "mode": "SUBWAY",      // 지하철
              "duration": 900.0,
              "route": { "gtfsId": "1:RR_ACC1_S-1-01-1D", "shortName": "1호선" },
              "from": { "stop": { "gtfsId": "1:..." } },
              "to": { "stop": { "gtfsId": "1:..." } }
            }
          ]
        }
      ]
    }
  }
}
```

**OTP가 출력하는 모드 코드** (determineMode 메서드):
| routeType | 모드 |
|-----------|------|
| 1, 12 | SUBWAY |
| 2, 100, 101, 102 | RAIL |
| 3, 700, 701, 702, 704 | BUS |
| 4 | FERRY |
| 기본값 | BUS |

**OTP 출력의 정류장 ID 형식**: `1:{gtfs_stop_id}` (예: `1:BS_3100_217000396`)

### 1.4 GTFS 데이터 경로

```
korean-otp/data/gtfs/
├── agency.txt       (운영기관)
├── calendar.txt     (운행 일정)
├── routes.txt       (노선 정의, 27,138개)
├── stops.txt        (정류장 정의, 212,105개)
├── stop_times.txt   (정차 시간표, 20,871,237개)
└── trips.txt        (트립 정의, 349,580개)
```

---

## 2. TCD 데이터 구조

### 2.1 개요

| 항목 | 값 |
|------|-----|
| 파일 | `DATA/tcd_2025_parquet/20250220/TCD_20250220.parquet` |
| 크기 | 740 MB |
| 총 레코드 | **18,420,218** |
| 서울 레코드 | **18,407,716** (99.9%) |
| 컬럼 수 | 27 |
| 분석 날짜 | 2025.02.20 (목요일) |

### 2.2 전체 27개 컬럼 스키마

| # | 컬럼명 | 타입 | 설명 | 분석 용도 |
|---|--------|------|------|----------|
| 0 | `운행일자` | int64 | 20250220 | 필터링 |
| 1 | `정산사 ID` | int64 | 정산 사업자 (3=지방, 8=수도권) | **수단 구분 아님** |
| 2 | `인련번호` | int64 | 동일 카드의 일일 통행 순번 | 통행 체인 |
| 3 | `가상카드번호` | string | 스마트카드 고유번호 | 개인 식별 |
| 4 | `정산지역코드` | string | 지역 코드 (11100=서울) | 서울 필터 |
| 5 | `카드구분코드` | string | C=일반카드, M=모바일 등 | - |
| 6 | `차량ID(국토부표준)` | double | 국토부 표준 차량ID | null 많음 |
| 7 | `차량ID(정산사업자)` | double | 정산사 차량ID | - |
| 8 | `차량등록번호` | string | 차량 번호판 | - |
| 9 | `운행출발일시` | double | 차량 운행 시작 | - |
| 10 | `운행종료일시` | double | 차량 운행 종료 | - |
| 11 | **`교통수단코드`** | **int64** | **수단 구분 핵심** | **BUS/SUBWAY/RAIL 분류** |
| 12 | `노선ID(국토부표준)` | double | 국토부 표준 노선ID | null 많음 |
| 13 | **`노선ID(정산사업자)`** | **string** | **정산사 노선ID** | **노선 식별 핵심** |
| 14 | **`승차일시`** | **int64** | 탑승 시간 (YYYYMMDDHHMMSS) | **OD 시간** |
| 15 | `발권일시` | double | 발권 시간 | - |
| 16 | `승차정류장ID(국토부표준)` | double | 국토부 승차 정류장 | null 많음 |
| 17 | **`승차정류장ID(정산사업자)`** | **int64** | **정산사 승차 정류장** | **출발 정류장** |
| 18 | `하차정류장ID(국토부표준)` | double | 국토부 하차 정류장 | null 많음 |
| 19 | **`하차정류장ID(정산사업자)`** | **double** | **정산사 하차 정류장** | **도착 정류장** |
| 20 | **`하차일시`** | **double** | 하차 시간 | **통행시간 계산** |
| 21 | `트랜잭션ID` | int64 | 거래 ID | - |
| 22 | **`환승건수`** | **int64** | 환승 횟수 (0~5) | **통행 체인 핵심** |
| 23 | **`사용자구분코드`** | **int64** | 이용자 유형 (1~7) | **유형별 분석 핵심** |
| 24 | `이용자수` | int64 | 동반 이용자 수 | 대부분 1 |
| 25 | `이용거리` | int64 | 통행 거리 (m) | 보조 |
| 26 | `탑승시간` | int64 | 탑승 시간 (초) | 보조 |

### 2.3 교통수단코드 분류 (서울)

**⚠️ RESEARCH_PLAN.md 정정: 수단 구분은 `정산사 ID`가 아니라 `교통수단코드`로 해야 함**

| 코드 범위 | 수단 | 레코드 수 | 비율 | 세부 |
|-----------|------|----------|------|------|
| **100~199** | **버스** | **4,925,225** | **26.8%** | 105=간선, 115=지선, 120=마을, 130=광역 |
| **200~299** | **지하철** | **8,707,772** | **47.3%** | 201~210=1~10호선, 231~237=기타노선, 290=기타 |
| **400~499** | **경기/인천 버스** | **~793,935** | **~4.3%** | 470=경기광역, 480=인천 등 |
| **500~599** | **철도(코레일)** | **~3,970,007** | **~21.6%** | 500=경의중앙, 533=분당, 582=경춘 등 |

**추천 분류 매핑**:
```python
def classify_mode(code):
    if 100 <= code <= 199:
        return 'BUS'
    elif 200 <= code <= 299:
        return 'SUBWAY'
    elif 400 <= code <= 499:
        return 'BUS'       # 경기/인천 버스도 버스로 분류
    elif 500 <= code <= 599:
        return 'RAIL'      # 코레일 (경의중앙선, 분당선 등)
    else:
        return 'OTHER'
```

### 2.4 사용자구분코드 분포 (서울)

| 코드 | 유형 | 레코드 수 | 비율 | 논문 매핑 |
|------|------|----------|------|----------|
| 1 | 일반 (General) | 15,323,964 | 83.2% | 01 |
| 2 | 어린이 (Children) | 142,395 | 0.8% | 02 |
| 3 | 청소년 (Youth) | 762,796 | 4.1% | 03 |
| 4 | 고령자 (Elderly) | 1,755,849 | 9.5% | 04 |
| 5 | 장애인 (Disabled) | 377,645 | 2.1% | 05 |
| 6 | 기타1 | 33,544 | 0.2% | 제외 |
| 7 | 기타2 | 11,523 | 0.1% | 제외 |

### 2.5 환승건수 분포 (서울)

| 환승 | 레코드 수 | 비율 | 해석 |
|------|----------|------|------|
| 0 | 14,203,035 | 77.2% | 무환승 (단일 레그) |
| 1 | 3,614,121 | 19.6% | 1회 환승 (2레그) |
| 2 | 508,074 | 2.8% | 2회 환승 (3레그) |
| 3 | 67,769 | 0.4% | 3회 환승 |
| 4 | 14,704 | 0.1% | 4회 환승 |
| 5 | 13 | 0.0% | 5회 환승 |

### 2.6 TCD vs TCN: 핵심 차이점

**⚠️ TCD에는 환승 정류장 컬럼이 없다**

RESEARCH_PLAN.md에서 기대한 `환승역1ID(운영사코드)`, `환승역2ID(운영사코드)` 컬럼은
실제 TCD_20250220.parquet에 **존재하지 않는다**.

TCD에서 환승 통행을 재구성하려면:
```
방법: 동일 가상카드번호의 인련번호(1,2,3...) 순서로 레코드를 결합

예: 카드 "ABC123", 환승건수=1
  인련번호=1: 승차정류장A → 하차정류장B (버스 105번)
  인련번호=2: 승차정류장B → 하차정류장C (지하철 2호선)
  → 통행 체인: A → B(환승) → C
```

이 방식은 **TCN의 환승역 컬럼보다 더 상세한 정보**를 제공한다:
- 각 레그별 노선, 수단, 시간, 정류장이 모두 개별 레코드로 존재
- TCN: 환승역 ID만 제공, 중간 노선/수단 정보 없음

### 2.7 Null 비율

| 컬럼 | Null 비율 | 영향 |
|------|----------|------|
| 노선ID(국토부표준) | 높음 | **사용 불가** → 정산사업자 ID 사용 |
| 승차정류장ID(국토부표준) | 높음 | **사용 불가** → 정산사업자 ID 사용 |
| 하차정류장ID(국토부표준) | 높음 | **사용 불가** → 정산사업자 ID 사용 |
| 하차정류장ID(정산사업자) | 1.1% | 하차 미태그 (하차 안 찍은 경우) |
| 승차정류장ID(정산사업자) | 0.0% | 거의 없음 |

**결론**: 국토부표준 ID는 대부분 null이므로, **정산사업자 ID 체계를 기본으로 사용**해야 한다.

---

## 3. 보조 데이터

### 3.1 STTN (정류장 마스터)

**파일**: `DATA/tcd_2025_parquet/20250220/STTN_20250220.parquet`
**레코드**: 50,211개 (고유 정류장 50,022개)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| 정류장 ID | int64 | **정산사업자 정류장 ID** (TCD의 승차/하차 정류장ID와 조인 키) |
| 정류장 명칭 | string | 정류장 이름 |
| 정류장 X 좌표 | double | **위도** (WGS84) |
| 정류장 Y 좌표 | double | **경도** (WGS84) |
| 시도명 | string | 시도 (서울특별시, 경기도 등) |
| 시군구명 | string | 시군구 |

**지역별 분포**:
- 경기도: 29,539개
- 서울특별시: 15,182개
- 인천광역시: 5,362개

**⚠️ 주의**: STTN의 X좌표=위도, Y좌표=경도 (일반적 컨벤션과 반대일 수 있으니 확인 필요)

### 3.2 ROUTE (노선 마스터)

**파일**: `DATA/tcd_2025_parquet/20250220/ROUTE_20250220.parquet`
**레코드**: 4,011개

| 컬럼 | 타입 | 설명 |
|------|------|------|
| 정산사 ID | int64 | 정산 사업자 |
| 노선ID | string | **정산사업자 노선ID** (TCD의 노선ID(정산사업자)와 조인 키) |
| 노선명(long) | string | 노선 전체 이름 |
| 노선명(short) | string | 노선 약칭 |
| 교통수단유형 | string | B=버스, T=도시철도, G=기타 |
| 총운행거리 | int64 | 노선 총 거리 (m) |
| 정류장수 | int64 | 노선 정류장 수 |

### 3.3 ROUTESTTN (노선-정류장 매핑)

**파일**: `DATA/tcd_2025_parquet/20250220/ROUTESTTN_20250220.parquet`
**레코드**: 257,499개 (고유 노선 4,012개, 고유 정류장 63,400개)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| 노선ID | string | 정산사업자 노선ID |
| 노선명(short) | string | 노선 약칭 |
| 교통수단유형 | string | B=버스(256,707), T=도시철도(782), G=기타(10) |
| **정류장순서** | **int64** | **0부터 시작하는 정류장 순번** |
| 정류장 ID | int64 | 정산사업자 정류장ID |
| 정류장 명칭 | string | 정류장 이름 |
| 정류장 X 좌표 | double | 위도 |
| 정류장 Y 좌표 | double | 경도 |
| 누적거리(m) | int64 | 기점부터 누적 거리 |
| 구간거리(m) | int64 | 직전 정류장과의 거리 |

**핵심 용도**: TCD의 노선ID + 승차정류장 + 하차정류장으로 **경유 정류장 시퀀스** 추출 가능

```
예: 노선 "29005049" (58번 버스)
    정류장순서 0: 관설동종점 (4372031)
    정류장순서 1: 원주자동차운전학원 (4370031)
    정류장순서 2: 학마을 (4388631)
    ...

TCD에서 승차=4370031, 하차=4388631이면:
    경유 정류장 = {4370031, 4388631} (순서 1~2)
```

---

## 4. GTFS 데이터 구조

### 4.1 파일별 규모

| 파일 | 레코드 수 | 설명 |
|------|----------|------|
| `stops.txt` | 212,105 | 전국 정류장 (stop_id, stop_name, stop_lat, stop_lon) |
| `routes.txt` | 27,138 | 전국 노선 (route_id, route_short_name, route_type) |
| `trips.txt` | 349,580 | 트립 정의 (route_id, service_id, trip_id) |
| `stop_times.txt` | 20,871,237 | 정차 시간표 (trip_id, stop_id, stop_sequence) |

### 4.2 GTFS ID 규칙

**정류장 ID (stop_id)**:
```
BS_3100_217000396     → 버스 정류장 (수도권, 국토부 코드)
BS_1100_100000001     → 서울 버스 정류장
RR_3100_K410          → 철도역 (코레일)
```
- `BS_`: 버스 정류장 (Bus Stop)
- `RR_`: 철도역 (Railroad)
- `AS_`: 공항 (Airport Stop)

**노선 ID (route_id)**:
```
BR_3100_239000140     → 버스 노선 (수도권)
BR_TAGO_GHB0034       → 버스 노선 (TAGO 시스템)
BR_KOTI_00000698      → 버스 노선 (KOTI)
RR_ACC1_S-1-01-1D     → 지하철 노선 (1호선, 하행)
```
- `BR_`: 버스 노선 (Bus Route)
- `RR_`: 철도 노선 (Railroad Route)
- `AR_`: 항공 노선

**트립 ID (trip_id)**:
```
BR_3100_239000140_Ord014  → 버스 트립 (노선_순번)
```

### 4.3 GTFS stop_times.txt 구조

```
trip_id, arrival_time, departure_time, stop_id, stop_sequence, pickup_type, drop_off_type, timepoint
```

이 파일이 **정류장 시퀀스 추출의 핵심**:
```
trip_id에서 route_id 조회 (trips.txt 조인)
→ 같은 route_id의 trip 하나 선택
→ stop_sequence 순서대로 stop_id 추출
→ 해당 노선의 정류장 시퀀스 완성
```

---

## 5. ID 매핑 체계

### 5.1 세 가지 ID 체계

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│    TCD (정산사업자)    │     │   TCN (교통카드)      │     │   GTFS (표준)         │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│ 노선: "29005049"     │     │ 노선: tcn_route_id   │     │ 노선: "BR_3100_..."   │
│ 정류장: 2923810      │     │       (정수)          │     │ 정류장: "BS_3100_..." │
│                     │     │                     │     │                     │
│ [정산사업자 코드]     │     │ [교통카드 내부 코드]   │     │ [국가 표준 코드]       │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         ↕                           ↕                           ↕
    ROUTESTTN 조인              매핑 CSV                    OTP 직접 사용
```

### 5.2 매핑 경로

**TCD → GTFS 노선 매핑** (3단계):
```
TCD 노선ID(정산사업자) → ROUTE 노선ID → tcn_route_id → gtfs_route_id
     "29005049"            "29005049"        ???         "BR_3100_..."
```

**⚠️ 핵심 문제**: TCD의 `노선ID(정산사업자)`와 매핑 CSV의 `tcn_route_id`는 **다른 ID 체계**이다.
- TCD 노선ID(정산사업자): 문자열 (예: "29005049", "43703300")
- 매핑 CSV tcn_route_id: 정수 (예: 0, 1, 2, ..., 25910)

### 5.3 매핑 전략

**방법 A: ROUTESTTN 경유 (정류장 시퀀스 기반)**
```
TCD 노선ID(정산사업자) + 승차정류장 + 하차정류장
    ↓ ROUTESTTN 조인
경유 정류장 시퀀스 [정산사업자 정류장ID 리스트]
    ↓ STTN → GTFS stops.txt 좌표 매칭
경유 정류장 시퀀스 [GTFS stop_id 리스트]
```

**방법 B: 노선명 기반 매핑**
```
TCD 노선ID(정산사업자) → ROUTE 노선명(short) → 매핑 CSV route_name → GTFS route_id
```

**방법 C: 직접 정류장 좌표 매칭** (추천)
```
TCD 승차정류장ID(정산사업자) → STTN 정류장 X/Y 좌표 → OD 쌍 생성
    (GTFS 노선 매핑 불필요 — OTP가 좌표로 경로 탐색)
```

### 5.4 추천: 방법 C (좌표 기반)

**OTP는 좌표를 입력받아 경로를 탐색하므로, TCD→GTFS 노선 매핑이 반드시 필요하지는 않다.**

```
Phase 1 데이터 흐름:
1. TCD에서 승차/하차 정류장ID 추출
2. STTN에서 정류장 좌표 조회
3. OD 좌표 쌍 생성 → OTP 배치 입력
4. OTP가 GTFS 기반으로 경로 탐색
5. 유사도 비교 시 ROUTESTTN의 정류장 시퀀스 활용
```

**노선 매핑이 필요한 경우**:
- 유사도 계산 시 TCD 실제 경로의 정류장 시퀀스를 추출할 때
- ROUTESTTN으로 TCD 노선의 정류장 순서를 파악할 때
- 이때는 TCD ↔ ROUTESTTN 간 `노선ID(정산사업자)` 조인으로 충분

---

## 6. 매핑 CSV 분석

### 6.1 두 CSV 비교

| 항목 | `tcn_route_mapping_complete.csv` | `tcn_to_gtfs_route_mapping.csv` |
|------|----------------------------------|----------------------------------|
| 크기 | 1.5 MB | 21 MB |
| 행 수 | 25,911 | 288,879 |
| 컬럼 | 4 (tcn_route_id, route_name, route_no, transport_type) | 5 (+ gtfs_route_id) |
| 관계 | 1:1 (tcn_route_id 고유) | 1:N (1개 tcn이 여러 GTFS에 매핑) |
| 용도 | TCN 노선 카탈로그 | **TCN → GTFS 변환** |

### 6.2 결론: 사용할 파일

**Phase 1 전처리에서는 두 CSV 모두 직접 사용하지 않는다.**

이유:
1. TCD의 `노선ID(정산사업자)`는 TCN의 `tcn_route_id`와 **다른 ID 체계**
2. TCD → OTP 연결은 **좌표 기반** (STTN 정류장 좌표 → OTP 배치)
3. TCD 실제 경로의 정류장 시퀀스는 **ROUTESTTN**으로 추출 가능

**매핑 CSV가 필요한 경우** (Phase 2 이후):
- OTP 출력의 GTFS route_id와 TCD 노선을 비교할 때
- 이때도 정류장 시퀀스 비교(S_jaccard, S_lcs)가 주 방법이므로 노선 ID 매핑은 보조적

### 6.3 정류장 ID 매핑 필요성

TCD 정류장ID(정산사업자)와 GTFS stop_id 간 매핑은 중요:

```
TCD 정류장ID: 2923810 (정수)
STTN 정류장ID: 2923810 (정수, 좌표 포함)
GTFS stop_id: "BS_3100_217000396" (문자열)
```

매핑 방법: **좌표 근접 매칭**
```python
# STTN에서 TCD 정류장 좌표 → GTFS stops.txt에서 가장 가까운 정류장
# Haversine 거리 < 100m이면 매칭
```

---

## 7. RESEARCH_PLAN.md 정정사항

### 7.1 컬럼명 정정

| RESEARCH_PLAN 기재 | 실제 TCD 컬럼명 | 비고 |
|-------------------|----------------|------|
| `운영사 ID` | `정산사 ID` | 이름만 다름, 값은 동일 (3, 8, 11) |
| `조회일번호` | `인련번호` | 동일 카드의 일일 순번 |
| `카드카드번호` | `가상카드번호` | - |
| `승차ID(운영사코드)` | `승차정류장ID(정산사업자)` | int64, null 0% |
| `하차ID(운영사코드)` | `하차정류장ID(정산사업자)` | double, null 1.1% |
| `승차시간` | `승차일시` | int64 (YYYYMMDDHHMMSS) |
| `하차시간` | `하차일시` | double |
| `환승역1ID(운영사코드)` | **존재하지 않음** | TCD에 환승역 컬럼 없음 |
| `환승역2ID(운영사코드)` | **존재하지 않음** | TCD에 환승역 컬럼 없음 |
| `환승구분` | `환승건수` | 값은 동일 (0~5) |
| `사용자유형코드` | `사용자구분코드` | 값은 동일 (1~7) |
| `거리/시간` | `이용거리` + `탑승시간` | 별도 컬럼 |

### 7.2 수단 구분 정정

**RESEARCH_PLAN**: `정산사 ID` (3=지하철, 8=버스)
**실제**: `교통수단코드` (100s=버스, 200s=지하철, 400s=기타버스, 500s=철도)

`정산사 ID`는 정산 사업자를 나타내며, 수도권(8)에서는 버스·지하철 모두 포함.
**수단 구분은 반드시 `교통수단코드`로 해야 한다.**

### 7.3 환승 통행 재구성 방법 정정

**RESEARCH_PLAN**: 환승역1ID, 환승역2ID 컬럼 사용
**실제**: 동일 `가상카드번호`의 `인련번호` 순서로 레코드 결합

```
환승건수=1인 통행:
  인련번호=1: 승차A → 하차B (노선1, 교통수단코드=115)
  인련번호=2: 승차B → 하차C (노선2, 교통수단코드=201)
  → 통행 체인: A(버스) → B(환승) → C(지하철)
```

### 7.4 Null 비율 정정

**RESEARCH_PLAN**: `승차ID(운영사코드)` null 47%
**실제**: `승차정류장ID(정산사업자)` null **0%** (int64, 모든 레코드에 값 존재)

국토부표준 ID 컬럼들이 null이 많은 것이지, 정산사업자 ID는 거의 완전함.

---

## 8. 데이터 흐름도

### Phase 1: 데이터 전처리 (수정된 흐름)

```
[TCD_20250220.parquet]  18.4M 레코드
        │
        ├── 서울 필터 (정산지역코드='11100')  → 18.4M
        ├── 사용자구분코드 1~5만 (6,7 제외) → ~18.3M
        ├── 하차일시 null 제거 (1.1%)       → ~18.1M
        ├── 교통수단코드로 수단 분류
        │     100~199: BUS (26.8%)
        │     200~299: SUBWAY (47.3%)
        │     400~499: BUS (4.3%)
        │     500~599: RAIL (21.6%)
        └── 비정상 제거 (탑승시간 > 4시간 등)
                │
                ↓
[cleaned_tcd.parquet]  ~17M 유효 레코드
        │
        ├── 가상카드번호 + 인련번호로 그룹핑
        ├── 환승건수=0: 단일 레그
        ├── 환승건수=1: 인련번호 1,2 결합 → 2레그
        ├── 환승건수=2: 인련번호 1,2,3 결합 → 3레그
        └── 각 레그의 노선ID, 수단코드, 승하차정류장 보존
                │
                ↓
[trip_chains.parquet]
        │
        ├── STTN 조인 → 승차/하차 정류장 좌표 획득
        ├── 첫 레그 승차정류장 = Origin 좌표
        ├── 마지막 레그 하차정류장 = Destination 좌표
        └── 출발 시간 파싱 (승차일시 → HH:MM)
                │
                ↓
[od_pairs.csv]  OTP 배치 입력
  from_lat, from_lon, to_lat, to_lon, departure_time

[trip_attributes.parquet]  유사도 비교용
  trip_id, user_type, legs[], modes[], stop_sequences[]
```

### Phase 2: OTP 배치 + 유사도

```
[od_pairs.csv] → OTP BatchRouter → [batch_result.json]
                                           │
[trip_attributes.parquet] ─────────────────┤
[ROUTESTTN] → 노선별 정류장 시퀀스 ────────┤
                                           ↓
                                   유사도 계산 (5개 지표)
                                   S_xfer, S_mode, S_jaccard, S_lcs, S_cost
                                           │
                                           ↓
                                   [similarity_results.parquet]
                                   매칭률 분석
```

---

## 9. 파일 인벤토리

### 데이터 파일

| 경로 | 크기 | 레코드 | 용도 |
|------|------|--------|------|
| `DATA/tcd_2025_parquet/20250220/TCD_20250220.parquet` | 740 MB | 18,420,218 | **주 분석 데이터** |
| `DATA/tcd_2025_parquet/20250220/STTN_20250220.parquet` | 1.9 MB | 50,211 | 정류장 좌표 |
| `DATA/tcd_2025_parquet/20250220/ROUTE_20250220.parquet` | 123 KB | 4,011 | 노선 마스터 |
| `DATA/tcd_2025_parquet/20250220/ROUTESTTN_20250220.parquet` | 4.3 MB | 257,499 | **정류장 시퀀스** |
| `korean-otp/data/gtfs/stop_times.txt` | ~800 MB | 20,871,237 | GTFS 정차 시간표 |
| `korean-otp/data/gtfs/stops.txt` | ~10 MB | 212,105 | GTFS 정류장 |
| `korean-otp/data/gtfs/routes.txt` | ~1 MB | 27,138 | GTFS 노선 |
| `korean-otp/data/gtfs/trips.txt` | ~15 MB | 349,580 | GTFS 트립 |
| `DATA/tcn_route_mapping_complete.csv` | 1.5 MB | 25,911 | TCN 노선 카탈로그 |
| `DATA/tcn_to_gtfs_route_mapping.csv` | 21 MB | 288,879 | TCN→GTFS 매핑 |
| `korean-otp/data/od_sample_1000.csv` | 45 KB | 1,000 | OD 샘플 |

### Java 소스 (수정 대상)

| 파일 | 핵심 수정 |
|------|----------|
| `korean-otp/src/.../KoreanCostCalculator.java` | TRANSFER_COST, WAIT_RELUCTANCE 파라미터화 |
| `korean-otp/src/.../KoreanAccessEgress.java` | walkReluctance 파라미터 추가 |
| `korean-otp/src/.../KoreanTransitDataProvider.java` | 보정 파라미터 전달 |
| `korean-otp/src/.../BatchRouter.java` | config 파일 읽기, route_attributes 출력 |

### 빌드/실행 환경

| 항목 | 값 |
|------|-----|
| Java | JDK 21 (`C:\Program Files\Java\jdk-21`) |
| Build | Gradle 8.x |
| Memory | `-Xmx40G` (OSM 로드 시) |
| Python | Anaconda (pandas, pyarrow, xlogit, biogeme) |
