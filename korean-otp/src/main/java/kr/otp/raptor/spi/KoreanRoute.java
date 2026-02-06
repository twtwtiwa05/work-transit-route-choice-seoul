package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.RaptorTripPattern;
import org.opentripplanner.raptor.spi.RaptorRoute;
import org.opentripplanner.raptor.spi.RaptorTimeTable;

/**
 * 한국 대중교통용 노선.
 *
 * RaptorRoute는 패턴(정류장 순서)과 시간표(트립들)를 연결하는 집합체.
 * Raptor 알고리즘에서 노선을 탐색할 때 이 클래스를 통해 접근.
 *
 * 구조:
 *   Route
 *     ├── Pattern (정류장 순서)
 *     └── TimeTable (트립들의 시간표)
 */
public class KoreanRoute implements RaptorRoute<KoreanTripSchedule> {

    private final KoreanTripPattern pattern;
    private final KoreanTimeTable timetable;

    // 원본 정보 (결과 출력용)
    private final String routeId;
    private final String routeShortName;
    private final String routeLongName;
    private final int routeType;

    public KoreanRoute(
        KoreanTripPattern pattern,
        KoreanTimeTable timetable,
        String routeId,
        String routeShortName,
        String routeLongName,
        int routeType
    ) {
        this.pattern = pattern;
        this.timetable = timetable;
        this.routeId = routeId;
        this.routeShortName = routeShortName;
        this.routeLongName = routeLongName;
        this.routeType = routeType;
    }

    /**
     * 간단한 생성자 (패턴과 시간표만)
     */
    public KoreanRoute(KoreanTripPattern pattern, KoreanTimeTable timetable) {
        this(pattern, timetable, null, null, null, -1);
    }

    @Override
    public RaptorTripPattern pattern() {
        return pattern;
    }

    @Override
    public RaptorTimeTable<KoreanTripSchedule> timetable() {
        return timetable;
    }

    /**
     * 노선 ID 반환
     */
    public String getRouteId() {
        return routeId;
    }

    /**
     * 노선 단축명 반환 ("2호선", "402번" 등)
     */
    public String getRouteShortName() {
        return routeShortName;
    }

    /**
     * 노선 전체명 반환
     */
    public String getRouteLongName() {
        return routeLongName;
    }

    /**
     * 노선 타입 반환 (GTFS route_type)
     */
    public int getRouteType() {
        return routeType;
    }

    /**
     * 트립 개수 반환
     */
    public int getTripCount() {
        return timetable.numberOfTripSchedules();
    }

    /**
     * 정류장 개수 반환
     */
    public int getStopCount() {
        return pattern.numberOfStopsInPattern();
    }

    @Override
    public String toString() {
        return String.format("Route[%s: %s, pattern=%d, trips=%d, stops=%d]",
            routeId,
            routeShortName != null ? routeShortName : "N/A",
            pattern.patternIndex(),
            getTripCount(),
            getStopCount());
    }
}
