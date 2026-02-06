"""
기본 변환기 클래스
- 파일 읽기/쓰기
- BOM 제거
- 공통 유틸리티 함수
"""
import pandas as pd
from pathlib import Path
from abc import ABC, abstractmethod


class BaseConverter(ABC):
    """
    모든 변환기의 기본 클래스

    공통 기능:
    - BOM 제거하며 CSV 읽기
    - BOM 없이 CSV 쓰기
    - 파일 복사 (BOM 제거)
    """

    def __init__(self, input_dir: Path, output_dir: Path):
        """
        Args:
            input_dir: 원본 GTFS 파일 경로
            output_dir: 변환된 GTFS 출력 경로
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

        # 출력 디렉토리 생성
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def read_csv(self, filename: str) -> pd.DataFrame:
        """
        BOM을 제거하며 CSV 파일 읽기

        Args:
            filename: 파일명 (예: "routes.txt")

        Returns:
            pandas DataFrame
        """
        filepath = self.input_dir / filename

        # encoding='utf-8-sig'는 BOM을 자동으로 처리
        return pd.read_csv(filepath, encoding='utf-8-sig')

    def write_csv(self, df: pd.DataFrame, filename: str) -> None:
        """
        BOM 없이 CSV 파일 쓰기

        Args:
            df: 저장할 DataFrame
            filename: 파일명 (예: "routes.txt")
        """
        filepath = self.output_dir / filename

        # encoding='utf-8'로 저장하면 BOM 없음
        df.to_csv(filepath, index=False, encoding='utf-8')

        print(f"  저장 완료: {filepath}")

    def copy_with_bom_removal(self, filename: str) -> int:
        """
        BOM만 제거하고 파일 복사

        Args:
            filename: 파일명

        Returns:
            레코드 수
        """
        df = self.read_csv(filename)
        self.write_csv(df, filename)
        return len(df)

    def get_input_path(self, filename: str) -> Path:
        """입력 파일 경로 반환"""
        return self.input_dir / filename

    def get_output_path(self, filename: str) -> Path:
        """출력 파일 경로 반환"""
        return self.output_dir / filename

    def file_exists(self, filename: str) -> bool:
        """입력 파일 존재 여부 확인"""
        return (self.input_dir / filename).exists()

    @abstractmethod
    def convert(self) -> dict:
        """
        변환 수행 (서브클래스에서 구현)

        Returns:
            변환 결과 정보 딕셔너리
        """
        pass

    @staticmethod
    def format_number(num: int) -> str:
        """숫자를 천단위 구분자로 포맷팅"""
        return f"{num:,}"
