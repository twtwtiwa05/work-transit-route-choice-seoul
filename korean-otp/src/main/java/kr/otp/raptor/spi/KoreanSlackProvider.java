package kr.otp.raptor.spi;

import org.opentripplanner.raptor.spi.RaptorSlackProvider;

/**
 * 한국 대중교통용 슬랙(여유시간) 제공자.
 *
 * 슬랙은 환승 시 필요한 여유 시간을 의미:
 * - boardSlack: 승차 전 대기 시간 (문 닫힘 대기 등)
 * - alightSlack: 하차 후 이동 시간
 * - transferSlack: 환승 시 추가 여유 시간
 *
 * slackIndex 매핑 (GtfsRoute.getSlackIndex() 참조):
 *   0 = 지하철/도시철도 (SUBWAY)
 *   1 = 버스 (BUS)
 *   2 = 철도 (RAIL)
 *   3 = 기타 (항공 등)
 */
public class KoreanSlackProvider implements RaptorSlackProvider {

    // 슬랙 인덱스 상수
    public static final int SUBWAY = 0;
    public static final int BUS = 1;
    public static final int RAIL = 2;
    public static final int OTHER = 3;

    // 환승 슬랙 (모든 환승에 공통 적용)
    private static final int TRANSFER_SLACK = 60;  // 1분

    // 승차 슬랙 (교통수단별)
    private static final int[] BOARD_SLACK = {
        60,   // 지하철: 1분 (문 닫힘 대기, 계단 이동)
        30,   // 버스: 30초
        120,  // 철도: 2분 (플랫폼 이동, 개찰구)
        180   // 기타(항공): 3분
    };

    // 하차 슬랙 (교통수단별)
    private static final int[] ALIGHT_SLACK = {
        30,   // 지하철: 30초
        10,   // 버스: 10초
        60,   // 철도: 1분
        120   // 기타(항공): 2분
    };

    @Override
    public int transferSlack() {
        return TRANSFER_SLACK;
    }

    @Override
    public int boardSlack(int slackIndex) {
        if (slackIndex < 0 || slackIndex >= BOARD_SLACK.length) {
            return BOARD_SLACK[BUS];  // 기본값: 버스
        }
        return BOARD_SLACK[slackIndex];
    }

    @Override
    public int alightSlack(int slackIndex) {
        if (slackIndex < 0 || slackIndex >= ALIGHT_SLACK.length) {
            return ALIGHT_SLACK[BUS];  // 기본값: 버스
        }
        return ALIGHT_SLACK[slackIndex];
    }

    @Override
    public String toString() {
        return "KoreanSlackProvider{" +
            "transferSlack=" + TRANSFER_SLACK +
            ", boardSlack=[SUBWAY=60, BUS=30, RAIL=120]" +
            ", alightSlack=[SUBWAY=30, BUS=10, RAIL=60]" +
            '}';
    }
}
