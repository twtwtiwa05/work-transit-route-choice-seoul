package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.RaptorTransferConstraint;
import org.opentripplanner.raptor.spi.RaptorBoardOrAlightEvent;

/**
 * 한국 대중교통용 탑승/하차 이벤트.
 *
 * Flyweight 패턴 적용 - 객체 재사용으로 GC 부담 최소화.
 * 검색 결과를 담는 mutable 객체로, 매 검색마다 값만 변경.
 *
 * 성능 핵심 클래스 - Raptor 알고리즘에서 가장 자주 호출됨.
 */
public class KoreanBoardAlightEvent implements RaptorBoardOrAlightEvent<KoreanTripSchedule> {

    private KoreanTripSchedule trip;
    private int tripIndex;
    private int stopPositionInPattern;
    private int time;
    private int earliestBoardTime;
    private boolean isEmpty;

    public KoreanBoardAlightEvent() {
        this.isEmpty = true;
    }

    /**
     * 검색 결과 설정 (Flyweight - 재사용)
     */
    public void set(
        KoreanTripSchedule trip,
        int tripIndex,
        int stopPositionInPattern,
        int time,
        int earliestBoardTime
    ) {
        this.trip = trip;
        this.tripIndex = tripIndex;
        this.stopPositionInPattern = stopPositionInPattern;
        this.time = time;
        this.earliestBoardTime = earliestBoardTime;
        this.isEmpty = false;
    }

    /**
     * 빈 결과로 초기화
     */
    public void setEmpty(int earliestBoardTime) {
        this.trip = null;
        this.tripIndex = -1;
        this.stopPositionInPattern = -1;
        this.time = -1;
        this.earliestBoardTime = earliestBoardTime;
        this.isEmpty = true;
    }

    @Override
    public int tripIndex() {
        return tripIndex;
    }

    @Override
    public KoreanTripSchedule trip() {
        return trip;
    }

    @Override
    public int stopPositionInPattern() {
        return stopPositionInPattern;
    }

    @Override
    public int time() {
        return time;
    }

    @Override
    public int earliestBoardTime() {
        return earliestBoardTime;
    }

    @Override
    public RaptorTransferConstraint transferConstraint() {
        // 제약 환승 미사용 - 일반 환승
        return RaptorTransferConstraint.REGULAR_TRANSFER;
    }

    @Override
    public boolean empty() {
        return isEmpty;
    }

    @Override
    public String toString() {
        if (isEmpty) {
            return "BoardAlightEvent[EMPTY]";
        }
        return String.format("BoardAlightEvent[trip=%s, idx=%d, stopPos=%d, time=%d]",
            trip != null ? trip.getTripId() : "null",
            tripIndex, stopPositionInPattern, time);
    }
}
