package kr.otp.osm;

/**
 * 도로망 엣지 (도로 세그먼트)
 */
public class StreetEdge {

    private final StreetNode fromNode;
    private final StreetNode toNode;
    private final double lengthMeters;   // 도로 길이 (미터)
    private final String roadType;       // 도로 유형 (footway, pedestrian, residential 등)

    public StreetEdge(StreetNode fromNode, StreetNode toNode, double lengthMeters, String roadType) {
        this.fromNode = fromNode;
        this.toNode = toNode;
        this.lengthMeters = lengthMeters;
        this.roadType = roadType;
    }

    public StreetNode getFromNode() {
        return fromNode;
    }

    public StreetNode getToNode() {
        return toNode;
    }

    public double getLengthMeters() {
        return lengthMeters;
    }

    public String getRoadType() {
        return roadType;
    }

    /**
     * 도보 이동 시간 (초)
     * 도로 유형별 속도 조정
     */
    public double getWalkTimeSeconds() {
        double speedMps = getWalkSpeedMps();
        return lengthMeters / speedMps;
    }

    /**
     * 도로 유형별 도보 속도 (m/s)
     */
    private double getWalkSpeedMps() {
        if (roadType == null) {
            return 1.2;  // 기본 속도
        }

        return switch (roadType) {
            case "footway", "pedestrian", "path" -> 1.3;      // 보행자 전용
            case "steps" -> 0.6;                               // 계단
            case "cycleway" -> 1.2;                            // 자전거도로
            case "residential", "living_street" -> 1.2;       // 주거지역
            case "tertiary", "secondary" -> 1.1;              // 일반 도로
            case "primary", "trunk" -> 1.0;                   // 큰 도로 (횡단 등 고려)
            default -> 1.2;
        };
    }

    @Override
    public String toString() {
        return String.format("Edge[%d→%d, %.1fm, %s]",
            fromNode.getOsmId(), toNode.getOsmId(), lengthMeters, roadType);
    }
}
