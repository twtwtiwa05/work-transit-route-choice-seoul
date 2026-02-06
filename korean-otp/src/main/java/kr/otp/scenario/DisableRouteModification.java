package kr.otp.scenario;

import kr.otp.raptor.data.TransitData;

import java.util.ArrayList;
import java.util.List;

/**
 * 노선 비활성화 수정.
 *
 * 지정된 노선을 비활성화하여 경로 탐색에서 제외합니다.
 * 파업, 사고, 공사 등의 시나리오에 사용.
 */
public class DisableRouteModification implements Modification {

    private final String routePattern;
    private final List<Integer> affectedRouteIndices;
    private final int affectedTripCount;

    public DisableRouteModification(String routePattern,
                                    List<Integer> affectedRouteIndices,
                                    TransitData transitData) {
        this.routePattern = routePattern;
        this.affectedRouteIndices = new ArrayList<>(affectedRouteIndices);

        // 영향받는 트립 수 계산
        int trips = 0;
        for (int idx : affectedRouteIndices) {
            trips += transitData.getRoute(idx).getTripCount();
        }
        this.affectedTripCount = trips;
    }

    @Override
    public Type getType() {
        return Type.DISABLE_ROUTE;
    }

    @Override
    public String getDescription() {
        return String.format("%s 비활성화 (%d개 노선, %d개 트립)",
            routePattern, affectedRouteIndices.size(), affectedTripCount);
    }

    @Override
    public int getAffectedRouteCount() {
        return affectedRouteIndices.size();
    }

    @Override
    public int getAffectedTripCount() {
        return affectedTripCount;
    }

    public String getRoutePattern() {
        return routePattern;
    }

    public List<Integer> getAffectedRouteIndices() {
        return affectedRouteIndices;
    }

    @Override
    public String toString() {
        return String.format("DisableRouteModification[%s, routes=%d, trips=%d]",
            routePattern, affectedRouteIndices.size(), affectedTripCount);
    }
}
