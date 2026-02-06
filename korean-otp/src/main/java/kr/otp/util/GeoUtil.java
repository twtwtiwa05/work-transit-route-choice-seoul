package kr.otp.util;

/**
 * 지리 계산 유틸리티.
 *
 * 좌표 간 거리 계산, 도보 시간 추정 등 제공.
 */
public final class GeoUtil {

    private GeoUtil() {}

    // 지구 반지름 (미터)
    private static final double EARTH_RADIUS_METERS = 6_371_000;

    // 도보 속도 (m/s) - 약 4.3km/h
    public static final double WALK_SPEED_MPS = 1.2;

    // 도보 속도 (m/min) - 약 72m/분
    public static final double WALK_SPEED_MPM = 72.0;

    // 최대 도보 거리 (미터) - 환승 시
    public static final double MAX_WALK_DISTANCE = 500.0;

    // 최대 Access/Egress 도보 거리 (미터)
    public static final double MAX_ACCESS_WALK_DISTANCE = 800.0;

    /**
     * 두 좌표 간의 직선 거리 계산 (Haversine formula)
     *
     * @param lat1 위도 1
     * @param lon1 경도 1
     * @param lat2 위도 2
     * @param lon2 경도 2
     * @return 거리 (미터)
     */
    public static double distance(double lat1, double lon1, double lat2, double lon2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);

        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                 + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                 * Math.sin(dLon / 2) * Math.sin(dLon / 2);

        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return EARTH_RADIUS_METERS * c;
    }

    /**
     * 거리에서 도보 시간 계산
     *
     * @param distanceMeters 거리 (미터)
     * @return 도보 시간 (초)
     */
    public static int walkDuration(double distanceMeters) {
        return (int) Math.ceil(distanceMeters / WALK_SPEED_MPS);
    }

    /**
     * 거리에서 도보 시간 계산 (분 단위)
     *
     * @param distanceMeters 거리 (미터)
     * @return 도보 시간 (분)
     */
    public static int walkDurationMinutes(double distanceMeters) {
        return (int) Math.ceil(distanceMeters / WALK_SPEED_MPM);
    }

    /**
     * 두 좌표 간의 도보 시간 계산
     *
     * @param lat1 위도 1
     * @param lon1 경도 1
     * @param lat2 위도 2
     * @param lon2 경도 2
     * @return 도보 시간 (초)
     */
    public static int walkDuration(double lat1, double lon1, double lat2, double lon2) {
        double dist = distance(lat1, lon1, lat2, lon2);
        return walkDuration(dist);
    }

    /**
     * 도보 가능 거리인지 확인
     *
     * @param distanceMeters 거리 (미터)
     * @return 도보 가능 여부
     */
    public static boolean isWalkable(double distanceMeters) {
        return distanceMeters <= MAX_WALK_DISTANCE;
    }

    /**
     * Access/Egress 도보 가능 거리인지 확인
     *
     * @param distanceMeters 거리 (미터)
     * @return 도보 가능 여부
     */
    public static boolean isAccessWalkable(double distanceMeters) {
        return distanceMeters <= MAX_ACCESS_WALK_DISTANCE;
    }

    /**
     * 빠른 거리 근사치 (for 필터링 용도)
     * Haversine보다 빠르지만 덜 정확함
     *
     * @param lat1 위도 1
     * @param lon1 경도 1
     * @param lat2 위도 2
     * @param lon2 경도 2
     * @return 대략적인 거리 (미터)
     */
    public static double fastDistance(double lat1, double lon1, double lat2, double lon2) {
        // 한국 중심 위도(37도) 기준 근사값
        double latMeters = (lat2 - lat1) * 111_000;
        double lonMeters = (lon2 - lon1) * 88_000; // cos(37°) ≈ 0.8
        return Math.sqrt(latMeters * latMeters + lonMeters * lonMeters);
    }

    /**
     * 주어진 좌표가 한국 영역 내에 있는지 확인
     *
     * @param lat 위도
     * @param lon 경도
     * @return 한국 영역 내 여부
     */
    public static boolean isInKorea(double lat, double lon) {
        // 한국 대략적 경계
        return lat >= 33.0 && lat <= 43.0
            && lon >= 124.0 && lon <= 132.0;
    }

    /**
     * 거리를 사람이 읽기 쉬운 형식으로 변환
     *
     * @param meters 거리 (미터)
     * @return "350m", "1.2km" 등
     */
    public static String formatDistance(double meters) {
        if (meters < 1000) {
            return String.format("%.0fm", meters);
        }
        return String.format("%.1fkm", meters / 1000);
    }
}
