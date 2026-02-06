package kr.otp.scenario;

import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanRoute;

import java.util.ArrayList;
import java.util.List;

/**
 * 시나리오 관리자.
 *
 * 수정 사항들을 관리하고 적용하는 중앙 클래스.
 *
 * 사용법:
 * <pre>
 * ScenarioManager manager = new ScenarioManager(transitData);
 *
 * // 수정 추가
 * manager.addHeadway("2호선", 2.0);
 * manager.addDisable("9호선");
 * manager.addNewRoute("급행버스", ...);
 *
 * // 시나리오 적용
 * ScenarioTransitData scenarioData = manager.apply();
 *
 * // Raptor로 검색
 * ScenarioTransitDataProvider provider = new ScenarioTransitDataProvider(scenarioData);
 * </pre>
 */
public class ScenarioManager {

    private final TransitData originalData;
    private final RouteSearcher routeSearcher;
    private final StopSearcher stopSearcher;

    private final List<Modification> modifications;

    // 적용된 시나리오 데이터 (캐시)
    private ScenarioTransitData appliedScenario;

    public ScenarioManager(TransitData transitData) {
        this.originalData = transitData;
        this.routeSearcher = new RouteSearcher(transitData);
        this.stopSearcher = new StopSearcher(transitData);
        this.modifications = new ArrayList<>();
    }

    // ═══════════════════════════════════════════════════════════════
    // 수정 추가 메서드
    // ═══════════════════════════════════════════════════════════════

    /**
     * 배차간격 조정 추가
     *
     * @param routePattern 노선 패턴 (예: "2호선", "402번")
     * @param factor 배차간격 배율 (2.0 = 2배 늘림, 0.5 = 절반으로 줄임)
     * @return 결과 메시지
     */
    public String addHeadway(String routePattern, double factor) {
        RouteSearcher.SearchResult result = routeSearcher.getSearchResult(routePattern);

        if (result.isEmpty()) {
            return String.format("오류: '%s' 패턴에 매칭되는 노선이 없습니다.", routePattern);
        }

        HeadwayModification mod = new HeadwayModification(
            routePattern, factor, result.getRouteIndices(), originalData);

        modifications.add(mod);
        invalidateApplied();

        return String.format("✓ %s", mod.getDescription());
    }

    /**
     * 노선 비활성화 추가
     *
     * @param routePattern 노선 패턴
     * @return 결과 메시지
     */
    public String addDisable(String routePattern) {
        RouteSearcher.SearchResult result = routeSearcher.getSearchResult(routePattern);

        if (result.isEmpty()) {
            return String.format("오류: '%s' 패턴에 매칭되는 노선이 없습니다.", routePattern);
        }

        DisableRouteModification mod = new DisableRouteModification(
            routePattern, result.getRouteIndices(), originalData);

        modifications.add(mod);
        invalidateApplied();

        return String.format("✓ %s", mod.getDescription());
    }

    /**
     * 신규 노선 추가
     *
     * @param modification 노선 추가 수정 객체
     * @return 결과 메시지
     */
    public String addNewRoute(AddRouteModification modification) {
        modifications.add(modification);
        invalidateApplied();

        return String.format("✓ %s", modification.getDescription());
    }

    /**
     * 신규 노선 추가 (빌더 시작)
     */
    public AddRouteModification.Builder newRouteBuilder() {
        return AddRouteModification.builder();
    }

    // ═══════════════════════════════════════════════════════════════
    // 수정 관리
    // ═══════════════════════════════════════════════════════════════

    /**
     * 모든 수정사항 목록
     */
    public List<Modification> getModifications() {
        return new ArrayList<>(modifications);
    }

    /**
     * 수정사항 수
     */
    public int getModificationCount() {
        return modifications.size();
    }

    /**
     * 특정 수정 제거
     */
    public void removeModification(int index) {
        if (index >= 0 && index < modifications.size()) {
            modifications.remove(index);
            invalidateApplied();
        }
    }

    /**
     * 모든 수정사항 제거
     */
    public void clearModifications() {
        modifications.clear();
        invalidateApplied();
    }

    /**
     * 적용 캐시 무효화
     */
    private void invalidateApplied() {
        appliedScenario = null;
    }

    // ═══════════════════════════════════════════════════════════════
    // 시나리오 적용
    // ═══════════════════════════════════════════════════════════════

    /**
     * 시나리오 적용 (ScenarioTransitData 생성)
     *
     * @return 시나리오가 적용된 TransitData
     */
    public ScenarioTransitData apply() {
        if (appliedScenario != null) {
            return appliedScenario;
        }

        appliedScenario = new ScenarioTransitData(originalData);

        int newPatternIndex = originalData.getRouteCount();

        for (Modification mod : modifications) {
            switch (mod.getType()) {
                case DISABLE_ROUTE:
                    DisableRouteModification disableMod = (DisableRouteModification) mod;
                    appliedScenario.disableRoutes(disableMod.getAffectedRouteIndices());
                    break;

                case HEADWAY:
                    HeadwayModification headwayMod = (HeadwayModification) mod;
                    for (int routeIdx : headwayMod.getAffectedRouteIndices()) {
                        KoreanRoute original = originalData.getRoute(routeIdx);
                        KoreanRoute modified = headwayMod.applyToRoute(original, newPatternIndex++);
                        appliedScenario.setModifiedRoute(routeIdx, modified);
                    }
                    break;

                case ADD_ROUTE:
                    AddRouteModification addMod = (AddRouteModification) mod;
                    KoreanRoute newRoute = addMod.generateRoute(newPatternIndex++);
                    appliedScenario.addRoute(newRoute);
                    break;

                default:
                    // 미지원 타입
                    break;
            }
        }

        return appliedScenario;
    }

    /**
     * 시나리오 데이터 프로바이더 생성
     */
    public ScenarioTransitDataProvider createProvider() {
        return new ScenarioTransitDataProvider(apply());
    }

    // ═══════════════════════════════════════════════════════════════
    // 검색 유틸리티
    // ═══════════════════════════════════════════════════════════════

    /**
     * 노선 검색
     */
    public RouteSearcher.SearchResult searchRoutes(String pattern) {
        return routeSearcher.getSearchResult(pattern);
    }

    /**
     * 정류장 검색
     */
    public List<StopSearcher.StopInfo> searchStops(String keyword, int maxResults) {
        return stopSearcher.search(keyword, maxResults);
    }

    /**
     * 좌표 근처 정류장 검색
     */
    public List<StopSearcher.StopInfo> searchStopsNearby(double lat, double lon, double radiusMeters, int maxResults) {
        return stopSearcher.searchNearby(lat, lon, radiusMeters, maxResults);
    }

    // ═══════════════════════════════════════════════════════════════
    // 정보
    // ═══════════════════════════════════════════════════════════════

    public TransitData getOriginalData() {
        return originalData;
    }

    /**
     * 수정사항 요약 출력
     */
    public String getSummary() {
        if (modifications.isEmpty()) {
            return "수정사항 없음";
        }

        StringBuilder sb = new StringBuilder();
        sb.append("=== 현재 시나리오 ===\n");

        int idx = 1;
        for (Modification mod : modifications) {
            sb.append(String.format("%d. [%s] %s%n",
                idx++, mod.getType(), mod.getDescription()));
        }

        return sb.toString();
    }

    @Override
    public String toString() {
        return String.format("ScenarioManager[수정사항=%d, 원본=%s]",
            modifications.size(), originalData);
    }
}
