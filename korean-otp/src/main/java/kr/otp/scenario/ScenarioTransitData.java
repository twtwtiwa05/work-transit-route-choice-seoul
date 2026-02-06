package kr.otp.scenario;

import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanRoute;
import kr.otp.raptor.spi.KoreanTransfer;

import java.util.*;

/**
 * 시나리오가 적용된 TransitData 래퍼.
 *
 * 원본 TransitData를 수정하지 않고, 수정사항만 오버레이.
 * - 비활성화된 노선 필터링
 * - 수정된 노선 대체
 * - 신규 노선 추가
 *
 * 메모리 효율: 수정된 부분만 저장, 원본은 참조만.
 */
public class ScenarioTransitData {

    private final TransitData originalData;

    // 비활성화된 노선 인덱스
    private final Set<Integer> disabledRouteIndices;

    // 수정된 노선 (routeIndex → modified route)
    private final Map<Integer, KoreanRoute> modifiedRoutes;

    // 추가된 노선
    private final List<KoreanRoute> addedRoutes;

    // 캐시: 정류장별 노선 인덱스 (재계산 필요 시)
    private int[][] cachedRoutesByStop;

    // 전체 노선 배열 (원본 + 수정 + 추가)
    private KoreanRoute[] allRoutes;

    public ScenarioTransitData(TransitData originalData) {
        this.originalData = originalData;
        this.disabledRouteIndices = new HashSet<>();
        this.modifiedRoutes = new HashMap<>();
        this.addedRoutes = new ArrayList<>();
    }

    /**
     * 노선 비활성화
     */
    public void disableRoute(int routeIndex) {
        disabledRouteIndices.add(routeIndex);
        invalidateCache();
    }

    /**
     * 노선 비활성화 (여러 개)
     */
    public void disableRoutes(Collection<Integer> routeIndices) {
        disabledRouteIndices.addAll(routeIndices);
        invalidateCache();
    }

    /**
     * 수정된 노선 추가
     */
    public void setModifiedRoute(int originalRouteIndex, KoreanRoute modifiedRoute) {
        modifiedRoutes.put(originalRouteIndex, modifiedRoute);
        invalidateCache();
    }

    /**
     * 신규 노선 추가
     */
    public void addRoute(KoreanRoute newRoute) {
        addedRoutes.add(newRoute);
        invalidateCache();
    }

    /**
     * 캐시 무효화
     */
    private void invalidateCache() {
        cachedRoutesByStop = null;
        allRoutes = null;
    }

    // ═══════════════════════════════════════════════════════════════
    // TransitData 호환 메서드들
    // ═══════════════════════════════════════════════════════════════

    public int getStopCount() {
        return originalData.getStopCount();
    }

    public String getStopId(int stopIndex) {
        return originalData.getStopId(stopIndex);
    }

    public String getStopName(int stopIndex) {
        return originalData.getStopName(stopIndex);
    }

    public double getStopLat(int stopIndex) {
        return originalData.getStopLat(stopIndex);
    }

    public double getStopLon(int stopIndex) {
        return originalData.getStopLon(stopIndex);
    }

    /**
     * 총 노선 수 (원본 - 비활성화 + 추가)
     */
    public int getRouteCount() {
        buildAllRoutes();
        return allRoutes.length;
    }

    /**
     * 노선 조회 (수정/추가 반영)
     */
    public KoreanRoute getRoute(int routeIndex) {
        buildAllRoutes();
        if (routeIndex < 0 || routeIndex >= allRoutes.length) {
            return null;
        }
        return allRoutes[routeIndex];
    }

    /**
     * 전체 노선 배열 빌드
     */
    private void buildAllRoutes() {
        if (allRoutes != null) {
            return;
        }

        List<KoreanRoute> routes = new ArrayList<>();

        // 원본 노선 (비활성화 제외, 수정 반영)
        int originalCount = originalData.getRouteCount();
        for (int i = 0; i < originalCount; i++) {
            if (disabledRouteIndices.contains(i)) {
                continue;
            }

            if (modifiedRoutes.containsKey(i)) {
                routes.add(modifiedRoutes.get(i));
            } else {
                routes.add(originalData.getRoute(i));
            }
        }

        // 추가된 노선
        routes.addAll(addedRoutes);

        allRoutes = routes.toArray(new KoreanRoute[0]);
    }

    /**
     * 환승 정보 (원본 그대로)
     */
    public Iterator<KoreanTransfer> getTransfersFrom(int stopIndex) {
        return originalData.getTransfersFrom(stopIndex);
    }

    public Iterator<KoreanTransfer> getTransfersTo(int stopIndex) {
        return originalData.getTransfersTo(stopIndex);
    }

    /**
     * 정류장별 경유 노선 인덱스 (재계산)
     */
    public int[] getRoutesByStop(int stopIndex) {
        buildRoutesByStop();

        if (stopIndex < 0 || stopIndex >= cachedRoutesByStop.length) {
            return new int[0];
        }

        int[] routes = cachedRoutesByStop[stopIndex];
        return routes != null ? routes : new int[0];
    }

    /**
     * 정류장별 노선 인덱스 재계산
     */
    private void buildRoutesByStop() {
        if (cachedRoutesByStop != null) {
            return;
        }

        buildAllRoutes();

        int stopCount = originalData.getStopCount();
        List<List<Integer>> routesByStopList = new ArrayList<>(stopCount);

        for (int i = 0; i < stopCount; i++) {
            routesByStopList.add(new ArrayList<>());
        }

        // 모든 노선을 순회하며 정류장별 인덱스 기록
        for (int routeIndex = 0; routeIndex < allRoutes.length; routeIndex++) {
            KoreanRoute route = allRoutes[routeIndex];
            int[] stopIndexes = ((kr.otp.raptor.spi.KoreanTripPattern) route.pattern()).getStopIndexes();

            for (int stopIndex : stopIndexes) {
                if (stopIndex >= 0 && stopIndex < stopCount) {
                    routesByStopList.get(stopIndex).add(routeIndex);
                }
            }
        }

        // 배열로 변환
        cachedRoutesByStop = new int[stopCount][];
        for (int i = 0; i < stopCount; i++) {
            List<Integer> list = routesByStopList.get(i);
            cachedRoutesByStop[i] = list.stream().mapToInt(Integer::intValue).toArray();
        }
    }

    public int getServiceStartTime() {
        return originalData.getServiceStartTime();
    }

    public int getServiceEndTime() {
        return originalData.getServiceEndTime();
    }

    public int getPatternCount() {
        return getRouteCount();
    }

    public int getTotalTripCount() {
        buildAllRoutes();
        int count = 0;
        for (KoreanRoute route : allRoutes) {
            count += route.getTripCount();
        }
        return count;
    }

    // ═══════════════════════════════════════════════════════════════
    // 통계 및 정보
    // ═══════════════════════════════════════════════════════════════

    public int getDisabledRouteCount() {
        return disabledRouteIndices.size();
    }

    public int getModifiedRouteCount() {
        return modifiedRoutes.size();
    }

    public int getAddedRouteCount() {
        return addedRoutes.size();
    }

    public TransitData getOriginalData() {
        return originalData;
    }

    @Override
    public String toString() {
        buildAllRoutes();
        return String.format("ScenarioTransitData[stops=%d, routes=%d (원본 %d, 비활성화 %d, 수정 %d, 추가 %d), trips=%d]",
            getStopCount(),
            allRoutes.length,
            originalData.getRouteCount(),
            disabledRouteIndices.size(),
            modifiedRoutes.size(),
            addedRoutes.size(),
            getTotalTripCount());
    }
}
