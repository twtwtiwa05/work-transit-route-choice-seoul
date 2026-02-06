"""
stop_times.txt 변환기

한국 GTFS의 stop_sequence를 정수로 변환합니다.

문제점:
  한국 GTFS: stop_sequence = 1.000000000 (float 형태)
  OTP 기대값: stop_sequence = 1 (정수)

처리 방식:
  - 1.7GB 대용량 파일이므로 청크 단위로 처리
  - 메모리 효율을 위해 스트리밍 방식 사용
"""
import pandas as pd
from pathlib import Path
from typing import Optional

from .base_converter import BaseConverter


class StopTimesConverter(BaseConverter):
    """stop_times.txt의 stop_sequence를 정수로 변환"""

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        chunk_size: int = 1_000_000,
        progress_interval: int = 5
    ):
        """
        Args:
            input_dir: 원본 GTFS 파일 경로
            output_dir: 변환된 GTFS 출력 경로
            chunk_size: 청크 크기 (기본 100만 행)
            progress_interval: 진행 상황 출력 간격 (청크 단위)
        """
        super().__init__(input_dir, output_dir)
        self.chunk_size = chunk_size
        self.progress_interval = progress_interval

    def convert(self) -> dict:
        """
        stop_times.txt 변환 수행 (청크 단위)

        Returns:
            {
                "total_records": 전체 레코드 수,
                "chunks_processed": 처리된 청크 수,
                "sample_before": 변환 전 샘플,
                "sample_after": 변환 후 샘플
            }
        """
        print("\n[stop_times.txt] stop_sequence 정수 변환 시작...")
        print(f"  청크 크기: {self.format_number(self.chunk_size)} rows")

        input_path = self.get_input_path("stop_times.txt")
        output_path = self.get_output_path("stop_times.txt")

        total_records = 0
        chunks_processed = 0
        sample_before = None
        sample_after = None

        # 청크 단위로 읽어서 처리
        reader = pd.read_csv(
            input_path,
            encoding='utf-8-sig',
            chunksize=self.chunk_size
        )

        for i, chunk in enumerate(reader):
            # 첫 번째 청크에서 샘플 저장
            if i == 0:
                sample_before = chunk['stop_sequence'].head(3).tolist()

            # stop_sequence 정수 변환
            chunk['stop_sequence'] = chunk['stop_sequence'].astype(int)

            # 첫 번째 청크에서 변환 후 샘플 저장
            if i == 0:
                sample_after = chunk['stop_sequence'].head(3).tolist()

            # 저장 (첫 청크는 헤더 포함, 이후는 추가 모드)
            mode = 'w' if i == 0 else 'a'
            header = (i == 0)

            chunk.to_csv(
                output_path,
                mode=mode,
                header=header,
                index=False,
                encoding='utf-8'
            )

            total_records += len(chunk)
            chunks_processed += 1

            # 진행 상황 출력
            if chunks_processed % self.progress_interval == 0:
                print(f"    처리 중... {self.format_number(total_records)} records")

        print(f"  전체 레코드 수: {self.format_number(total_records)}")
        print(f"  처리된 청크 수: {chunks_processed}")

        # 샘플 출력
        if sample_before and sample_after:
            print(f"\n  [변환 샘플]")
            print(f"    변환 전: {sample_before}")
            print(f"    변환 후: {sample_after}")

        print(f"  저장 완료: {output_path}")

        return {
            "total_records": total_records,
            "chunks_processed": chunks_processed,
            "sample_before": sample_before,
            "sample_after": sample_after,
        }

    def validate(self) -> bool:
        """
        변환 결과 검증

        Returns:
            검증 통과 여부
        """
        output_path = self.get_output_path("stop_times.txt")

        if not output_path.exists():
            print("  오류: 출력 파일이 없습니다.")
            return False

        # 첫 몇 줄만 읽어서 타입 확인
        df = pd.read_csv(output_path, nrows=100)

        # stop_sequence가 정수인지 확인
        is_integer = df['stop_sequence'].dtype in ['int64', 'int32']

        if is_integer:
            print("  검증 통과: stop_sequence가 정수형입니다.")
        else:
            print(f"  검증 실패: stop_sequence 타입 = {df['stop_sequence'].dtype}")

        return is_integer
