# Transit Route Choice Model (ITS World Congress 2026)

서울 대중교통 경로선택 모델 연구 - TCD(교통카드) 데이터 기반

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **목적** | 이용자 유형별 경로선택 행태 분석 (MNL, Mixed Logit) |
| **데이터** | TCD 교통카드 데이터 (2025.02) + GTFS + OTP |
| **범위** | 서울 대중교통 (버스, 지하철) |

## 진행 현황

| Phase | 내용 | 상태 |
|-------|------|------|
| Phase 1 | TCD 전처리, OD 추출, ID 매핑 | ✅ 완료 |
| Phase 2 | OTP 배치 실행, 유사도 계산 | ✅ 완료 |
| Phase 3 | 모델 추정 (MNL, Mixed Logit) | 🔄 진행중 |
| Phase 4 | 반복 보정 | 🔲 예정 |

### Phase 3 세부 현황

| Step | 내용 | 상태 |
|------|------|------|
| Step 1 | Choice Set 생성 | ✅ |
| Step 2 | 대안 속성 추출 | ✅ |
| Step 3 | 모델 입력 준비 | ✅ |
| Step 4 | MNL 추정 | ✅ |
| Step 5 | Mixed Logit 추정 | 🔄 진행중 |
| Step 6 | Latent Class | 🔲 |
| Step 7 | LightGBM | 🔲 |

## 폴더 구조

```
main/
├── scripts/
│   ├── data/           # Phase 1 전처리 스크립트
│   ├── matching/       # Phase 2 OTP 매칭 스크립트
│   └── models/         # Phase 3 모델 추정 스크립트
├── docs/               # 계획서, 문서
├── output/             # 데이터 파일 (.gitignore로 대부분 제외)
└── results/            # 모델 추정 결과
```

## 필요 데이터 (다른 컴퓨터에서 이어서 하려면)

GitHub에 포함된 파일:
- `output/model_input_train.parquet` - 학습 데이터 (329K 체인)
- `output/model_input_test.parquet` - 테스트 데이터 (82K 체인)
- `output/trip_attributes_filtered.parquet` - 체인 속성
- `results/mnl_results.json` - MNL 추정 결과

## 실행 방법

### Step 5: Mixed Logit

```bash
cd main
python scripts/models/step5_estimate_mixed_logit.py
```

**설정** (step5_estimate_mixed_logit.py 내):
- `N_DRAWS = 500` - 시뮬레이션 draws 수
- `SAMPLE_SIZE = 30000` - 샘플링 체인 수

**예상 시간**: 1.5-2.5시간 (30K 샘플 기준)

## 주요 결과 (MNL)

| 지표 | Pooled | Elderly | Disabled |
|------|--------|---------|----------|
| ρ² | 0.469 | 0.582 | 0.515 |
| Hit Rate | 62.9% | 78.5% | 73.0% |
| 보행 가중치 | 22.7× | 7.3× | 30.2× |

상세 결과: `results/PHASE3_RESULTS1_MNL.md`

## 요구사항

```
pandas>=2.0.0
numpy>=1.24.0
pyarrow>=14.0.0
scipy>=1.11.0
```

## 참고 문서

- `docs/RESEARCH_PLAN.md` - 전체 연구 계획
- `docs/PHASE3_MODEL_ESTIMATION_PLAN.md` - Phase 3 상세 계획
- `docs/SIMILARITY_METRICS_FRAMEWORK.md` - 유사도 지표 정의

---

## Author

**김태우 (Taewoo Kim)**
가천대학교 (Gachon University)
