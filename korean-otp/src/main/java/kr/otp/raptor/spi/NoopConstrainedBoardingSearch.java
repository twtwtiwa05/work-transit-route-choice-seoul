package kr.otp.raptor.spi;

import org.opentripplanner.raptor.spi.RaptorBoardOrAlightEvent;
import org.opentripplanner.raptor.spi.RaptorConstrainedBoardingSearch;
import org.opentripplanner.raptor.spi.RaptorTimeTable;

/**
 * 제약 환승 미사용시 사용하는 No-op 구현체.
 *
 * 한국 GTFS에서는 제약 환승(guaranteed transfer, stay-seated 등)을
 * 사용하지 않으므로, 항상 false를 반환하여 일반 환승으로 처리.
 */
public class NoopConstrainedBoardingSearch
    implements RaptorConstrainedBoardingSearch<KoreanTripSchedule> {

    public static final NoopConstrainedBoardingSearch INSTANCE = new NoopConstrainedBoardingSearch();

    private final KoreanBoardAlightEvent emptyEvent = new KoreanBoardAlightEvent();

    private NoopConstrainedBoardingSearch() {
        // Singleton
    }

    @Override
    public boolean transferExistTargetStop(int targetStopPos) {
        // 제약 환승 없음
        return false;
    }

    @Override
    public boolean transferExistSourceStop(int targetStopPos) {
        // 제약 환승 없음
        return false;
    }

    @Override
    public RaptorBoardOrAlightEvent<KoreanTripSchedule> find(
        RaptorTimeTable<KoreanTripSchedule> targetTimetable,
        int transferSlack,
        KoreanTripSchedule sourceTrip,
        int sourceStopIndex,
        int prevTransitArrivalTime,
        int earliestBoardTime
    ) {
        // 제약 환승 없음 - 빈 결과 반환
        emptyEvent.setEmpty(earliestBoardTime);
        return emptyEvent;
    }
}
