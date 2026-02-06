#!/usr/bin/env python3
"""
한국 GTFS 전처리기

한국 KTDB GTFS 데이터를 OTP(OpenTripPlanner) 호환 표준 GTFS로 변환합니다.

변환 작업:
1. BOM 제거 (모든 파일)
2. route_type 매핑 변환 (routes.txt)
3. stop_sequence 정수화 (stop_times.txt)
4. 도시철도환승정보 → transfers.txt 변환 (선택)

사용법:
    python gtfs_preprocessor.py [--skip-transfers] [--validate]

옵션:
    --skip-transfers: transfers.txt 생성 건너뛰기
    --validate: 변환 후 검증 수행
"""
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# 현재 스크립트 경로를 기준으로 모듈 경로 추가
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import (
    INPUT_DIR,
    OUTPUT_DIR,
    TRANSFER_XLSX,
    COPY_ONLY_FILES,
    CHUNK_SIZE,
    PROGRESS_INTERVAL,
)
from converters import (
    BaseConverter,
    RouteTypeConverter,
    StopTimesConverter,
    TransfersConverter,
)


class GtfsPreprocessor:
    """한국 GTFS 전처리기 메인 클래스"""

    def __init__(
        self,
        input_dir: Path = INPUT_DIR,
        output_dir: Path = OUTPUT_DIR,
        transfer_xlsx: Path = TRANSFER_XLSX,
        skip_transfers: bool = False,
    ):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.transfer_xlsx = Path(transfer_xlsx) if transfer_xlsx else None
        self.skip_transfers = skip_transfers

        # 결과 저장
        self.results = {}
        self.start_time = None
        self.end_time = None

    def run(self) -> dict:
        """전처리 실행"""
        self.start_time = time.time()

        self._print_header()
        self._validate_input()

        # 1. BOM만 제거하고 복사할 파일들
        self._copy_files()

        # 2. routes.txt 변환
        self._convert_routes()

        # 3. stop_times.txt 변환
        self._convert_stop_times()

        # 4. transfers.txt 생성 (선택)
        if not self.skip_transfers:
            self._convert_transfers()
        else:
            print("\n[transfers.txt] 생성 건너뛰기 (--skip-transfers)")

        self.end_time = time.time()
        self._print_summary()

        return self.results

    def _print_header(self) -> None:
        """헤더 출력"""
        print("=" * 70)
        print("  한국 GTFS 전처리기")
        print("  Korean GTFS Preprocessor for OpenTripPlanner")
        print("=" * 70)
        print(f"\n실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"입력 경로: {self.input_dir}")
        print(f"출력 경로: {self.output_dir}")

    def _validate_input(self) -> None:
        """입력 파일 검증"""
        print("\n" + "-" * 70)
        print("입력 파일 확인")
        print("-" * 70)

        required_files = [
            "agency.txt",
            "calendar.txt",
            "stops.txt",
            "routes.txt",
            "trips.txt",
            "stop_times.txt",
        ]

        missing = []
        for filename in required_files:
            filepath = self.input_dir / filename
            if filepath.exists():
                size = filepath.stat().st_size
                size_str = self._format_size(size)
                print(f"  [OK] {filename} ({size_str})")
            else:
                print(f"  [MISSING] {filename}")
                missing.append(filename)

        if missing:
            print(f"\n오류: 필수 파일 누락 - {missing}")
            sys.exit(1)

        # 출력 디렉토리 생성
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _copy_files(self) -> None:
        """BOM만 제거하고 파일 복사"""
        print("\n" + "-" * 70)
        print("단순 복사 (BOM 제거)")
        print("-" * 70)

        # BaseConverter를 직접 사용할 수 없으므로 간단한 복사 클래스 생성
        class SimpleCopier(BaseConverter):
            def convert(self):
                pass

        copier = SimpleCopier(self.input_dir, self.output_dir)

        for filename in COPY_ONLY_FILES:
            if (self.input_dir / filename).exists():
                count = copier.copy_with_bom_removal(filename)
                print(f"  {filename}: {count:,} records")
                self.results[filename] = {"records": count}
            else:
                print(f"  {filename}: 파일 없음 (건너뛰기)")

    def _convert_routes(self) -> None:
        """routes.txt 변환"""
        print("\n" + "-" * 70)
        print("routes.txt 변환 (route_type 매핑)")
        print("-" * 70)

        converter = RouteTypeConverter(self.input_dir, self.output_dir)
        result = converter.convert()
        self.results["routes.txt"] = result

    def _convert_stop_times(self) -> None:
        """stop_times.txt 변환"""
        print("\n" + "-" * 70)
        print("stop_times.txt 변환 (stop_sequence 정수화)")
        print("-" * 70)

        converter = StopTimesConverter(
            self.input_dir,
            self.output_dir,
            chunk_size=CHUNK_SIZE,
            progress_interval=PROGRESS_INTERVAL,
        )
        result = converter.convert()
        self.results["stop_times.txt"] = result

    def _convert_transfers(self) -> None:
        """transfers.txt 변환"""
        print("\n" + "-" * 70)
        print("transfers.txt 생성 (도시철도환승정보)")
        print("-" * 70)

        converter = TransfersConverter(
            self.input_dir,
            self.output_dir,
            xlsx_path=self.transfer_xlsx,
        )
        result = converter.convert()
        self.results["transfers.txt"] = result

    def _print_summary(self) -> None:
        """결과 요약 출력"""
        elapsed = self.end_time - self.start_time

        print("\n" + "=" * 70)
        print("  변환 완료!")
        print("=" * 70)

        print(f"\n소요 시간: {elapsed:.1f}초")
        print(f"출력 경로: {self.output_dir}")

        print("\n[생성된 파일]")
        for filepath in sorted(self.output_dir.glob("*.txt")):
            size = filepath.stat().st_size
            print(f"  {filepath.name}: {self._format_size(size)}")

        print("\n" + "-" * 70)
        print("다음 단계: OTP에서 그래프 빌드")
        print("-" * 70)
        print("""
1. 변환된 GTFS 파일을 zip으로 압축:
   cd {output_dir}
   zip korean-gtfs.zip *.txt

2. OTP 그래프 빌드:
   java -Xmx8G -jar otp-shaded.jar --build --save .

3. OTP 서버 실행:
   java -Xmx8G -jar otp-shaded.jar --load .
""".format(output_dir=self.output_dir))

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """파일 크기를 읽기 쉬운 형태로 변환"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"


def validate_output(output_dir: Path) -> bool:
    """변환 결과 검증"""
    print("\n" + "=" * 70)
    print("  변환 결과 검증")
    print("=" * 70)

    all_passed = True

    # 1. 파일 존재 확인
    required_files = [
        "agency.txt",
        "calendar.txt",
        "stops.txt",
        "routes.txt",
        "trips.txt",
        "stop_times.txt",
    ]

    print("\n[파일 존재 확인]")
    for filename in required_files:
        filepath = output_dir / filename
        if filepath.exists():
            print(f"  [PASS] {filename}")
        else:
            print(f"  [FAIL] {filename} - 파일 없음")
            all_passed = False

    # 2. BOM 확인
    print("\n[BOM 제거 확인]")
    for filename in required_files:
        filepath = output_dir / filename
        if filepath.exists():
            with open(filepath, 'rb') as f:
                first_bytes = f.read(3)
            has_bom = first_bytes == b'\xef\xbb\xbf'
            if has_bom:
                print(f"  [FAIL] {filename} - BOM 존재")
                all_passed = False
            else:
                print(f"  [PASS] {filename}")

    # 3. routes.txt route_type 확인
    print("\n[route_type 변환 확인]")
    import pandas as pd
    routes_path = output_dir / "routes.txt"
    if routes_path.exists():
        df = pd.read_csv(routes_path)
        valid_types = {1, 2, 3, 4, 1100}  # SUBWAY, RAIL, BUS, FERRY, AIRPLANE
        actual_types = set(df['route_type'].unique())
        invalid_types = actual_types - valid_types

        if invalid_types:
            print(f"  [FAIL] 잘못된 route_type: {invalid_types}")
            all_passed = False
        else:
            print(f"  [PASS] route_type 값: {sorted(actual_types)}")

    # 4. stop_times.txt stop_sequence 확인
    print("\n[stop_sequence 정수 확인]")
    stop_times_path = output_dir / "stop_times.txt"
    if stop_times_path.exists():
        df = pd.read_csv(stop_times_path, nrows=1000)
        dtype = df['stop_sequence'].dtype

        if dtype in ['int64', 'int32']:
            print(f"  [PASS] stop_sequence dtype: {dtype}")
        else:
            print(f"  [FAIL] stop_sequence dtype: {dtype} (정수가 아님)")
            all_passed = False

    # 결과
    print("\n" + "-" * 70)
    if all_passed:
        print("모든 검증 통과!")
    else:
        print("일부 검증 실패. 위의 오류를 확인하세요.")

    return all_passed


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="한국 GTFS 전처리기 - OTP 호환 GTFS로 변환"
    )
    parser.add_argument(
        "--skip-transfers",
        action="store_true",
        help="transfers.txt 생성 건너뛰기"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="변환 후 검증 수행"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(INPUT_DIR),
        help="입력 GTFS 디렉토리"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help="출력 GTFS 디렉토리"
    )

    args = parser.parse_args()

    # 전처리 실행
    preprocessor = GtfsPreprocessor(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        skip_transfers=args.skip_transfers,
    )

    preprocessor.run()

    # 검증
    if args.validate:
        validate_output(Path(args.output_dir))


if __name__ == "__main__":
    main()
