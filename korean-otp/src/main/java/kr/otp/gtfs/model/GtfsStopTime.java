package kr.otp.gtfs.model;

/**
 * GTFS stop_times.txt 레코드를 나타내는 클래스.
 *
 * 메모리 효율성을 위해 시간을 초 단위 int로 저장.
 * 약 2000만개의 레코드를 처리해야 하므로 메모리 최적화 중요.
 *
 * 시간 형식: "HH:MM:SS" → 자정 이후 초 (예: "09:30:00" → 34200)
 * 참고: GTFS는 24:00:00 이후 시간도 허용 (예: "25:30:00" = 다음날 01:30)
 */
public record GtfsStopTime(
    String tripId,
    int arrivalTime,      // 초 단위 (자정 기준)
    int departureTime,    // 초 단위 (자정 기준)
    String stopId,
    int stopSequence,
    int pickupType,       // 0=정규, 1=없음, 2=전화예약, 3=기사요청
    int dropOffType       // 0=정규, 1=없음, 2=전화예약, 3=기사요청
) {
    // 상수
    public static final int PICKUP_REGULAR = 0;
    public static final int PICKUP_NONE = 1;
    public static final int DROP_OFF_REGULAR = 0;
    public static final int DROP_OFF_NONE = 1;

    /**
     * CSV 라인을 파싱하여 GtfsStopTime 생성
     *
     * @param parts CSV 라인 배열 [trip_id, arrival_time, departure_time, stop_id, stop_sequence, pickup_type, drop_off_type, timepoint]
     * @return GtfsStopTime 인스턴스
     */
    public static GtfsStopTime fromCsv(String[] parts) {
        return new GtfsStopTime(
            parts[0].trim(),                           // trip_id
            parseTime(parts[1].trim()),                // arrival_time
            parseTime(parts[2].trim()),                // departure_time
            parts[3].trim(),                           // stop_id
            parseIntOrDouble(parts[4].trim()),         // stop_sequence
            parseIntOrDouble(parts[5].trim()),         // pickup_type
            parseIntOrDouble(parts[6].trim())          // drop_off_type
        );
    }

    /**
     * 정수 또는 부동소수점 문자열을 정수로 변환
     * "1" 또는 "1.000000000" 모두 처리
     */
    private static int parseIntOrDouble(String value) {
        if (value.contains(".")) {
            return (int) Double.parseDouble(value);
        }
        return Integer.parseInt(value);
    }

    /**
     * "HH:MM:SS" 형식의 시간을 초 단위로 변환
     * GTFS는 24시간 이후의 시간도 허용 (예: "25:30:00")
     *
     * @param timeStr 시간 문자열 "HH:MM:SS"
     * @return 자정 이후 초
     */
    public static int parseTime(String timeStr) {
        if (timeStr == null || timeStr.isEmpty()) {
            return -1;
        }
        String[] parts = timeStr.split(":");
        int hours = Integer.parseInt(parts[0]);
        int minutes = Integer.parseInt(parts[1]);
        int seconds = Integer.parseInt(parts[2]);
        return hours * 3600 + minutes * 60 + seconds;
    }

    /**
     * 초 단위 시간을 "HH:MM" 형식으로 변환
     *
     * @param seconds 자정 이후 초
     * @return "HH:MM" 형식 문자열
     */
    public static String formatTime(int seconds) {
        if (seconds < 0) return "--:--";
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }

    /**
     * 초 단위 시간을 "HH:MM:SS" 형식으로 변환
     *
     * @param seconds 자정 이후 초
     * @return "HH:MM:SS" 형식 문자열
     */
    public static String formatTimeFull(int seconds) {
        if (seconds < 0) return "--:--:--";
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        int s = seconds % 60;
        return String.format("%02d:%02d:%02d", h, m, s);
    }

    /**
     * 이 정류장에서 승차 가능한지 확인
     *
     * @return 승차 가능 여부
     */
    public boolean canBoard() {
        return pickupType == PICKUP_REGULAR;
    }

    /**
     * 이 정류장에서 하차 가능한지 확인
     *
     * @return 하차 가능 여부
     */
    public boolean canAlight() {
        return dropOffType == DROP_OFF_REGULAR;
    }

    @Override
    public String toString() {
        return String.format("StopTime[trip=%s, stop=%s, seq=%d, arr=%s, dep=%s]",
            tripId, stopId, stopSequence,
            formatTime(arrivalTime), formatTime(departureTime));
    }
}
