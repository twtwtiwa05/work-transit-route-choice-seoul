package kr.otp.osm;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

/**
 * A* 알고리즘 기반 도보 경로 탐색기
 */
public class WalkingRouter {

    private static final Logger LOG = LoggerFactory.getLogger(WalkingRouter.class);

    private static final double WALK_SPEED_MPS = 1.2;  // 도보 속도 (m/s)
    private static final double MAX_SEARCH_DISTANCE = 500.0;   // 최대 탐색 거리 (m) - 성능 최적화

    private final StreetNetwork network;

    public WalkingRouter(StreetNetwork network) {
        this.network = network;
    }

    /**
     * 두 좌표 사이의 도보 경로 검색
     *
     * @param fromLat 출발지 위도
     * @param fromLon 출발지 경도
     * @param toLat   도착지 위도
     * @param toLon   도착지 경도
     * @return 도보 경로 결과 (null if not found)
     */
    public WalkingPath findPath(double fromLat, double fromLon, double toLat, double toLon) {
        // 출발지/도착지에서 가장 가까운 노드 찾기
        StreetNode startNode = network.findNearestNode(fromLat, fromLon, 500);
        StreetNode endNode = network.findNearestNode(toLat, toLon, 500);

        if (startNode == null || endNode == null) {
            return null;
        }

        // 출발지/도착지에서 노드까지의 직선 거리
        double startWalkDistance = StreetNetwork.haversineDistance(fromLat, fromLon, startNode.getLat(), startNode.getLon());
        double endWalkDistance = StreetNetwork.haversineDistance(toLat, toLon, endNode.getLat(), endNode.getLon());

        // 같은 노드면 직접 연결
        if (startNode.equals(endNode)) {
            double totalDistance = startWalkDistance + endWalkDistance;
            return new WalkingPath(totalDistance, totalDistance / WALK_SPEED_MPS, List.of(startNode));
        }

        // A* 탐색
        WalkingPath path = aStarSearch(startNode, endNode);

        if (path == null) {
            return null;
        }

        // 출발지/도착지 거리 추가
        double totalDistance = startWalkDistance + path.getDistanceMeters() + endWalkDistance;
        double totalTime = totalDistance / WALK_SPEED_MPS;

        return new WalkingPath(totalDistance, totalTime, path.getNodes());
    }

    /**
     * 좌표에서 정류장까지의 도보 거리 계산
     */
    public double getWalkingDistance(double fromLat, double fromLon, double toLat, double toLon) {
        WalkingPath path = findPath(fromLat, fromLon, toLat, toLon);
        return path != null ? path.getDistanceMeters() : -1;
    }

    /**
     * 도로 노드 간 도보 거리 계산 (사전 계산된 노드 사용)
     * findNearestNode 호출 생략으로 성능 향상
     */
    public double getWalkingDistanceBetweenNodes(StreetNode startNode, StreetNode endNode) {
        if (startNode == null || endNode == null) {
            return -1;
        }
        if (startNode.equals(endNode)) {
            return 0;
        }

        WalkingPath path = aStarSearch(startNode, endNode);
        return path != null ? path.getDistanceMeters() : -1;
    }

    /**
     * A* 알고리즘 (최적화 버전)
     *
     * HashMap 기반 상태 관리 - 15M 노드 초기화 불필요
     */
    private WalkingPath aStarSearch(StreetNode start, StreetNode goal) {
        // HashMap 기반 상태 관리 (노드 초기화 불필요!)
        Map<Long, Double> gScores = new HashMap<>();
        Map<Long, Double> fScores = new HashMap<>();
        Map<Long, StreetNode> parents = new HashMap<>();

        // 우선순위 큐 (f-score 기준)
        PriorityQueue<StreetNode> openSet = new PriorityQueue<>(
            Comparator.comparingDouble(n -> fScores.getOrDefault(n.getOsmId(), Double.MAX_VALUE))
        );

        Set<Long> closedSet = new HashSet<>();

        // 시작 노드 초기화
        gScores.put(start.getOsmId(), 0.0);
        fScores.put(start.getOsmId(), heuristic(start, goal));
        openSet.add(start);

        int iterations = 0;
        int maxIterations = 15000;  // 성능 최적화 (500m 거리 충분)

        while (!openSet.isEmpty() && iterations < maxIterations) {
            iterations++;

            StreetNode current = openSet.poll();
            long currentId = current.getOsmId();

            // 목표 도달
            if (current.equals(goal)) {
                return reconstructPathFromMap(goal, parents, gScores.get(currentId));
            }

            // 이미 처리됨
            if (closedSet.contains(currentId)) {
                continue;
            }
            closedSet.add(currentId);

            double currentGScore = gScores.getOrDefault(currentId, Double.MAX_VALUE);

            // 최대 거리 초과 체크
            if (currentGScore > MAX_SEARCH_DISTANCE) {
                continue;
            }

            // 인접 노드 탐색
            for (StreetEdge edge : current.getOutgoingEdges()) {
                StreetNode neighbor = edge.getToNode();
                long neighborId = neighbor.getOsmId();

                if (closedSet.contains(neighborId)) {
                    continue;
                }

                double tentativeGScore = currentGScore + edge.getLengthMeters();
                double neighborGScore = gScores.getOrDefault(neighborId, Double.MAX_VALUE);

                if (tentativeGScore < neighborGScore) {
                    // 더 좋은 경로 발견
                    parents.put(neighborId, current);
                    gScores.put(neighborId, tentativeGScore);
                    fScores.put(neighborId, tentativeGScore + heuristic(neighbor, goal));
                    openSet.add(neighbor);
                }
            }
        }

        // 경로 없음
        return null;
    }

    /**
     * HashMap 기반 경로 역추적
     */
    private WalkingPath reconstructPathFromMap(StreetNode goal, Map<Long, StreetNode> parents, double totalDistance) {
        List<StreetNode> path = new ArrayList<>();
        StreetNode current = goal;

        while (current != null) {
            path.add(current);
            current = parents.get(current.getOsmId());
        }

        Collections.reverse(path);
        double totalTime = totalDistance / WALK_SPEED_MPS;

        return new WalkingPath(totalDistance, totalTime, path);
    }

    /**
     * 휴리스틱 함수 (직선 거리)
     */
    private double heuristic(StreetNode from, StreetNode to) {
        return StreetNetwork.haversineDistance(
            from.getLat(), from.getLon(),
            to.getLat(), to.getLon()
        );
    }

    /**
     * 경로 역추적
     */
    private WalkingPath reconstructPath(StreetNode goal) {
        List<StreetNode> path = new ArrayList<>();
        StreetNode current = goal;

        while (current != null) {
            path.add(current);
            current = current.getParent();
        }

        Collections.reverse(path);

        // 총 거리 계산
        double totalDistance = 0;
        for (int i = 0; i < path.size() - 1; i++) {
            totalDistance += StreetNetwork.haversineDistance(
                path.get(i).getLat(), path.get(i).getLon(),
                path.get(i + 1).getLat(), path.get(i + 1).getLon()
            );
        }

        double totalTime = totalDistance / WALK_SPEED_MPS;

        return new WalkingPath(totalDistance, totalTime, path);
    }

    /**
     * 도보 경로 결과
     */
    public static class WalkingPath {
        private final double distanceMeters;
        private final double timeSeconds;
        private final List<StreetNode> nodes;

        public WalkingPath(double distanceMeters, double timeSeconds, List<StreetNode> nodes) {
            this.distanceMeters = distanceMeters;
            this.timeSeconds = timeSeconds;
            this.nodes = nodes;
        }

        public double getDistanceMeters() {
            return distanceMeters;
        }

        public double getTimeSeconds() {
            return timeSeconds;
        }

        public List<StreetNode> getNodes() {
            return nodes;
        }

        @Override
        public String toString() {
            return String.format("WalkingPath[%.0fm, %.0f초, %d nodes]",
                distanceMeters, timeSeconds, nodes.size());
        }
    }
}
