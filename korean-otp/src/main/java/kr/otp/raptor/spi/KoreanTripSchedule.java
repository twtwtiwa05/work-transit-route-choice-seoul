package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.RaptorTripPattern;
import org.opentripplanner.raptor.api.model.RaptorTripSchedule;

/**
 * 한국 대중교통용 트립 스케줄.
 *
 * 하나의 트립(차량 운행)에 대한 시간표 정보.
 * 각 정류장에서의 도착/출발 시간을 초 단위로 저장.
 *
 * 성능 최적화:
 * - primitive int[] 배열 사용 (객체 배열 X)
 * - 시간은 자정 기준 초 단위 (09:00 = 32400)
 */
public class KoreanTripSchedule implements RaptorTripSchedule {

    private final int tripSortIndex;       // 정렬 인덱스 (첫 정류장 출발 시간)
    private final int[] arrivalTimes;      // 각 정류장 도착 시간 (초)
    private final int[] departureTimes;    // 각 정류장 출발 시간 (초)
    private final KoreanTripPattern pattern;

    // 원본 정보 (결과 출력용)
    private final String tripId;
    private final String routeId;
    private final String routeShortName;   // "2호선", "402번" 등
    private final String routeLongName;
    private final int routeType;

    public KoreanTripSchedule(
        int tripSortIndex,
        int[] arrivalTimes,
        int[] departureTimes,
        KoreanTripPattern pattern,
        String tripId,
        String routeId,
        String routeShortName,
        String routeLongName,
        int routeType
    ) {
        this.tripSortIndex = tripSortIndex;
        this.arrivalTimes = arrivalTimes;
        this.departureTimes = departureTimes;
        this.pattern = pattern;
        this.tripId = tripId;
        this.routeId = routeId;
        this.routeShortName = routeShortName;
        this.routeLongName = routeLongName;
        this.routeType = routeType;
    }

    /**
     * 이전 버전 호환을 위한 생성자
     */
    public KoreanTripSchedule(
        int tripSortIndex,
        int[] arrivalTimes,
        int[] departureTimes,
        KoreanTripPattern pattern,
        String tripId,
        String routeShortName
    ) {
        this(tripSortIndex, arrivalTimes, departureTimes, pattern, tripId, null, routeShortName, null, -1);
    }

    @Override
    public int tripSortIndex() {
        return tripSortIndex;
    }

    @Override
    public int arrival(int stopPosInPattern) {
        return arrivalTimes[stopPosInPattern];
    }

    @Override
    public int departure(int stopPosInPattern) {
        return departureTimes[stopPosInPattern];
    }

    @Override
    public RaptorTripPattern pattern() {
        return pattern;
    }

    /**
     * 트립 ID 반환 (결과 출력용)
     */
    public String getTripId() {
        return tripId;
    }

    /**
     * 노선 ID 반환
     */
    public String getRouteId() {
        return routeId;
    }

    /**
     * 노선 단축명 반환 (결과 출력용)
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
     * 첫 정류장 출발 시간
     */
    public int getFirstDepartureTime() {
        return departureTimes[0];
    }

    /**
     * 마지막 정류장 도착 시간
     */
    public int getLastArrivalTime() {
        return arrivalTimes[arrivalTimes.length - 1];
    }

    /**
     * 시간 포맷팅 (디버깅용)
     */
    private String formatTime(int seconds) {
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }

    @Override
    public String toString() {
        return String.format("Trip[%s, %s, %s→%s, stops=%d]",
            tripId,
            routeShortName,
            formatTime(getFirstDepartureTime()),
            formatTime(getLastArrivalTime()),
            arrivalTimes.length
        );
    }
}
