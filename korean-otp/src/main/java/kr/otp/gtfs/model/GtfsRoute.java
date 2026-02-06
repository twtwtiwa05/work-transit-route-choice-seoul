package kr.otp.gtfs.model;

/**
 * GTFS routes.txt 레코드를 나타내는 불변 클래스.
 *
 * route_type에 따라 Raptor의 slackIndex가 결정됨:
 * - 0, 1, 2 (지하철/전철): slackIndex = 0
 * - 3 (버스): slackIndex = 1
 * - 100-199 (철도): slackIndex = 2
 * - 700-799 (버스): slackIndex = 1
 * - 1100-1199 (항공): slackIndex = 3
 */
public record GtfsRoute(
    String routeId,
    String agencyId,
    String routeShortName,
    String routeLongName,
    int routeType
) {
    // Slack Index 상수 (교통수단별 승하차 여유시간)
    public static final int SLACK_SUBWAY = 0;   // 지하철
    public static final int SLACK_BUS = 1;      // 버스
    public static final int SLACK_RAIL = 2;     // 철도
    public static final int SLACK_AIR = 3;      // 항공

    /**
     * CSV 라인을 파싱하여 GtfsRoute 생성
     *
     * @param parts CSV 라인을 쉼표로 분리한 배열
     * @return GtfsRoute 인스턴스
     */
    public static GtfsRoute fromCsv(String[] parts) {
        return new GtfsRoute(
            parts[0].trim(),                     // route_id
            parts[1].trim(),                     // agency_id
            parts[2].trim(),                     // route_short_name
            parts[3].trim(),                     // route_long_name
            Integer.parseInt(parts[4].trim())    // route_type
        );
    }

    /**
     * 교통수단별 Slack Index 반환
     * Raptor에서 승차/하차 슬랙 계산에 사용
     *
     * @return slackIndex (0=지하철, 1=버스, 2=철도, 3=항공)
     */
    public int getSlackIndex() {
        return switch (routeType) {
            // 표준 GTFS route_type
            case 0, 1, 2 -> SLACK_SUBWAY;       // Tram, Subway, Rail (도시철도)
            case 3 -> SLACK_BUS;                // Bus
            case 4 -> SLACK_RAIL;               // Ferry → 철도와 유사하게 처리
            case 5 -> SLACK_SUBWAY;             // Cable car
            case 6 -> SLACK_SUBWAY;             // Gondola
            case 7 -> SLACK_RAIL;               // Funicular

            // 확장 route_type (한국 데이터)
            default -> {
                if (routeType >= 100 && routeType < 200) {
                    yield SLACK_RAIL;           // Railway Service
                } else if (routeType >= 200 && routeType < 300) {
                    yield SLACK_RAIL;           // Coach Service
                } else if (routeType >= 400 && routeType < 500) {
                    yield SLACK_SUBWAY;         // Urban Railway Service
                } else if (routeType >= 700 && routeType < 800) {
                    yield SLACK_BUS;            // Bus Service
                } else if (routeType >= 900 && routeType < 1000) {
                    yield SLACK_SUBWAY;         // Tram Service
                } else if (routeType >= 1100 && routeType < 1200) {
                    yield SLACK_AIR;            // Air Service
                } else {
                    yield SLACK_BUS;            // 기본값: 버스
                }
            }
        };
    }

    /**
     * 교통수단 타입을 사람이 읽을 수 있는 문자열로 반환
     */
    public String getRouteTypeName() {
        return switch (routeType) {
            case 0 -> "트램";
            case 1 -> "지하철";
            case 2 -> "철도";
            case 3 -> "버스";
            case 4 -> "페리";
            case 5, 6 -> "케이블카";
            case 7 -> "푸니쿨라";
            default -> {
                if (routeType >= 100 && routeType < 200) yield "철도";
                else if (routeType >= 400 && routeType < 500) yield "도시철도";
                else if (routeType >= 700 && routeType < 800) yield "버스";
                else if (routeType >= 1100 && routeType < 1200) yield "항공";
                else yield "기타";
            }
        };
    }

    /**
     * 표시용 이름 반환 (짧은 이름 우선)
     */
    public String getDisplayName() {
        if (routeShortName != null && !routeShortName.isEmpty() && !routeShortName.equals("-")) {
            return routeShortName;
        }
        if (routeLongName != null && !routeLongName.isEmpty() && !routeLongName.equals("-")) {
            return routeLongName;
        }
        return routeId;
    }

    @Override
    public String toString() {
        return String.format("Route[%s: %s (%s)]", routeId, getDisplayName(), getRouteTypeName());
    }
}
