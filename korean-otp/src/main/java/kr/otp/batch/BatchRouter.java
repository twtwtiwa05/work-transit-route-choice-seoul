package kr.otp.batch;

import kr.otp.CalibrationConfig;
import kr.otp.core.KoreanRaptor;
import kr.otp.gtfs.GtfsBundle;
import kr.otp.gtfs.loader.GtfsLoader;
import kr.otp.osm.OsmLoader;
import kr.otp.osm.StreetNetwork;
import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.data.TransitDataBuilder;
import kr.otp.raptor.spi.KoreanTripPattern;
import kr.otp.raptor.spi.KoreanTripSchedule;

import org.opentripplanner.raptor.api.path.RaptorPath;
import org.opentripplanner.raptor.api.path.PathLeg;
import org.opentripplanner.raptor.api.path.TransitPathLeg;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.Base64;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

/**
 * 배치 경로 탐색 - 대량 OD 요청 병렬 처리 (MULTI_CRITERIA 모드)
 *
 * v3.0: 장시간 실행 안정성 강화
 * - 청크 기반 처리 (메모리 최적화)
 * - 체크포인트/재개 지원 (크래시 복구)
 * - 스트리밍 NDJSON 출력
 * - 진행률 + ETA 표시
 * - 최대 10개 Pareto-optimal 경로
 * - Step 4용 summary 블록
 *
 * 사용법:
 *   java -Xmx40G -XX:+UseG1GC -cp korean-raptor.jar kr.otp.batch.BatchRouter [input.csv] [output.ndjson] [threads]
 *
 * 입력 CSV 형식:
 *   from_lat,from_lon,to_lat,to_lon,departure_time
 *   37.5547,126.9707,37.4979,127.0276,09:00
 *
 * 출력: NDJSON (각 줄이 하나의 JSON 객체, summary 필드 포함)
 */
public class BatchRouter {

    private static final int DEFAULT_THREADS = 8;
    private static final int WARMUP_COUNT = 10;
    private static final boolean USE_MULTI_CRITERIA = true;

    // v3.0 추가: 장시간 실행 최적화 상수
    private static final int MAX_ITINERARIES = 10;    // 경로 최대 10개
    private static final int CHUNK_SIZE = 10_000;     // 청크 크기

    public static void main(String[] args) {
        // UTF-8 출력 설정
        try {
            System.setOut(new PrintStream(System.out, true, StandardCharsets.UTF_8));
            System.setErr(new PrintStream(System.err, true, StandardCharsets.UTF_8));
        } catch (Exception e) {
            // 무시
        }

        // 인자 파싱
        String inputFile = args.length > 0 ? args[0] : "data/od_sample_1000.csv";
        String outputFile = args.length > 1 ? args[1] : "batch_result.ndjson";
        int numThreads = args.length > 2 ? Integer.parseInt(args[2]) : DEFAULT_THREADS;

        // 출력 파일 확장자 자동 교정
        if (outputFile.endsWith(".json")) {
            outputFile = outputFile.substring(0, outputFile.length() - 5) + ".ndjson";
        }

        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println("           배치 경로 탐색 (Batch Router) v3.0                  ");
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.printf("  입력: %s%n", inputFile);
        System.out.printf("  출력: %s%n", outputFile);
        System.out.printf("  스레드: %d%n", numThreads);
        System.out.printf("  청크 크기: %,d%n", CHUNK_SIZE);
        System.out.printf("  최대 경로 수: %d%n", MAX_ITINERARIES);
        System.out.println();

        try {
            // 0. 보정 설정 로드
            CalibrationConfig calibrationConfig = loadCalibrationConfig();
            System.out.printf("  보정 설정: %s%n%n", calibrationConfig);

            // 1. 데이터 로드
            KoreanRaptor raptor = initializeRaptor(calibrationConfig);

            // 2. OD 요청 로드
            List<ODRequest> requests = loadRequests(inputFile);
            int totalRequests = requests.size();
            System.out.printf("요청 로드 완료: %,d개%n%n", totalRequests);

            // 3. 체크포인트 확인 (재개 지원)
            Path progressPath = Path.of(outputFile + ".progress");
            int resumeFrom = 0;
            boolean appendMode = false;

            if (Files.exists(Path.of(outputFile)) && Files.exists(progressPath)) {
                try {
                    resumeFrom = Integer.parseInt(Files.readString(progressPath).trim());
                    if (resumeFrom > 0 && resumeFrom < totalRequests) {
                        appendMode = true;
                        System.out.printf("═══════════════════════════════════════════════════════════════%n");
                        System.out.printf("  이전 진행 발견: %,d건 완료 → 이어서 실행%n", resumeFrom);
                        System.out.printf("═══════════════════════════════════════════════════════════════%n%n");
                    } else if (resumeFrom >= totalRequests) {
                        System.out.println("이미 완료된 작업입니다.");
                        return;
                    }
                } catch (Exception e) {
                    System.out.println("체크포인트 파일 읽기 실패 → 처음부터 시작");
                }
            }

            // 4. JVM 웜업
            warmup(raptor, requests);

            // 5. 배치 실행 (청크 기반)
            runBatchWithCheckpoint(raptor, requests, numThreads, outputFile, progressPath, resumeFrom, appendMode);

            // 6. 완료 후 progress 파일 삭제
            Files.deleteIfExists(progressPath);

            System.out.println();
            System.out.println("═══════════════════════════════════════════════════════════════");
            System.out.println("                       배치 완료                                ");
            System.out.println("═══════════════════════════════════════════════════════════════");
            System.out.printf("  출력 파일: %s%n", outputFile);
            System.out.printf("  총 처리: %,d건%n", totalRequests);

        } catch (Exception e) {
            System.err.println("오류: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    /**
     * 보정 설정 로드 (calibration_config.json)
     */
    private static CalibrationConfig loadCalibrationConfig() {
        Path configPath = Path.of("calibration_config.json");
        if (Files.exists(configPath)) {
            try {
                CalibrationConfig config = CalibrationConfig.fromJsonFile(configPath);
                System.out.println("보정 설정 로드: " + configPath);
                return config;
            } catch (IOException e) {
                System.err.println("보정 설정 파일 읽기 실패: " + e.getMessage() + " → 기본값 사용");
            }
        } else {
            System.out.println("보정 설정 파일 없음 → 기본값 사용");
        }
        return CalibrationConfig.defaults();
    }

    /**
     * Raptor 엔진 초기화
     */
    private static KoreanRaptor initializeRaptor(CalibrationConfig calibrationConfig) throws Exception {
        Path gtfsDir = Path.of("data/gtfs");
        Path osmPath = Path.of("data/osm/south-korea.osm.pbf");

        System.out.println("[1/2] GTFS 데이터 로드 중...");
        long startTime = System.currentTimeMillis();

        GtfsLoader loader = new GtfsLoader(gtfsDir);
        GtfsBundle gtfs = loader.load();

        TransitDataBuilder builder = new TransitDataBuilder(gtfs);
        TransitData transitData = builder.build();

        long gtfsElapsed = System.currentTimeMillis() - startTime;
        System.out.printf("  완료: %,d 정류장, %,d 패턴 (%.1f초)%n",
            transitData.getStopCount(), transitData.getRouteCount(), gtfsElapsed / 1000.0);

        // OSM 로드 (선택적)
        StreetNetwork streetNetwork = null;
        if (Files.exists(osmPath)) {
            System.out.println("[2/2] OSM 도로망 로드 중...");
            long osmStart = System.currentTimeMillis();

            try {
                OsmLoader osmLoader = new OsmLoader(osmPath);
                streetNetwork = osmLoader.load();
                long osmElapsed = System.currentTimeMillis() - osmStart;
                System.out.printf("  완료: %s (%.1f초)%n", streetNetwork, osmElapsed / 1000.0);
            } catch (Exception e) {
                System.err.println("  OSM 로드 실패: " + e.getMessage());
            }
        } else {
            System.out.println("[2/2] OSM 파일 없음 - 직선 거리 사용");
        }

        KoreanRaptor raptor = new KoreanRaptor(transitData, streetNetwork, calibrationConfig);

        long totalElapsed = System.currentTimeMillis() - startTime;
        System.out.printf("%n초기화 완료 (%.1f초)%n", totalElapsed / 1000.0);
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println();

        return raptor;
    }

    /**
     * CSV에서 OD 요청 로드
     */
    private static List<ODRequest> loadRequests(String inputFile) throws IOException {
        List<ODRequest> requests = new ArrayList<>();

        try (BufferedReader reader = Files.newBufferedReader(Path.of(inputFile), StandardCharsets.UTF_8)) {
            String line;
            boolean header = true;

            while ((line = reader.readLine()) != null) {
                if (header) {
                    header = false;
                    continue;
                }

                String[] parts = line.split(",");
                if (parts.length >= 5) {
                    double fromLat = Double.parseDouble(parts[0].trim());
                    double fromLon = Double.parseDouble(parts[1].trim());
                    double toLat = Double.parseDouble(parts[2].trim());
                    double toLon = Double.parseDouble(parts[3].trim());
                    int departureTime = parseTime(parts[4].trim());

                    requests.add(new ODRequest(requests.size(), fromLat, fromLon, toLat, toLon, departureTime));
                }
            }
        }

        return requests;
    }

    /**
     * JVM 웜업 - 처음 N개 요청으로 JIT 컴파일 유도
     */
    private static void warmup(KoreanRaptor raptor, List<ODRequest> requests) {
        String mode = USE_MULTI_CRITERIA ? "MULTI_CRITERIA" : "STANDARD";
        System.out.printf("JVM 웜업 중 (%d개 요청, %s 모드)...%n", WARMUP_COUNT, mode);
        long warmupStart = System.currentTimeMillis();

        int count = Math.min(WARMUP_COUNT, requests.size());
        for (int i = 0; i < count; i++) {
            ODRequest req = requests.get(i);
            if (USE_MULTI_CRITERIA) {
                raptor.routeMultiCriteria(req.fromLat, req.fromLon, req.toLat, req.toLon, req.departureTime);
            } else {
                raptor.route(req.fromLat, req.fromLon, req.toLat, req.toLon, req.departureTime);
            }
        }

        long warmupElapsed = System.currentTimeMillis() - warmupStart;
        System.out.printf("웜업 완료 (%.1f초)%n%n", warmupElapsed / 1000.0);
    }

    /**
     * 청크 기반 배치 실행 (체크포인트/재개 지원)
     */
    private static void runBatchWithCheckpoint(
            KoreanRaptor raptor,
            List<ODRequest> requests,
            int numThreads,
            String outputFile,
            Path progressPath,
            int resumeFrom,
            boolean appendMode) throws Exception {

        int total = requests.size();
        int totalChunks = (total + CHUNK_SIZE - 1) / CHUNK_SIZE;
        int startChunk = resumeFrom / CHUNK_SIZE;

        String mode = USE_MULTI_CRITERIA ? "MULTI_CRITERIA" : "STANDARD";
        System.out.printf("배치 실행 시작: %,d개 요청, %d 스레드, %s 모드%n", total - resumeFrom, numThreads, mode);
        System.out.printf("청크: %d/%d 부터 시작%n", startChunk + 1, totalChunks);
        System.out.println("─────────────────────────────────────────────────────────────────");

        ExecutorService executor = Executors.newFixedThreadPool(numThreads);
        long batchStartTime = System.currentTimeMillis();

        // 통계 추적
        int successCount = 0;
        int noRouteCount = 0;
        int errorCount = 0;
        List<Long> searchTimes = new ArrayList<>();

        // 출력 파일 열기 (append 또는 새로 생성)
        OpenOption[] options = appendMode
            ? new OpenOption[]{StandardOpenOption.APPEND}
            : new OpenOption[]{StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING};

        try (BufferedWriter writer = Files.newBufferedWriter(Path.of(outputFile), StandardCharsets.UTF_8, options)) {

            int processedCount = resumeFrom;

            for (int chunkIdx = startChunk; chunkIdx < totalChunks; chunkIdx++) {
                int chunkStart = chunkIdx * CHUNK_SIZE;
                int chunkEnd = Math.min(chunkStart + CHUNK_SIZE, total);

                // 첫 청크에서 resumeFrom 위치부터 시작
                if (chunkIdx == startChunk && resumeFrom > chunkStart) {
                    chunkStart = resumeFrom;
                }

                List<ODRequest> chunkRequests = requests.subList(chunkStart, chunkEnd);

                // 청크 실행
                List<RouteResult> chunkResults = runChunk(raptor, chunkRequests, executor);

                // 결과 즉시 기록
                for (RouteResult result : chunkResults) {
                    writer.write(result.toJson());
                    writer.newLine();

                    // 통계 업데이트
                    searchTimes.add(result.searchTimeMs);
                    if (result.error != null) {
                        errorCount++;
                    } else if (result.paths.isEmpty()) {
                        noRouteCount++;
                    } else {
                        successCount++;
                    }
                }
                writer.flush();

                processedCount = chunkEnd;

                // 체크포인트 업데이트
                Files.writeString(progressPath, String.valueOf(processedCount));

                // 진행률 + ETA 출력
                long elapsed = System.currentTimeMillis() - batchStartTime;
                int processedSinceStart = processedCount - resumeFrom;
                double rate = processedSinceStart * 1000.0 / elapsed;
                long remainingCount = total - processedCount;
                long remainingMs = rate > 0 ? (long) (remainingCount / rate * 1000) : 0;

                System.out.printf("[청크 %d/%d] %,d/%,d (%.1f%%) | 경과: %s | ETA: %s | %.1f req/s%n",
                    chunkIdx + 1, totalChunks,
                    processedCount, total,
                    processedCount * 100.0 / total,
                    formatDuration(elapsed),
                    formatDuration(remainingMs),
                    rate);
            }
        }

        executor.shutdown();
        executor.awaitTermination(1, TimeUnit.MINUTES);

        long totalElapsed = System.currentTimeMillis() - batchStartTime;
        int processedTotal = total - resumeFrom;

        System.out.println("─────────────────────────────────────────────────────────────────");
        System.out.printf("배치 완료: %s (%.1f req/s)%n%n",
            formatDuration(totalElapsed), processedTotal * 1000.0 / totalElapsed);

        // 통계 출력
        printStatistics(successCount, noRouteCount, errorCount, searchTimes);
    }

    /**
     * 단일 청크 실행 (병렬 처리)
     */
    private static List<RouteResult> runChunk(KoreanRaptor raptor, List<ODRequest> requests, ExecutorService executor)
            throws InterruptedException {

        List<Future<RouteResult>> futures = new ArrayList<>();

        for (ODRequest req : requests) {
            futures.add(executor.submit(() -> {
                long start = System.currentTimeMillis();

                try {
                    List<RaptorPath<KoreanTripSchedule>> paths;
                    if (USE_MULTI_CRITERIA) {
                        paths = raptor.routeMultiCriteria(req.fromLat, req.fromLon, req.toLat, req.toLon, req.departureTime);
                    } else {
                        paths = raptor.route(req.fromLat, req.fromLon, req.toLat, req.toLon, req.departureTime);
                    }

                    long elapsed = System.currentTimeMillis() - start;
                    return new RouteResult(req, paths, elapsed, raptor);

                } catch (Exception e) {
                    long elapsed = System.currentTimeMillis() - start;
                    return new RouteResult(req, List.of(), elapsed, raptor, e.getMessage());
                }
            }));
        }

        // 결과 수집
        List<RouteResult> results = new ArrayList<>();
        for (Future<RouteResult> future : futures) {
            try {
                results.add(future.get());
            } catch (ExecutionException e) {
                System.err.println("실행 오류: " + e.getMessage());
            }
        }

        return results;
    }

    /**
     * 통계 출력
     */
    private static void printStatistics(int success, int noRoute, int error, List<Long> times) {
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println("                       성능 통계                               ");
        System.out.println("═══════════════════════════════════════════════════════════════");

        int total = success + noRoute + error;

        System.out.printf("  총 요청: %,d개%n", total);
        System.out.printf("  성공 (경로 있음): %,d개 (%.1f%%)%n", success, success * 100.0 / total);
        System.out.printf("  경로 없음: %,d개 (%.1f%%)%n", noRoute, noRoute * 100.0 / total);
        System.out.printf("  실패: %,d개 (%.1f%%)%n", error, error * 100.0 / total);
        System.out.println();

        // 검색 시간 통계
        if (!times.isEmpty()) {
            List<Long> sorted = times.stream().sorted().collect(Collectors.toList());
            long sum = sorted.stream().mapToLong(Long::longValue).sum();
            double avg = sum / (double) sorted.size();
            long min = sorted.get(0);
            long max = sorted.get(sorted.size() - 1);
            long p50 = sorted.get((int) (sorted.size() * 0.50));
            long p95 = sorted.get((int) (sorted.size() * 0.95));
            long p99 = sorted.get(Math.min((int) (sorted.size() * 0.99), sorted.size() - 1));

            System.out.println("  검색 시간 (ms):");
            System.out.printf("    평균: %.1f ms%n", avg);
            System.out.printf("    최소: %d ms%n", min);
            System.out.printf("    P50:  %d ms%n", p50);
            System.out.printf("    P95:  %d ms%n", p95);
            System.out.printf("    P99:  %d ms%n", p99);
            System.out.printf("    최대: %d ms%n", max);
            System.out.println();
            System.out.printf("  처리량: %.1f req/s (단일 스레드 환산)%n", 1000.0 / avg);
        }

        System.out.println("═══════════════════════════════════════════════════════════════");
    }

    /**
     * 시간 파싱 (HH:MM -> 초)
     */
    private static int parseTime(String timeStr) {
        String[] parts = timeStr.split(":");
        int h = Integer.parseInt(parts[0]);
        int m = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
        return h * 3600 + m * 60;
    }

    /**
     * 시간 포맷 (초 -> HH:MM)
     */
    private static String formatTime(int seconds) {
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }

    /**
     * 밀리초를 읽기 쉬운 형태로 변환 (예: "1h 23m" 또는 "45m 30s")
     */
    private static String formatDuration(long ms) {
        if (ms < 0) return "계산중...";

        long seconds = ms / 1000;
        long minutes = seconds / 60;
        long hours = minutes / 60;

        if (hours > 0) {
            return String.format("%dh %dm", hours, minutes % 60);
        } else if (minutes > 0) {
            return String.format("%dm %ds", minutes, seconds % 60);
        } else {
            return String.format("%ds", seconds);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 내부 클래스
    // ═══════════════════════════════════════════════════════════════

    /**
     * OD 요청
     */
    static class ODRequest {
        final int id;
        final double fromLat, fromLon;
        final double toLat, toLon;
        final int departureTime;

        ODRequest(int id, double fromLat, double fromLon, double toLat, double toLon, int departureTime) {
            this.id = id;
            this.fromLat = fromLat;
            this.fromLon = fromLon;
            this.toLat = toLat;
            this.toLon = toLon;
            this.departureTime = departureTime;
        }
    }

    /**
     * 경로 결과
     */
    static class RouteResult {
        final ODRequest request;
        final List<RaptorPath<KoreanTripSchedule>> paths;
        final long searchTimeMs;
        final String error;
        final KoreanRaptor raptor;

        // 기준 날짜 (2026-01-19 00:00:00 KST)
        private static final long BASE_DATE_MS = 1768860000000L;

        RouteResult(ODRequest request, List<RaptorPath<KoreanTripSchedule>> paths,
                    long searchTimeMs, KoreanRaptor raptor) {
            this(request, paths, searchTimeMs, raptor, null);
        }

        RouteResult(ODRequest request, List<RaptorPath<KoreanTripSchedule>> paths,
                    long searchTimeMs, KoreanRaptor raptor, String error) {
            this.request = request;
            this.paths = paths;
            this.searchTimeMs = searchTimeMs;
            this.raptor = raptor;
            this.error = error;
        }

        /**
         * NDJSON 형식으로 변환 (한 줄, 들여쓰기 없음)
         */
        String toJson() {
            StringBuilder sb = new StringBuilder();
            sb.append("{");
            sb.append(String.format("\"id\":%d,", request.id));
            sb.append(String.format("\"searchTimeMs\":%d,", searchTimeMs));
            sb.append("\"data\":{\"plan\":{");

            if (error != null) {
                sb.append(String.format("\"error\":\"%s\",", escapeJson(error)));
                sb.append("\"itineraries\":[]");
            } else if (paths.isEmpty()) {
                sb.append("\"itineraries\":[]");
            } else {
                sb.append("\"itineraries\":[");

                int pathIdx = 0;
                for (RaptorPath<KoreanTripSchedule> path : paths) {
                    if (pathIdx > 0) sb.append(",");
                    sb.append(pathToJson(path));
                    pathIdx++;
                    if (pathIdx >= MAX_ITINERARIES) break;  // 최대 10개 경로
                }

                sb.append("]");
            }

            sb.append("}}}");
            return sb.toString();
        }

        private String pathToJson(RaptorPath<KoreanTripSchedule> path) {
            StringBuilder sb = new StringBuilder();
            sb.append("{");

            long startTimeMs = secondsToTimestamp(path.startTime());
            long endTimeMs = secondsToTimestamp(path.endTime());

            sb.append(String.format("\"startTime\":%d,", startTimeMs));
            sb.append(String.format("\"endTime\":%d,", endTimeMs));
            sb.append(String.format("\"duration\":%d,", path.durationInSeconds()));

            double walkDistance = calculateWalkDistance(path);
            sb.append(String.format("\"walkDistance\":%.2f,", walkDistance));

            int cost = path.c1();
            sb.append(String.format("\"generalizedCost\":%d,", cost));

            // Summary 계산을 위한 변수
            int transitLegCount = 0;
            int rideTimeSec = 0;
            int walkTimeSec = 0;
            boolean hasSubway = false;
            List<String> modes = new ArrayList<>();
            List<String> stopSequence = new ArrayList<>();

            // legs 배열 구성 + summary 데이터 수집
            StringBuilder legsSb = new StringBuilder();
            legsSb.append("[");

            PathLeg<?> leg = path.accessLeg();
            boolean first = true;

            while (leg != null) {
                if (!first) legsSb.append(",");
                first = false;

                legsSb.append("{");

                if (leg.isAccessLeg()) {
                    long legStartMs = secondsToTimestamp(leg.fromTime());
                    long legEndMs = secondsToTimestamp(leg.toTime());
                    int toStop = leg.toStop();
                    double distance = estimateWalkDistance(leg.duration());

                    walkTimeSec += leg.duration();

                    legsSb.append("\"mode\":\"WALK\",");
                    legsSb.append(String.format("\"startTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"endTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"duration\":%.1f,", (double) leg.duration()));
                    legsSb.append(String.format("\"distance\":%.2f,", distance));
                    legsSb.append(String.format("\"generalizedCost\":%d,", leg.duration() * 2));

                    // from (Origin)
                    legsSb.append("\"from\":{");
                    legsSb.append("\"name\":\"Origin\",");
                    legsSb.append(String.format("\"lat\":%.6f,", request.fromLat));
                    legsSb.append(String.format("\"lon\":%.6f,", request.fromLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legStartMs));
                    legsSb.append("\"stop\":null},");

                    // to (정류장)
                    double[] coords = raptor.getStopCoords(toStop);
                    double tLat = coords != null ? coords[0] : 0;
                    double tLon = coords != null ? coords[1] : 0;
                    String toStopId = raptor.getStopId(toStop);
                    legsSb.append("\"to\":{");
                    legsSb.append(String.format("\"name\":\"%s\",", escapeJson(raptor.getStopName(toStop))));
                    legsSb.append(String.format("\"lat\":%.6f,", tLat));
                    legsSb.append(String.format("\"lon\":%.6f,", tLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legEndMs));
                    legsSb.append("\"stop\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(toStopId)));
                    legsSb.append(String.format("\"id\":\"%s\",", toBase64StopId(toStopId)));
                    legsSb.append("\"code\":null}},");
                    legsSb.append("\"route\":null,\"trip\":null,");
                    legsSb.append("\"legGeometry\":{");
                    legsSb.append(String.format("\"points\":\"%s\"}", encodePolyline(request.fromLat, request.fromLon, tLat, tLon)));

                } else if (leg.isTransitLeg()) {
                    TransitPathLeg<KoreanTripSchedule> transitLeg = (TransitPathLeg<KoreanTripSchedule>) leg;
                    KoreanTripSchedule trip = transitLeg.trip();

                    long legStartMs = secondsToTimestamp(transitLeg.fromTime());
                    long legEndMs = secondsToTimestamp(transitLeg.toTime());
                    int fromStop = transitLeg.fromStop();
                    int toStop = transitLeg.toStop();

                    String mode = determineMode(trip);

                    // Summary 데이터 수집
                    transitLegCount++;
                    rideTimeSec += transitLeg.duration();
                    if (mode.equals("SUBWAY")) hasSubway = true;
                    modes.add(mode);

                    // stop_sequence 수집: 승차역 + 중간역 + 하차역
                    collectStopSequence(trip, fromStop, toStop, stopSequence);

                    legsSb.append(String.format("\"mode\":\"%s\",", mode));
                    legsSb.append(String.format("\"startTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"endTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"duration\":%.1f,", (double) transitLeg.duration()));
                    legsSb.append(String.format("\"distance\":%.2f,", 0.0));
                    legsSb.append(String.format("\"generalizedCost\":%d,", transitLeg.duration()));

                    // from
                    double[] fromCoords = raptor.getStopCoords(fromStop);
                    double fLat = fromCoords != null ? fromCoords[0] : 0;
                    double fLon = fromCoords != null ? fromCoords[1] : 0;
                    String fromStopId = raptor.getStopId(fromStop);
                    legsSb.append("\"from\":{");
                    legsSb.append(String.format("\"name\":\"%s\",", escapeJson(raptor.getStopName(fromStop))));
                    legsSb.append(String.format("\"lat\":%.6f,", fLat));
                    legsSb.append(String.format("\"lon\":%.6f,", fLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legStartMs));
                    legsSb.append("\"stop\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(fromStopId)));
                    legsSb.append(String.format("\"id\":\"%s\",", toBase64StopId(fromStopId)));
                    legsSb.append("\"code\":null}},");

                    // to
                    double[] toCoords = raptor.getStopCoords(toStop);
                    double tLat = toCoords != null ? toCoords[0] : 0;
                    double tLon = toCoords != null ? toCoords[1] : 0;
                    String toStopId = raptor.getStopId(toStop);
                    legsSb.append("\"to\":{");
                    legsSb.append(String.format("\"name\":\"%s\",", escapeJson(raptor.getStopName(toStop))));
                    legsSb.append(String.format("\"lat\":%.6f,", tLat));
                    legsSb.append(String.format("\"lon\":%.6f,", tLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legEndMs));
                    legsSb.append("\"stop\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(toStopId)));
                    legsSb.append(String.format("\"id\":\"%s\",", toBase64StopId(toStopId)));
                    legsSb.append("\"code\":null}},");

                    // route
                    legsSb.append("\"route\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(trip.getRouteId())));
                    legsSb.append(String.format("\"longName\":\"%s\",", escapeJson(trip.getRouteLongName())));
                    legsSb.append(String.format("\"shortName\":\"%s\"", escapeJson(trip.getRouteShortName())));
                    legsSb.append("},");

                    // trip
                    legsSb.append("\"trip\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\"", toOtpGtfsId(trip.getTripId())));
                    legsSb.append("},");

                    // intermediateStops
                    legsSb.append("\"intermediateStops\":");
                    legsSb.append(buildIntermediateStops(trip, fromStop, toStop));
                    legsSb.append(",");

                    legsSb.append("\"legGeometry\":{");
                    legsSb.append(String.format("\"points\":\"%s\"}", encodePolyline(fLat, fLon, tLat, tLon)));

                } else if (leg.isTransferLeg()) {
                    long legStartMs = secondsToTimestamp(leg.fromTime());
                    long legEndMs = secondsToTimestamp(leg.toTime());
                    int fromStop = leg.fromStop();
                    int toStop = leg.toStop();
                    double distance = estimateWalkDistance(leg.duration());

                    walkTimeSec += leg.duration();

                    legsSb.append("\"mode\":\"WALK\",");
                    legsSb.append(String.format("\"startTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"endTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"duration\":%.1f,", (double) leg.duration()));
                    legsSb.append(String.format("\"distance\":%.2f,", distance));
                    legsSb.append(String.format("\"generalizedCost\":%d,", leg.duration() * 2));

                    // from
                    double[] fromCoords = raptor.getStopCoords(fromStop);
                    double fLat = fromCoords != null ? fromCoords[0] : 0;
                    double fLon = fromCoords != null ? fromCoords[1] : 0;
                    String fromStopId = raptor.getStopId(fromStop);
                    legsSb.append("\"from\":{");
                    legsSb.append(String.format("\"name\":\"%s\",", escapeJson(raptor.getStopName(fromStop))));
                    legsSb.append(String.format("\"lat\":%.6f,", fLat));
                    legsSb.append(String.format("\"lon\":%.6f,", fLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legStartMs));
                    legsSb.append("\"stop\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(fromStopId)));
                    legsSb.append(String.format("\"id\":\"%s\",", toBase64StopId(fromStopId)));
                    legsSb.append("\"code\":null}},");

                    // to
                    double[] toCoords = raptor.getStopCoords(toStop);
                    double tLat = toCoords != null ? toCoords[0] : 0;
                    double tLon = toCoords != null ? toCoords[1] : 0;
                    String toStopId = raptor.getStopId(toStop);
                    legsSb.append("\"to\":{");
                    legsSb.append(String.format("\"name\":\"%s\",", escapeJson(raptor.getStopName(toStop))));
                    legsSb.append(String.format("\"lat\":%.6f,", tLat));
                    legsSb.append(String.format("\"lon\":%.6f,", tLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legEndMs));
                    legsSb.append("\"stop\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(toStopId)));
                    legsSb.append(String.format("\"id\":\"%s\",", toBase64StopId(toStopId)));
                    legsSb.append("\"code\":null}},");
                    legsSb.append("\"route\":null,\"trip\":null,");
                    legsSb.append("\"legGeometry\":{");
                    legsSb.append(String.format("\"points\":\"%s\"}", encodePolyline(fLat, fLon, tLat, tLon)));

                } else if (leg.isEgressLeg()) {
                    long legStartMs = secondsToTimestamp(leg.fromTime());
                    long legEndMs = secondsToTimestamp(leg.toTime());
                    int fromStop = leg.fromStop();
                    double distance = estimateWalkDistance(leg.duration());

                    walkTimeSec += leg.duration();

                    legsSb.append("\"mode\":\"WALK\",");
                    legsSb.append(String.format("\"startTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"endTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"duration\":%.1f,", (double) leg.duration()));
                    legsSb.append(String.format("\"distance\":%.2f,", distance));
                    legsSb.append(String.format("\"generalizedCost\":%d,", leg.duration() * 2));

                    // from
                    double[] fromCoords = raptor.getStopCoords(fromStop);
                    double fLat = fromCoords != null ? fromCoords[0] : 0;
                    double fLon = fromCoords != null ? fromCoords[1] : 0;
                    String fromStopId = raptor.getStopId(fromStop);
                    legsSb.append("\"from\":{");
                    legsSb.append(String.format("\"name\":\"%s\",", escapeJson(raptor.getStopName(fromStop))));
                    legsSb.append(String.format("\"lat\":%.6f,", fLat));
                    legsSb.append(String.format("\"lon\":%.6f,", fLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legStartMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legStartMs));
                    legsSb.append("\"stop\":{");
                    legsSb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(fromStopId)));
                    legsSb.append(String.format("\"id\":\"%s\",", toBase64StopId(fromStopId)));
                    legsSb.append("\"code\":null}},");

                    // to (Destination)
                    legsSb.append("\"to\":{");
                    legsSb.append("\"name\":\"Destination\",");
                    legsSb.append(String.format("\"lat\":%.6f,", request.toLat));
                    legsSb.append(String.format("\"lon\":%.6f,", request.toLon));
                    legsSb.append(String.format("\"departureTime\":%d,", legEndMs));
                    legsSb.append(String.format("\"arrivalTime\":%d,", legEndMs));
                    legsSb.append("\"stop\":null},");
                    legsSb.append("\"route\":null,\"trip\":null,");
                    legsSb.append("\"legGeometry\":{");
                    legsSb.append(String.format("\"points\":\"%s\"}", encodePolyline(fLat, fLon, request.toLat, request.toLon)));
                }

                legsSb.append("}");

                leg = leg.isEgressLeg() ? null : leg.nextLeg();
            }

            legsSb.append("]");

            // Summary 블록 추가
            sb.append("\"summary\":{");
            sb.append(String.format("\"n_transfers\":%d,", Math.max(0, transitLegCount - 1)));
            sb.append(String.format("\"ride_time_sec\":%d,", rideTimeSec));
            sb.append(String.format("\"walk_time_sec\":%d,", walkTimeSec));
            sb.append(String.format("\"has_subway\":%s,", hasSubway));
            sb.append("\"modes\":[");
            for (int i = 0; i < modes.size(); i++) {
                if (i > 0) sb.append(",");
                sb.append(String.format("\"%s\"", modes.get(i)));
            }
            sb.append("],");
            sb.append("\"stop_sequence\":[");
            for (int i = 0; i < stopSequence.size(); i++) {
                if (i > 0) sb.append(",");
                sb.append(String.format("\"%s\"", stopSequence.get(i)));
            }
            sb.append("]},");

            // Legs 추가
            sb.append("\"legs\":");
            sb.append(legsSb.toString());

            sb.append("}");
            return sb.toString();
        }

        /**
         * transit leg의 모든 정류장을 stop_sequence에 수집
         */
        private void collectStopSequence(KoreanTripSchedule trip, int boardStopIndex, int alightStopIndex, List<String> stopSequence) {
            KoreanTripPattern pattern = (KoreanTripPattern) trip.pattern();
            int[] stopIndexes = pattern.getStopIndexes();

            int boardPos = -1;
            int alightPos = -1;
            for (int i = 0; i < stopIndexes.length; i++) {
                if (stopIndexes[i] == boardStopIndex && boardPos < 0) {
                    boardPos = i;
                }
                if (stopIndexes[i] == alightStopIndex && i > boardPos && boardPos >= 0) {
                    alightPos = i;
                    break;
                }
            }

            if (boardPos < 0 || alightPos < 0) return;

            // 승차역 + 중간역 + 하차역 모두 추가
            for (int i = boardPos; i <= alightPos; i++) {
                int stopIdx = stopIndexes[i];
                String stopId = raptor.getStopId(stopIdx);
                stopSequence.add(toOtpGtfsId(stopId));
            }
        }

        /**
         * transit leg의 중간 정류장 목록 생성 (board/alight 제외)
         */
        private String buildIntermediateStops(KoreanTripSchedule trip, int boardStopIndex, int alightStopIndex) {
            KoreanTripPattern pattern = (KoreanTripPattern) trip.pattern();
            int[] stopIndexes = pattern.getStopIndexes();

            // 패턴 내 board/alight 위치 찾기
            int boardPos = -1;
            int alightPos = -1;
            for (int i = 0; i < stopIndexes.length; i++) {
                if (stopIndexes[i] == boardStopIndex && boardPos < 0) {
                    boardPos = i;
                }
                if (stopIndexes[i] == alightStopIndex && i > boardPos && boardPos >= 0) {
                    alightPos = i;
                    break;
                }
            }

            if (boardPos < 0 || alightPos < 0 || alightPos <= boardPos + 1) {
                return "[]";
            }

            StringBuilder sb = new StringBuilder();
            sb.append("[");
            boolean first = true;
            for (int i = boardPos + 1; i < alightPos; i++) {
                if (!first) sb.append(",");
                first = false;
                int stopIdx = stopIndexes[i];
                String stopId = raptor.getStopId(stopIdx);
                String stopName = raptor.getStopName(stopIdx);
                sb.append("{");
                sb.append(String.format("\"gtfsId\":\"%s\",", toOtpGtfsId(stopId)));
                sb.append(String.format("\"name\":\"%s\"", escapeJson(stopName)));
                sb.append("}");
            }
            sb.append("]");
            return sb.toString();
        }

        /**
         * 초 단위 시간을 Unix timestamp (ms)로 변환
         */
        private long secondsToTimestamp(int seconds) {
            return BASE_DATE_MS + (seconds * 1000L);
        }

        /**
         * 도보 시간으로 거리 추정 (1.2 m/s)
         */
        private double estimateWalkDistance(int durationSeconds) {
            return durationSeconds * 1.2;
        }

        /**
         * 경로의 총 도보 거리 계산
         */
        private double calculateWalkDistance(RaptorPath<KoreanTripSchedule> path) {
            double total = 0;
            PathLeg<?> leg = path.accessLeg();
            while (leg != null) {
                if (leg.isAccessLeg() || leg.isTransferLeg() || leg.isEgressLeg()) {
                    total += estimateWalkDistance(leg.duration());
                }
                leg = leg.isEgressLeg() ? null : leg.nextLeg();
            }
            return total;
        }

        /**
         * 교통수단 모드 결정 (route type 기반)
         */
        private String determineMode(KoreanTripSchedule trip) {
            int routeType = trip.getRouteType();
            switch (routeType) {
                case 1:  // Subway
                case 12: // Metro
                    return "SUBWAY";
                case 2:  // Rail
                case 100: // Railway
                case 101: // High Speed Rail
                case 102: // Long Distance Rail
                    return "RAIL";
                case 3:  // Bus
                case 700: // Bus
                case 701: // Regional Bus
                case 702: // Express Bus
                case 704: // Local Bus
                    return "BUS";
                case 4:  // Ferry
                    return "FERRY";
                case 7:  // Funicular
                    return "FUNICULAR";
                default:
                    return "BUS";  // 기본값
            }
        }

        private String escapeJson(String s) {
            if (s == null) return "";
            return s.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
        }

        /**
         * GTFS ID에 OTP 형식 prefix 추가 (예: "1:BS_3100_...")
         */
        private String toOtpGtfsId(String gtfsId) {
            if (gtfsId == null) return "1:unknown";
            return "1:" + gtfsId;
        }

        /**
         * GTFS ID를 OTP 형식 Base64 ID로 변환
         * 예: "Stop:1:BS_3100_217000396" → Base64 인코딩
         */
        private String toBase64StopId(String gtfsId) {
            if (gtfsId == null) return null;
            String fullId = "Stop:1:" + gtfsId;
            return Base64.getEncoder().encodeToString(fullId.getBytes(StandardCharsets.UTF_8));
        }

        /**
         * Google Polyline Algorithm으로 좌표를 인코딩
         */
        private String encodePolyline(double lat1, double lon1, double lat2, double lon2) {
            StringBuilder sb = new StringBuilder();

            int prevLat = 0;
            int prevLon = 0;

            int lat1E5 = (int) Math.round(lat1 * 1e5);
            int lon1E5 = (int) Math.round(lon1 * 1e5);

            encodeValue(lat1E5 - prevLat, sb);
            encodeValue(lon1E5 - prevLon, sb);

            prevLat = lat1E5;
            prevLon = lon1E5;

            int lat2E5 = (int) Math.round(lat2 * 1e5);
            int lon2E5 = (int) Math.round(lon2 * 1e5);

            encodeValue(lat2E5 - prevLat, sb);
            encodeValue(lon2E5 - prevLon, sb);

            return sb.toString();
        }

        /**
         * Polyline 인코딩 헬퍼
         */
        private void encodeValue(int value, StringBuilder sb) {
            int v = value < 0 ? ~(value << 1) : (value << 1);
            while (v >= 0x20) {
                sb.append((char) ((0x20 | (v & 0x1f)) + 63));
                v >>= 5;
            }
            sb.append((char) (v + 63));
        }
    }
}
