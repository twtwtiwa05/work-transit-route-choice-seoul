package kr.otp.osm;

import de.topobyte.osm4j.core.access.OsmIterator;
import de.topobyte.osm4j.core.model.iface.*;
import de.topobyte.osm4j.core.model.util.OsmModelUtil;
import de.topobyte.osm4j.pbf.seq.PbfIterator;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.*;

/**
 * OSM PBF 파일 로더
 * 도보 가능한 도로망만 추출
 */
public class OsmLoader {

    private static final Logger LOG = LoggerFactory.getLogger(OsmLoader.class);

    // 도보 가능한 도로 유형
    private static final Set<String> WALKABLE_HIGHWAYS = Set.of(
        "footway",      // 보행자 전용
        "pedestrian",   // 보행자 구역
        "path",         // 오솔길
        "steps",        // 계단
        "cycleway",     // 자전거도로 (보행 가능)
        "residential",  // 주거지역
        "living_street",// 생활도로
        "tertiary",     // 3차 도로
        "secondary",    // 2차 도로
        "primary",      // 1차 도로
        "trunk",        // 간선도로
        "unclassified", // 분류되지 않은 도로
        "service",      // 서비스 도로
        "track"         // 비포장 도로
    );

    // 도보 불가능한 태그
    private static final Set<String> NO_WALK_ACCESS = Set.of("no", "private");

    private final Path osmPath;

    // 임시 저장 (2-pass 로딩)
    private final Map<Long, double[]> nodeCoords = new HashMap<>();  // nodeId → [lat, lon]
    private final List<WayData> walkableWays = new ArrayList<>();

    public OsmLoader(Path osmPath) {
        this.osmPath = osmPath;
    }

    /**
     * OSM 데이터 로드 및 도로망 구축
     */
    public StreetNetwork load() throws IOException {
        LOG.info("OSM 데이터 로드 시작: {}", osmPath);
        long startTime = System.currentTimeMillis();

        // Pass 1: Way에서 사용하는 노드 ID 수집 + 도보 가능한 Way 저장
        LOG.info("  Pass 1: Way 분석 중...");
        Set<Long> neededNodeIds = new HashSet<>();
        collectWaysAndNodeIds(neededNodeIds);
        LOG.info("    도보 가능 Way: {}개, 필요 노드: {}개", walkableWays.size(), neededNodeIds.size());

        // Pass 2: 필요한 노드의 좌표 수집
        LOG.info("  Pass 2: 노드 좌표 수집 중...");
        collectNodeCoordinates(neededNodeIds);
        LOG.info("    좌표 수집 완료: {}개", nodeCoords.size());

        // 도로망 구축
        LOG.info("  도로망 구축 중...");
        StreetNetwork network = buildNetwork();

        long elapsed = System.currentTimeMillis() - startTime;
        LOG.info("OSM 로드 완료: {} ({}ms)", network, elapsed);

        // 메모리 정리
        nodeCoords.clear();
        walkableWays.clear();

        return network;
    }

    /**
     * Pass 1: 도보 가능한 Way와 노드 ID 수집
     */
    private void collectWaysAndNodeIds(Set<Long> neededNodeIds) throws IOException {
        try (InputStream input = new FileInputStream(osmPath.toFile())) {
            OsmIterator iterator = new PbfIterator(input, true);

            for (EntityContainer container : iterator) {
                if (container.getType() == EntityType.Way) {
                    OsmWay way = (OsmWay) container.getEntity();

                    if (isWalkable(way)) {
                        // 노드 ID 목록 추출
                        long[] nodeIds = new long[way.getNumberOfNodes()];
                        for (int i = 0; i < way.getNumberOfNodes(); i++) {
                            nodeIds[i] = way.getNodeId(i);
                            neededNodeIds.add(nodeIds[i]);
                        }

                        // Way 정보 저장
                        Map<String, String> tags = OsmModelUtil.getTagsAsMap(way);
                        String highway = tags.get("highway");
                        boolean oneway = "yes".equals(tags.get("oneway"));

                        walkableWays.add(new WayData(way.getId(), nodeIds, highway, oneway));
                    }
                }
            }
        }
    }

    /**
     * Pass 2: 필요한 노드의 좌표 수집
     */
    private void collectNodeCoordinates(Set<Long> neededNodeIds) throws IOException {
        try (InputStream input = new FileInputStream(osmPath.toFile())) {
            OsmIterator iterator = new PbfIterator(input, true);

            for (EntityContainer container : iterator) {
                if (container.getType() == EntityType.Node) {
                    OsmNode node = (OsmNode) container.getEntity();

                    if (neededNodeIds.contains(node.getId())) {
                        nodeCoords.put(node.getId(), new double[]{node.getLatitude(), node.getLongitude()});
                    }
                }
            }
        }
    }

    /**
     * 도로망 구축
     */
    private StreetNetwork buildNetwork() {
        StreetNetwork network = new StreetNetwork();

        for (WayData way : walkableWays) {
            // 노드 생성 또는 조회
            StreetNode[] nodes = new StreetNode[way.nodeIds.length];
            boolean valid = true;

            for (int i = 0; i < way.nodeIds.length; i++) {
                double[] coords = nodeCoords.get(way.nodeIds[i]);
                if (coords == null) {
                    valid = false;
                    break;
                }
                nodes[i] = network.getOrCreateNode(way.nodeIds[i], coords[0], coords[1]);
            }

            if (!valid) continue;

            // 엣지 생성
            for (int i = 0; i < nodes.length - 1; i++) {
                StreetNode from = nodes[i];
                StreetNode to = nodes[i + 1];

                double distance = StreetNetwork.haversineDistance(
                    from.getLat(), from.getLon(),
                    to.getLat(), to.getLon()
                );

                // 정방향 엣지
                network.addEdge(new StreetEdge(from, to, distance, way.highway));

                // 역방향 엣지 (일방통행이 아닌 경우)
                if (!way.oneway) {
                    network.addEdge(new StreetEdge(to, from, distance, way.highway));
                }
            }
        }

        return network;
    }

    /**
     * 도보 가능한 도로인지 확인
     */
    private boolean isWalkable(OsmWay way) {
        Map<String, String> tags = OsmModelUtil.getTagsAsMap(way);

        String highway = tags.get("highway");
        if (highway == null || !WALKABLE_HIGHWAYS.contains(highway)) {
            return false;
        }

        // 도보 접근 불가 체크
        String foot = tags.get("foot");
        if (foot != null && NO_WALK_ACCESS.contains(foot)) {
            return false;
        }

        String access = tags.get("access");
        if (access != null && NO_WALK_ACCESS.contains(access)) {
            // foot 태그로 허용된 경우 제외
            if (!"yes".equals(foot) && !"designated".equals(foot)) {
                return false;
            }
        }

        return true;
    }

    /**
     * Way 데이터 임시 저장용
     */
    private static class WayData {
        final long wayId;
        final long[] nodeIds;
        final String highway;
        final boolean oneway;

        WayData(long wayId, long[] nodeIds, String highway, boolean oneway) {
            this.wayId = wayId;
            this.nodeIds = nodeIds;
            this.highway = highway;
            this.oneway = oneway;
        }
    }
}
