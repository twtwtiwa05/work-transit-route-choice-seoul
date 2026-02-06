package kr.otp.raptor.spi;

import kr.otp.CalibrationConfig;
import org.opentripplanner.raptor.api.model.RaptorAccessEgress;
import org.opentripplanner.raptor.api.model.RaptorTransferConstraint;
import org.opentripplanner.raptor.spi.RaptorCostCalculator;

/**
 * 한국 대중교통용 비용 계산기.
 *
 * Multi-Criteria 탐색에서 경로의 "비용"을 계산.
 * 비용은 시간 + 환승 페널티 등으로 구성.
 *
 * 단위: centi-seconds (1초 = 100)
 * 예: 1분 = 6000 centi-seconds
 *
 * 비용 구성:
 * - 승차 비용 (첫 승차 / 환승)
 * - 대기 시간 비용
 * - 탑승 시간 비용
 * - Egress 비용
 */
public class KoreanCostCalculator implements RaptorCostCalculator<KoreanTripSchedule> {

    // 비용 계수 (centi-seconds 단위, 1초 = 100)
    private final int firstBoardCost;
    private final int transferCost;
    private final double waitReluctance;

    public KoreanCostCalculator() {
        this(CalibrationConfig.defaults());
    }

    public KoreanCostCalculator(CalibrationConfig config) {
        this.firstBoardCost = config.getFirstBoardCostSeconds() * 100;
        this.transferCost = config.getTransferCostSeconds() * 100;
        this.waitReluctance = config.getWaitReluctance();
    }

    @Override
    public int boardingCost(
        boolean firstBoarding,
        int prevArrivalTime,
        int boardStop,
        int boardTime,
        KoreanTripSchedule trip,
        RaptorTransferConstraint transferConstraints
    ) {
        // 대기 시간 계산
        int waitTime = boardTime - prevArrivalTime;
        int waitCost = (int) (waitTime * 100 * waitReluctance);

        // 첫 승차 vs 환승
        int boardCost = firstBoarding ? firstBoardCost : transferCost;

        return boardCost + waitCost;
    }

    @Override
    public int onTripRelativeRidingCost(int boardTime, KoreanTripSchedule tripScheduledBoarded) {
        return ZERO_COST;
    }

    @Override
    public int transitArrivalCost(
        int boardCost,
        int alightSlack,
        int transitTime,
        KoreanTripSchedule trip,
        int toStop
    ) {
        return boardCost + (transitTime * 100);
    }

    @Override
    public int waitCost(int waitTimeInSeconds) {
        return (int) (waitTimeInSeconds * 100 * waitReluctance);
    }

    @Override
    public int calculateRemainingMinCost(int minTravelTime, int minNumTransfers, int fromStop) {
        return (minTravelTime * 100) + (minNumTransfers * transferCost);
    }

    @Override
    public int costEgress(RaptorAccessEgress egress) {
        return egress.c1();
    }

    @Override
    public String toString() {
        return "KoreanCostCalculator{" +
            "firstBoardCost=" + (firstBoardCost / 100) + "s, " +
            "transferCost=" + (transferCost / 100) + "s, " +
            "waitReluctance=" + waitReluctance +
            '}';
    }
}
