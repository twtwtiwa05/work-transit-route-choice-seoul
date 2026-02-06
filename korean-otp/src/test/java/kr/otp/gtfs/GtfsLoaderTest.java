package kr.otp.gtfs;

import kr.otp.gtfs.loader.GtfsLoader;
import kr.otp.gtfs.model.GtfsRoute;
import kr.otp.gtfs.model.GtfsStop;
import kr.otp.gtfs.model.GtfsStopTime;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * GTFS 로더 테스트.
 *
 * 실제 한국 GTFS 데이터를 사용하여 테스트.
 */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class GtfsLoaderTest {

    private static final Path GTFS_DIR = Path.of("data/gtfs");

    private GtfsBundle bundle;

    @BeforeAll
    void setUp() {
        // GTFS 데이터가 있는 경우에만 로드
        if (GTFS_DIR.toFile().exists()) {
            GtfsLoader loader = new GtfsLoader(GTFS_DIR);
            bundle = loader.load();
        }
    }

    @Test
    void testGtfsLoad() {
        if (bundle == null) {
            System.out.println("GTFS 데이터가 없어 테스트를 건너뜁니다.");
            return;
        }

        // 기본 통계 확인
        System.out.println("=== GTFS 로드 결과 ===");
        System.out.printf("정류장: %,d개%n", bundle.getStopCount());
        System.out.printf("노선: %,d개%n", bundle.getRouteCount());
        System.out.printf("트립: %,d개%n", bundle.getTripCount());
        System.out.printf("시간표: %,d개%n", bundle.getStopTimeCount());

        // 기대값 검증
        assertTrue(bundle.getStopCount() > 200_000, "정류장 수가 부족합니다");
        assertTrue(bundle.getRouteCount() > 20_000, "노선 수가 부족합니다");
        assertTrue(bundle.getTripCount() > 300_000, "트립 수가 부족합니다");
        assertTrue(bundle.getStopTimeCount() > 20_000_000, "시간표 수가 부족합니다");
    }

    @Test
    void testStopRetrieval() {
        if (bundle == null) return;

        // 아무 정류장이나 가져오기
        GtfsStop stop = bundle.getAllStops().iterator().next();
        assertNotNull(stop);
        assertNotNull(stop.stopId());
        assertNotNull(stop.stopName());
        assertTrue(stop.lat() != 0);
        assertTrue(stop.lon() != 0);

        System.out.println("샘플 정류장: " + stop);
    }

    @Test
    void testRouteTypes() {
        if (bundle == null) return;

        // 교통수단별 통계
        int subway = 0, bus = 0, rail = 0, air = 0;

        for (GtfsRoute route : bundle.getAllRoutes()) {
            switch (route.getSlackIndex()) {
                case GtfsRoute.SLACK_SUBWAY -> subway++;
                case GtfsRoute.SLACK_BUS -> bus++;
                case GtfsRoute.SLACK_RAIL -> rail++;
                case GtfsRoute.SLACK_AIR -> air++;
            }
        }

        System.out.println("=== 교통수단별 노선 수 ===");
        System.out.printf("지하철/도시철도: %,d개%n", subway);
        System.out.printf("버스: %,d개%n", bus);
        System.out.printf("철도: %,d개%n", rail);
        System.out.printf("항공: %,d개%n", air);

        assertTrue(bus > 0, "버스 노선이 없습니다");
    }

    @Test
    void testStopTimesOrdering() {
        if (bundle == null) return;

        // 아무 트립의 stop_times 가져오기
        String tripId = bundle.getAllTripIds().iterator().next();
        List<GtfsStopTime> stopTimes = bundle.getStopTimes(tripId);

        assertFalse(stopTimes.isEmpty(), "stop_times가 비어있습니다");

        // stop_sequence 순으로 정렬되어 있는지 확인
        int prevSeq = -1;
        for (GtfsStopTime st : stopTimes) {
            assertTrue(st.stopSequence() > prevSeq,
                "stop_times가 정렬되어 있지 않습니다");
            prevSeq = st.stopSequence();
        }

        System.out.println("샘플 트립 stop_times (정렬 확인):");
        stopTimes.stream().limit(5).forEach(st ->
            System.out.printf("  seq=%d, stop=%s, arr=%s, dep=%s%n",
                st.stopSequence(), st.stopId(),
                GtfsStopTime.formatTime(st.arrivalTime()),
                GtfsStopTime.formatTime(st.departureTime())
            )
        );
    }

    @Test
    void testServiceTimes() {
        if (bundle == null) return;

        int startTime = bundle.getServiceStartTime();
        int endTime = bundle.getServiceEndTime();

        System.out.printf("서비스 시간: %s ~ %s%n",
            GtfsStopTime.formatTime(startTime),
            GtfsStopTime.formatTime(endTime)
        );

        assertTrue(startTime >= 0, "서비스 시작 시간이 음수입니다");
        assertTrue(endTime > startTime, "서비스 종료 시간이 시작 시간보다 빠릅니다");
    }

    @Test
    void testStopDistance() {
        if (bundle == null) return;

        // 두 정류장 간 거리 테스트
        var stops = bundle.getAllStops().iterator();
        GtfsStop stop1 = stops.next();
        GtfsStop stop2 = stops.next();

        double distance = stop1.distanceTo(stop2);
        System.out.printf("두 정류장 간 거리: %s ~ %s = %.0fm%n",
            stop1.stopName(), stop2.stopName(), distance);

        assertTrue(distance >= 0, "거리가 음수입니다");
    }
}
