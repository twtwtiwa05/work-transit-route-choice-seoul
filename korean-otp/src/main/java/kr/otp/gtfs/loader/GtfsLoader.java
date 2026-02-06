package kr.otp.gtfs.loader;

import kr.otp.gtfs.GtfsBundle;
import kr.otp.gtfs.model.GtfsRoute;
import kr.otp.gtfs.model.GtfsStop;
import kr.otp.gtfs.model.GtfsStopTime;
import kr.otp.gtfs.model.GtfsTrip;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.NumberFormat;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * GTFS 데이터 로더.
 *
 * 대용량 파일(2000만+ 레코드)을 효율적으로 처리하기 위해:
 * - BufferedReader 스트리밍 사용
 * - 진행률 표시
 * - 메모리 효율적인 파싱
 *
 * 사용법:
 * <pre>
 *     GtfsLoader loader = new GtfsLoader(gtfsDir);
 *     GtfsBundle bundle = loader.load();
 * </pre>
 */
public class GtfsLoader {

    private static final Logger log = LoggerFactory.getLogger(GtfsLoader.class);

    private static final int PROGRESS_INTERVAL = 500_000; // 진행률 표시 간격
    private static final NumberFormat NUM_FORMAT = NumberFormat.getNumberInstance(Locale.KOREA);

    private final Path gtfsDir;

    public GtfsLoader(Path gtfsDir) {
        this.gtfsDir = gtfsDir;
    }

    /**
     * GTFS 데이터를 로드하여 GtfsBundle 반환
     *
     * @return 로드된 GtfsBundle
     * @throws GtfsLoadException 로드 실패 시
     */
    public GtfsBundle load() {
        log.info("GTFS 데이터 로드 시작: {}", gtfsDir);
        long startTime = System.currentTimeMillis();

        GtfsBundle.Builder builder = GtfsBundle.builder();

        try {
            // 1. stops.txt 로드
            int stopCount = loadStops(builder);
            log.info("  정류장 로드 완료: {}개", fmt(stopCount));

            // 2. routes.txt 로드
            int routeCount = loadRoutes(builder);
            log.info("  노선 로드 완료: {}개", fmt(routeCount));

            // 3. trips.txt 로드
            int tripCount = loadTrips(builder);
            log.info("  트립 로드 완료: {}개", fmt(tripCount));

            // 4. stop_times.txt 로드 (가장 큰 파일)
            int stopTimeCount = loadStopTimes(builder);
            log.info("  시간표 로드 완료: {}개", fmt(stopTimeCount));

            long elapsed = System.currentTimeMillis() - startTime;
            log.info("GTFS 로드 완료 (소요시간: {}초)", String.format("%.1f", elapsed / 1000.0));

            return builder.build();

        } catch (IOException e) {
            throw new GtfsLoadException("GTFS 로드 실패: " + e.getMessage(), e);
        }
    }

    /**
     * stops.txt 로드
     */
    private int loadStops(GtfsBundle.Builder builder) throws IOException {
        Path file = gtfsDir.resolve("stops.txt");
        AtomicInteger count = new AtomicInteger(0);

        try (BufferedReader reader = createReader(file)) {
            String header = reader.readLine(); // 헤더 스킵
            validateHeader(header, "stop_id", "stops.txt");

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;

                try {
                    String[] parts = parseCsvLine(line);
                    if (parts.length >= 4) {
                        builder.addStop(GtfsStop.fromCsv(parts));
                        count.incrementAndGet();
                    }
                } catch (Exception e) {
                    log.warn("stops.txt 파싱 오류 (line {}): {}", count.get() + 2, e.getMessage());
                }
            }
        }

        return count.get();
    }

    /**
     * routes.txt 로드
     */
    private int loadRoutes(GtfsBundle.Builder builder) throws IOException {
        Path file = gtfsDir.resolve("routes.txt");
        AtomicInteger count = new AtomicInteger(0);

        try (BufferedReader reader = createReader(file)) {
            String header = reader.readLine();
            validateHeader(header, "route_id", "routes.txt");

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;

                try {
                    String[] parts = parseCsvLine(line);
                    if (parts.length >= 5) {
                        builder.addRoute(GtfsRoute.fromCsv(parts));
                        count.incrementAndGet();
                    }
                } catch (Exception e) {
                    log.warn("routes.txt 파싱 오류 (line {}): {}", count.get() + 2, e.getMessage());
                }
            }
        }

        return count.get();
    }

    /**
     * trips.txt 로드
     */
    private int loadTrips(GtfsBundle.Builder builder) throws IOException {
        Path file = gtfsDir.resolve("trips.txt");
        AtomicInteger count = new AtomicInteger(0);

        try (BufferedReader reader = createReader(file)) {
            String header = reader.readLine();
            validateHeader(header, "route_id", "trips.txt");

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;

                try {
                    String[] parts = parseCsvLine(line);
                    if (parts.length >= 3) {
                        builder.addTrip(GtfsTrip.fromCsv(parts));
                        count.incrementAndGet();
                    }
                } catch (Exception e) {
                    log.warn("trips.txt 파싱 오류 (line {}): {}", count.get() + 2, e.getMessage());
                }
            }
        }

        return count.get();
    }

    /**
     * stop_times.txt 로드 (대용량 파일 - 약 2000만 레코드)
     */
    private int loadStopTimes(GtfsBundle.Builder builder) throws IOException {
        Path file = gtfsDir.resolve("stop_times.txt");
        AtomicInteger count = new AtomicInteger(0);

        // 파일 크기로 예상 레코드 수 추정 (진행률 표시용)
        long fileSize = Files.size(file);
        long estimatedRecords = fileSize / 80; // 대략 한 줄당 80바이트

        log.info("  stop_times.txt 로드 중... (예상: {}개)", fmt(estimatedRecords));

        try (BufferedReader reader = createReader(file)) {
            String header = reader.readLine();
            validateHeader(header, "trip_id", "stop_times.txt");

            String line;
            long lastProgressTime = System.currentTimeMillis();

            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;

                try {
                    String[] parts = parseCsvLine(line);
                    if (parts.length >= 7) {
                        builder.addStopTime(GtfsStopTime.fromCsv(parts));
                        int current = count.incrementAndGet();

                        // 진행률 표시 (50만건마다)
                        if (current % PROGRESS_INTERVAL == 0) {
                            long now = System.currentTimeMillis();
                            double elapsed = (now - lastProgressTime) / 1000.0;
                            double rate = PROGRESS_INTERVAL / elapsed;
                            log.info("    {}개 로드됨 ({} records/sec)",
                                fmt(current), String.format("%.0f", rate));
                            lastProgressTime = now;
                        }
                    }
                } catch (Exception e) {
                    // 대용량 파일에서는 개별 오류 로깅 최소화
                    if (count.get() < 100) {
                        log.warn("stop_times.txt 파싱 오류 (line {}): {}",
                            count.get() + 2, e.getMessage());
                    }
                }
            }
        }

        return count.get();
    }

    /**
     * CSV 라인 파싱 (쉼표 구분, 따옴표 처리)
     */
    private String[] parseCsvLine(String line) {
        // 간단한 CSV 파싱 (따옴표 내 쉼표는 무시)
        // GTFS 데이터는 대부분 따옴표를 사용하지 않으므로 단순 split 사용
        // 복잡한 경우에는 OpenCSV 라이브러리 사용 가능
        return line.split(",", -1);
    }

    /**
     * UTF-8 BufferedReader 생성 (버퍼 크기 최적화)
     */
    private BufferedReader createReader(Path file) throws IOException {
        // 대용량 파일용 큰 버퍼 사용 (8MB)
        return new BufferedReader(
            new InputStreamReader(
                new FileInputStream(file.toFile()),
                StandardCharsets.UTF_8
            ),
            8 * 1024 * 1024
        );
    }

    /**
     * CSV 헤더 검증
     */
    private void validateHeader(String header, String expectedColumn, String fileName) {
        if (header == null || !header.contains(expectedColumn)) {
            throw new GtfsLoadException(
                String.format("%s 헤더가 올바르지 않습니다. 예상: %s, 실제: %s",
                    fileName, expectedColumn, header)
            );
        }
    }

    /**
     * 숫자 포맷팅 (천단위 콤마)
     */
    private static String fmt(long num) {
        return NUM_FORMAT.format(num);
    }

    /**
     * GTFS 로드 예외
     */
    public static class GtfsLoadException extends RuntimeException {
        public GtfsLoadException(String message) {
            super(message);
        }

        public GtfsLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
