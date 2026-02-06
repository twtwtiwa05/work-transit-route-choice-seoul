package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.SearchDirection;
import org.opentripplanner.raptor.spi.RaptorTimeTable;
import org.opentripplanner.raptor.spi.RaptorTripScheduleSearch;

/**
 * 한국 대중교통용 시간표.
 *
 * 하나의 패턴에 속한 모든 트립들의 시간표.
 * 트립들은 첫 정류장 출발 시간 기준으로 정렬됨.
 *
 * 성능 최적화:
 * - 검색 객체 캐싱: 정방향/역방향 검색기 재사용
 * - 배열 기반: ArrayList 대신 primitive 배열
 */
public class KoreanTimeTable implements RaptorTimeTable<KoreanTripSchedule> {

    private final KoreanTripSchedule[] schedules;  // 시간순 정렬

    // 캐싱: 검색 객체 재사용
    private final KoreanTripScheduleSearch forwardSearch;
    private final KoreanTripScheduleSearch reverseSearch;

    public KoreanTimeTable(KoreanTripSchedule[] schedules) {
        this.schedules = schedules;
        this.forwardSearch = new KoreanTripScheduleSearch(schedules, SearchDirection.FORWARD);
        this.reverseSearch = new KoreanTripScheduleSearch(schedules, SearchDirection.REVERSE);
    }

    @Override
    public KoreanTripSchedule getTripSchedule(int index) {
        return schedules[index];
    }

    @Override
    public int numberOfTripSchedules() {
        return schedules.length;
    }

    @Override
    public RaptorTripScheduleSearch<KoreanTripSchedule> tripSearch(SearchDirection direction) {
        return (direction == SearchDirection.FORWARD) ? forwardSearch : reverseSearch;
    }

    /**
     * 첫 트립의 출발 시간
     */
    public int getFirstDepartureTime() {
        if (schedules.length == 0) return -1;
        return schedules[0].getFirstDepartureTime();
    }

    /**
     * 마지막 트립의 출발 시간
     */
    public int getLastDepartureTime() {
        if (schedules.length == 0) return -1;
        return schedules[schedules.length - 1].getFirstDepartureTime();
    }

    @Override
    public String toString() {
        if (schedules.length == 0) {
            return "TimeTable[empty]";
        }
        return String.format("TimeTable[trips=%d, first=%s, last=%s]",
            schedules.length,
            formatTime(getFirstDepartureTime()),
            formatTime(getLastDepartureTime()));
    }

    private String formatTime(int seconds) {
        if (seconds < 0) return "N/A";
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }
}
