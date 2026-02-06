package kr.otp.util;

/**
 * 시간 변환 유틸리티.
 *
 * GTFS와 Raptor는 모두 자정 이후 초 단위로 시간을 표현.
 * 이 클래스는 다양한 시간 형식 간의 변환을 제공.
 */
public final class TimeUtil {

    private TimeUtil() {}

    // 상수
    public static final int SECONDS_IN_MINUTE = 60;
    public static final int SECONDS_IN_HOUR = 3600;
    public static final int SECONDS_IN_DAY = 86400;

    // 일반적인 시간대
    public static final int TIME_04_00 = 4 * SECONDS_IN_HOUR;
    public static final int TIME_09_00 = 9 * SECONDS_IN_HOUR;
    public static final int TIME_18_00 = 18 * SECONDS_IN_HOUR;
    public static final int TIME_24_00 = 24 * SECONDS_IN_HOUR;

    /**
     * "HH:MM" 형식을 초 단위로 변환
     *
     * @param time "09:30" 형식
     * @return 자정 이후 초 (예: 34200)
     */
    public static int parseHHMM(String time) {
        String[] parts = time.split(":");
        int hours = Integer.parseInt(parts[0].trim());
        int minutes = Integer.parseInt(parts[1].trim());
        return hours * SECONDS_IN_HOUR + minutes * SECONDS_IN_MINUTE;
    }

    /**
     * "HH:MM:SS" 형식을 초 단위로 변환
     *
     * @param time "09:30:00" 형식
     * @return 자정 이후 초
     */
    public static int parseHHMMSS(String time) {
        String[] parts = time.split(":");
        int hours = Integer.parseInt(parts[0].trim());
        int minutes = Integer.parseInt(parts[1].trim());
        int seconds = parts.length > 2 ? Integer.parseInt(parts[2].trim()) : 0;
        return hours * SECONDS_IN_HOUR + minutes * SECONDS_IN_MINUTE + seconds;
    }

    /**
     * 초 단위를 "HH:MM" 형식으로 변환
     *
     * @param seconds 자정 이후 초
     * @return "09:30" 형식
     */
    public static String formatHHMM(int seconds) {
        if (seconds < 0) return "--:--";
        int h = seconds / SECONDS_IN_HOUR;
        int m = (seconds % SECONDS_IN_HOUR) / SECONDS_IN_MINUTE;
        return String.format("%02d:%02d", h, m);
    }

    /**
     * 초 단위를 "HH:MM:SS" 형식으로 변환
     *
     * @param seconds 자정 이후 초
     * @return "09:30:00" 형식
     */
    public static String formatHHMMSS(int seconds) {
        if (seconds < 0) return "--:--:--";
        int h = seconds / SECONDS_IN_HOUR;
        int m = (seconds % SECONDS_IN_HOUR) / SECONDS_IN_MINUTE;
        int s = seconds % SECONDS_IN_MINUTE;
        return String.format("%02d:%02d:%02d", h, m, s);
    }

    /**
     * 초 단위를 사람이 읽기 쉬운 형식으로 변환
     * 예: "32분", "1시간 5분"
     *
     * @param seconds 소요 시간 (초)
     * @return 읽기 쉬운 형식
     */
    public static String formatDuration(int seconds) {
        if (seconds < 0) return "-";
        if (seconds < SECONDS_IN_MINUTE) {
            return seconds + "초";
        }
        int minutes = seconds / SECONDS_IN_MINUTE;
        if (minutes < 60) {
            return minutes + "분";
        }
        int hours = minutes / 60;
        int remainingMinutes = minutes % 60;
        if (remainingMinutes == 0) {
            return hours + "시간";
        }
        return hours + "시간 " + remainingMinutes + "분";
    }

    /**
     * 두 시간 사이의 차이 계산
     *
     * @param startSeconds 시작 시간 (초)
     * @param endSeconds 종료 시간 (초)
     * @return 소요 시간 (초)
     */
    public static int duration(int startSeconds, int endSeconds) {
        return endSeconds - startSeconds;
    }

    /**
     * 시간이 유효한 범위인지 확인
     *
     * @param seconds 확인할 시간 (초)
     * @return 유효 여부 (0 ~ 48시간)
     */
    public static boolean isValidTime(int seconds) {
        return seconds >= 0 && seconds <= 48 * SECONDS_IN_HOUR;
    }

    /**
     * 시간을 분 단위로 변환
     *
     * @param seconds 초 단위 시간
     * @return 분 단위 (반올림)
     */
    public static int toMinutes(int seconds) {
        return (seconds + 30) / SECONDS_IN_MINUTE;
    }

    /**
     * 분 단위를 초 단위로 변환
     *
     * @param minutes 분 단위
     * @return 초 단위
     */
    public static int fromMinutes(int minutes) {
        return minutes * SECONDS_IN_MINUTE;
    }
}
