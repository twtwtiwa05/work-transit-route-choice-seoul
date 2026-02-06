package kr.otp.osm;

import java.util.ArrayList;
import java.util.List;

/**
 * 도로망 노드 (교차점, 도로 끝점)
 */
public class StreetNode {

    private final long osmId;
    private final double lat;
    private final double lon;
    private final List<StreetEdge> outgoingEdges;

    // A* 탐색용 임시 필드
    private double gScore = Double.MAX_VALUE;  // 시작점에서 이 노드까지의 비용
    private double fScore = Double.MAX_VALUE;  // gScore + 휴리스틱
    private StreetNode parent = null;          // 경로 역추적용

    public StreetNode(long osmId, double lat, double lon) {
        this.osmId = osmId;
        this.lat = lat;
        this.lon = lon;
        this.outgoingEdges = new ArrayList<>();
    }

    public void addEdge(StreetEdge edge) {
        outgoingEdges.add(edge);
    }

    public long getOsmId() {
        return osmId;
    }

    public double getLat() {
        return lat;
    }

    public double getLon() {
        return lon;
    }

    public List<StreetEdge> getOutgoingEdges() {
        return outgoingEdges;
    }

    // A* 관련 메서드
    public double getGScore() {
        return gScore;
    }

    public void setGScore(double gScore) {
        this.gScore = gScore;
    }

    public double getFScore() {
        return fScore;
    }

    public void setFScore(double fScore) {
        this.fScore = fScore;
    }

    public StreetNode getParent() {
        return parent;
    }

    public void setParent(StreetNode parent) {
        this.parent = parent;
    }

    public void resetSearchState() {
        this.gScore = Double.MAX_VALUE;
        this.fScore = Double.MAX_VALUE;
        this.parent = null;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(osmId);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (obj == null || getClass() != obj.getClass()) return false;
        StreetNode other = (StreetNode) obj;
        return osmId == other.osmId;
    }

    @Override
    public String toString() {
        return String.format("Node[%d](%.6f, %.6f)", osmId, lat, lon);
    }
}
