package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.SearchDirection;
import org.opentripplanner.raptor.spi.RaptorBoardOrAlightEvent;
import org.opentripplanner.raptor.spi.RaptorTripScheduleSearch;

/**
 * 한국 대중교통용 트립 검색기.
 *
 * 이진 검색(Binary Search)으로 탑승 가능한 트립을 O(log n) 시간에 검색.
 * Raptor 알고리즘의 성능 핵심 클래스.
 *
 * 성능 최적화:
 * - Flyweight 패턴: 결과 객체 재사용 (GC 최소화)
 * - 이진 검색: 수백 개의 트립에서도 빠른 검색
 * - primitive 연산: 객체 생성 최소화
 */
public class KoreanTripScheduleSearch implements RaptorTripScheduleSearch<KoreanTripSchedule> {

    private final KoreanTripSchedule[] schedules;  // 시간순 정렬됨
    private final SearchDirection direction;

    // Flyweight: 결과 객체 재사용 (GC 최소화)
    private final KoreanBoardAlightEvent event;

    public KoreanTripScheduleSearch(
        KoreanTripSchedule[] schedules,
        SearchDirection direction
    ) {
        this.schedules = schedules;
        this.direction = direction;
        this.event = new KoreanBoardAlightEvent();
    }

    @Override
    public RaptorBoardOrAlightEvent<KoreanTripSchedule> search(
        int earliestBoardTime,
        int stopPositionInPattern,
        int tripIndexLimit
    ) {
        // 트립이 없으면 빈 결과
        if (schedules == null || schedules.length == 0) {
            event.setEmpty(earliestBoardTime);
            return event;
        }

        // 검색 범위 결정
        int limit = (tripIndexLimit == UNBOUNDED_TRIP_INDEX)
            ? schedules.length
            : Math.min(tripIndexLimit + 1, schedules.length);

        // 이진 검색으로 탑승 가능한 첫 트립 찾기
        int index = binarySearch(earliestBoardTime, stopPositionInPattern, limit);

        if (index < 0 || index >= limit) {
            event.setEmpty(earliestBoardTime);
            return event;
        }

        KoreanTripSchedule trip = schedules[index];
        int time = (direction == SearchDirection.FORWARD)
            ? trip.departure(stopPositionInPattern)
            : trip.arrival(stopPositionInPattern);

        // Flyweight: 새 객체 생성 없이 재사용
        event.set(trip, index, stopPositionInPattern, time, earliestBoardTime);
        return event;
    }

    /**
     * 이진 검색: O(log n) 복잡도
     *
     * 정방향: earliestBoardTime 이상인 첫 트립 찾기
     * 역방향: earliestBoardTime 이하인 마지막 트립 찾기
     */
    private int binarySearch(int targetTime, int stopPos, int limit) {
        int low = 0;
        int high = limit - 1;
        int result = -1;

        while (low <= high) {
            int mid = (low + high) >>> 1;  // 오버플로우 방지
            int tripTime = (direction == SearchDirection.FORWARD)
                ? schedules[mid].departure(stopPos)
                : schedules[mid].arrival(stopPos);

            if (direction == SearchDirection.FORWARD) {
                // 정방향: targetTime 이상인 첫 트립
                if (tripTime >= targetTime) {
                    result = mid;
                    high = mid - 1;
                } else {
                    low = mid + 1;
                }
            } else {
                // 역방향: targetTime 이하인 마지막 트립
                if (tripTime <= targetTime) {
                    result = mid;
                    low = mid + 1;
                } else {
                    high = mid - 1;
                }
            }
        }

        return result;
    }

    /**
     * 검색 방향 반환
     */
    public SearchDirection getDirection() {
        return direction;
    }

    /**
     * 트립 개수 반환
     */
    public int getTripCount() {
        return schedules != null ? schedules.length : 0;
    }
}
