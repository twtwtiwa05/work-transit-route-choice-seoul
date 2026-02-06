package kr.otp.raptor.spi;

import org.opentripplanner.raptor.api.model.RaptorTransfer;

/**
 * 한국 대중교통용 환승 정보.
 *
 * 한 정류장에서 다른 정류장으로 도보 환승하는 경로를 나타냄.
 * Raptor 알고리즘에서 정류장 간 환승 가능 여부와 소요 시간을 제공.
 */
public class KoreanTransfer implements RaptorTransfer {

    private final int toStopIndex;        // 도착 정류장 인덱스
    private final int durationSeconds;    // 환승 소요 시간 (초)
    private final int cost;               // 비용 (centi-seconds, 1초 = 100)
    private final double distanceMeters;  // 환승 거리 (미터)

    public KoreanTransfer(int toStopIndex, int durationSeconds, double distanceMeters) {
        this.toStopIndex = toStopIndex;
        this.durationSeconds = durationSeconds;
        this.distanceMeters = distanceMeters;
        // 비용 = 시간(초) * 100 (centi-seconds 단위)
        this.cost = durationSeconds * 100;
    }

    /**
     * 직선 거리 기반 환승 생성 (도보 속도 1.2 m/s 가정)
     */
    public static KoreanTransfer fromDistance(int toStopIndex, double distanceMeters) {
        int duration = (int) Math.ceil(distanceMeters / 1.2);  // 1.2 m/s
        return new KoreanTransfer(toStopIndex, duration, distanceMeters);
    }

    @Override
    public int stop() {
        return toStopIndex;
    }

    @Override
    public int durationInSeconds() {
        return durationSeconds;
    }

    @Override
    public int c1() {
        return cost;
    }

    public double getDistanceMeters() {
        return distanceMeters;
    }

    @Override
    public String toString() {
        return String.format("Transfer[→%d, %ds, %.0fm]",
            toStopIndex, durationSeconds, distanceMeters);
    }
}
