package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.RaptorAccessEgress;

/**
 * 한국 대중교통용 접근/이탈 경로.
 *
 * Access: 출발지 → 첫 번째 정류장 (도보)
 * Egress: 마지막 정류장 → 목적지 (도보)
 *
 * Raptor는 Access와 Egress를 동일하게 취급함.
 */
public class KoreanAccessEgress implements RaptorAccessEgress {

    private final int stopIndex;          // 정류장 인덱스
    private final int durationSeconds;    // 소요 시간 (초)
    private final int cost;               // 비용 (centi-seconds)
    private final double distanceMeters;  // 거리 (미터)

    public KoreanAccessEgress(int stopIndex, int durationSeconds, double distanceMeters) {
        this(stopIndex, durationSeconds, distanceMeters, 1.0);
    }

    public KoreanAccessEgress(int stopIndex, int durationSeconds, double distanceMeters, double walkReluctance) {
        this.stopIndex = stopIndex;
        this.durationSeconds = durationSeconds;
        this.distanceMeters = distanceMeters;
        // 비용 = 시간(초) * 100 * walkReluctance (centi-seconds 단위)
        this.cost = (int) (durationSeconds * 100 * walkReluctance);
    }

    /**
     * 직선 거리 기반 Access/Egress 생성 (도보 속도 1.2 m/s 가정)
     */
    public static KoreanAccessEgress fromDistance(int stopIndex, double distanceMeters) {
        return fromDistance(stopIndex, distanceMeters, 1.0);
    }

    public static KoreanAccessEgress fromDistance(int stopIndex, double distanceMeters, double walkReluctance) {
        int duration = (int) Math.ceil(distanceMeters / 1.2);  // 1.2 m/s
        return new KoreanAccessEgress(stopIndex, duration, distanceMeters, walkReluctance);
    }

    @Override
    public int stop() {
        return stopIndex;
    }

    @Override
    public int c1() {
        return cost;
    }

    @Override
    public int durationInSeconds() {
        return durationSeconds;
    }

    @Override
    public int earliestDepartureTime(int requestedDepartureTime) {
        return requestedDepartureTime;
    }

    @Override
    public int latestArrivalTime(int requestedArrivalTime) {
        return requestedArrivalTime;
    }

    @Override
    public boolean hasOpeningHours() {
        return false;
    }

    /**
     * 거리 정보 반환 (결과 출력용)
     */
    public double getDistanceMeters() {
        return distanceMeters;
    }

    @Override
    public String toString() {
        return String.format("Access/Egress[stop=%d, %ds, %.0fm]",
            stopIndex, durationSeconds, distanceMeters);
    }
}
