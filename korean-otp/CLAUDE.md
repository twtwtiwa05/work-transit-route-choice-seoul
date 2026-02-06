# CLAUDE.md

Claude Code 작업 가이드 - 한국형 Raptor 경로탐색 엔진

## Project Overview

OTP **Raptor 모듈(JAR)을 그대로 사용**, SPI 인터페이스만 구현하여 한국 GTFS 연결하는 **CLI 기반 대중교통 경로탐색 엔진**

**GitHub:** https://github.com/twtwtiwa05/korean-raptor

**목표:** 출발/도착 좌표 → Raptor 실행 → 경로 출력 **(< 1초) ✅ 달성 (~0.35초)**

---

## Current Status

| Step | 작업 | 상태 |
|------|------|------|
| Phase 1 | GTFS 전처리 (Python) | ✅ 완료 |
| Step 1 | GTFS 모델 & 로더 | ✅ 완료 |
| Step 2 | SPI 구현체 | ✅ 완료 |
| Step 3 | 데이터 빌더 (TransitDataBuilder) | ✅ 완료 |
| Step 4 | 메인 엔진 & CLI | ✅ 완료 |
| Step 4.5 | OSM 기반 도보 경로 | ✅ 완료 |
| Step 5 | GitHub 업로드 & 문서화 | ✅ 완료 |
| Step 6 | MULTI_CRITERIA 최적화 | ✅ 완료 |
| Step 7 | 불필요한 환승 버그 수정 | ✅ 완료 |
| Step 8 | 배치 성능 테스트 (1000 OD) | ✅ 완료 |
| Step 9 | 시나리오 모드 (동적 노선 수정) | ✅ **완료** |

---

## 성능 현황

| 항목 | 값 |
|------|-----|
| 정류장 | 212,105개 |
| 노선(패턴) | 32,229개 |
| 트립 | 349,509개 |
| OSM 노드 | 15,711,249개 |
| **단일 검색 (MULTI_CRITERIA)** | **~0.365초** |
| **배치 처리량 (16스레드)** | **43.4 req/s** |
| **1000 OD 처리** | **23초** |
| **성공률** | **96.7%** |

---

## Step 6: MULTI_CRITERIA 최적화 (완료)

### 최종 설정

`KoreanRaptor.java`에 최적화된 MULTI_CRITERIA 모드:

```java
// STANDARD와 동일 조건 + relaxC1 비활성화
MC_SEARCH_WINDOW_SECONDS = 900    // 15분 (STANDARD와 동일)
MC_ADDITIONAL_TRANSFERS = 3        // 3회 (STANDARD와 동일)
MC_RELAX_RATIO = 1.0               // relaxC1 비활성화 (핵심!)
MC_RELAX_SLACK = 0                 // relaxC1 비활성화

// 메서드
raptor.routeMultiCriteria(fromLat, fromLon, toLat, toLon, departureTime)
```

### 핵심 발견

**relaxC1 비활성화가 성능 향상의 핵심:**
- relaxC1 활성화 시: 파레토 지배 조건 완화 → 더 많은 해 생존 → **느려짐**
- relaxC1 비활성화 시: 엄격한 파레토 → 불필요한 해 제거 → **빨라짐**

### 성능 비교 (동일 조건)

| 프로파일 | 검색 시간 | 경로 수 | 특징 |
|----------|----------|--------|------|
| STANDARD | ~0.35초 | 4개 | 시간 기준 최적 |
| MULTI_CRITERIA | ~0.35초 | **11개** | 파레토 최적 (시간/환승/비용) |

**결론:** MC가 STD와 동일한 속도로 **2.75배 더 많은 경로** 제공!

### CLI 사용법

```
[STD, n=5] > mc                    # MULTI_CRITERIA 모드 전환
검색 모드: MULTI_CRITERIA (파레토 최적)
[MC, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00
```

---

## Step 7: 불필요한 환승 버그 수정 (완료)

### 문제

지하철 직행 경로가 표시되지 않고, 불필요한 버스 환승이 추가됨:
```
서울역 → 홍대입구 (공항철도 직행 가능)
실제 결과: 공항철도 → 환승 도보 → 버스 → 목적지 (환승 1회)
기대 결과: 공항철도 → 도보 → 목적지 (환승 0회)
```

### 원인

`osmCandidateLimit=5`로 인해 버스 정류장만 A* 계산 대상이 됨.
지하철역은 직선 거리 기준 상위 5개에서 제외되어 egress 목록에 포함되지 않음.

### 해결

Access/Egress 후보를 30개로 확대:
```java
// AccessEgressFinder.java
MAX_STOPS = 30              // 10 → 30
osmCandidateLimit = 30      // 5 → 30

// KoreanRaptor.java
MAX_ACCESS_STOPS = 30       // 10 → 30
MAX_EGRESS_STOPS = 30       // 10 → 30
```

### 결과

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 환승 | 1회 | **0회** |
| 소요시간 | 22분 | **16분** |
| 검색시간 | 0.487초 | **0.314초** |

---

## Step 8: 배치 성능 테스트 (완료)

### 테스트 환경

- CPU: AMD Ryzen 7 9700X (8코어/16스레드)
- RAM: 64GB DDR5
- 병렬 스레드: 16개

### 최적 설정

```java
// KoreanRaptor.java
MAX_ACCESS_WALK_METERS = 800.0    // 도보 거리 800m
MAX_EGRESS_WALK_METERS = 800.0
SEARCH_WINDOW_SECONDS = 1800      // 검색 윈도우 30분
MAX_ACCESS_STOPS = 30
MAX_EGRESS_STOPS = 30

// AccessEgressFinder.java
osmCandidateLimit = 50            // A* 후보 50개
```

### 성능 결과

| 항목 | 값 |
|------|-----|
| 1000 OD 처리 시간 | **23초** |
| 처리량 (16스레드) | **43.4 req/s** |
| OD 1건당 평균 | **0.365초** |
| P50 (중앙값) | 322ms |
| P95 | 663ms |
| 성공률 | **96.7%** |

### 배치 실행

```cmd
cd korean-otp
batch-test.cmd
```

---

## Step 9: 시나리오 모드 (완료)

### 개요

원본 데이터를 수정하지 않고 **오버레이 방식**으로 대중교통 네트워크 변경을 시뮬레이션:
- 배차간격 조정 (headway)
- 노선 비활성화 (disable)
- 신규 노선 추가 (add-route)

### 핵심 기능

```
[MAIN] > scenario                    # 시나리오 모드 진입

[SCENARIO] > headway 2호선 1.5       # 배차간격 1.5배 (감축)
[SCENARIO] > disable 9호선           # 노선 비활성화
[SCENARIO] > add-route               # 신규 노선 추가 (대화형)
[SCENARIO] > apply                   # 시나리오 적용
[SCENARIO] > compare 37.55 126.97 37.50 127.03 09:00   # 비교 분석
[SCENARIO] > exit                    # 원본 상태로 복귀
```

### 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    ScenarioCli                          │
│  headway, disable, add-route, apply, compare, exit      │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                  ScenarioManager                         │
│  - modifications: List<Modification>                     │
│  - apply() → ScenarioTransitData                        │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│               ScenarioTransitData                        │
│  - originalData (불변)                                   │
│  - disabledRouteIndices (Set)                           │
│  - modifiedRoutes (Map)                                 │
│  - addedRoutes (List)                                   │
└─────────────────────────────────────────────────────────┘
```

### 성능 최적화

**AccessEgressFinder 재사용**으로 apply 시간 단축:
- 수정 전: 6.7초 (OSM 매핑 재계산)
- 수정 후: **~0.05초** (재사용)

```java
// KoreanRaptor.java - 기존 AccessEgressFinder 재사용 생성자
public KoreanRaptor(TransitData transitData, AccessEgressFinder existingFinder)
```

### 사용 예시: GTX-A 노선 추가

```
[SCENARIO] > add-route
노선명: GTX-A
노선타입(0=트램,2=철도,3=버스): 2
정류장 검색> 수서
  → [1] 수서역 선택
정류장 검색> 성남
  → [2] 성남역 선택
이동시간(분): 8
정류장 검색> done
첫차: 05:30
막차: 23:30
배차간격(분): 10
→ GTX-A 노선 추가 완료 (109 trips)
```

### 패키지 구조

```
kr.otp.scenario/
├── Modification.java              # 수정 인터페이스
├── HeadwayModification.java       # 배차간격 조정
├── DisableRouteModification.java  # 노선 비활성화
├── AddRouteModification.java      # 신규 노선 추가
├── ScenarioTransitData.java       # 수정된 TransitData
├── ScenarioTransitDataProvider.java # SPI 래퍼
├── ScenarioManager.java           # 시나리오 관리
├── ScenarioCli.java               # CLI 인터페이스
├── RouteSearcher.java             # 노선 검색 유틸
└── StopSearcher.java              # 정류장 검색 유틸
```

---

## Build Environment

```
Platform: Windows 11
Java:     JDK 21
          JAVA_HOME = C:\Program Files\Java\jdk-21
Build:    Gradle 8.x (gradlew wrapper 포함)
Memory:   -Xmx40G (OSM 로드 시 필요)
```

### Claude Code 빌드 방법

PowerShell에서 JAVA_HOME이 설정되지 않은 경우:

```powershell
# 방법 1: 임시 스크립트 생성 후 실행
# build-temp.ps1 파일 생성:
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
.\gradlew.bat fatJar

# 실행:
powershell.exe -ExecutionPolicy Bypass -Command "cd 'C:\Users\USER\OneDrive\Desktop\연구실\otp핵심\korean-otp'; ./build-temp.ps1"
```

---

## Quick Commands

```powershell
# 빌드 (JAVA_HOME 설정된 환경에서)
cd korean-otp
.\gradlew.bat fatJar

# 실행
search.cmd 37.5547 126.9707 37.4979 127.0276 09:00 5

# 대화형 모드
search.cmd

# 대화형 CLI 명령어
mc       # MULTI_CRITERIA 모드 토글
n=10     # 결과 수 변경
q        # 종료
```

---

## Key Files

| 파일 | 설명 |
|------|------|
| `KoreanRaptor.java` | 메인 엔진, 프로파일 설정 |
| `AccessEgressFinder.java` | 좌표→정류장 검색, 병렬 A* |
| `WalkingRouter.java` | A* 알고리즘 (HashMap 최적화) |
| `KoreanTransitDataProvider.java` | OTP SPI 최상위 구현체 |
| `BatchRouter.java` | 배치 처리 (병렬 OD 검색) |
| `ScenarioManager.java` | 시나리오 모드 관리 |
| `ScenarioCli.java` | 시나리오 모드 CLI |

---

## Documentation (korean-otp/docs/)

| 문서 | 내용 |
|------|------|
| `GETTING_STARTED.md` | 설치/실행 가이드 |
| `TECHNICAL_ARCHITECTURE.md` | 시스템 설계, SPI 구현 상세 |
| `LIMITATIONS_AND_FUTURE_WORK.md` | 한계점, 개선 로드맵 |
| `BATCH_PERFORMANCE_TEST.md` | 배치 성능 테스트 결과 |
| `Scenario-Mode.md` | 시나리오 모드 사용법 |

---

*마지막 업데이트: 2026-01-19 (시나리오 모드 - 배차간격/노선비활성화/신규노선 추가)*
