package kr.otp;

import kr.otp.core.KoreanRaptor;
import kr.otp.gtfs.GtfsBundle;
import kr.otp.gtfs.loader.GtfsLoader;
import kr.otp.osm.OsmLoader;
import kr.otp.osm.StreetNetwork;
import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.data.TransitDataBuilder;
import kr.otp.raptor.spi.KoreanTripSchedule;
import kr.otp.batch.BatchRouter;
import kr.otp.scenario.ScenarioCli;

import org.opentripplanner.raptor.api.path.RaptorPath;
import org.opentripplanner.raptor.api.path.PathLeg;
import org.opentripplanner.raptor.api.path.TransitPathLeg;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Korean Raptor 경로탐색 엔진 CLI.
 *
 * 사용법:
 *   java -jar korean-raptor.jar [출발위도] [출발경도] [도착위도] [도착경도] [시간] [결과수]
 *
 * 예시:
 *   java -jar korean-raptor.jar 37.5547 126.9707 37.4979 127.0276 09:00 5
 */
public class Main {

    private static int maxResults = 5;   // 기본 결과 수
    private static boolean useMultiCriteria = false;  // MULTI_CRITERIA 모드

    public static void main(String[] args) {
        // "batch" 서브 커맨드 → BatchRouter로 위임
        if (args.length > 0 && args[0].equalsIgnoreCase("batch")) {
            String[] batchArgs = new String[args.length - 1];
            System.arraycopy(args, 1, batchArgs, 0, batchArgs.length);
            BatchRouter.main(batchArgs);
            return;
        }

        // "multi-batch" 서브 커맨드 → BatchRouter.runMultiBatch로 위임
        if (args.length > 0 && args[0].equalsIgnoreCase("multi-batch")) {
            String[] mbArgs = new String[args.length - 1];
            System.arraycopy(args, 1, mbArgs, 0, mbArgs.length);
            BatchRouter.runMultiBatch(mbArgs);
            return;
        }

        // UTF-8 출력 설정
        try {
            System.setOut(new PrintStream(System.out, true, StandardCharsets.UTF_8));
            System.setErr(new PrintStream(System.err, true, StandardCharsets.UTF_8));
        } catch (Exception e) {
            // 무시
        }

        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println("           한국형 Raptor 경로탐색 엔진 v1.0.0-SNAPSHOT           ");
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println();

        // GTFS 데이터 경로
        Path gtfsDir = Path.of("data/gtfs");

        if (!gtfsDir.toFile().exists()) {
            System.err.println("오류: GTFS 데이터 디렉토리가 존재하지 않습니다: " + gtfsDir);
            System.err.println("data/gtfs/ 디렉토리에 GTFS 파일을 준비해주세요.");
            System.exit(1);
        }

        try {
            // ═══════════════════════════════════════════════════════════════
            // Step 1: GTFS 로드
            // ═══════════════════════════════════════════════════════════════
            System.out.println("[1/4] GTFS 데이터 로드 중...");
            long startTime = System.currentTimeMillis();

            GtfsLoader loader = new GtfsLoader(gtfsDir);
            GtfsBundle gtfs = loader.load();

            long elapsed = System.currentTimeMillis() - startTime;
            System.out.printf("  완료: %,d 정류장, %,d 노선, %,d 트립 (%.1f초)%n",
                gtfs.getStopCount(), gtfs.getRouteCount(), gtfs.getTripCount(), elapsed / 1000.0);

            // ═══════════════════════════════════════════════════════════════
            // Step 2: TransitData 빌드
            // ═══════════════════════════════════════════════════════════════
            System.out.println("[2/4] Raptor 데이터 구조 생성 중...");
            long buildStart = System.currentTimeMillis();

            TransitDataBuilder builder = new TransitDataBuilder(gtfs);
            transitData = builder.build();  // 전역 변수에 저장

            long buildElapsed = System.currentTimeMillis() - buildStart;
            System.out.printf("  완료: %,d 패턴, %,d 트립 (%.1f초)%n",
                transitData.getRouteCount(), transitData.getTotalTripCount(), buildElapsed / 1000.0);

            // ═══════════════════════════════════════════════════════════════
            // Step 3: OSM 도로망 로드 (선택적)
            // ═══════════════════════════════════════════════════════════════
            streetNetwork = null;  // 전역 변수에 저장
            Path osmPath = Path.of("data/osm/south-korea.osm.pbf");

            if (Files.exists(osmPath)) {
                System.out.println("[3/4] OSM 도로망 로드 중...");
                long osmStart = System.currentTimeMillis();

                try {
                    OsmLoader osmLoader = new OsmLoader(osmPath);
                    streetNetwork = osmLoader.load();

                    long osmElapsed = System.currentTimeMillis() - osmStart;
                    System.out.printf("  완료: %s (%.1f초)%n", streetNetwork, osmElapsed / 1000.0);
                } catch (Exception e) {
                    System.err.println("  OSM 로드 실패 (직선 거리 사용): " + e.getMessage());
                }
            } else {
                System.out.println("[3/4] OSM 파일 없음 - 직선 거리 사용");
                System.out.println("  (OSM 활성화: data/osm/south-korea.osm.pbf 파일 추가)");
            }

            // ═══════════════════════════════════════════════════════════════
            // Step 4: KoreanRaptor 초기화
            // ═══════════════════════════════════════════════════════════════
            System.out.println("[4/4] Raptor 엔진 초기화...");
            long raptorStart = System.currentTimeMillis();

            KoreanRaptor raptor = new KoreanRaptor(transitData, streetNetwork);

            long raptorElapsed = System.currentTimeMillis() - raptorStart;
            System.out.printf("  완료: %s (%.1f초)%n", raptor, raptorElapsed / 1000.0);
            System.out.printf("  도보 거리: %s%n", raptor.isUsingOsm() ? "OSM 기반 (실제 도로)" : "직선 거리 (Haversine)");

            // 총 소요 시간
            long totalElapsed = System.currentTimeMillis() - startTime;
            System.out.println();
            System.out.println("═══════════════════════════════════════════════════════════════");
            System.out.printf("  초기화 완료! (%.1f초)%n", totalElapsed / 1000.0);
            System.out.println("═══════════════════════════════════════════════════════════════");
            System.out.println();

            // ═══════════════════════════════════════════════════════════════
            // 커맨드라인 인자가 있으면 바로 검색 실행
            // ═══════════════════════════════════════════════════════════════
            if (args.length >= 5) {
                double fromLat = Double.parseDouble(args[0]);
                double fromLon = Double.parseDouble(args[1]);
                double toLat = Double.parseDouble(args[2]);
                double toLon = Double.parseDouble(args[3]);
                int departureTime = parseTime(args[4]);

                if (args.length >= 6) {
                    maxResults = Integer.parseInt(args[5]);
                }

                searchAndPrint(raptor, fromLat, fromLon, toLat, toLon, departureTime);
            } else {
                // 대화형 CLI
                runInteractiveCli(raptor);
            }

        } catch (Exception e) {
            System.err.println("오류 발생: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    /**
     * 경로 검색 및 출력
     */
    private static void searchAndPrint(KoreanRaptor raptor,
                                        double fromLat, double fromLon,
                                        double toLat, double toLon,
                                        int departureTime) {
        String modeStr = useMultiCriteria ? "MULTI_CRITERIA" : "STANDARD";
        System.out.printf("검색 [%s]: (%.4f, %.4f) → (%.4f, %.4f) @ %s 이후, 최대 %d개%n",
            modeStr, fromLat, fromLon, toLat, toLon, formatTime(departureTime), maxResults);
        System.out.println("─────────────────────────────────────────────────────");

        long searchStart = System.currentTimeMillis();

        List<RaptorPath<KoreanTripSchedule>> paths;
        if (useMultiCriteria) {
            paths = raptor.routeMultiCriteria(fromLat, fromLon, toLat, toLon, departureTime);
        } else {
            paths = raptor.route(fromLat, fromLon, toLat, toLon, departureTime);
        }

        long searchElapsed = System.currentTimeMillis() - searchStart;

        if (paths.isEmpty()) {
            System.out.println("경로를 찾을 수 없습니다.");
            return;
        }

        // 요청 시간 이후 출발하는 경로만 필터링 + 출발시간순 정렬
        List<RaptorPath<KoreanTripSchedule>> filteredPaths = paths.stream()
            .filter(p -> p.startTime() >= departureTime)  // 요청 시간 이후만
            .sorted(Comparator.comparingInt(RaptorPath::startTime))  // 출발시간 순
            .collect(Collectors.toList());

        if (filteredPaths.isEmpty()) {
            System.out.printf("전체 %d개 경로 중 %s 이후 출발 경로가 없습니다.%n",
                paths.size(), formatTime(departureTime));
            return;
        }

        System.out.printf("%s 이후 경로 %d개 (전체 %d개, %.3f초)%n%n",
            formatTime(departureTime), filteredPaths.size(), paths.size(), searchElapsed / 1000.0);

        int pathNum = 1;
        for (RaptorPath<KoreanTripSchedule> path : filteredPaths) {
            printPath(pathNum++, path, raptor);
            if (pathNum > maxResults) break;
        }
    }

    /**
     * 경로 출력
     */
    private static void printPath(int num, RaptorPath<KoreanTripSchedule> path, KoreanRaptor raptor) {
        int startTime = path.startTime();
        int endTime = path.endTime();
        int duration = path.durationInSeconds();
        int transfers = path.numberOfTransfers();

        System.out.printf("■ 경로 %d: %s 출발 → %s 도착 (%d분, 환승 %d회)%n",
            num,
            formatTime(startTime),
            formatTime(endTime),
            duration / 60,
            transfers
        );

        // 각 구간 출력
        PathLeg<?> leg = path.accessLeg();
        int legNum = 1;

        while (leg != null) {
            if (leg.isAccessLeg()) {
                int walkTime = leg.duration();
                if (walkTime > 0) {
                    System.out.printf("  %d. 도보 %d분 → %s%n",
                        legNum++, walkTime / 60,
                        raptor.getStopName(leg.toStop()));
                }
            } else if (leg.isTransitLeg()) {
                TransitPathLeg<KoreanTripSchedule> transitLeg = (TransitPathLeg<KoreanTripSchedule>) leg;
                KoreanTripSchedule trip = transitLeg.trip();
                String routeName = trip.getRouteShortName();

                System.out.printf("  %d. [%s] %s %s → %s %s%n",
                    legNum++,
                    routeName,
                    raptor.getStopName(transitLeg.fromStop()),
                    formatTime(transitLeg.fromTime()),
                    raptor.getStopName(transitLeg.toStop()),
                    formatTime(transitLeg.toTime())
                );
            } else if (leg.isTransferLeg()) {
                int walkTime = leg.duration();
                System.out.printf("  %d. 환승 도보 %d분%n", legNum++, walkTime / 60);
            } else if (leg.isEgressLeg()) {
                int walkTime = leg.duration();
                if (walkTime > 0) {
                    System.out.printf("  %d. 도보 %d분 → 목적지%n", legNum++, walkTime / 60);
                }
            }

            // EgressLeg는 마지막 leg이므로 nextLeg() 호출 불가
            leg = leg.isEgressLeg() ? null : leg.nextLeg();
        }

        System.out.println();
    }

    // 전역 데이터 (시나리오 모드용)
    private static TransitData transitData;
    private static StreetNetwork streetNetwork;

    /**
     * 대화형 CLI
     */
    private static void runInteractiveCli(KoreanRaptor raptor) {
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println("  대화형 경로 검색");
        System.out.println("───────────────────────────────────────────────────────────────");
        System.out.println("  입력: 출발위도 출발경도 도착위도 도착경도 시간 [결과수]");
        System.out.println("  예시: 37.5547 126.9707 37.4979 127.0276 09:00 5");
        System.out.println("  명령: q(종료), n=숫자(결과수 변경), mc(MULTI_CRITERIA), std(STANDARD)");
        System.out.println("  시나리오: scenario (시나리오 모드 진입)");
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println();

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            String line;
            printPrompt();

            while ((line = reader.readLine()) != null) {
                line = line.trim();

                if (line.equalsIgnoreCase("q") || line.equalsIgnoreCase("quit") || line.equalsIgnoreCase("exit")) {
                    System.out.println("종료합니다.");
                    break;
                }

                if (line.isEmpty()) {
                    printPrompt();
                    continue;
                }

                // 결과수 변경 명령
                if (line.startsWith("n=")) {
                    try {
                        maxResults = Integer.parseInt(line.substring(2));
                        System.out.println("결과수를 " + maxResults + "개로 변경했습니다.");
                    } catch (NumberFormatException e) {
                        System.out.println("형식 오류. 예: n=10");
                    }
                    printPrompt();
                    continue;
                }

                // MULTI_CRITERIA 모드 전환
                if (line.equalsIgnoreCase("mc")) {
                    useMultiCriteria = true;
                    System.out.println("검색 모드: MULTI_CRITERIA (파레토 최적)");
                    printPrompt();
                    continue;
                }

                // STANDARD 모드 전환
                if (line.equalsIgnoreCase("std")) {
                    useMultiCriteria = false;
                    System.out.println("검색 모드: STANDARD (최단 시간)");
                    printPrompt();
                    continue;
                }

                // 시나리오 모드 진입
                if (line.equalsIgnoreCase("scenario") || line.equalsIgnoreCase("sc")) {
                    ScenarioCli scenarioCli = new ScenarioCli(transitData, streetNetwork, reader, raptor);
                    boolean returnToMain = scenarioCli.run();
                    if (!returnToMain) {
                        System.out.println("종료합니다.");
                        break;
                    }
                    printPrompt();
                    continue;
                }

                try {
                    String[] parts = line.split("\\s+");
                    if (parts.length < 5) {
                        System.out.println("형식 오류. 예: 37.5547 126.9707 37.4979 127.0276 09:00");
                        printPrompt();
                        continue;
                    }

                    double fromLat = Double.parseDouble(parts[0]);
                    double fromLon = Double.parseDouble(parts[1]);
                    double toLat = Double.parseDouble(parts[2]);
                    double toLon = Double.parseDouble(parts[3]);
                    int departureTime = parseTime(parts[4]);

                    // 6번째 인자가 있으면 결과수로 사용
                    if (parts.length >= 6) {
                        maxResults = Integer.parseInt(parts[5]);
                    }

                    searchAndPrint(raptor, fromLat, fromLon, toLat, toLon, departureTime);

                } catch (NumberFormatException e) {
                    System.out.println("숫자 형식 오류: " + e.getMessage());
                } catch (Exception e) {
                    System.out.println("검색 오류: " + e.getMessage());
                }

                System.out.println();
                printPrompt();
            }
        } catch (Exception e) {
            System.err.println("CLI 오류: " + e.getMessage());
        }
    }

    /**
     * 프롬프트 출력
     */
    private static void printPrompt() {
        String modeStr = useMultiCriteria ? "MC" : "STD";
        System.out.printf("[%s, n=%d] > ", modeStr, maxResults);
    }

    /**
     * 시간 포맷팅 (초 → HH:MM)
     */
    private static String formatTime(int seconds) {
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }

    /**
     * 시간 파싱 (HH:MM → 초)
     */
    private static int parseTime(String timeStr) {
        String[] parts = timeStr.split(":");
        int h = Integer.parseInt(parts[0]);
        int m = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
        return h * 3600 + m * 60;
    }

}
