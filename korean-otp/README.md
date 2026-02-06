# Korean Raptor

**한국 전국 대중교통 경로탐색 엔진** - OTP Raptor 기반

[![Java](https://img.shields.io/badge/Java-21-orange.svg)](https://openjdk.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

> 출발/도착 좌표만 입력하면 **0.35초 내**에 최적 대중교통 경로를 찾아주는 CLI 엔진
>
> **검색 모드**: STANDARD / MULTI_CRITERIA | **시나리오 모드**: 노선 추가/삭제/배차 조정

### Quick Start

```bash
# 빌드
./gradlew fatJar

# 경로 검색 (서울역 → 강남역)
search.cmd 37.5547 126.9707 37.4979 127.0276 09:00

# 대화형 모드
search.cmd
> mc                   # MULTI_CRITERIA 모드
> scenario             # 시나리오 모드
```

### Based on

[OpenTripPlanner](https://github.com/opentripplanner/OpenTripPlanner)의 **Raptor 모듈** 사용 - Microsoft Research의 [RAPTOR](https://www.microsoft.com/en-us/research/publication/round-based-public-transit-routing/) (2012) 기반

---

## Documentation

| 문서 | 설명 |
|------|------|
| **[시작 가이드](docs/GETTING_STARTED.md)** | 설치, 데이터 준비, 실행 방법 |
| **[기술 아키텍처](docs/TECHNICAL_ARCHITECTURE.md)** | SPI 구현, OSM 통합, 성능 최적화 |
| **[시나리오 모드](docs/Scenario-Mode.md)** | 노선 추가/삭제, 배차 조정 시뮬레이션 |
| **[배치 테스트](docs/BATCH_PERFORMANCE_TEST.md)** | 1000 OD 대량 처리 성능 |
| **[한계점 및 로드맵](docs/LIMITATIONS_AND_FUTURE_WORK.md)** | 제한사항, 개선 계획 |

---

## Features

| 기능 | 설명 |
|------|------|
| **전국 대중교통** | 버스, 지하철, KTX/SRT, 일반철도 (21만 정류장, 35만 트립) |
| **초고속 검색** | ~0.35초 (STANDARD: 4개, MULTI_CRITERIA: 11개 파레토 최적) |
| **시나리오 모드** | 노선 추가/삭제, 배차간격 조정 → 정책 시뮬레이션 |
| **배치 처리** | 1000 OD → 23초 (43.4 req/s, 16스레드 병렬) |
| **OSM 도보 경로** | A* 알고리즘 기반 실제 도로 경로 (15M 노드) |
| **좌표 기반 검색** | 위도/경도 → 가까운 정류장 자동 탐색 |

---

## Demo

```
═══════════════════════════════════════════════════════════════
           한국형 Raptor 경로탐색 엔진 v1.0.0-SNAPSHOT
═══════════════════════════════════════════════════════════════

[1/4] GTFS 데이터 로드 중...
  완료: 212,105 정류장, 27,138 노선, 349,580 트립 (8.2초)
[2/4] Raptor 데이터 구조 생성 중...
  완료: 32,229 패턴, 349,509 트립 (4.1초)
[3/4] OSM 도로망 로드 중...
  완료: StreetNetwork[nodes=15711249, edges=3547892] (45.3초)
[4/4] Raptor 엔진 초기화...
  완료: KoreanRaptor[stops=212105, routes=32229, trips=349509]
  도보 거리: OSM 기반 (실제 도로)

═══════════════════════════════════════════════════════════════
  초기화 완료! (58.2초)
═══════════════════════════════════════════════════════════════

[STD, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00 5
검색 [STANDARD]: (37.5547, 126.9707) → (37.4979, 127.0276) @ 09:00 이후, 최대 5개
─────────────────────────────────────────────────────────────────
09:00 이후 경로 4개 (전체 4개, 0.350초)

■ 경로 1: 09:00 출발 → 09:40 도착 (39분, 환승 2회)
  1. 도보 3분 → 서울역버스환승센터
  2. [500] 서울역버스환승센터 09:03 → 숙대입구역 09:07
  3. 환승 도보 1분
  4. [서울4호선] 숙대입구 09:11 → 사당 09:25
  5. 환승 도보 0분
  6. [서울2호선] 사당 09:30 → 강남 09:39
  7. 도보 0분 → 목적지

[STD, n=5] > mc
검색 모드: MULTI_CRITERIA (파레토 최적)

[MC, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00 5
검색 [MULTI_CRITERIA]: (37.5547, 126.9707) → (37.4979, 127.0276) @ 09:00 이후, 최대 5개
─────────────────────────────────────────────────────────────────
09:00 이후 경로 11개 (전체 11개, 0.350초)

■ 경로 1: 09:00 출발 → 09:40 도착 (39분, 환승 2회)  ← 시간 최적
  ...
■ 경로 2: 09:02 출발 → 09:48 도착 (45분, 환승 1회)  ← 환승 최적
  ...
```

---

## Installation

### 1. 요구사항

- **Java 21** 이상
- **40GB+ RAM** (OSM 사용 시) / 8GB (OSM 미사용)
- **GTFS 데이터** (한국 전국)

### 2. 빌드

```bash
git clone https://github.com/twtwtiwa05/korean-raptor.git
cd korean-raptor

# Fat JAR 빌드
./gradlew fatJar   # Linux/macOS
gradlew.bat fatJar # Windows
```

### 3. 데이터 준비

#### GTFS 데이터 (필수)
```
data/gtfs/
├── stops.txt
├── routes.txt
├── trips.txt
├── stop_times.txt
├── calendar.txt
└── transfers.txt
```

#### OSM 데이터 (선택적 - 실제 도보 경로)
```bash
mkdir -p data/osm
curl -L -o data/osm/south-korea.osm.pbf \
  https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
```

---

## Usage

### 커맨드라인 실행

```bash
# Windows
search.cmd [출발위도] [출발경도] [도착위도] [도착경도] [시간] [결과수]

# 예시: 서울역 → 강남역, 09:00 출발
search.cmd 37.5547 126.9707 37.4979 127.0276 09:00 5
```

### 대화형 모드

```bash
search.cmd

[STD, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00   # STANDARD 모드 검색
[STD, n=5] > mc                                         # MULTI_CRITERIA 모드 전환
[MC, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00    # MULTI_CRITERIA 검색
[MC, n=5] > std                                         # STANDARD 모드 전환
[STD, n=5] > n=10                                       # 결과 개수 변경
[STD, n=10] > q                                         # 종료
```

### 검색 모드

| 모드 | 명령어 | 특징 | 검색 시간 | 경로 수 |
|------|--------|------|----------|--------|
| **STANDARD** | `std` | 시간 기준 최적 경로 | ~0.35초 | 4개 |
| **MULTI_CRITERIA** | `mc` | 파레토 최적 (시간/환승/비용 다양) | ~0.35초 | **11개** |

### 시나리오 모드

대중교통 네트워크 변경을 시뮬레이션하여 정책 효과를 분석합니다.

```bash
[STD, n=5] > scenario                              # 시나리오 모드 진입

[SCENARIO] > disable 9호선                          # 노선 비활성화
[SCENARIO] > headway 2호선 1.5                      # 배차간격 1.5배 (감축)
[SCENARIO] > add-route                             # 신규 노선 추가 (대화형)
[SCENARIO] > apply                                 # 시나리오 적용
[SCENARIO] > compare 37.55 126.97 37.50 127.03 09:00  # 원본 vs 시나리오 비교
[SCENARIO] > exit                                  # 원본 상태로 복귀
```

**사용 예시:** 9호선 폐선 시 강남역 접근성 변화, GTX-A 개통 효과 분석

> 상세 사용법: **[시나리오 모드 문서](docs/Scenario-Mode.md)**

### 테스트 좌표

| 구간 | 출발 | 도착 | 명령어 |
|------|------|------|--------|
| 서울역→강남역 | 37.5547, 126.9707 | 37.4979, 127.0276 | `37.5547 126.9707 37.4979 127.0276 09:00` |
| 서울역→부산역 | 37.5547, 126.9707 | 35.1150, 129.0410 | `37.5547 126.9707 35.1150 129.0410 09:00` |
| 홍대→잠실 | 37.5571, 126.9244 | 37.5133, 127.1001 | `37.5571 126.9244 37.5133 127.1001 09:00` |

---

## Performance

### 데이터 규모

| 항목 | 수량 |
|------|------|
| 정류장 | 212,105개 |
| 노선(패턴) | 32,229개 |
| 트립 | 349,509개 |
| 환승 | 2,027,380개 |
| OSM 노드 | 15,711,249개 |

### 검색 성능

| 항목 | STANDARD | MULTI_CRITERIA |
|------|----------|----------------|
| 단일 검색 | ~0.35초 | ~0.35초 |
| 경로 수 | 4개 | **11개** (파레토 최적) |
| 배치 처리 (16스레드) | **43.4 req/s** | - |
| 1000 OD 처리 | **23초** | - |

> 배치 테스트 상세: **[BATCH_PERFORMANCE_TEST.md](docs/BATCH_PERFORMANCE_TEST.md)**

### 최적화 기법

**공통:**
- **병렬 A* 실행**: 멀티코어 활용 (8코어)
- **HashMap 기반 A***: 15M 노드 초기화 제거
- **정류장-노드 사전 매핑**: 초기화 시 1회 계산

**MULTI_CRITERIA 최적화** (14초 → 0.35초, 40배 개선):
- **relaxC1 비활성화**: 엄격한 파레토 지배 → 불필요한 해 빠르게 제거
- **PARETO_CHECK_AGAINST_DESTINATION**: 목적지 기준 조기 가지치기
- **STANDARD와 동일 조건**: 15분 윈도우, 3회 환승 (탐색 공간 동일)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Korean Raptor Engine                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [좌표 입력]                                                 │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────┐     ┌─────────────────────┐       │
│  │ AccessEgressFinder  │────▶│   WalkingRouter     │       │
│  │ (가까운 정류장 탐색)  │     │   (A* 병렬 실행)     │       │
│  └─────────────────────┘     └─────────────────────┘       │
│       │                              │                      │
│       │                              ▼                      │
│       │                      ┌─────────────────────┐       │
│       │                      │   StreetNetwork     │       │
│       │                      │   (15M 노드 그래프)   │       │
│       │                      └─────────────────────┘       │
│       │                              ▲                      │
│       │                              │                      │
│       │                      ┌─────────────────────┐       │
│       │                      │     OsmLoader       │       │
│       │                      │  (south-korea.pbf)  │       │
│       │                      └─────────────────────┘       │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  OTP Raptor JAR                      │   │
│  │         (STANDARD / MULTI_CRITERIA 프로파일)         │   │
│  └─────────────────────────────────────────────────────┘   │
│       │                                                     │
│       ▼                                                     │
│  [경로 결과 출력]                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
korean-otp/
├── build.gradle                 # Gradle 빌드 설정
├── search.cmd                   # 실행 스크립트 (Windows)
├── search.ps1                   # 실행 스크립트 (PowerShell)
│
├── libs/                        # OTP Raptor JAR
│   ├── raptor-*.jar
│   └── utils-*.jar
│
├── data/
│   ├── gtfs/                    # GTFS 데이터
│   └── osm/                     # OSM 데이터 (선택적)
│
└── src/main/java/kr/otp/
    ├── Main.java                # CLI 진입점
    │
    ├── core/                    # 핵심 엔진
    │   ├── KoreanRaptor.java
    │   └── AccessEgressFinder.java
    │
    ├── scenario/                # 시나리오 모드 ⭐
    │   ├── ScenarioManager.java
    │   ├── ScenarioCli.java
    │   ├── ScenarioTransitData.java
    │   └── *Modification.java
    │
    ├── osm/                     # OSM 도보 경로
    │   ├── OsmLoader.java
    │   ├── StreetNetwork.java
    │   └── WalkingRouter.java
    │
    ├── gtfs/                    # GTFS 모델 & 로더
    │   ├── model/
    │   └── loader/
    │
    └── raptor/
        ├── data/                # TransitData
        └── spi/                 # OTP SPI 구현체
```

---

## Configuration

### STANDARD 모드 설정 (`KoreanRaptor.java`)

```java
MAX_ACCESS_WALK_METERS = 400.0   // 최대 도보 거리 (m)
SEARCH_WINDOW_SECONDS = 900      // 검색 시간 범위 (15분)
MAX_ACCESS_STOPS = 30            // 출발 정류장 후보 수 (지하철역 포함 위해 증가)
MAX_EGRESS_STOPS = 30            // 도착 정류장 후보 수 (지하철역 포함 위해 증가)
numberOfAdditionalTransfers(3)   // 최대 환승 횟수
```

### MULTI_CRITERIA 모드 설정 (`KoreanRaptor.java`)

```java
MC_SEARCH_WINDOW_SECONDS = 900   // 검색 시간 범위 (15분, STANDARD와 동일)
MC_ADDITIONAL_TRANSFERS = 3      // 최대 추가 환승 횟수 (STANDARD와 동일)
MC_RELAX_RATIO = 1.0             // relaxC1 비활성화 (엄격한 파레토)
MC_RELAX_SLACK = 0               // relaxC1 비활성화
```

### A* 설정 (`WalkingRouter.java`)

```java
MAX_SEARCH_DISTANCE = 500.0      // 최대 탐색 거리 (m)
maxIterations = 15000            // 최대 반복 횟수
WALK_SPEED_MPS = 1.2             // 도보 속도 (m/s)
```

---

## Dependencies

- [OTP Raptor](https://github.com/opentripplanner/OpenTripPlanner) - 경로탐색 알고리즘
- [osm4j](https://github.com/topobyte/osm4j) - OSM 파싱
- [OpenCSV](https://opencsv.sourceforge.net/) - GTFS CSV 파싱
- [SLF4J](https://www.slf4j.org/) + [Logback](https://logback.qos.ch/) - 로깅

---

## References

- [RAPTOR Algorithm Paper](https://www.microsoft.com/en-us/research/publication/round-based-public-transit-routing/) - Microsoft Research, 2012
- [OpenTripPlanner](https://www.opentripplanner.org/) - 오픈소스 대중교통 플래너
- [GTFS Specification](https://gtfs.org/schedule/reference/) - General Transit Feed Specification
- [OpenStreetMap](https://www.openstreetmap.org/) - 오픈소스 지도 데이터

---

## Author

**김태우 (Taewoo Kim)**

- 가천대학교 학부생
- CAMMUS 연구원
- GitHub: [@twtwtiwa05](https://github.com/twtwtiwa05)
- Email: twdaniel@gachon.ac.kr

---

## License

이 프로젝트의 소스 코드는 **MIT License**로 배포됩니다 - [LICENSE](LICENSE) 참조.

**의존성 라이선스:**
- OTP Raptor JAR (`libs/`): [LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html) - OpenTripPlanner 프로젝트

---

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Acknowledgments

- [OpenTripPlanner](https://github.com/opentripplanner/OpenTripPlanner) 팀의 Raptor 알고리즘 구현
- [Geofabrik](https://download.geofabrik.de/) OSM 데이터 제공
- 한국 공공데이터포털 GTFS 데이터

---

**Made with ❤️ for Korean public transit**
