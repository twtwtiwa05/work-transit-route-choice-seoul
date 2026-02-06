"""
도시철도환승정보 → transfers.txt 변환기

도시철도환승정보.xlsx 파일을 GTFS transfers.txt로 변환합니다.

원본 형식 (도시철도환승정보.xlsx):
  - Fr_Stop_ID: 출발 정류장 ID
  - To_Stop_ID: 도착 정류장 ID
  - Time_Min: 환승 시간 (분, float)

변환 형식 (transfers.txt):
  - from_stop_id: 출발 정류장 ID
  - to_stop_id: 도착 정류장 ID
  - transfer_type: 환승 타입 (2 = MIN_TIME)
  - min_transfer_time: 최소 환승 시간 (초)

참고:
  - transfers.txt가 없어도 OTP는 동작합니다.
  - OTP의 DirectTransferGenerator가 stops.txt의 좌표와 OSM을 기반으로
    자동으로 도보 환승 경로를 생성합니다.
  - 이 파일은 도시철도 환승처럼 정확한 환승 시간이 필요할 때 사용합니다.

GTFS transfer_type 정의:
  - 0: RECOMMENDED (권장 환승)
  - 1: GUARANTEED (보장 환승, 차량이 기다림)
  - 2: MIN_TIME (최소 환승 시간 지정)
  - 3: FORBIDDEN (환승 금지)
  - 4: STAY_SEATED (동일 차량 환승)
"""
import pandas as pd
from pathlib import Path
from typing import Optional

from .base_converter import BaseConverter


class TransfersConverter(BaseConverter):
    """도시철도환승정보.xlsx → transfers.txt 변환"""

    # GTFS transfer_type
    TRANSFER_TYPE_MIN_TIME = 2

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        xlsx_path: Optional[Path] = None
    ):
        """
        Args:
            input_dir: 원본 GTFS 파일 경로
            output_dir: 변환된 GTFS 출력 경로
            xlsx_path: 도시철도환승정보.xlsx 경로 (None이면 기본 경로)
        """
        super().__init__(input_dir, output_dir)

        if xlsx_path:
            self.xlsx_path = Path(xlsx_path)
        else:
            self.xlsx_path = self.input_dir / "202303_GTFS_도시철도환승정보.xlsx"

    def convert(self) -> dict:
        """
        도시철도환승정보 → transfers.txt 변환 수행

        Returns:
            {
                "total_transfers": 전체 환승 레코드 수,
                "avg_transfer_time": 평균 환승 시간 (초),
                "min_transfer_time": 최소 환승 시간 (초),
                "max_transfer_time": 최대 환승 시간 (초),
            }
        """
        print("\n[transfers.txt] 도시철도환승정보 변환 시작...")

        # 파일 존재 확인
        if not self.xlsx_path.exists():
            print(f"  경고: 파일이 없습니다 - {self.xlsx_path}")
            print("  transfers.txt 생성을 건너뜁니다.")
            return {"skipped": True, "reason": "file_not_found"}

        try:
            # 1. 엑셀 파일 읽기
            # 헤더가 7번째 행 (0-indexed: 6)에 있음
            df = pd.read_excel(self.xlsx_path, header=6)

            # 컬럼명 정리
            df.columns = ['Xfer_SEQ', 'Fr_Stop_ID', 'To_Stop_ID', 'Time_Min', 'Data_Ref']

            # 첫 행이 헤더 중복인 경우 제거
            if df.iloc[0]['Xfer_SEQ'] == 'Xfer_SEQ':
                df = df.iloc[1:]

            print(f"  원본 레코드 수: {self.format_number(len(df))}")

            # 2. 데이터 정제
            # Time_Min을 숫자로 변환 (오류는 NaN으로)
            df['Time_Min'] = pd.to_numeric(df['Time_Min'], errors='coerce')

            # NaN 제거
            before_count = len(df)
            df = df.dropna(subset=['Fr_Stop_ID', 'To_Stop_ID', 'Time_Min'])
            after_count = len(df)

            if before_count != after_count:
                print(f"  제거된 불완전 레코드: {before_count - after_count}")

            # 3. transfers.txt 형식으로 변환
            transfers = pd.DataFrame({
                'from_stop_id': df['Fr_Stop_ID'],
                'to_stop_id': df['To_Stop_ID'],
                'transfer_type': self.TRANSFER_TYPE_MIN_TIME,
                'min_transfer_time': (df['Time_Min'].astype(float) * 60).astype(int)
            })

            # 4. 통계 계산
            total_transfers = len(transfers)
            avg_time = transfers['min_transfer_time'].mean()
            min_time = transfers['min_transfer_time'].min()
            max_time = transfers['min_transfer_time'].max()

            print(f"  전체 환승 레코드: {self.format_number(total_transfers)}")
            print(f"  환승 시간 통계:")
            print(f"    - 평균: {avg_time:.0f}초 ({avg_time/60:.1f}분)")
            print(f"    - 최소: {min_time}초 ({min_time/60:.1f}분)")
            print(f"    - 최대: {max_time}초 ({max_time/60:.1f}분)")

            # 5. 저장
            self.write_csv(transfers, "transfers.txt")

            return {
                "total_transfers": total_transfers,
                "avg_transfer_time": avg_time,
                "min_transfer_time": min_time,
                "max_transfer_time": max_time,
            }

        except Exception as e:
            print(f"  오류 발생: {e}")
            return {"skipped": True, "reason": str(e)}

    def create_empty_transfers(self) -> None:
        """빈 transfers.txt 생성 (헤더만)"""
        transfers = pd.DataFrame(columns=[
            'from_stop_id',
            'to_stop_id',
            'transfer_type',
            'min_transfer_time'
        ])
        self.write_csv(transfers, "transfers.txt")
        print("  빈 transfers.txt 생성 완료")
