"""
route_type 변환기

한국 KTDB의 route_type을 표준 GTFS(OTP 호환)로 변환합니다.

한국 GTFS:
  - 0: 시내/농어촌/마을버스
  - 1: 도시철도/경전철
  - 2: 해운
  - 3: 시외버스
  - 4: 일반철도
  - 5: 공항리무진버스
  - 6: 고속철도
  - 7: 항공

표준 GTFS (OTP):
  - 0: TRAM
  - 1: SUBWAY
  - 2: RAIL
  - 3: BUS
  - 4: FERRY
  - 1100: AIRPLANE (TPEG 확장)

변환하지 않으면:
  - 한국 시내버스(0) → OTP에서 TRAM으로 오인식
  - 한국 일반철도(4) → OTP에서 FERRY로 오인식
"""
from pathlib import Path

from .base_converter import BaseConverter


class RouteTypeConverter(BaseConverter):
    """routes.txt의 route_type을 표준 GTFS로 변환"""

    # 매핑 테이블 (한국 → OTP)
    MAPPING = {
        0: 3,     # 시내/농어촌/마을버스 → BUS
        1: 1,     # 도시철도/경전철 → SUBWAY
        2: 4,     # 해운 → FERRY
        3: 3,     # 시외버스 → BUS
        4: 2,     # 일반철도 → RAIL
        5: 3,     # 공항리무진버스 → BUS
        6: 2,     # 고속철도 → RAIL
        7: 1100,  # 항공 → AIRPLANE
    }

    # 한국 코드 설명
    KR_NAMES = {
        0: "시내/농어촌/마을버스",
        1: "도시철도/경전철",
        2: "해운",
        3: "시외버스",
        4: "일반철도",
        5: "공항리무진버스",
        6: "고속철도",
        7: "항공",
    }

    # OTP 코드 설명
    OTP_NAMES = {
        1: "SUBWAY",
        2: "RAIL",
        3: "BUS",
        4: "FERRY",
        1100: "AIRPLANE",
    }

    def convert(self) -> dict:
        """
        routes.txt 변환 수행

        Returns:
            {
                "total_routes": 전체 노선 수,
                "original_distribution": 원본 route_type 분포,
                "converted_distribution": 변환된 route_type 분포
            }
        """
        print("\n[routes.txt] route_type 변환 시작...")

        # 1. 파일 읽기
        df = self.read_csv("routes.txt")
        total_routes = len(df)
        print(f"  전체 노선 수: {self.format_number(total_routes)}")

        # 2. 원본 분포 출력
        original_dist = df['route_type'].value_counts().sort_index().to_dict()
        print("\n  [원본 route_type 분포]")
        for code, count in sorted(original_dist.items()):
            name = self.KR_NAMES.get(code, "알 수 없음")
            print(f"    {code} ({name}): {self.format_number(count)}")

        # 3. 매핑 적용
        df['route_type'] = df['route_type'].map(self.MAPPING)

        # 4. 매핑되지 않은 값 확인
        unmapped = df[df['route_type'].isna()]
        if len(unmapped) > 0:
            print(f"\n  경고: 매핑되지 않은 route_type {len(unmapped)}건")

        # 5. 변환 후 분포 출력
        converted_dist = df['route_type'].value_counts().sort_index().to_dict()
        print("\n  [변환된 route_type 분포]")
        for code, count in sorted(converted_dist.items()):
            name = self.OTP_NAMES.get(int(code), "알 수 없음")
            print(f"    {int(code)} ({name}): {self.format_number(count)}")

        # 6. 저장
        self.write_csv(df, "routes.txt")

        return {
            "total_routes": total_routes,
            "original_distribution": original_dist,
            "converted_distribution": converted_dist,
        }
