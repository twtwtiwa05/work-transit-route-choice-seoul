# Korean Raptor 시작 가이드

처음 사용하시는 분을 위한 상세 설치 및 실행 가이드입니다.

---

## 목차

1. [필수 요구사항](#1-필수-요구사항)
2. [Java 설치](#2-java-설치)
3. [프로젝트 다운로드](#3-프로젝트-다운로드)
4. [GTFS 데이터 준비](#4-gtfs-데이터-준비)
5. [OSM 데이터 준비 (선택)](#5-osm-데이터-준비-선택)
6. [빌드](#6-빌드)
7. [실행](#7-실행)
8. [사용법](#8-사용법)
9. [문제 해결](#9-문제-해결)

---

## 1. 필수 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| **운영체제** | Windows 10/11, Linux, macOS | Windows 11 |
| **Java** | JDK 21 이상 | JDK 21 |
| **메모리(RAM)** | 8GB (OSM 미사용) | 40GB+ (OSM 사용) |
| **디스크** | 5GB | 10GB+ |
| **CPU** | 4코어 | 8코어+ |

### 메모리 안내

- **OSM 미사용**: 8GB RAM으로 실행 가능 (직선 거리 기반)
- **OSM 사용**: 40GB+ RAM 필요 (실제 도보 경로, 15M 노드 그래프)

---

## 2. Java 설치

### Windows

#### 방법 1: Oracle JDK (권장)

1. [Oracle JDK 21 다운로드](https://www.oracle.com/java/technologies/downloads/#java21) 접속
2. **Windows** 탭 선택
3. **x64 Installer** 다운로드 (예: `jdk-21_windows-x64_bin.exe`)
4. 설치 파일 실행 → 기본 설정으로 설치

#### 방법 2: OpenJDK (무료)

1. [Adoptium OpenJDK 21](https://adoptium.net/temurin/releases/?version=21) 접속
2. **Windows x64** → **.msi** 다운로드
3. 설치 파일 실행 → **Set JAVA_HOME variable** 체크 → 설치

#### Java 설치 확인

```cmd
java -version
```

출력 예시:
```
openjdk version "21.0.2" 2024-01-16
OpenJDK Runtime Environment Temurin-21.0.2+13 (build 21.0.2+13)
OpenJDK 64-Bit Server VM Temurin-21.0.2+13 (build 21.0.2+13, mixed mode)
```

> 버전이 21 이상이면 정상입니다.

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install openjdk-21-jdk

# 확인
java -version
```

### macOS

```bash
# Homebrew 사용
brew install openjdk@21

# 환경변수 설정
echo 'export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 확인
java -version
```

---

## 3. 프로젝트 다운로드

### 방법 1: Git Clone (권장)

```bash
# Git이 설치되어 있다면
git clone https://github.com/twtwtiwa05/korean-raptor.git
cd korean-raptor
```

### 방법 2: ZIP 다운로드

1. [GitHub 저장소](https://github.com/twtwtiwa05/korean-raptor) 접속
2. 녹색 **Code** 버튼 클릭
3. **Download ZIP** 클릭
4. 압축 해제

---

## 4. GTFS 데이터 준비

GTFS(General Transit Feed Specification)는 대중교통 시간표 데이터 형식입니다.

### 필요한 파일

```
korean-raptor/
└── data/
    └── gtfs/
        ├── stops.txt        # 정류장 정보
        ├── routes.txt       # 노선 정보
        ├── trips.txt        # 운행 정보
        ├── stop_times.txt   # 정차 시간표
        ├── calendar.txt     # 운행 요일
        └── transfers.txt    # 환승 정보 (선택)
```

### GTFS 데이터 구하기

#### 한국 공공데이터포털

1. [공공데이터포털](https://www.data.go.kr/) 접속
2. "GTFS" 검색
3. 필요한 지역 데이터 다운로드:
   - 전국 버스 GTFS
   - 전국 철도 GTFS
   - 지하철 GTFS

#### 데이터 배치

다운로드한 파일들을 `data/gtfs/` 폴더에 복사합니다.

```cmd
mkdir data\gtfs
# 다운로드한 GTFS 파일들을 data\gtfs\ 폴더로 복사
```

### GTFS 파일 형식 확인

각 파일의 첫 줄(헤더)이 올바른지 확인하세요:

**stops.txt**
```csv
stop_id,stop_name,stop_lat,stop_lon
100000001,서울역버스환승센터,37.5547,126.9707
```

**routes.txt**
```csv
route_id,route_short_name,route_long_name,route_type
1001,750B,서울역-숙대입구,3
```

**trips.txt**
```csv
route_id,service_id,trip_id,trip_headsign
1001,weekday,trip_001,숙대입구방면
```

**stop_times.txt**
```csv
trip_id,arrival_time,departure_time,stop_id,stop_sequence
trip_001,09:00:00,09:00:00,100000001,1
trip_001,09:05:00,09:05:00,100000002,2
```

**calendar.txt**
```csv
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
weekday,1,1,1,1,1,0,0,20240101,20241231
```

---

## 5. OSM 데이터 준비 (선택)

OSM(OpenStreetMap) 데이터를 사용하면 실제 도로를 따라 도보 거리를 계산합니다.
사용하지 않으면 직선 거리(Haversine)로 계산합니다.

### 요구사항

- **메모리**: 40GB+ RAM 필요
- **디스크**: 약 300MB

### 다운로드

```cmd
mkdir data\osm

# Windows (curl 사용)
curl -L -o data\osm\south-korea.osm.pbf https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
```

또는 브라우저에서 직접 다운로드:
- [Geofabrik 한국 OSM](https://download.geofabrik.de/asia/south-korea.html) 접속
- `south-korea-latest.osm.pbf` 클릭하여 다운로드
- `data/osm/` 폴더에 저장

> **중요: 파일명은 반드시 `south-korea.osm.pbf`로 저장해야 합니다.**
>
> Geofabrik에서 다운로드하면 `south-korea-latest.osm.pbf`로 저장되는데,
> 이 경우 프로그램이 파일을 인식하지 못합니다.
>
> ```cmd
> # 파일명 변경 (필수)
> rename data\osm\south-korea-latest.osm.pbf south-korea.osm.pbf
> ```

### OSM 사용 여부

| OSM 파일 | 동작 | 메모리 | 정확도 |
|----------|------|--------|--------|
| 있음 | 실제 도로 기반 A* 알고리즘 | 40GB+ | 높음 |
| 없음 | 직선 거리 (Haversine) | 8GB | 보통 |

---

## 6. 빌드

### Windows (CMD)

```cmd
cd korean-raptor
gradlew.bat fatJar
```

### Windows (PowerShell)

```powershell
cd korean-raptor
.\gradlew.bat fatJar
```

### Linux / macOS

```bash
cd korean-raptor
chmod +x gradlew
./gradlew fatJar
```

### 빌드 성공 확인

```
BUILD SUCCESSFUL in XXs
```

빌드 결과물: `build/libs/korean-raptor-1.0.0-SNAPSHOT-all.jar`

---

## 7. 실행

### Windows (CMD 권장 - 한글 출력)

```cmd
search.cmd
```

### Windows (PowerShell)

```powershell
.\search.ps1
```

### Linux / macOS

```bash
java -Xmx40G -jar build/libs/korean-raptor-1.0.0-SNAPSHOT-all.jar
```

> **-Xmx40G**: OSM 사용 시 40GB 메모리 할당. OSM 미사용 시 `-Xmx8G`로 변경 가능.

### 초기화 화면

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

[STD, n=5] >
```

프롬프트 설명:
- `STD`: 현재 검색 모드 (STANDARD)
- `MC`: MULTI_CRITERIA 모드
- `n=5`: 결과 개수

---

## 8. 사용법

### 기본 사용법

프롬프트에 다음 형식으로 입력합니다:

```
[출발위도] [출발경도] [도착위도] [도착경도] [출발시간] [결과수]
```

### 예시: 서울역 → 강남역

```
[STD, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00 5
```

**입력값 설명:**
| 값 | 의미 | 예시 |
|----|------|------|
| 37.5547 | 출발지 위도 | 서울역 |
| 126.9707 | 출발지 경도 | 서울역 |
| 37.4979 | 도착지 위도 | 강남역 |
| 127.0276 | 도착지 경도 | 강남역 |
| 09:00 | 출발 시간 | 오전 9시 |
| 5 | 결과 개수 | 최대 5개 경로 |

### 결과 출력 예시 (STANDARD 모드)

```
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
```

### 결과 출력 예시 (MULTI_CRITERIA 모드)

```
검색 [MULTI_CRITERIA]: (37.5547, 126.9707) → (37.4979, 127.0276) @ 09:00 이후, 최대 5개
─────────────────────────────────────────────────────────────────
09:00 이후 경로 11개 (전체 11개, 0.350초)

■ 경로 1: 09:00 출발 → 09:40 도착 (39분, 환승 2회)  ← 시간 최적
  ...
■ 경로 2: 09:02 출발 → 09:48 도착 (45분, 환승 1회)  ← 환승 최적
  ...
```

MULTI_CRITERIA 모드는 시간/환승/비용 등 다양한 기준의 파레토 최적 경로를 반환합니다.
STANDARD와 동일한 속도(~0.35초)로 **2.75배 더 많은 경로**(11개 vs 4개)를 제공합니다.

### 좌표 찾는 방법

1. [Google Maps](https://maps.google.com) 접속
2. 원하는 위치 우클릭
3. 좌표 복사 (예: `37.5547, 126.9707`)

또는 [Kakao Map](https://map.kakao.com)에서도 확인 가능합니다.

### 대화형 명령어

| 명령어 | 설명 |
|--------|------|
| `mc` | MULTI_CRITERIA 모드로 전환 (파레토 최적) |
| `std` | STANDARD 모드로 전환 (시간 최적) |
| `n=10` | 결과 개수를 10개로 변경 |
| `q` 또는 `quit` | 프로그램 종료 |

### 검색 모드 비교

| 모드 | 명령어 | 특징 | 검색 시간 | 경로 수 |
|------|--------|------|----------|--------|
| **STANDARD** | `std` | 시간 기준 최적 경로 | ~0.35초 | 4개 |
| **MULTI_CRITERIA** | `mc` | 파레토 최적 (시간/환승/비용 다양) | ~0.35초 | **11개** |

**MULTI_CRITERIA 모드 예시:**
```
[STD, n=5] > mc
검색 모드: MULTI_CRITERIA (파레토 최적)
[MC, n=5] > 37.5547 126.9707 37.4979 127.0276 09:00
...
[MC, n=5] > std
검색 모드: STANDARD (최단 시간)
[STD, n=5] >
```

### 테스트 좌표 모음

#### 장거리 (KTX/철도)

| 구간 | 명령어 |
|------|--------|
| 서울역 → 부산역 | `37.5547 126.9707 35.1150 129.0410 09:00 5` |
| 서울역 → 대구역 | `37.5547 126.9707 35.8714 128.6014 09:00 5` |
| 서울역 → 대전역 | `37.5547 126.9707 36.3510 127.3848 09:00 5` |

#### 중거리 (지하철/버스)

| 구간 | 명령어 |
|------|--------|
| 서울역 → 강남역 | `37.5547 126.9707 37.4979 127.0276 09:00 5` |
| 홍대입구 → 잠실역 | `37.5571 126.9244 37.5133 127.1001 09:00 5` |
| 종로3가 → 여의도 | `37.5662 126.9785 37.4837 126.9029 09:00 5` |

#### 단거리

| 구간 | 명령어 |
|------|--------|
| 서울역 → 홍대입구 | `37.5547 126.9707 37.5571 126.9244 09:00 5` |
| 강남역 → 잠실역 | `37.4979 127.0276 37.5133 127.1001 09:00 5` |

---

## 9. 문제 해결

### Java를 찾을 수 없음

**증상:**
```
'java'은(는) 내부 또는 외부 명령, 실행할 수 있는 프로그램, 또는 배치 파일이 아닙니다.
```

**해결:**
1. Java가 설치되었는지 확인
2. 환경변수 PATH에 Java 경로 추가:
   - 시스템 속성 → 환경변수 → Path → 편집
   - `C:\Program Files\Java\jdk-21\bin` 추가

### 메모리 부족 (OutOfMemoryError)

**증상:**
```
java.lang.OutOfMemoryError: Java heap space
```

**해결:**
1. `search.cmd` 파일 열기
2. `-Xmx` 값 증가 (예: `-Xmx40G` → `-Xmx50G`)
3. OSM 사용하지 않으려면 `data/osm/` 폴더 삭제

### GTFS 데이터 오류

**증상:**
```
Error loading GTFS: stops.txt not found
```

**해결:**
1. `data/gtfs/` 폴더에 필요한 파일이 있는지 확인
2. 파일 이름이 정확한지 확인 (대소문자 구분)
3. CSV 형식이 올바른지 확인 (UTF-8 인코딩)

### 경로를 찾을 수 없음

**증상:**
```
경로를 찾을 수 없습니다
```

**원인:**
- 출발지/도착지 근처에 정류장이 없음
- 해당 시간대에 운행하는 노선이 없음
- GTFS 데이터에 해당 지역이 포함되지 않음

**해결:**
- 다른 좌표로 시도
- 출발 시간 변경
- GTFS 데이터 확인

### 한글 깨짐

**증상:**
```
???? ?? ??? ????
```

**해결:**
- CMD 대신 PowerShell 사용, 또는
- CMD에서 실행 전: `chcp 65001` 입력

---

## 추가 정보

- **소스 코드**: [GitHub](https://github.com/twtwtiwa05/korean-raptor)
- **버그 리포트**: [GitHub Issues](https://github.com/twtwtiwa05/korean-raptor/issues)
- **이메일**: twdaniel@gachon.ac.kr

---

*마지막 업데이트: 2026-01*
