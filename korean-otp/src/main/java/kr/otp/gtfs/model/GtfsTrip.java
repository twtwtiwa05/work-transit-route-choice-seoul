package kr.otp.gtfs.model;

/**
 * GTFS trips.txt 레코드를 나타내는 불변 클래스.
 *
 * 하나의 Trip은 특정 시간에 운행되는 차량의 한 번의 운행을 나타냄.
 * 같은 route_id를 가진 여러 Trip이 있을 수 있음 (같은 노선의 다른 운행 시각).
 */
public record GtfsTrip(
    String routeId,
    String serviceId,
    String tripId
) {
    /**
     * CSV 라인을 파싱하여 GtfsTrip 생성
     *
     * @param parts CSV 라인을 쉼표로 분리한 배열 [route_id, service_id, trip_id]
     * @return GtfsTrip 인스턴스
     */
    public static GtfsTrip fromCsv(String[] parts) {
        return new GtfsTrip(
            parts[0].trim(),  // route_id
            parts[1].trim(),  // service_id
            parts[2].trim()   // trip_id
        );
    }

    @Override
    public String toString() {
        return String.format("Trip[%s on route %s]", tripId, routeId);
    }
}
