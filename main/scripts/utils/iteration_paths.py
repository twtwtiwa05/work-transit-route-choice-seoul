"""
Iteration별 경로 관리 유틸리티

환경변수 ITERATION을 읽어 output/iter{N}/, results/iter{N}/ 경로를 반환.
Phase 4 반복 보정에서 각 iteration 결과를 분리 저장.

사용법:
    from utils.iteration_paths import get_paths
    paths = get_paths()  # 환경변수 ITERATION 자동 읽기
    paths = get_paths(iteration=1)  # 명시적 지정

    # 경로 접근
    paths.output_dir       # output/iter1/
    paths.results_dir      # results/iter1/
    paths.otp_alternatives # output/iter1/otp_alternatives.parquet
"""

import os
from pathlib import Path
from dataclasses import dataclass

# 프로젝트 루트 (main/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class IterationPaths:
    """Iteration별 경로를 담는 데이터 클래스"""
    iteration: int
    output_dir: Path
    results_dir: Path

    # === Output 파일 경로 ===
    @property
    def otp_alternatives(self) -> Path:
        return self.output_dir / "otp_alternatives.parquet"

    @property
    def failed_od_ids(self) -> Path:
        return self.output_dir / "failed_od_ids.parquet"

    @property
    def trip_attrs_matched(self) -> Path:
        return self.output_dir / "trip_attributes_matched.parquet"

    @property
    def similarity_results(self) -> Path:
        return self.output_dir / "similarity_results.parquet"

    @property
    def similarity_summary(self) -> Path:
        return self.output_dir / "similarity_summary.parquet"

    @property
    def choice_set(self) -> Path:
        return self.output_dir / "choice_set.parquet"

    @property
    def alternative_attributes(self) -> Path:
        return self.output_dir / "alternative_attributes.parquet"

    @property
    def model_input(self) -> Path:
        return self.output_dir / "model_input.parquet"

    @property
    def model_input_train(self) -> Path:
        return self.output_dir / "model_input_train.parquet"

    @property
    def model_input_test(self) -> Path:
        return self.output_dir / "model_input_test.parquet"

    # === Results 파일 경로 ===
    @property
    def mnl_results(self) -> Path:
        return self.results_dir / "mnl_results.json"

    @property
    def mixed_logit_results(self) -> Path:
        return self.results_dir / "mixed_logit_results.json"

    @property
    def latent_class_results(self) -> Path:
        return self.results_dir / "latent_class_results.json"

    @property
    def lightgbm_results(self) -> Path:
        return self.results_dir / "lightgbm_results.json"

    # === 공통 입력 파일 (iteration 무관) ===
    @property
    def trip_attrs_filtered(self) -> Path:
        """Phase 1 결과 (iter0에 있음)"""
        return PROJECT_ROOT / "output" / "trip_attributes_filtered.parquet"

    @property
    def tcd_leg_stops(self) -> Path:
        return PROJECT_ROOT / "output" / "tcd_leg_traversed_stops.parquet"

    @property
    def stop_mapping(self) -> Path:
        return PROJECT_ROOT / "output" / "gtfs_tcd_stop_mapping.parquet"

    @property
    def route_mapping(self) -> Path:
        return PROJECT_ROOT / "output" / "gtfs_tcd_route_mapping.parquet"


def get_iteration() -> int:
    """환경변수 ITERATION을 읽어 반환. 기본값 0."""
    return int(os.environ.get("ITERATION", "0"))


def get_paths(iteration: int = None) -> IterationPaths:
    """
    Iteration별 경로 객체를 반환.

    Parameters
    ----------
    iteration : int, optional
        반복 회차. None이면 환경변수 ITERATION 사용 (기본 0).

    Returns
    -------
    IterationPaths
        해당 iteration의 경로들을 담은 객체.
    """
    if iteration is None:
        iteration = get_iteration()

    # iter0은 output/ 루트에, iter1+는 output/iter{N}/
    if iteration == 0:
        output_dir = PROJECT_ROOT / "output"
        results_dir = PROJECT_ROOT / "results"
    else:
        output_dir = PROJECT_ROOT / "output" / f"iter{iteration}"
        results_dir = PROJECT_ROOT / "results" / f"iter{iteration}"

    # 디렉토리 생성
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    return IterationPaths(
        iteration=iteration,
        output_dir=output_dir,
        results_dir=results_dir,
    )


def get_otp_ndjson_path(iteration: int = None) -> Path:
    """
    OTP 배치 결과 NDJSON 경로를 반환.

    환경변수 OTP_NDJSON_PATH가 설정되어 있으면 그 값 사용.
    아니면 korean-otp/batch_result_iter{N}.ndjson
    """
    env_path = os.environ.get("OTP_NDJSON_PATH")
    if env_path:
        return Path(env_path)

    if iteration is None:
        iteration = get_iteration()

    otp_dir = PROJECT_ROOT.parent / "korean-otp"
    return otp_dir / f"batch_result_iter{iteration}.ndjson"


def print_iteration_info():
    """현재 iteration 정보를 출력."""
    iteration = get_iteration()
    paths = get_paths(iteration)

    print(f"\n{'='*50}")
    print(f"  Iteration: {iteration}")
    print(f"  Output: {paths.output_dir}")
    print(f"  Results: {paths.results_dir}")
    print(f"{'='*50}\n")


# CLI 테스트용
if __name__ == "__main__":
    import sys

    # 인자로 iteration 지정 가능
    if len(sys.argv) > 1:
        os.environ["ITERATION"] = sys.argv[1]

    print_iteration_info()
    paths = get_paths()

    print("Output 경로:")
    print(f"  otp_alternatives: {paths.otp_alternatives}")
    print(f"  similarity_results: {paths.similarity_results}")
    print(f"  choice_set: {paths.choice_set}")
    print(f"  model_input_train: {paths.model_input_train}")

    print("\nResults 경로:")
    print(f"  mnl_results: {paths.mnl_results}")

    print("\n공통 입력 경로:")
    print(f"  trip_attrs_filtered: {paths.trip_attrs_filtered}")
