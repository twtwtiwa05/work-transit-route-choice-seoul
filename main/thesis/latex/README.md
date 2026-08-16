# ITS World Congress 2026 논문 — LaTeX 프로젝트

`02_1716_FINAL.pdf` (Word 기반)를 LaTeX으로 전환한 프로젝트.
학회 공식 템플릿(`../2026_GANGNEUNG_ITS_WC_Paper Template.doc`) 규격을
`itswc2026.sty`에 그대로 구현했다.

## 파일 구조

```
latex/
├── main.tex                  # 진입점: 제목/저자/초록/참고문헌
├── itswc2026.sty             # 학회 규격 스타일 (A4, 25mm, TNR 12pt, 헤딩 체계)
├── sections/
│   ├── introduction.tex
│   ├── literature.tex        # + Table 1
│   ├── data_methodology.tex  # + Table 2-4, 수식
│   ├── results.tex           # + Table 5-8, Figure 1-3
│   ├── calibration_reranking.tex  # + Table 9-11, Figure 4-5
│   └── conclusions.tex
└── figures/                  # 300dpi PNG (results/figures에서 제목 제거본)
```

## 빌드 방법

MiKTeX 설치 필요 (이미 설치됨: `winget install MiKTeX.MiKTeX`).

```powershell
cd main\thesis\latex
pdflatex main.tex
pdflatex main.tex   # 상호참조/인용번호 확정을 위해 2회 실행
```

처음 빌드 시 MiKTeX이 필요한 패키지(newtx, titlesec 등)를 자동 다운로드한다
(AutoInstall 활성화됨).

## 편집 환경 추천

- **VS Code + LaTeX Workshop 확장**: 저장 시 자동 빌드, PDF 미리보기,
  SyncTeX(PDF↔소스 양방향 점프) 지원
- 설치: VS Code 확장 탭에서 "LaTeX Workshop" 검색

## 학회 규격 요약 (itswc2026.sty가 강제)

| 항목 | 규격 |
|------|------|
| 용지/여백 | ISO A4, 상하좌우 25mm |
| 글꼴 | Times New Roman 12pt (newtx), 1단, 줄간격 1.0 |
| 제목 | 대문자, 볼드, 중앙, 18pt |
| 1단계 헤딩 | 대문자, 볼드, 중앙, 16pt |
| 2단계 헤딩 | 대문자, 볼드, 좌측, 14pt |
| 3단계 헤딩 | 첫 글자만 대문자, 볼드, 좌측, 12pt |
| 4단계 헤딩 | 볼드 이탤릭, 런인(같은 줄 이어쓰기), 12pt |
| 표 캡션 | 표 아래, 볼드 ("Table 1. …"), 표 본문 11pt 이상 |
| 참고문헌 | 끝에 (1) (2) … 번호, 본문 인용도 (1) 형식 |
| 페이지 번호 | 하단 중앙 |

## 그림 관리

`figures/`의 PNG는 `main/results/figures/` 원본에서 matplotlib 제목만
크롭한 것 (스크립트: 세션 스크래치패드 `crop_titles.py`).
그림을 다시 만들면 같은 이름으로 교체하면 된다.

| 논문 그림 | 원본 파일 |
|-----------|----------|
| Figure 1 | fig6_similarity_distribution.png |
| Figure 2 | fig1_hit_rate_comparison.png |
| Figure 3 | fig4_shap_beta_validation.png |
| Figure 4 | fig13_otp_mnl_disagreement.png |
| Figure 5 | fig12_mnl_improvement_by_nalts.png |

주의: Word FINAL PDF의 Figure 2(66.8%)·Figure 3(옛 계수)은 본문 표와
불일치했으나, 이 LaTeX판은 저장소의 정합 데이터 그림으로 교체하여 해결함.
