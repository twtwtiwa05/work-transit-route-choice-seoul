package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.RaptorTripPattern;

/**
 * 한국 대중교통용 트립 패턴.
 *
 * 패턴은 동일한 정류장 순서를 공유하는 트립들의 그룹.
 * 예: 2호선 외선순환의 모든 트립은 같은 패턴을 공유
 *
 * GTFS에서 같은 route_id와 같은 정류장 순서를 가진 trip들이 하나의 패턴이 됨.
 */
public class KoreanTripPattern implements RaptorTripPattern {

    private final int patternIndex;       // 패턴 고유 인덱스
    private final int[] stopIndexes;      // 패턴 내 정류장 순서 (stopIndex 배열)
    private final int slackIndex;         // 교통수단별 슬랙 (0=지하철, 1=버스, 2=철도)
    private final int priorityGroupId;    // 우선순위 그룹 (기본=0)
    private final String debugInfo;       // 디버깅 정보 ("BUS_402" 등)

    // 승차/하차 가능 여부 (null이면 기본값 사용)
    private final boolean[] canBoard;
    private final boolean[] canAlight;

    /**
     * 기본 생성자 - 모든 정류장에서 승하차 가능
     */
    public KoreanTripPattern(
        int patternIndex,
        int[] stopIndexes,
        int slackIndex,
        String debugInfo
    ) {
        this(patternIndex, stopIndexes, slackIndex, 0, debugInfo, null, null);
    }

    /**
     * 전체 생성자
     */
    public KoreanTripPattern(
        int patternIndex,
        int[] stopIndexes,
        int slackIndex,
        int priorityGroupId,
        String debugInfo,
        boolean[] canBoard,
        boolean[] canAlight
    ) {
        this.patternIndex = patternIndex;
        this.stopIndexes = stopIndexes;
        this.slackIndex = slackIndex;
        this.priorityGroupId = priorityGroupId;
        this.debugInfo = debugInfo;
        this.canBoard = canBoard;
        this.canAlight = canAlight;
    }

    @Override
    public int patternIndex() {
        return patternIndex;
    }

    @Override
    public int numberOfStopsInPattern() {
        return stopIndexes.length;
    }

    @Override
    public int stopIndex(int stopPositionInPattern) {
        return stopIndexes[stopPositionInPattern];
    }

    @Override
    public boolean boardingPossibleAt(int stopPositionInPattern) {
        // 마지막 정류장에서는 승차 불가 (내리기만 가능)
        if (stopPositionInPattern >= stopIndexes.length - 1) {
            return false;
        }
        // canBoard 배열이 있으면 사용, 없으면 true
        if (canBoard != null) {
            return canBoard[stopPositionInPattern];
        }
        return true;
    }

    @Override
    public boolean alightingPossibleAt(int stopPositionInPattern) {
        // 첫 정류장에서는 하차 불가 (타기만 가능)
        if (stopPositionInPattern <= 0) {
            return false;
        }
        // canAlight 배열이 있으면 사용, 없으면 true
        if (canAlight != null) {
            return canAlight[stopPositionInPattern];
        }
        return true;
    }

    @Override
    public int slackIndex() {
        return slackIndex;
    }

    @Override
    public int priorityGroupId() {
        return priorityGroupId;
    }

    @Override
    public String debugInfo() {
        return debugInfo;
    }

    /**
     * 정류장 인덱스 배열 반환 (빌더용)
     */
    public int[] getStopIndexes() {
        return stopIndexes;
    }

    @Override
    public String toString() {
        return String.format("Pattern[%d: %s, stops=%d, slack=%d]",
            patternIndex, debugInfo, stopIndexes.length, slackIndex);
    }
}
