package kr.otp.osm;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

/**
 * 도로망 그래프
 * - 노드: 교차점, 도로 끝점
 * - 엣지: 도로 세그먼트
 * - 공간 인덱스: 가까운 노드 검색용
 */
public class StreetNetwork {

    private static final Logger LOG = LoggerFactory.getLogger(StreetNetwork.class);

    // 노드 저장 (OSM ID → Node)
    private final Map<Long, StreetNode> nodes = new HashMap<>();

    // 공간 인덱스 (격자 기반)
    private static final double GRID_SIZE = 0.001;  // 약 100m
    private final Map<String, List<StreetNode>> spatialIndex = new HashMap<>();

    // 통계
    private int edgeCount = 0;

    public void addNode(StreetNode node) {
        nodes.put(node.getOsmId(), node);

        // 공간 인덱스에 추가
        String gridKey = getGridKey(node.getLat(), node.getLon());
        spatialIndex.computeIfAbsent(gridKey, k -> new ArrayList<>()).add(node);
    }

    public StreetNode getNode(long osmId) {
        return nodes.get(osmId);
    }

    public StreetNode getOrCreateNode(long osmId, double lat, double lon) {
        return nodes.computeIfAbsent(osmId, id -> {
            StreetNode node = new StreetNode(id, lat, lon);
            // 공간 인덱스에 추가
            String gridKey = getGridKey(lat, lon);
            spatialIndex.computeIfAbsent(gridKey, k -> new ArrayList<>()).add(node);
            return node;
        });
    }

    public void addEdge(StreetEdge edge) {
        edge.getFromNode().addEdge(edge);
        edgeCount++;
    }

    /**
     * 주어진 좌표에서 가장 가까운 노드 찾기
     */
    public StreetNode findNearestNode(double lat, double lon, double maxDistanceMeters) {
        StreetNode nearest = null;
        double minDistance = Double.MAX_VALUE;

        // 주변 그리드 셀 검색
        int gridRadius = (int) Math.ceil(maxDistanceMeters / 111000.0 / GRID_SIZE) + 1;

        String centerKey = getGridKey(lat, lon);
        String[] parts = centerKey.split(",");
        int centerX = Integer.parseInt(parts[0]);
        int centerY = Integer.parseInt(parts[1]);

        for (int dx = -gridRadius; dx <= gridRadius; dx++) {
            for (int dy = -gridRadius; dy <= gridRadius; dy++) {
                String key = (centerX + dx) + "," + (centerY + dy);
                List<StreetNode> cellNodes = spatialIndex.get(key);

                if (cellNodes != null) {
                    for (StreetNode node : cellNodes) {
                        double dist = haversineDistance(lat, lon, node.getLat(), node.getLon());
                        if (dist < minDistance && dist <= maxDistanceMeters) {
                            minDistance = dist;
                            nearest = node;
                        }
                    }
                }
            }
        }

        return nearest;
    }

    /**
     * 주어진 좌표 근처의 모든 노드 찾기
     */
    public List<StreetNode> findNearbyNodes(double lat, double lon, double maxDistanceMeters) {
        List<NodeDistance> candidates = new ArrayList<>();

        int gridRadius = (int) Math.ceil(maxDistanceMeters / 111000.0 / GRID_SIZE) + 1;

        String centerKey = getGridKey(lat, lon);
        String[] parts = centerKey.split(",");
        int centerX = Integer.parseInt(parts[0]);
        int centerY = Integer.parseInt(parts[1]);

        for (int dx = -gridRadius; dx <= gridRadius; dx++) {
            for (int dy = -gridRadius; dy <= gridRadius; dy++) {
                String key = (centerX + dx) + "," + (centerY + dy);
                List<StreetNode> cellNodes = spatialIndex.get(key);

                if (cellNodes != null) {
                    for (StreetNode node : cellNodes) {
                        double dist = haversineDistance(lat, lon, node.getLat(), node.getLon());
                        if (dist <= maxDistanceMeters) {
                            candidates.add(new NodeDistance(node, dist));
                        }
                    }
                }
            }
        }

        // 거리순 정렬
        candidates.sort(Comparator.comparingDouble(nd -> nd.distance));

        return candidates.stream().map(nd -> nd.node).toList();
    }

    /**
     * 모든 노드의 검색 상태 초기화 (A* 검색 전)
     */
    public void resetSearchStates() {
        for (StreetNode node : nodes.values()) {
            node.resetSearchState();
        }
    }

    /**
     * 격자 키 생성
     */
    private String getGridKey(double lat, double lon) {
        int x = (int) Math.floor(lat / GRID_SIZE);
        int y = (int) Math.floor(lon / GRID_SIZE);
        return x + "," + y;
    }

    /**
     * Haversine 거리 계산 (미터)
     */
    public static double haversineDistance(double lat1, double lon1, double lat2, double lon2) {
        final double R = 6_371_000; // 지구 반지름 (미터)

        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);

        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                 + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                 * Math.sin(dLon / 2) * Math.sin(dLon / 2);

        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        return R * c;
    }

    public int getNodeCount() {
        return nodes.size();
    }

    public int getEdgeCount() {
        return edgeCount;
    }

    public Collection<StreetNode> getAllNodes() {
        return nodes.values();
    }

    @Override
    public String toString() {
        return String.format("StreetNetwork[nodes=%d, edges=%d]", nodes.size(), edgeCount);
    }

    private static class NodeDistance {
        final StreetNode node;
        final double distance;

        NodeDistance(StreetNode node, double distance) {
            this.node = node;
            this.distance = distance;
        }
    }
}
