package kr.otp.core;

import kr.otp.osm.StreetNetwork;
import kr.otp.osm.StreetNode;
import kr.otp.osm.WalkingRouter;
import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanAccessEgress;

import org.opentripplanner.raptor.api.model.RaptorAccessEgress;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/**
 * 좌표에서 가까운 정류장을 찾아 Access/Egress 경로를 생성.
 *
 * Access: 출발지 좌표 → 근처 정류장들 (도보)
 * Egress: 근처 정류장들 → 목적지 좌표 (도보)
 *
 * OSM 데이터가 있으면 실제 도보 경로 거리 사용,
 * 없으면 직선 거리(Haversine) 사용.
 */
public class AccessEgressFinder {

    private static final Logger LOG = LoggerFactory.getLogger(AccessEgressFinder.class);

    private static final double WALK_SPEED_MPS = 1.2;  // 도보 속도 (m/s)
    private static final int MAX_STOPS = 30;           // 최대 검색 정류장 수 (지하철역 포함 위해 증가)

    private final TransitData transitData;
    private final double walkReluctance;

    // 정류장 좌표 캐시
    private final double[] stopLats;
    private final double[] stopLons;
    private final int stopCount;

    // OSM 기반 도보 경로 (선택적)
    private WalkingRouter walkingRouter;
    private StreetNetwork streetNetwork;
    private boolean useOsm = false;

    // 정류장별 가장 가까운 도로 노드 (사전 계산)
    private StreetNode[] stopNearestNodes;

    // 병렬 A* 실행용 스레드 풀
    private ExecutorService executor;

    public AccessEgressFinder(TransitData transitData) {
        this(transitData, 1.0);
    }

    public AccessEgressFinder(TransitData transitData, double walkReluctance) {
        this.transitData = transitData;
        this.walkReluctance = walkReluctance;
        this.stopCount = transitData.getStopCount();

        // 좌표 캐시 (성능 최적화)
        this.stopLats = new double[stopCount];
        this.stopLons = new double[stopCount];

        for (int i = 0; i < stopCount; i++) {
            this.stopLats[i] = transitData.getStopLat(i);
            this.stopLons[i] = transitData.getStopLon(i);
        }
    }

    /**
     * OSM 도로망 설정 (실제 도보 거리 계산 활성화)
     */
    public void setStreetNetwork(StreetNetwork streetNetwork) {
        if (streetNetwork != null) {
            this.streetNetwork = streetNetwork;
            this.walkingRouter = new WalkingRouter(streetNetwork);
            this.useOsm = true;

            // 병렬 A* 스레드 풀 초기화 (CPU 코어 수만큼)
            int cores = Runtime.getRuntime().availableProcessors();
            this.executor = Executors.newFixedThreadPool(cores);
            LOG.info("병렬 A* 스레드 풀: {}개 코어", cores);

            // 정류장별 가장 가까운 도로 노드 사전 계산 (성능 최적화)
            LOG.info("정류장-도로노드 매핑 계산 중...");
            long start = System.currentTimeMillis();
            precomputeStopNearestNodes();
            long elapsed = System.currentTimeMillis() - start;
            LOG.info("OSM 기반 도보 거리 계산 활성화 (매핑: {}ms)", elapsed);
        }
    }

    /**
     * 정류장별 가장 가까운 도로 노드 사전 계산
     */
    private void precomputeStopNearestNodes() {
        stopNearestNodes = new StreetNode[stopCount];
        int mapped = 0;

        for (int i = 0; i < stopCount; i++) {
            StreetNode node = streetNetwork.findNearestNode(stopLats[i], stopLons[i], 300);
            stopNearestNodes[i] = node;
            if (node != null) mapped++;
        }

        LOG.info("  정류장 {}개 중 {}개 도로망 연결", stopCount, mapped);
    }

    /**
     * OSM 사용 여부
     */
    public boolean isUsingOsm() {
        return useOsm;
    }

    /**
     * 출발지 근처 정류장 찾기 (Access)
     *
     * @param lat 출발지 위도
     * @param lon 출발지 경도
     * @param maxDistanceMeters 최대 도보 거리 (미터)
     * @return Access 경로 목록 (가까운 순)
     */
    public List<RaptorAccessEgress> findAccess(double lat, double lon, double maxDistanceMeters) {
        return findNearbyStops(lat, lon, maxDistanceMeters);
    }

    /**
     * 목적지 근처 정류장 찾기 (Egress)
     *
     * @param lat 목적지 위도
     * @param lon 목적지 경도
     * @param maxDistanceMeters 최대 도보 거리 (미터)
     * @return Egress 경로 목록 (가까운 순)
     */
    public List<RaptorAccessEgress> findEgress(double lat, double lon, double maxDistanceMeters) {
        return findNearbyStops(lat, lon, maxDistanceMeters);
    }

    /**
     * 주어진 좌표에서 가까운 정류장 찾기
     *
     * OSM 모드: 직선 거리로 상위 후보만 선별 후 A* 계산 (성능 최적화)
     */
    private List<RaptorAccessEgress> findNearbyStops(double lat, double lon, double maxDistanceMeters) {
        List<StopDistance> candidates = new ArrayList<>();

        // 위도 범위 필터링 (대략적인 필터) - 직선거리 기준으로 먼저 필터링
        double latDiff = maxDistanceMeters / 111000.0;  // 약 111km per degree

        // 1단계: 직선 거리로 모든 후보 수집
        for (int i = 0; i < stopCount; i++) {
            double stopLat = stopLats[i];

            // 위도 범위 체크 (빠른 필터링)
            if (Math.abs(stopLat - lat) > latDiff) {
                continue;
            }

            double stopLon = stopLons[i];

            // 직선 거리 계산
            double straightDistance = haversineDistance(lat, lon, stopLat, stopLon);
            if (straightDistance <= maxDistanceMeters * 1.5) {  // 여유있게 필터링
                candidates.add(new StopDistance(i, straightDistance, straightDistance));
            }
        }

        // 직선 거리순 정렬
        candidates.sort(Comparator.comparingDouble(s -> s.straightDistance));

        // 2단계: OSM 모드면 상위 후보만 A* 계산 (성능 최적화)
        List<RaptorAccessEgress> result = new ArrayList<>();

        if (useOsm) {
            // 출발지/목적지 도로 노드 한 번만 검색
            StreetNode originNode = streetNetwork.findNearestNode(lat, lon, 300);

            if (originNode == null) {
                // 도로망에 연결 안됨 - 직선 거리 × 1.3 사용
                int count = Math.min(candidates.size(), MAX_STOPS);
                for (int i = 0; i < count; i++) {
                    StopDistance sd = candidates.get(i);
                    double walkDistance = sd.straightDistance * 1.3;
                    if (walkDistance <= maxDistanceMeters) {
                        int durationSeconds = (int) Math.ceil(walkDistance / WALK_SPEED_MPS);
                        result.add(new KoreanAccessEgress(sd.stopIndex, durationSeconds, walkDistance, walkReluctance));
                    }
                }
                return result;
            }

            // 상위 50개 후보만 A* 계산 (병렬 실행) - 도보 거리 800m 대응
            int osmCandidateLimit = Math.min(candidates.size(), 50);
            final StreetNode origin = originNode;
            final double maxDist = maxDistanceMeters;
            final double originLat = lat;
            final double originLon = lon;

            // 병렬 A* 작업 제출
            List<Future<StopDistance>> futures = new ArrayList<>();
            for (int i = 0; i < osmCandidateLimit; i++) {
                final StopDistance sd = candidates.get(i);
                futures.add(executor.submit(() -> {
                    StreetNode stopNode = stopNearestNodes[sd.stopIndex];

                    double walkDistance;
                    if (stopNode == null) {
                        walkDistance = sd.straightDistance * 1.3;
                    } else if (origin.equals(stopNode)) {
                        walkDistance = sd.straightDistance;
                    } else {
                        walkDistance = walkingRouter.getWalkingDistanceBetweenNodes(origin, stopNode);
                        if (walkDistance < 0) {
                            walkDistance = sd.straightDistance * 1.3;
                        } else {
                            double originToNode = StreetNetwork.haversineDistance(originLat, originLon, origin.getLat(), origin.getLon());
                            double stopNodeToStop = StreetNetwork.haversineDistance(stopNode.getLat(), stopNode.getLon(), stopLats[sd.stopIndex], stopLons[sd.stopIndex]);
                            walkDistance += originToNode + stopNodeToStop;
                        }
                    }

                    if (walkDistance <= maxDist) {
                        return new StopDistance(sd.stopIndex, walkDistance, sd.straightDistance);
                    }
                    return null;
                }));
            }

            // 결과 수집
            List<StopDistance> osmCalculated = new ArrayList<>();
            for (Future<StopDistance> future : futures) {
                try {
                    StopDistance sd = future.get(2000, TimeUnit.MILLISECONDS);
                    if (sd != null) {
                        osmCalculated.add(sd);
                    }
                } catch (Exception e) {
                    // 타임아웃 또는 오류 - 무시
                }
            }

            // 실제 도보 거리순 정렬
            osmCalculated.sort(Comparator.comparingDouble(s -> s.walkDistance));

            int count = Math.min(osmCalculated.size(), MAX_STOPS);
            for (int i = 0; i < count; i++) {
                StopDistance sd = osmCalculated.get(i);
                int durationSeconds = (int) Math.ceil(sd.walkDistance / WALK_SPEED_MPS);
                result.add(new KoreanAccessEgress(sd.stopIndex, durationSeconds, sd.walkDistance, walkReluctance));
            }
        } else {
            // 직선 거리 모드 - 바로 반환
            int count = Math.min(candidates.size(), MAX_STOPS);
            for (int i = 0; i < count; i++) {
                StopDistance sd = candidates.get(i);
                if (sd.straightDistance <= maxDistanceMeters) {
                    int durationSeconds = (int) Math.ceil(sd.straightDistance / WALK_SPEED_MPS);
                    result.add(new KoreanAccessEgress(sd.stopIndex, durationSeconds, sd.straightDistance, walkReluctance));
                }
            }
        }

        return result;
    }

    /**
     * 정류장 인덱스로 이름 조회
     */
    public String getStopName(int stopIndex) {
        return transitData.getStopName(stopIndex);
    }

    /**
     * Haversine 거리 계산 (미터)
     */
    private static double haversineDistance(double lat1, double lon1, double lat2, double lon2) {
        final double R = 6_371_000; // 지구 반지름 (미터)

        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);

        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                 + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                 * Math.sin(dLon / 2) * Math.sin(dLon / 2);

        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c;
    }

    /**
     * 정류장-거리 쌍
     */
    private static class StopDistance {
        final int stopIndex;
        final double walkDistance;      // 도보 거리 (OSM 또는 직선)
        final double straightDistance;  // 직선 거리 (참고용)

        StopDistance(int stopIndex, double walkDistance, double straightDistance) {
            this.stopIndex = stopIndex;
            this.walkDistance = walkDistance;
            this.straightDistance = straightDistance;
        }
    }
}
