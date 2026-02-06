package kr.otp.scenario;

import kr.otp.raptor.data.TransitData;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * 정류장명으로 정류장을 검색하는 유틸리티.
 *
 * 신규 노선 추가 시 정류장 검색에 사용.
 */
public class StopSearcher {

    private final TransitData transitData;

    public StopSearcher(TransitData transitData) {
        this.transitData = transitData;
    }

    /**
     * 이름으로 정류장 검색
     *
     * @param keyword 검색 키워드
     * @param maxResults 최대 결과 수
     * @return 매칭된 정류장 목록
     */
    public List<StopInfo> search(String keyword, int maxResults) {
        List<StopInfo> results = new ArrayList<>();

        if (keyword == null || keyword.isEmpty()) {
            return results;
        }

        String lowerKeyword = keyword.toLowerCase().trim();
        int stopCount = transitData.getStopCount();

        // 1차: 정확히 일치하는 것 먼저
        for (int i = 0; i < stopCount; i++) {
            String name = transitData.getStopName(i);
            if (name != null && name.toLowerCase().equals(lowerKeyword)) {
                results.add(new StopInfo(i, name,
                    transitData.getStopLat(i),
                    transitData.getStopLon(i),
                    MatchType.EXACT));
            }
        }

        // 2차: 시작하는 것
        if (results.size() < maxResults) {
            for (int i = 0; i < stopCount; i++) {
                String name = transitData.getStopName(i);
                if (name != null && name.toLowerCase().startsWith(lowerKeyword)) {
                    StopInfo info = new StopInfo(i, name,
                        transitData.getStopLat(i),
                        transitData.getStopLon(i),
                        MatchType.STARTS_WITH);
                    if (!results.contains(info)) {
                        results.add(info);
                    }
                }
                if (results.size() >= maxResults * 2) break;
            }
        }

        // 3차: 포함하는 것
        if (results.size() < maxResults) {
            for (int i = 0; i < stopCount; i++) {
                String name = transitData.getStopName(i);
                if (name != null && name.toLowerCase().contains(lowerKeyword)) {
                    StopInfo info = new StopInfo(i, name,
                        transitData.getStopLat(i),
                        transitData.getStopLon(i),
                        MatchType.CONTAINS);
                    if (!results.contains(info)) {
                        results.add(info);
                    }
                }
                if (results.size() >= maxResults * 3) break;
            }
        }

        // 정렬: EXACT → STARTS_WITH → CONTAINS, 그 안에서 이름순
        results.sort(Comparator
            .comparing(StopInfo::getMatchType)
            .thenComparing(StopInfo::getName));

        // 최대 결과 수 제한
        if (results.size() > maxResults) {
            return results.subList(0, maxResults);
        }

        return results;
    }

    /**
     * 좌표 근처 정류장 검색
     *
     * @param lat 위도
     * @param lon 경도
     * @param radiusMeters 검색 반경 (미터)
     * @param maxResults 최대 결과 수
     * @return 가까운 순으로 정렬된 정류장 목록
     */
    public List<StopInfo> searchNearby(double lat, double lon, double radiusMeters, int maxResults) {
        List<StopInfo> results = new ArrayList<>();
        int stopCount = transitData.getStopCount();

        // 위도 범위 필터 (대략)
        double latRange = radiusMeters / 111000.0;

        for (int i = 0; i < stopCount; i++) {
            double stopLat = transitData.getStopLat(i);

            if (Math.abs(stopLat - lat) > latRange) {
                continue;
            }

            double stopLon = transitData.getStopLon(i);
            double distance = haversineDistance(lat, lon, stopLat, stopLon);

            if (distance <= radiusMeters) {
                results.add(new StopInfo(i, transitData.getStopName(i),
                    stopLat, stopLon, MatchType.NEARBY, distance));
            }
        }

        // 거리순 정렬
        results.sort(Comparator.comparingDouble(StopInfo::getDistance));

        // 최대 결과 수 제한
        if (results.size() > maxResults) {
            return results.subList(0, maxResults);
        }

        return results;
    }

    /**
     * Haversine 거리 계산 (미터)
     */
    private static double haversineDistance(double lat1, double lon1, double lat2, double lon2) {
        final double R = 6_371_000;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                 + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                 * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    /**
     * 매칭 타입
     */
    public enum MatchType {
        EXACT,      // 정확히 일치
        STARTS_WITH, // 시작 일치
        CONTAINS,   // 포함
        NEARBY      // 좌표 근처
    }

    /**
     * 정류장 정보
     */
    public static class StopInfo {
        private final int stopIndex;
        private final String name;
        private final double lat;
        private final double lon;
        private final MatchType matchType;
        private final double distance;  // NEARBY인 경우만 사용

        public StopInfo(int stopIndex, String name, double lat, double lon, MatchType matchType) {
            this(stopIndex, name, lat, lon, matchType, 0);
        }

        public StopInfo(int stopIndex, String name, double lat, double lon, MatchType matchType, double distance) {
            this.stopIndex = stopIndex;
            this.name = name;
            this.lat = lat;
            this.lon = lon;
            this.matchType = matchType;
            this.distance = distance;
        }

        public int getStopIndex() {
            return stopIndex;
        }

        public String getName() {
            return name;
        }

        public double getLat() {
            return lat;
        }

        public double getLon() {
            return lon;
        }

        public MatchType getMatchType() {
            return matchType;
        }

        public double getDistance() {
            return distance;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (o == null || getClass() != o.getClass()) return false;
            StopInfo stopInfo = (StopInfo) o;
            return stopIndex == stopInfo.stopIndex;
        }

        @Override
        public int hashCode() {
            return stopIndex;
        }

        @Override
        public String toString() {
            if (matchType == MatchType.NEARBY) {
                return String.format("[%d] %s (%.1fm)", stopIndex, name, distance);
            }
            return String.format("[%d] %s", stopIndex, name);
        }
    }
}
