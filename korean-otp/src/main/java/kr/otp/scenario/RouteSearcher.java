package kr.otp.scenario;

import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanRoute;

import java.util.ArrayList;
import java.util.List;

/**
 * 노선명으로 노선을 검색하는 유틸리티.
 *
 * 검색 패턴:
 *   - "2호선"        → routeShortName에 "2호선" 포함
 *   - "402"          → routeShortName에 "402" 포함
 *   - "버스_402"     → 버스 타입이고 "402" 포함
 *   - "지하철_2"     → 지하철 타입이고 "2" 포함
 *   - "ROUTE:12345"  → routeId가 "12345"인 경우
 */
public class RouteSearcher {

    // GTFS route_type 상수
    private static final int TYPE_TRAM = 0;
    private static final int TYPE_SUBWAY = 1;
    private static final int TYPE_RAIL = 2;
    private static final int TYPE_BUS = 3;

    private final TransitData transitData;

    public RouteSearcher(TransitData transitData) {
        this.transitData = transitData;
    }

    /**
     * 패턴으로 노선 검색
     *
     * @param pattern 검색 패턴
     * @return 매칭된 노선 인덱스 목록
     */
    public List<Integer> search(String pattern) {
        List<Integer> results = new ArrayList<>();

        if (pattern == null || pattern.isEmpty()) {
            return results;
        }

        pattern = pattern.trim();

        // ROUTE: 접두사 - 정확한 routeId 매칭
        if (pattern.startsWith("ROUTE:")) {
            String routeId = pattern.substring(6);
            return searchByRouteId(routeId);
        }

        // 버스_ 접두사 - 버스만 검색
        if (pattern.startsWith("버스_")) {
            String keyword = pattern.substring(3);
            return searchByTypeAndName(TYPE_BUS, keyword);
        }

        // 지하철_ 접두사 - 지하철만 검색
        if (pattern.startsWith("지하철_")) {
            String keyword = pattern.substring(4);
            return searchByTypeAndName(TYPE_SUBWAY, keyword);
        }

        // 기본: routeShortName 포함 검색
        return searchByName(pattern);
    }

    /**
     * routeId로 정확히 검색
     */
    private List<Integer> searchByRouteId(String routeId) {
        List<Integer> results = new ArrayList<>();
        int routeCount = transitData.getRouteCount();

        for (int i = 0; i < routeCount; i++) {
            KoreanRoute route = transitData.getRoute(i);
            if (routeId.equals(route.getRouteId())) {
                results.add(i);
            }
        }

        return results;
    }

    /**
     * routeShortName에 키워드가 포함된 노선 검색
     */
    private List<Integer> searchByName(String keyword) {
        List<Integer> results = new ArrayList<>();
        int routeCount = transitData.getRouteCount();
        String lowerKeyword = keyword.toLowerCase();

        for (int i = 0; i < routeCount; i++) {
            KoreanRoute route = transitData.getRoute(i);
            String shortName = route.getRouteShortName();

            if (shortName != null && shortName.toLowerCase().contains(lowerKeyword)) {
                results.add(i);
            }
        }

        return results;
    }

    /**
     * 특정 타입이면서 키워드가 포함된 노선 검색
     */
    private List<Integer> searchByTypeAndName(int routeType, String keyword) {
        List<Integer> results = new ArrayList<>();
        int routeCount = transitData.getRouteCount();
        String lowerKeyword = keyword.toLowerCase();

        for (int i = 0; i < routeCount; i++) {
            KoreanRoute route = transitData.getRoute(i);

            // 타입 확인
            if (!matchesType(route.getRouteType(), routeType)) {
                continue;
            }

            // 이름 확인
            String shortName = route.getRouteShortName();
            if (shortName != null && shortName.toLowerCase().contains(lowerKeyword)) {
                results.add(i);
            }
        }

        return results;
    }

    /**
     * 노선 타입 매칭 (GTFS route_type 범위 고려)
     */
    private boolean matchesType(int actualType, int expectedType) {
        switch (expectedType) {
            case TYPE_SUBWAY:
                return actualType == 1 || (actualType >= 400 && actualType < 500);
            case TYPE_BUS:
                return actualType == 3 || (actualType >= 700 && actualType < 800);
            case TYPE_RAIL:
                return actualType == 2 || (actualType >= 100 && actualType < 200);
            case TYPE_TRAM:
                return actualType == 0;
            default:
                return actualType == expectedType;
        }
    }

    /**
     * 검색 결과 정보 가져오기
     */
    public SearchResult getSearchResult(String pattern) {
        List<Integer> routeIndices = search(pattern);
        return new SearchResult(pattern, routeIndices, transitData);
    }

    /**
     * 검색 결과를 담는 클래스
     */
    public static class SearchResult {
        private final String pattern;
        private final List<Integer> routeIndices;
        private final TransitData transitData;
        private int totalTrips = -1;

        public SearchResult(String pattern, List<Integer> routeIndices, TransitData transitData) {
            this.pattern = pattern;
            this.routeIndices = routeIndices;
            this.transitData = transitData;
        }

        public String getPattern() {
            return pattern;
        }

        public List<Integer> getRouteIndices() {
            return routeIndices;
        }

        public int getRouteCount() {
            return routeIndices.size();
        }

        public int getTotalTrips() {
            if (totalTrips < 0) {
                totalTrips = 0;
                for (int idx : routeIndices) {
                    totalTrips += transitData.getRoute(idx).getTripCount();
                }
            }
            return totalTrips;
        }

        public boolean isEmpty() {
            return routeIndices.isEmpty();
        }

        /**
         * 첫 번째 매칭 노선 이름 (미리보기용)
         */
        public String getFirstRouteName() {
            if (routeIndices.isEmpty()) return null;
            return transitData.getRoute(routeIndices.get(0)).getRouteShortName();
        }

        @Override
        public String toString() {
            if (routeIndices.isEmpty()) {
                return String.format("'%s': 매칭 노선 없음", pattern);
            }
            return String.format("'%s': %d개 노선, %d개 트립 (예: %s)",
                pattern, getRouteCount(), getTotalTrips(), getFirstRouteName());
        }
    }
}
