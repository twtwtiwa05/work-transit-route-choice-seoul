package kr.otp.gtfs;

import kr.otp.gtfs.model.GtfsRoute;
import kr.otp.gtfs.model.GtfsStop;
import kr.otp.gtfs.model.GtfsStopTime;
import kr.otp.gtfs.model.GtfsTrip;

import java.util.*;

/**
 * 모든 GTFS 데이터를 담는 컨테이너 클래스.
 *
 * 효율적인 조회를 위해 다양한 인덱스를 제공:
 * - stopId → GtfsStop
 * - routeId → GtfsRoute
 * - tripId → GtfsTrip
 * - tripId → List<GtfsStopTime> (시간순 정렬됨)
 *
 * 불변 객체로 설계되어 thread-safe.
 */
public class GtfsBundle {

    private final Map<String, GtfsStop> stopsById;
    private final Map<String, GtfsRoute> routesById;
    private final Map<String, GtfsTrip> tripsById;
    private final Map<String, List<GtfsStopTime>> stopTimesByTripId;

    // 추가 인덱스
    private final Map<String, List<GtfsTrip>> tripsByRouteId;

    // 통계
    private final int stopCount;
    private final int routeCount;
    private final int tripCount;
    private final int stopTimeCount;

    private GtfsBundle(Builder builder) {
        this.stopsById = Map.copyOf(builder.stopsById);
        this.routesById = Map.copyOf(builder.routesById);
        this.tripsById = Map.copyOf(builder.tripsById);

        // stopTimes를 tripId별로 그룹화하고 stop_sequence로 정렬
        Map<String, List<GtfsStopTime>> sortedStopTimes = new HashMap<>();
        for (Map.Entry<String, List<GtfsStopTime>> entry : builder.stopTimesByTripId.entrySet()) {
            List<GtfsStopTime> sorted = new ArrayList<>(entry.getValue());
            sorted.sort(Comparator.comparingInt(GtfsStopTime::stopSequence));
            sortedStopTimes.put(entry.getKey(), List.copyOf(sorted));
        }
        this.stopTimesByTripId = Map.copyOf(sortedStopTimes);

        // tripsByRouteId 인덱스 생성
        Map<String, List<GtfsTrip>> tripsByRoute = new HashMap<>();
        for (GtfsTrip trip : tripsById.values()) {
            tripsByRoute.computeIfAbsent(trip.routeId(), k -> new ArrayList<>()).add(trip);
        }
        // 불변 리스트로 변환
        Map<String, List<GtfsTrip>> immutableTripsByRoute = new HashMap<>();
        for (Map.Entry<String, List<GtfsTrip>> entry : tripsByRoute.entrySet()) {
            immutableTripsByRoute.put(entry.getKey(), List.copyOf(entry.getValue()));
        }
        this.tripsByRouteId = Map.copyOf(immutableTripsByRoute);

        // 통계
        this.stopCount = stopsById.size();
        this.routeCount = routesById.size();
        this.tripCount = tripsById.size();
        this.stopTimeCount = stopTimesByTripId.values().stream()
            .mapToInt(List::size)
            .sum();
    }

    // ═══════════════════════════════════════════════════════════════
    // 조회 메서드
    // ═══════════════════════════════════════════════════════════════

    public GtfsStop getStop(String stopId) {
        return stopsById.get(stopId);
    }

    public GtfsRoute getRoute(String routeId) {
        return routesById.get(routeId);
    }

    public GtfsTrip getTrip(String tripId) {
        return tripsById.get(tripId);
    }

    public List<GtfsStopTime> getStopTimes(String tripId) {
        return stopTimesByTripId.getOrDefault(tripId, List.of());
    }

    public List<GtfsTrip> getTripsByRoute(String routeId) {
        return tripsByRouteId.getOrDefault(routeId, List.of());
    }

    public GtfsRoute getRouteForTrip(String tripId) {
        GtfsTrip trip = tripsById.get(tripId);
        return trip != null ? routesById.get(trip.routeId()) : null;
    }

    // ═══════════════════════════════════════════════════════════════
    // 컬렉션 접근
    // ═══════════════════════════════════════════════════════════════

    public Collection<GtfsStop> getAllStops() {
        return stopsById.values();
    }

    public Collection<GtfsRoute> getAllRoutes() {
        return routesById.values();
    }

    public Collection<GtfsTrip> getAllTrips() {
        return tripsById.values();
    }

    public Set<String> getAllStopIds() {
        return stopsById.keySet();
    }

    public Set<String> getAllRouteIds() {
        return routesById.keySet();
    }

    public Set<String> getAllTripIds() {
        return tripsById.keySet();
    }

    // ═══════════════════════════════════════════════════════════════
    // 통계
    // ═══════════════════════════════════════════════════════════════

    public int getStopCount() {
        return stopCount;
    }

    public int getRouteCount() {
        return routeCount;
    }

    public int getTripCount() {
        return tripCount;
    }

    public int getStopTimeCount() {
        return stopTimeCount;
    }

    /**
     * 서비스 시작 시간 (가장 이른 출발 시간)
     *
     * @return 초 단위 시간 (예: 04:00 = 14400)
     */
    public int getServiceStartTime() {
        return stopTimesByTripId.values().stream()
            .flatMap(List::stream)
            .mapToInt(GtfsStopTime::departureTime)
            .filter(t -> t >= 0)
            .min()
            .orElse(4 * 3600); // 기본값: 04:00
    }

    /**
     * 서비스 종료 시간 (가장 늦은 도착 시간)
     *
     * @return 초 단위 시간 (예: 26:00 = 93600)
     */
    public int getServiceEndTime() {
        return stopTimesByTripId.values().stream()
            .flatMap(List::stream)
            .mapToInt(GtfsStopTime::arrivalTime)
            .filter(t -> t >= 0)
            .max()
            .orElse(26 * 3600); // 기본값: 26:00
    }

    @Override
    public String toString() {
        return String.format(
            "GtfsBundle[stops=%,d, routes=%,d, trips=%,d, stopTimes=%,d]",
            stopCount, routeCount, tripCount, stopTimeCount
        );
    }

    // ═══════════════════════════════════════════════════════════════
    // Builder
    // ═══════════════════════════════════════════════════════════════

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private final Map<String, GtfsStop> stopsById = new HashMap<>();
        private final Map<String, GtfsRoute> routesById = new HashMap<>();
        private final Map<String, GtfsTrip> tripsById = new HashMap<>();
        private final Map<String, List<GtfsStopTime>> stopTimesByTripId = new HashMap<>();

        public Builder addStop(GtfsStop stop) {
            stopsById.put(stop.stopId(), stop);
            return this;
        }

        public Builder addRoute(GtfsRoute route) {
            routesById.put(route.routeId(), route);
            return this;
        }

        public Builder addTrip(GtfsTrip trip) {
            tripsById.put(trip.tripId(), trip);
            return this;
        }

        public Builder addStopTime(GtfsStopTime stopTime) {
            stopTimesByTripId
                .computeIfAbsent(stopTime.tripId(), k -> new ArrayList<>())
                .add(stopTime);
            return this;
        }

        public GtfsBundle build() {
            return new GtfsBundle(this);
        }
    }
}
