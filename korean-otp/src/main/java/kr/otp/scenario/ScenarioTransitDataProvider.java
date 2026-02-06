package kr.otp.scenario;

import kr.otp.raptor.spi.*;
import kr.otp.util.BitSetIntIterator;
import org.opentripplanner.raptor.api.model.RaptorStopNameResolver;
import org.opentripplanner.raptor.api.model.RaptorTransfer;
import org.opentripplanner.raptor.spi.*;

import java.util.BitSet;
import java.util.Iterator;

/**
 * 시나리오용 Raptor Transit Data Provider.
 *
 * ScenarioTransitData를 래핑하여 Raptor SPI 인터페이스 제공.
 * KoreanTransitDataProvider와 동일한 인터페이스이지만 시나리오 데이터 사용.
 */
public class ScenarioTransitDataProvider
    implements RaptorTransitDataProvider<KoreanTripSchedule> {

    private final ScenarioTransitData data;
    private final KoreanCostCalculator costCalculator;
    private final KoreanSlackProvider slackProvider;

    public ScenarioTransitDataProvider(ScenarioTransitData data) {
        this.data = data;
        this.costCalculator = new KoreanCostCalculator();
        this.slackProvider = new KoreanSlackProvider();
    }

    // ═══════════════════════════════════════════════════════════════
    // 필수 구현: 정류장
    // ═══════════════════════════════════════════════════════════════

    @Override
    public int numberOfStops() {
        return data.getStopCount();
    }

    // ═══════════════════════════════════════════════════════════════
    // 필수 구현: 환승
    // ═══════════════════════════════════════════════════════════════

    @Override
    public Iterator<? extends RaptorTransfer> getTransfersFromStop(int fromStop) {
        return data.getTransfersFrom(fromStop);
    }

    @Override
    public Iterator<? extends RaptorTransfer> getTransfersToStop(int toStop) {
        return data.getTransfersTo(toStop);
    }

    // ═══════════════════════════════════════════════════════════════
    // 필수 구현: 노선
    // ═══════════════════════════════════════════════════════════════

    @Override
    public IntIterator routeIndexIterator(IntIterator stops) {
        BitSet activeRoutes = new BitSet();
        while (stops.hasNext()) {
            int stopIndex = stops.next();
            for (int routeIdx : data.getRoutesByStop(stopIndex)) {
                activeRoutes.set(routeIdx);
            }
        }
        return new BitSetIntIterator(activeRoutes);
    }

    @Override
    public RaptorRoute<KoreanTripSchedule> getRouteForIndex(int routeIndex) {
        return data.getRoute(routeIndex);
    }

    // ═══════════════════════════════════════════════════════════════
    // 필수 구현: 비용 & 슬랙
    // ═══════════════════════════════════════════════════════════════

    @Override
    public RaptorCostCalculator<KoreanTripSchedule> multiCriteriaCostCalculator() {
        return costCalculator;
    }

    @Override
    public RaptorSlackProvider slackProvider() {
        return slackProvider;
    }

    // ═══════════════════════════════════════════════════════════════
    // 디버깅/옵션
    // ═══════════════════════════════════════════════════════════════

    @Override
    public RaptorStopNameResolver stopNameResolver() {
        return stopIndex -> data.getStopName(stopIndex);
    }

    @Override
    public int getValidTransitDataStartTime() {
        return data.getServiceStartTime();
    }

    @Override
    public int getValidTransitDataEndTime() {
        return data.getServiceEndTime();
    }

    // ═══════════════════════════════════════════════════════════════
    // 제약 환승 (미사용)
    // ═══════════════════════════════════════════════════════════════

    @Override
    public RaptorPathConstrainedTransferSearch<KoreanTripSchedule> transferConstraintsSearch() {
        return null;
    }

    @Override
    public RaptorConstrainedBoardingSearch<KoreanTripSchedule> transferConstraintsForwardSearch(int routeIndex) {
        return NoopConstrainedBoardingSearch.INSTANCE;
    }

    @Override
    public RaptorConstrainedBoardingSearch<KoreanTripSchedule> transferConstraintsReverseSearch(int routeIndex) {
        return NoopConstrainedBoardingSearch.INSTANCE;
    }

    // ═══════════════════════════════════════════════════════════════
    // 추가 메서드
    // ═══════════════════════════════════════════════════════════════

    public ScenarioTransitData getScenarioTransitData() {
        return data;
    }

    @Override
    public String toString() {
        return "ScenarioTransitDataProvider{" + data + "}";
    }
}
