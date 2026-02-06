package kr.otp.scenario;

import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanRoute;
import kr.otp.raptor.spi.KoreanTimeTable;
import kr.otp.raptor.spi.KoreanTripPattern;
import kr.otp.raptor.spi.KoreanTripSchedule;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * 배차간격 조정 수정.
 *
 * 지정된 노선의 배차간격을 조정합니다.
 * factor > 1.0: 배차간격 증가 (운행 감소)
 * factor < 1.0: 배차간격 감소 (운행 증가)
 *
 * 알고리즘:
 * - factor > 1.0: 기존 트립에서 일부만 선택 (균등 간격)
 * - factor < 1.0: 기존 트립 사이에 새 트립 보간
 */
public class HeadwayModification implements Modification {

    private final String routePattern;
    private final double factor;
    private final List<Integer> affectedRouteIndices;
    private final TransitData transitData;

    private int originalTripCount;
    private int newTripCount;

    public HeadwayModification(String routePattern, double factor,
                               List<Integer> affectedRouteIndices, TransitData transitData) {
        this.routePattern = routePattern;
        this.factor = factor;
        this.affectedRouteIndices = new ArrayList<>(affectedRouteIndices);
        this.transitData = transitData;

        // 영향받는 트립 수 계산
        this.originalTripCount = 0;
        for (int idx : affectedRouteIndices) {
            originalTripCount += transitData.getRoute(idx).getTripCount();
        }

        // 새 트립 수 계산 (factor 적용)
        if (factor >= 1.0) {
            // 감소: 1/factor 비율로 트립 선택
            this.newTripCount = (int) Math.ceil(originalTripCount / factor);
        } else {
            // 증가: 트립 보간
            this.newTripCount = (int) Math.ceil(originalTripCount / factor);
        }
    }

    @Override
    public Type getType() {
        return Type.HEADWAY;
    }

    @Override
    public String getDescription() {
        String direction = factor > 1.0 ? "감소" : "증가";
        return String.format("%s: 배차간격 %.1f배 (%s, %d→%d 트립)",
            routePattern, factor, direction, originalTripCount, newTripCount);
    }

    @Override
    public int getAffectedRouteCount() {
        return affectedRouteIndices.size();
    }

    @Override
    public int getAffectedTripCount() {
        return originalTripCount;
    }

    public String getRoutePattern() {
        return routePattern;
    }

    public double getFactor() {
        return factor;
    }

    public List<Integer> getAffectedRouteIndices() {
        return affectedRouteIndices;
    }

    public int getNewTripCount() {
        return newTripCount;
    }

    /**
     * 수정된 노선 생성
     *
     * @param originalRoute 원본 노선
     * @param newPatternIndex 새 패턴 인덱스
     * @return 수정된 노선
     */
    public KoreanRoute applyToRoute(KoreanRoute originalRoute, int newPatternIndex) {
        KoreanTimeTable originalTimeTable = (KoreanTimeTable) originalRoute.timetable();
        KoreanTripPattern originalPattern = (KoreanTripPattern) originalRoute.pattern();

        // 새 패턴 생성 (인덱스만 변경)
        KoreanTripPattern newPattern = new KoreanTripPattern(
            newPatternIndex,
            originalPattern.getStopIndexes(),
            originalPattern.slackIndex(),
            originalPattern.debugInfo()
        );

        // 새 시간표 생성
        KoreanTripSchedule[] newSchedules;

        if (factor >= 1.0) {
            // 트립 수 감소 - 균등 간격으로 선택
            newSchedules = reduceTrips(originalTimeTable, newPattern, factor);
        } else {
            // 트립 수 증가 - 보간
            newSchedules = interpolateTrips(originalTimeTable, newPattern, factor);
        }

        KoreanTimeTable newTimeTable = new KoreanTimeTable(newSchedules);

        return new KoreanRoute(
            newPattern,
            newTimeTable,
            originalRoute.getRouteId(),
            originalRoute.getRouteShortName(),
            originalRoute.getRouteLongName(),
            originalRoute.getRouteType()
        );
    }

    /**
     * 트립 수 감소 (factor >= 1.0)
     *
     * 예: factor=2.0이면 트립 수 절반 (매 2번째 트립만 선택)
     */
    private KoreanTripSchedule[] reduceTrips(KoreanTimeTable timeTable,
                                              KoreanTripPattern newPattern,
                                              double factor) {
        int originalCount = timeTable.numberOfTripSchedules();
        int newCount = Math.max(1, (int) Math.ceil(originalCount / factor));

        List<KoreanTripSchedule> newSchedules = new ArrayList<>();

        // 균등 간격으로 트립 선택
        for (int i = 0; i < newCount; i++) {
            int originalIndex = (int) Math.round(i * factor);
            if (originalIndex >= originalCount) {
                originalIndex = originalCount - 1;
            }

            KoreanTripSchedule original = timeTable.getTripSchedule(originalIndex);
            KoreanTripSchedule copy = copyScheduleWithNewPattern(original, newPattern, i);
            newSchedules.add(copy);
        }

        return newSchedules.toArray(new KoreanTripSchedule[0]);
    }

    /**
     * 트립 수 증가 (factor < 1.0)
     *
     * 예: factor=0.5이면 트립 수 2배 (기존 트립 사이에 보간)
     */
    private KoreanTripSchedule[] interpolateTrips(KoreanTimeTable timeTable,
                                                   KoreanTripPattern newPattern,
                                                   double factor) {
        int originalCount = timeTable.numberOfTripSchedules();
        if (originalCount < 2) {
            // 보간 불가 - 원본 반환
            KoreanTripSchedule[] result = new KoreanTripSchedule[originalCount];
            for (int i = 0; i < originalCount; i++) {
                result[i] = copyScheduleWithNewPattern(timeTable.getTripSchedule(i), newPattern, i);
            }
            return result;
        }

        int newCount = (int) Math.ceil(originalCount / factor);
        List<KoreanTripSchedule> newSchedules = new ArrayList<>();

        // 첫 트립 시간과 마지막 트립 시간
        int firstDeparture = timeTable.getTripSchedule(0).departure(0);
        int lastDeparture = timeTable.getTripSchedule(originalCount - 1).departure(0);
        int totalSpan = lastDeparture - firstDeparture;

        // 새 배차 간격
        int newHeadway = totalSpan / (newCount - 1);

        // 정류장 간 소요시간 (첫 트립 기준)
        KoreanTripSchedule firstTrip = timeTable.getTripSchedule(0);
        int stopCount = newPattern.numberOfStopsInPattern();
        int[] travelTimes = new int[stopCount - 1];
        int[] dwellTimes = new int[stopCount - 1];

        for (int s = 0; s < stopCount - 1; s++) {
            travelTimes[s] = firstTrip.arrival(s + 1) - firstTrip.departure(s);
            dwellTimes[s] = firstTrip.departure(s + 1) - firstTrip.arrival(s + 1);
        }

        // 새 트립 생성
        for (int i = 0; i < newCount; i++) {
            int departure = firstDeparture + (i * newHeadway);

            int[] arrivalTimes = new int[stopCount];
            int[] departureTimes = new int[stopCount];

            departureTimes[0] = departure;
            arrivalTimes[0] = departure;

            for (int s = 1; s < stopCount; s++) {
                arrivalTimes[s] = departureTimes[s - 1] + travelTimes[s - 1];
                departureTimes[s] = arrivalTimes[s] + (s < stopCount - 1 ? dwellTimes[s - 1] : 0);
            }

            KoreanTripSchedule newTrip = new KoreanTripSchedule(
                departure,  // tripSortIndex
                arrivalTimes,
                departureTimes,
                newPattern,
                "SCENARIO_" + i,
                firstTrip.getRouteShortName()
            );

            newSchedules.add(newTrip);
        }

        return newSchedules.toArray(new KoreanTripSchedule[0]);
    }

    /**
     * 스케줄 복사 (새 패턴으로)
     */
    private KoreanTripSchedule copyScheduleWithNewPattern(KoreanTripSchedule original,
                                                          KoreanTripPattern newPattern,
                                                          int newIndex) {
        int stopCount = newPattern.numberOfStopsInPattern();
        int[] arrivals = new int[stopCount];
        int[] departures = new int[stopCount];

        for (int i = 0; i < stopCount; i++) {
            arrivals[i] = original.arrival(i);
            departures[i] = original.departure(i);
        }

        return new KoreanTripSchedule(
            original.tripSortIndex(),
            arrivals,
            departures,
            newPattern,
            original.getTripId(),
            original.getRouteShortName()
        );
    }

    @Override
    public String toString() {
        return String.format("HeadwayModification[%s, factor=%.2f, routes=%d, trips=%d→%d]",
            routePattern, factor, affectedRouteIndices.size(), originalTripCount, newTripCount);
    }
}
