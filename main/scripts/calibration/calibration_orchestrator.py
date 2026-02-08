#!/usr/bin/env python3
"""
Phase 4: 반복 보정 오케스트레이터

반복 루프의 전체 흐름을 관리한다:
  1. param_mapper → calibration_config.json 업데이트
  2. OTP 배치 실행 (Java, 수동 또는 자동)
  3. 파이프라인 실행 (파싱 → 유사도 → Choice Set → MNL 추정)
  4. 수렴 검사
  5. 미수렴 시 반복

사용법:
    # Iteration 1: Phase 3 결과로 첫 θ 계산 → OTP 실행 안내
    python calibration_orchestrator.py --step param-map --iteration 1

    # OTP 배치 완료 후: NDJSON 파싱 + 파이프라인 실행
    python calibration_orchestrator.py --step pipeline --iteration 1 \
        --ndjson /path/to/batch_result_iter1.ndjson

    # 수렴 확인
    python calibration_orchestrator.py --step check --iteration 1

    # 전체 자동 (서브샘플 전용)
    python calibration_orchestrator.py --step auto --max-iter 5
"""

import json
import os
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
MATCHING_DIR = SCRIPTS_DIR / "matching"
MODELS_DIR = SCRIPTS_DIR / "models"
CALIBRATION_DIR = SCRIPTS_DIR / "calibration"
OUTPUT_DIR = ROOT / "output"
RESULTS_DIR = ROOT / "results"
OTP_DIR = ROOT.parent / "korean-otp"
LOG_PATH = RESULTS_DIR / "calibration_log.json"


def run_script(script_path, env_extra=None, description=""):
    """Python 스크립트를 subprocess로 실행한다."""
    print(f"\n  [{description}] 실행 중: {script_path.name}")
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        env=env,
        capture_output=False,  # 실시간 출력
    )
    if result.returncode != 0:
        print(f"  오류: {script_path.name} 실패 (exit code {result.returncode})")
        return False
    return True


def step_param_map(iteration, source="lc_class2", iter_results=None):
    """STEP 1: β → θ 매핑 + calibration_config.json 업데이트"""
    print(f"\n{'='*60}")
    print(f"  STEP 1: 파라미터 매핑 (Iteration {iteration})")
    print(f"{'='*60}")

    # param_mapper를 직접 import하여 호출
    sys.path.insert(0, str(CALIBRATION_DIR))
    from param_mapper import run as param_map_run
    theta = param_map_run(iteration, source, iter_results)

    print(f"\n  → calibration_config.json 업데이트 완료")
    print(f"  → OTP 배치 실행 필요!")
    print(f"\n  OTP 실행 방법:")
    print(f"    cd {OTP_DIR}")
    print(f"    java -jar build/libs/korean-otp.jar \\")
    print(f"      --input od_pairs_filtered.csv \\")
    print(f"      --output batch_result_iter{iteration}.ndjson \\")
    print(f"      --config calibration_config.json")
    print(f"\n  완료 후 다음 명령 실행:")
    print(f"    python calibration_orchestrator.py --step pipeline "
          f"--iteration {iteration} \\")
    print(f"      --ndjson <batch_result_iter{iteration}.ndjson 경로>")

    return theta


def step_pipeline(iteration, ndjson_path):
    """STEP 2-6: 파이프라인 실행 (파싱 → 유사도 → Choice Set → MNL)"""
    print(f"\n{'='*60}")
    print(f"  STEP 2-6: 파이프라인 (Iteration {iteration})")
    print(f"{'='*60}")

    ndjson = Path(ndjson_path)
    if not ndjson.exists():
        print(f"  오류: NDJSON 파일 없음 — {ndjson}")
        return False

    print(f"  입력 NDJSON: {ndjson}")
    print(f"  크기: {ndjson.stat().st_size / (1024**3):.1f} GB")

    # ── 이전 결과 백업 ──
    backup_dir = OUTPUT_DIR / f"iter{iteration - 1}_backup"
    files_to_backup = [
        "otp_alternatives.parquet",
        "similarity_results.parquet",
        "choice_set.parquet",
        "model_input.parquet",
        "model_input_train.parquet",
        "model_input_test.parquet",
    ]
    if not backup_dir.exists():
        backup_dir.mkdir(parents=True)
        for fname in files_to_backup:
            src = OUTPUT_DIR / fname
            if src.exists():
                dst = backup_dir / fname
                print(f"    백업: {fname} → iter{iteration-1}_backup/")
                # 심볼릭 링크 대신 하드링크 (용량 절약)
                try:
                    os.link(str(src), str(dst))
                except OSError:
                    import shutil
                    shutil.copy2(str(src), str(dst))

    # ── 2. OTP 결과 파싱 ──
    # step4_parse_otp_results.py는 OTP_NDJSON_PATH 환경변수를 읽도록 수정 필요
    # 환경변수가 설정되지 않은 경우를 대비한 안내
    print(f"\n  [2/6] OTP 결과 파싱")
    env_extra = {"OTP_NDJSON_PATH": str(ndjson)}
    step4_script = MATCHING_DIR / "step4_parse_otp_results.py"
    if not run_script(step4_script, env_extra, "OTP 파싱"):
        print("  주의: step4 실행 실패. OTP_NDJSON_PATH 환경변수 지원 필요.")
        print("  step4_parse_otp_results.py의 OTP_RESULT 경로를 수동 수정하세요:")
        print(f"    OTP_RESULT = Path(r\"{ndjson}\")")
        return False

    # ── 3. 유사도 계산 ──
    print(f"\n  [3/6] 유사도 계산")
    step5_script = MATCHING_DIR / "step5_calculate_similarity.py"
    if not run_script(step5_script, description="유사도"):
        return False

    # ── 4. Choice Set 구성 ──
    print(f"\n  [4/6] Choice Set 구성")
    step1_script = MODELS_DIR / "step1_create_choice_set.py"
    if not run_script(step1_script, description="Choice Set"):
        return False

    # ── 5. 속성 추출 + 모델 입력 준비 ──
    print(f"\n  [5/6] 속성 추출 + 모델 입력 준비")
    step2_script = MODELS_DIR / "step2_extract_attributes.py"
    step3_script = MODELS_DIR / "step3_prepare_model_input.py"
    if not run_script(step2_script, description="속성 추출"):
        return False
    if not run_script(step3_script, description="모델 입력"):
        return False

    # ── 6. MNL Pooled 추정 ──
    print(f"\n  [6/6] MNL Pooled 추정")
    step4_mnl_script = MODELS_DIR / "step4_estimate_mnl.py"
    if not run_script(step4_mnl_script, description="MNL 추정"):
        return False

    # ── 매칭률 기록 ──
    match_rate = compute_match_rate()
    update_log_match_rate(iteration, match_rate)

    print(f"\n  파이프라인 완료!")
    print(f"  매칭률: {match_rate:.1%}" if match_rate else "  매칭률: 계산 불가")

    return True


def compute_match_rate():
    """현재 choice_set 기반 매칭률을 계산한다."""
    try:
        import pandas as pd
        cs = pd.read_parquet(OUTPUT_DIR / "choice_set.parquet")
        n_chains = cs["chain_id"].nunique() if "chain_id" in cs.columns else len(cs)

        # 전체 체인 수 (trip_attributes에서)
        trip_attrs = OUTPUT_DIR / "trip_attributes_matched.parquet"
        if trip_attrs.exists():
            ta = pd.read_parquet(trip_attrs)
            total = ta["chain_id"].nunique() if "chain_id" in ta.columns else len(ta)
            return n_chains / total if total > 0 else 0
    except Exception as e:
        print(f"  매칭률 계산 오류: {e}")
    return 0


def update_log_match_rate(iteration, match_rate):
    """보정 로그에 매칭률을 추가한다."""
    if not LOG_PATH.exists():
        return
    with open(LOG_PATH) as f:
        log = json.load(f)

    for entry in log.get("iterations", []):
        if entry.get("iteration") == iteration:
            entry["match_rate"] = match_rate
            entry["pipeline_completed"] = datetime.now().isoformat()
            break

    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def step_check(iteration):
    """STEP 7: 수렴 검사"""
    print(f"\n{'='*60}")
    print(f"  STEP 7: 수렴 검사 (Iteration {iteration})")
    print(f"{'='*60}")

    sys.path.insert(0, str(CALIBRATION_DIR))
    from convergence_checker import load_log, check_convergence, print_summary

    log = load_log()
    if log is None:
        return None

    print_summary(log)
    result = check_convergence(log)

    if result["converged"]:
        if result.get("naturally_converged"):
            print(f"\n  수렴 완료! 다음 단계:")
        else:
            print(f"\n  최대 반복 도달. 다음 단계:")
        print(f"    1. 최종 모형 재추정 (MNL 5유형 + ML + LC + LightGBM)")
        print(f"    2. 유형별 확률 배정:")
        print(f"       python probabilistic_router.py --test-cases")
        print(f"    3. 수렴 그래프 생성:")
        print(f"       python convergence_checker.py --plot --summary")
    else:
        next_iter = iteration + 1
        print(f"\n  다음 반복 실행:")
        print(f"    python calibration_orchestrator.py --step param-map "
              f"--iteration {next_iter}")

    return result


def step_final():
    """수렴 후 최종 작업: 4개 모형 재추정 + 확률 배정 + 시각화"""
    print(f"\n{'='*60}")
    print(f"  최종 단계: 수렴 파라미터 기반 재추정")
    print(f"{'='*60}")

    # MNL (pooled + 유형별) — 이미 마지막 파이프라인에서 실행됨
    print(f"\n  [1/4] MNL 유형별 — 이미 완료 (마지막 파이프라인)")

    # Mixed Logit
    print(f"\n  [2/4] Mixed Logit 추정")
    ml_script = MODELS_DIR / "step5_estimate_mixed_logit.py"
    if ml_script.exists():
        run_script(ml_script, description="Mixed Logit")
    else:
        print(f"    스크립트 없음, 건너뜀")

    # Latent Class
    print(f"\n  [3/4] Latent Class 추정")
    lc_script = MODELS_DIR / "step6_estimate_latent_class.py"
    if lc_script.exists():
        run_script(lc_script, description="Latent Class")
    else:
        print(f"    스크립트 없음, 건너뜀")

    # LightGBM
    print(f"\n  [4/4] LightGBM 벤치마크")
    lgb_script = MODELS_DIR / "step7_lightgbm_benchmark.py"
    if lgb_script.exists():
        run_script(lgb_script, description="LightGBM")
    else:
        print(f"    스크립트 없음, 건너뜀")

    # 확률 배정
    print(f"\n  [추가] 유형별 확률 배정")
    sys.path.insert(0, str(CALIBRATION_DIR))
    from probabilistic_router import load_mnl_params, run_test_cases
    params = load_mnl_params()
    run_test_cases(params)

    # 수렴 그래프
    print(f"\n  [추가] 수렴 그래프 생성")
    from convergence_checker import load_log, plot_convergence
    log = load_log()
    if log:
        plot_convergence(log)

    print(f"\n  최종 단계 완료!")


def print_status():
    """현재 보정 상태를 출력한다."""
    print(f"\n{'='*60}")
    print(f"  Phase 4 반복 보정 — 현재 상태")
    print(f"{'='*60}")

    # 현재 config 확인
    config_path = OTP_DIR / "calibration_config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        print(f"\n  현재 OTP 파라미터:")
        print(f"    walkReluctance = {config.get('walkReluctance', '?')}")
        print(f"    transferCostSeconds = {config.get('transferCostSeconds', '?')}")
    else:
        print(f"\n  calibration_config.json 없음 (기본값 사용 중)")

    # 로그 확인
    if LOG_PATH.exists():
        with open(LOG_PATH) as f:
            log = json.load(f)
        n_iters = len(log.get("iterations", []))
        print(f"\n  완료된 반복: {n_iters}회")
        if n_iters > 0:
            last = log["iterations"][-1]
            print(f"  마지막 반복: Iteration {last['iteration']}")
            wr = last["theta_new"]["walkReluctance"]
            tc = last["theta_new"]["transferCostSeconds"]
            print(f"    θ: walkReluctance={wr:.2f}, transferCost={tc}초")
            if last.get("match_rate"):
                print(f"    매칭률: {last['match_rate']:.1%}")
    else:
        print(f"\n  아직 반복 실행 이력 없음")

    print(f"\n  다음 명령:")
    print(f"    python calibration_orchestrator.py --step param-map --iteration 1")


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: 반복 보정 오케스트레이터",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 순서:
  1. --step param-map   : β→θ 매핑 + config 업데이트
  2. (OTP 배치 수동 실행)
  3. --step pipeline    : NDJSON 파싱 → 유사도 → Choice Set → MNL
  4. --step check       : 수렴 검사
  5. 미수렴 시 1번으로 반복
  6. --step final       : 수렴 후 4개 모형 재추정 + 확률 배정
""")

    parser.add_argument("--step",
                        choices=["status", "param-map", "pipeline",
                                 "check", "final"],
                        default="status",
                        help="실행할 단계")
    parser.add_argument("--iteration", type=int, default=1,
                        help="반복 회차 (1부터 시작)")
    parser.add_argument("--ndjson", type=str, default=None,
                        help="OTP 배치 결과 NDJSON 경로 (pipeline 단계용)")
    parser.add_argument("--source", default="lc_class2",
                        choices=["lc_class2", "mnl_pooled"],
                        help="iteration 1의 β 소스")

    args = parser.parse_args()

    if args.step == "status":
        print_status()

    elif args.step == "param-map":
        # iteration ≥ 2이면 이전 반복의 MNL 결과 경로 자동 탐색
        iter_results = None
        if args.iteration >= 2:
            iter_results = str(RESULTS_DIR / "mnl_results.json")
        step_param_map(args.iteration, args.source, iter_results)

    elif args.step == "pipeline":
        if not args.ndjson:
            print("  오류: --ndjson 경로를 지정하세요")
            print(f"  예: --ndjson /path/to/batch_result_iter{args.iteration}.ndjson")
            sys.exit(1)
        step_pipeline(args.iteration, args.ndjson)

    elif args.step == "check":
        step_check(args.iteration)

    elif args.step == "final":
        step_final()


if __name__ == "__main__":
    main()
