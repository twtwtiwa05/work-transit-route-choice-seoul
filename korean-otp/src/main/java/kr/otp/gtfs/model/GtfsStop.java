package kr.otp.gtfs.model;

/**
 * GTFS stops.txt 레코드를 나타내는 불변 클래스.
 *
 * 메모리 효율성을 위해 record 사용.
 * 약 21만개의 정류장을 메모리에 유지해야 함.
 */
public record GtfsStop(
    String stopId,
    String stopName,
    double lat,
    double lon
) {
    /**
     * CSV 라인을 파싱하여 GtfsStop 생성
     *
     * @param parts CSV 라인을 쉼표로 분리한 배열 [stop_id, stop_name, stop_lat, stop_lon]
     * @return GtfsStop 인스턴스
     */
    public static GtfsStop fromCsv(String[] parts) {
        return new GtfsStop(
            parts[0].trim(),                    // stop_id
            parts[1].trim(),                    // stop_name
            Double.parseDouble(parts[2].trim()), // stop_lat
            Double.parseDouble(parts[3].trim())  // stop_lon
        );
    }

    /**
     * 두 정류장 사이의 직선 거리 계산 (Haversine formula)
     *
     * @param other 다른 정류장
     * @return 거리 (미터)
     */
    public double distanceTo(GtfsStop other) {
        return haversineDistance(this.lat, this.lon, other.lat, other.lon);
    }

    /**
     * 주어진 좌표까지의 직선 거리 계산
     *
     * @param toLat 목적지 위도
     * @param toLon 목적지 경도
     * @return 거리 (미터)
     */
    public double distanceTo(double toLat, double toLon) {
        return haversineDistance(this.lat, this.lon, toLat, toLon);
    }

    private static double haversineDistance(double lat1, double lon1, double lat2, double lon2) {
        final double R = 6_371_000; // 지구 반지름 (미터)

        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);

        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                 + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                 * Math.sin(dLon / 2) * Math.sin(dLon / 2);

        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c;
    }

    @Override
    public String toString() {
        return String.format("Stop[%s: %s (%.5f, %.5f)]", stopId, stopName, lat, lon);
    }
}
