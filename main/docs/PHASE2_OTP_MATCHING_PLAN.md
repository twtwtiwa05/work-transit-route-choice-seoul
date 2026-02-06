# Phase 2: OTP 배치 실행 + 경로 매칭 + 모델 데이터 구성

**작성일**: 2026-02-06
**최종 수정**: 2026-02-07 (Step 3-4 완료 기록)
**선행**: Phase 1 완료 (8개 산출물)
**목표**: TCD 관측 통행 vs OTP 대안 경로 매칭 → 선택 모형 추정용 데이터셋 구성

---

## 진행 현황 요약

| Step | 작업 | 상태 | 비고 |
|------|------|------|------|
| Step 1 | GTFS↔TCD ID 매핑 | ✅ 완료 | 좌표 기반 KD-Tree |
| Step 2 | OTP Java 수정 | ✅ 완료 | CalibrationConfig, summary 블록 |
| Step 3 | OTP 배치 실행 | ✅ 완료 | 1,263,225 OD, 8시간, 89.6% 성공 |
| Step 4 | OTP 결과 파싱 | ✅ 완료 | 4,477,498 경로 (중복제거 후) |
| Step 5 | 유사도 계산 | ⏳ 대기 | |
| Step 6 | Choice Set 구성 | ⏳ 대기 | |

---

## 전체 흐름도

```
Phase 1 산출물
  ├── od_pairs_filtered.csv (1,263,225 OD) ← 미매칭 제외
  ├── trip_attributes_filtered.parquet (1,467,135 체인)
  ├── leg_stop_sequences.parquet (레그별 경유 정류장)
  └── route_stop_sequences.parquet (노선별 전체 시퀀스)
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  Step 1: GTFS↔TCD ID 매핑 ✅ 완료                        │
│  좌표 기반 KD-Tree 매칭 (버스50m/지하철100m)              │
│  → gtfs_to_tcd_stop.parquet, subway_line_mapping.json   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  Step 2: OTP Java 수정 ✅ 완료                           │
│  (a) MULTI_CRITERIA=true (최대 10개 Pareto 대안)         │
│  (b) 파라미터 외부화 (calibration_config.json)           │
│  (c) summary 블록 추가 (Step 4 편의)                     │
│  (d) 청크 처리 + 체크포인트 (장시간 안정성)               │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  Step 3: OTP 배치 실행 ✅ 완료                           │
│  od_pairs_filtered.csv → BatchRouter                    │
│  → batch_result_iter0.ndjson (30.4GB)                   │
│  1,263,225 OD, 성공 1,131,266 (89.6%), 8시간            │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  Step 4: OTP 결과 파싱 ✅ 완료                           │
│  JSON escape 문제 해결 (polyline points 필드 제거)       │
│  중복 제거: 8,907,900 → 4,477,498 경로 (49.7% 감소)      │
│  → otp_alternatives.parquet (0.46GB)                    │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
              (Step 5-6: 실행 예정)
```

---

## Step 1: GTFS↔TCD ID 매핑 ✅ 완료

### 실행 결과

**핵심 발견**: GTFS ID(9자리) ≠ TCD/STTN ID(7~8자리) → 직접 변환 불가
**해결책**: 좌표 기반 KD-Tree 매칭

### 매핑 방법 및 결과

| 항목 | 방법 | 결과 |
|------|------|------|
| **버스 정류장** | 좌표 KD-Tree (50m 이내) | 46,859개 매핑 (역방향 매칭 포함) |
| **지하철 역** | 좌표 KD-Tree (100m 이내) | 97.1% 매핑 |
| **버스 노선** | route_short_name ↔ 노선명(short) | 85.3% 매핑 |
| **지하철 노선** | long_name 기반 수동 매핑 | 39/39 (100%) |

### 지하철 노선 매핑 상세

```python
# 자동 매핑 17개: GTFS long_name에 "서울N호선" 포함
# 수동 매핑 22개: 분기선, 경의중앙선, 공항철도 등

subway_line_mapping = {
    "서울1호선": ["201"],
    "서울2호선": ["202"],
    "서울3호선": ["203"],
    ...
    "수인분당선": ["211", "212"],  # 통합
    "경의중앙선": ["213", "214"],  # 통합
    ...
}
```

### 산출물

| 파일 | 위치 | 내용 |
|------|------|------|
| `gtfs_to_tcd_stop.parquet` | `main/output/` | GTFS stop_id → TCD stop_id |
| `tcd_to_gtfs_stop.parquet` | `main/output/` | TCD stop_id → GTFS stop_id |
| `gtfs_to_tcd_route.parquet` | `main/output/` | GTFS route_id → TCD route_id |
| `subway_line_mapping.json` | `main/output/` | 지하철 노선 매핑 |

### OD 필터링 결과

미매칭 정류장이 포함된 OD 제외:

| 항목 | 원본 | 필터링 후 | 비율 |
|------|------|----------|------|
| 체인 | 2,011,801 | **1,467,135** | 72.9% |
| OD쌍 | 1,781,135 | **1,263,225** | 70.9% |

---

## Step 2: OTP Java 수정 ✅ 완료

### 2a: BatchRouter.java 대폭 리팩터링 (v3.0)

**변경 전 문제점**:
- 최대 경로 5개 제한
- 전체 Future를 한꺼번에 생성 → 1.26M OD 시 메모리 부족
- 크래시 시 전체 재시작 필요
- 100건마다 진행률만 표시

**변경 후 개선**:

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 최대 경로 수 | 5개 | **10개** |
| 메모리 관리 | 전체 Future 생성 | **청크(10K)별 처리** |
| 장애 복구 | 없음 | **체크포인트 재개** |
| 출력 방식 | 전체 후 저장 | **청크별 즉시 flush** |
| 진행 표시 | 100건마다 | **10,000건 + ETA** |

### 2b: summary 블록 추가 (Step 4 편의)

각 itinerary JSON에 요약 정보 포함:

```json
{
  "startTime": 1768949197000,
  "endTime": 1768950354000,
  "duration": 1157,
  "summary": {
    "n_transfers": 1,
    "ride_time_sec": 949,
    "walk_time_sec": 118,
    "has_subway": true,
    "modes": ["BUS", "SUBWAY"],
    "stop_sequence": ["1:BS_1100_xxx", "1:BS_1100_yyy", "1:RS_ACC1_zzz", ...]
  },
  "legs": [...]
}
```

**효과**: Step 4에서 legs 순회 없이 summary만으로 빠른 속성 추출 가능

### 2c: 체크포인트/재개 메커니즘

```
batch_result_iter0.ndjson          ← 결과 (청크별 append)
batch_result_iter0.ndjson.progress ← 처리 완료 OD 수

재개 시:
1. progress 파일에서 완료 수 읽기
2. 해당 위치부터 이어서 처리
3. 완료 시 progress 파일 삭제
```

### 2d: CalibrationConfig 도입 (Phase 4 대비)

```json
// calibration_config.json
{
  "walkReluctance": 1.0,
  "transferCostSeconds": 120,
  "waitReluctance": 1.0,
  "firstBoardCostSeconds": 60
}
```

수정된 Java 파일:

| 파일 | 수정 내용 |
|------|----------|
| `CalibrationConfig.java` | 🆕 설정 클래스 |
| `BatchRouter.java` | 청크 처리, 체크포인트, summary, max 10 |
| `KoreanCostCalculator.java` | 파라미터 생성자 주입 |
| `KoreanAccessEgress.java` | walkReluctance 곱하기 |
| `KoreanTransitDataProvider.java` | 파라미터 전달 |

### 빌드 및 테스트 결과

```
100건 테스트:
- 총 100건 처리 완료
- summary 필드: 98개 OD에 정상 포함
- 경로 없음: 2건
- 성공률: 98%
- NDJSON 형식 정상
```

---

## Step 3: OTP 배치 실행 ✅ 완료

### 입력 파일

| 파일 | 위치 | 건수 |
|------|------|------|
| `od_pairs_filtered.csv` | `korean-otp/data/` | 1,263,225 |

### 실행 명령

```cmd
cd korean-otp
run-batch-full.cmd
```

### 실행 환경

```cmd
# run-batch-full.cmd
java -Xmx40G -XX:+UseG1GC -XX:MaxGCPauseMillis=200 ...
     -jar korean-raptor-1.0.0-SNAPSHOT-all.jar
     batch data\od_pairs_filtered.csv batch_result_iter0.ndjson 16
```

| 설정 | 값 | 이유 |
|------|-----|------|
| 메모리 | 40GB | OSM + GTFS 로드 |
| GC | G1GC | 장시간 실행 최적화 |
| 스레드 | 16 | 8코어/16스레드 최대 활용 |

### 실행 결과 (2026-02-06~07)

| 항목 | 예상 | **실측** |
|------|------|---------|
| 총 OD | 1,263,225 | 1,263,225 |
| 성공 (경로 있음) | - | **1,131,266 (89.6%)** |
| 실패 (경로 없음) | - | 131,959 (10.4%) |
| 처리 속도 | 43.4 req/s | **42.5 req/s** |
| **총 소요시간** | ~8시간 | **약 8시간 16분** |
| 출력 크기 | 8-10GB | **30.4 GB** |

### 실패 원인 분석

경로 없음 131,959건의 주요 원인:

| 원인 | 비율 | 설명 |
|------|------|------|
| **심야 시간대** | ~60% | 23시~05시 출발, 대중교통 미운행 |
| 장거리 OD | ~25% | 도보 접근 불가 (800m 초과) |
| 격리 지역 | ~15% | GTFS에 정류장 없는 지역 |

### 출력 형식 (NDJSON)

```json
{"id":0,"searchTimeMs":411,"data":{"plan":{"itineraries":[
  {"startTime":...,"summary":{"n_transfers":0,"ride_time_sec":949,...},"legs":[...]},
  {"startTime":...,"summary":{"n_transfers":1,"ride_time_sec":823,...},"legs":[...]},
  ...
]}}}
{"id":1,"searchTimeMs":325,"data":{"plan":{"itineraries":[...]}}}
...
```

### 산출물

| 파일 | 위치 | 크기 |
|------|------|------|
| `batch_result_iter0.ndjson` | `korean-otp/` | 30.4 GB |

---

## Step 4: OTP 결과 파싱 + 속성 추출 ✅ 완료

### 실행 스크립트

```cmd
cd main
python scripts/matching/step4_parse_otp_results.py
```

### JSON 파싱 문제 및 해결

**문제**: Polyline 인코딩의 `points` 필드에 백슬래시(`\`) 문자 포함으로 JSON 파싱 실패

```
Invalid \escape: line 1 column 2033
Expecting ',' delimiter at pos 7798
```

**원인 분석**:
- Google Polyline 인코딩은 경로 형상을 문자열로 압축 표현
- 압축 문자열에 `\` 포함 시 JSON escape 시퀀스와 충돌
- 예: `"points":"ukndFkojfW{zAp\"}}` → `\"` 가 이스케이프된 따옴표로 해석됨

**해결책**: `points` 필드 제거 (Step 4에서 불필요)

```python
def fix_json_escapes(line):
    # "points":"..." 패턴을 빈 문자열로 대체
    fixed = re.sub(r'"points":"[^"]*(?:\\.[^"]*)*"', '"points":""', line)
    return fixed
```

### 중복 경로 분석 및 제거

**문제**: OTP MULTI_CRITERIA 모드가 같은 노선의 다른 시간대 차량을 별개 경로로 출력

```
예: OD 0에서 서울2호선 7개 경로 출력 (모두 동일한 경유 정류장)
  alt 0: 서울2호선, duration=603s, ride=330s
  alt 1: 서울2호선, duration=603s, ride=330s  ← 중복
  alt 2~6: ...                                 ← 중복
```

**중복 유형 분석**:

| 중복 기준 | 건수 | 설명 |
|----------|------|------|
| route_names 동일 | 1,960,823 | 같은 노선 조합 |
| route_names + stop_sequence 동일 | 1,908,879 | 노선 + 경유 정류장 동일 |
| **완전 동일** (route + 경유 + 시간) | **6,339,281** | 진짜 중복 |

**중복 제거 기준**: route_names + stop_sequence 동일 시 첫 번째만 유지

```python
df['dedup_key'] = df['route_names'] + '|' + df['stop_sequence']
df_dedup = df.drop_duplicates(subset=['od_id', 'dedup_key'], keep='first')
```

### 파싱 결과

| 항목 | 중복 제거 전 | 중복 제거 후 |
|------|-------------|-------------|
| 총 경로 수 | 8,907,900 | **4,477,498** |
| 제거된 경로 | - | 4,430,402 (49.7%) |
| OD 수 | 1,131,266 | 1,131,266 |
| OD당 평균 경로 | 7.87 | **3.96** |
| 파일 크기 | - | **0.46 GB** |

### OD당 경로 수 분포 (중복 제거 후)

| 경로 수 | OD 수 | 비율 |
|--------|-------|------|
| 1개 | 253,263 | 22.4% |
| 2개 | 144,397 | 12.8% |
| 3개 | 143,764 | 12.7% |
| 4개 | 141,018 | 12.5% |
| 5개 | 130,235 | 11.5% |
| 6~10개 | 318,589 | 28.2% |

### 추출된 속성

| 컬럼 | 타입 | 원천 | 설명 |
|------|------|------|------|
| `od_id` | int32 | JSON id | OD 쌍 식별자 |
| `alt_id` | int8 | itinerary 인덱스 | 경로 대안 번호 (0~) |
| `total_duration` | int32 | duration | 총 소요시간 (초) |
| `ride_time_sec` | int32 | summary | 차내 시간 (초) |
| `walk_time_sec` | int32 | summary | 도보 시간 (초) |
| `wait_time_sec` | int32 | 계산 | 대기 시간 = 총 - 차내 - 도보 |
| `n_transfers` | int8 | summary | 환승 횟수 |
| `has_subway` | int8 | summary | 지하철 포함 여부 (0/1) |
| `modes` | string | summary | 수단 시퀀스 (JSON) |
| `route_ids` | string | legs | 노선 GTFS ID (JSON) |
| `route_names` | string | legs | 노선명 (JSON) |
| `stop_sequence` | string | summary | 경유 정류장 ID (JSON) |
| `boarding_stops` | string | legs | 승차 정류장 ID (JSON) |
| `alighting_stops` | string | legs | 하차 정류장 ID (JSON) |
| `generalized_cost` | int32 | generalizedCost | 일반화 비용 |
| `walk_distance` | float32 | walkDistance | 도보 거리 (m) |

### 산출물

| 파일 | 위치 | 크기 | 내용 |
|------|------|------|------|
| `otp_alternatives.parquet` | `main/output/` | 0.46GB | 4,477,498 경로 |
| `failed_od_ids.parquet` | `main/output/` | - | 131,959 OD (경로 없음) |
| `trip_attributes_matched.parquet` | `main/output/` | - | 매칭된 체인 속성 |

---

## Step 5-6: 유사도 계산 + Choice Set (예정)

(기존 계획 유지 - Step 3 완료 후 진행)

---

## 입력/출력 파일 요약

### Phase 1 → Phase 2 입력

| 파일 | 건수 | 용도 |
|------|------|------|
| `od_pairs_filtered.csv` | 1,263,225 | OTP 배치 입력 |
| `trip_attributes_filtered.parquet` | 1,467,135 | 체인 속성 (od_id 매핑) |
| `leg_stop_sequences.parquet` | - | TCD 레그별 경유 정류장 |
| `gtfs_to_tcd_stop.parquet` | 46,859 | 정류장 ID 매핑 |
| `subway_line_mapping.json` | 39 | 지하철 노선 매핑 |

### Phase 2 산출물

| 파일 | 규모 | 상태 | 설명 |
|------|------|------|------|
| `batch_result_iter0.ndjson` | 30.4GB | ✅ | OTP 배치 원시 결과 |
| `otp_alternatives.parquet` | 4.48M행, 0.46GB | ✅ | 파싱된 OTP 대안 경로 (중복 제거) |
| `failed_od_ids.parquet` | 131,959행 | ✅ | 경로 없음 OD 목록 |
| `trip_attributes_matched.parquet` | - | ✅ | 매칭된 체인 속성 |
| `similarity_matrix.parquet` | - | ⏳ | 체인×대안 유사도 |
| `model_input.parquet` | - | ⏳ | 모델 추정용 최종 데이터 |

---

## 환승 매칭 주의사항 (Step 5에서 반영 필요)

Phase 1 분석에서 발견된 환승 패턴:

| 환승 유형 | 동일 정류장 비율 | 대응 |
|-----------|-----------------|------|
| BUS↔SUBWAY | ID 체계 다름 | 좌표 기반 근접성 (300m) |
| BUS→BUS | 32.2% | 좌표 반경 매칭 필요 |
| SUBWAY→SUBWAY | 89.2% | 대부분 동일역, 10.8% 도보환승 |

**결론**: 환승 정류장 매칭 시 "동일 정류장" 가정은 위험 → 좌표 반경 기반 매칭

---

## 실행 순서 + 소요시간

| 단계 | 작업 | 소요 시간 | 상태 |
|------|------|----------|------|
| Step 1 | ID 매핑 + OD 필터링 | 2시간 | ✅ 완료 |
| Step 2 | OTP Java 수정 + 빌드 + 테스트 | 3시간 | ✅ 완료 |
| Step 3 | OTP 배치 실행 | **8시간 16분** | ✅ 완료 |
| Step 4 | OTP 결과 파싱 + 중복 제거 | **약 30분** | ✅ 완료 |
| Step 5 | 유사도 계산 | 30-60분 | ⏳ 대기 |
| Step 6 | Choice Set + 모델 입력 | 20분 | ⏳ 대기 |
| **합계** | | **~14시간** | |

---

## 다음 단계 (Phase 3)

Phase 2 산출물 `model_input.parquet`을 사용하여:
1. **MNL 추정** (기준선) — 풀링 + 유형별 5개
2. **Mixed Logit 추정** (주력) — 랜덤 파라미터 (μ, σ)
3. **Latent Class 추정** (비교) — K=2~6 클래스
4. **LightGBM 벤치마크** — 예측 정확도 비교
5. **모델 비교** — ρ², Hit Rate, AIC/BIC
