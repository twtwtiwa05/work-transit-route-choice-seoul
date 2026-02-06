package kr.otp.scenario;

import kr.otp.core.AccessEgressFinder;
import kr.otp.core.KoreanRaptor;
import kr.otp.osm.StreetNetwork;
import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanTripSchedule;

import org.opentripplanner.raptor.api.path.PathLeg;
import org.opentripplanner.raptor.api.path.RaptorPath;
import org.opentripplanner.raptor.api.path.TransitPathLeg;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 시나리오 모드 CLI.
 *
 * 대화형으로 시나리오를 생성하고 테스트하는 인터페이스.
 */
public class ScenarioCli {

    private final ScenarioManager manager;
    private final TransitData originalData;
    private final StreetNetwork streetNetwork;
    private final BufferedReader reader;

    // 원본 Raptor (AccessEgressFinder 재사용 위해 보관)
    private final KoreanRaptor originalRaptor;

    // 시나리오 적용된 Raptor (null이면 미적용)
    private KoreanRaptor scenarioRaptor;

    // 검색 설정
    private int maxResults = 5;

    public ScenarioCli(TransitData transitData, StreetNetwork streetNetwork, BufferedReader reader) {
        this(transitData, streetNetwork, reader, null);
    }

    public ScenarioCli(TransitData transitData, StreetNetwork streetNetwork, BufferedReader reader, KoreanRaptor originalRaptor) {
        this.originalData = transitData;
        this.streetNetwork = streetNetwork;
        this.reader = reader;
        this.originalRaptor = originalRaptor;
        this.manager = new ScenarioManager(transitData);
    }

    /**
     * 시나리오 모드 실행
     *
     * @return true이면 메인 CLI로 복귀, false이면 프로그램 종료
     */
    public boolean run() throws IOException {
        System.out.println();
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println("  시나리오 모드");
        System.out.println("───────────────────────────────────────────────────────────────");
        System.out.println("  명령어: help, list, clear, apply, exit");
        System.out.println("  노선수정: headway <노선> <배율>, disable <노선>");
        System.out.println("  노선추가: add-route");
        System.out.println("  검색: search <출발lat> <출발lon> <도착lat> <도착lon> <시간>");
        System.out.println("  비교: compare <출발lat> <출발lon> <도착lat> <도착lon> <시간>");
        System.out.println("═══════════════════════════════════════════════════════════════");
        System.out.println();

        String line;
        printPrompt();

        while ((line = reader.readLine()) != null) {
            line = line.trim();

            if (line.isEmpty()) {
                printPrompt();
                continue;
            }

            // 명령어 파싱
            String[] parts = line.split("\\s+", 2);
            String command = parts[0].toLowerCase();
            String args = parts.length > 1 ? parts[1] : "";

            try {
                switch (command) {
                    case "exit":
                    case "quit":
                    case "q":
                        System.out.println("시나리오 모드 종료. 메인 CLI로 복귀합니다.");
                        return true;

                    case "help":
                    case "?":
                        printHelp();
                        break;

                    case "list":
                    case "ls":
                        printModifications();
                        break;

                    case "clear":
                        manager.clearModifications();
                        scenarioRaptor = null;
                        System.out.println("모든 수정사항이 제거되었습니다.");
                        break;

                    case "headway":
                        handleHeadway(args);
                        break;

                    case "disable":
                        handleDisable(args);
                        break;

                    case "add-route":
                        handleAddRoute();
                        break;

                    case "apply":
                        handleApply();
                        break;

                    case "search":
                        handleSearch(args);
                        break;

                    case "compare":
                        handleCompare(args);
                        break;

                    case "route":
                    case "routes":
                        handleRouteSearch(args);
                        break;

                    case "stop":
                    case "stops":
                        handleStopSearch(args);
                        break;

                    case "n":
                        handleSetMaxResults(args);
                        break;

                    default:
                        System.out.println("알 수 없는 명령어: " + command);
                        System.out.println("'help'로 명령어 목록을 확인하세요.");
                }
            } catch (Exception e) {
                System.out.println("오류: " + e.getMessage());
            }

            System.out.println();
            printPrompt();
        }

        return false;
    }

    private void printPrompt() {
        String status = scenarioRaptor != null ? "적용됨" : "미적용";
        System.out.printf("[SCENARIO:%d, %s] > ", manager.getModificationCount(), status);
    }

    private void printHelp() {
        System.out.println();
        System.out.println("=== 시나리오 명령어 ===");
        System.out.println();
        System.out.println("  list                    현재 수정사항 보기");
        System.out.println("  clear                   모든 수정사항 제거");
        System.out.println("  apply                   시나리오 적용");
        System.out.println("  exit                    시나리오 모드 종료");
        System.out.println();
        System.out.println("=== 노선 수정 ===");
        System.out.println();
        System.out.println("  headway <노선> <배율>   배차간격 조정");
        System.out.println("    예: headway 2호선 2.0    (배차간격 2배 = 운행 감소)");
        System.out.println("    예: headway 신분당선 0.5 (배차간격 0.5배 = 운행 증가)");
        System.out.println();
        System.out.println("  disable <노선>          노선 비활성화");
        System.out.println("    예: disable 9호선");
        System.out.println("    예: disable 버스_402");
        System.out.println();
        System.out.println("=== 노선 추가 ===");
        System.out.println();
        System.out.println("  add-route               대화형 노선 추가");
        System.out.println();
        System.out.println("=== 검색 ===");
        System.out.println();
        System.out.println("  search <출발lat> <출발lon> <도착lat> <도착lon> <시간>");
        System.out.println("    시나리오 적용된 상태에서 경로 검색");
        System.out.println();
        System.out.println("  compare <출발lat> <출발lon> <도착lat> <도착lon> <시간>");
        System.out.println("    원본 vs 시나리오 비교");
        System.out.println();
        System.out.println("=== 유틸리티 ===");
        System.out.println();
        System.out.println("  route <검색어>          노선 검색");
        System.out.println("  stop <검색어>           정류장 검색");
        System.out.println("  n=<숫자>                결과 수 변경");
    }

    private void printModifications() {
        if (manager.getModificationCount() == 0) {
            System.out.println("수정사항이 없습니다.");
            return;
        }

        System.out.println(manager.getSummary());
    }

    private void handleHeadway(String args) {
        String[] parts = args.split("\\s+");
        if (parts.length < 2) {
            System.out.println("사용법: headway <노선명> <배율>");
            System.out.println("예: headway 2호선 2.0");
            return;
        }

        String routePattern = parts[0];
        double factor;
        try {
            factor = Double.parseDouble(parts[1]);
        } catch (NumberFormatException e) {
            System.out.println("배율은 숫자여야 합니다: " + parts[1]);
            return;
        }

        if (factor <= 0) {
            System.out.println("배율은 0보다 커야 합니다.");
            return;
        }

        String result = manager.addHeadway(routePattern, factor);
        System.out.println(result);
        scenarioRaptor = null;  // 재적용 필요
    }

    private void handleDisable(String args) {
        if (args.isEmpty()) {
            System.out.println("사용법: disable <노선명>");
            System.out.println("예: disable 9호선");
            return;
        }

        String result = manager.addDisable(args);
        System.out.println(result);
        scenarioRaptor = null;  // 재적용 필요
    }

    private void handleAddRoute() throws IOException {
        System.out.println();
        System.out.println("=== 신규 노선 추가 ===");
        System.out.println();

        AddRouteModification.Builder builder = AddRouteModification.builder();

        // 노선 이름
        System.out.print("노선 이름: ");
        String name = reader.readLine().trim();
        if (name.isEmpty()) {
            System.out.println("취소되었습니다.");
            return;
        }
        builder.routeShortName(name);
        builder.routeId("NEW_" + name.replace(" ", "_"));

        // 노선 타입
        System.out.print("노선 타입 (1=지하철, 2=철도, 3=버스) [3]: ");
        String typeStr = reader.readLine().trim();
        int routeType = typeStr.isEmpty() ? 3 : Integer.parseInt(typeStr);
        builder.routeType(routeType);

        // 정류장 입력
        System.out.println();
        System.out.println("정류장을 입력하세요 (이름으로 검색, 'done'으로 완료):");

        List<Integer> stopIndices = new ArrayList<>();
        List<String> stopNames = new ArrayList<>();
        int stopNum = 1;

        while (true) {
            System.out.printf("  %d번 정류장: ", stopNum);
            String input = reader.readLine().trim();

            if (input.equalsIgnoreCase("done") || input.isEmpty()) {
                if (stopIndices.size() < 2) {
                    System.out.println("최소 2개 정류장이 필요합니다.");
                    continue;
                }
                break;
            }

            // 정류장 검색
            List<StopSearcher.StopInfo> results = manager.searchStops(input, 5);

            if (results.isEmpty()) {
                System.out.println("    → 매칭되는 정류장이 없습니다.");
                continue;
            }

            if (results.size() == 1) {
                StopSearcher.StopInfo stop = results.get(0);
                System.out.printf("    → 선택됨: %s%n", stop.getName());
                builder.addStop(stop.getStopIndex(), stop.getName());
                stopIndices.add(stop.getStopIndex());
                stopNames.add(stop.getName());
                stopNum++;
            } else {
                System.out.println("    여러 개 매칭됨:");
                for (int i = 0; i < results.size(); i++) {
                    System.out.printf("      [%d] %s%n", i + 1, results.get(i).getName());
                }
                System.out.print("    선택 (번호): ");
                String choice = reader.readLine().trim();
                try {
                    int idx = Integer.parseInt(choice) - 1;
                    if (idx >= 0 && idx < results.size()) {
                        StopSearcher.StopInfo stop = results.get(idx);
                        System.out.printf("    → 선택됨: %s%n", stop.getName());
                        builder.addStop(stop.getStopIndex(), stop.getName());
                        stopIndices.add(stop.getStopIndex());
                        stopNames.add(stop.getName());
                        stopNum++;
                    }
                } catch (NumberFormatException e) {
                    System.out.println("    잘못된 입력입니다.");
                }
            }
        }

        // 소요시간 입력
        System.out.println();
        System.out.println("정류장 간 소요시간 (분):");

        List<Integer> travelTimes = new ArrayList<>();
        for (int i = 0; i < stopIndices.size() - 1; i++) {
            System.out.printf("  %s → %s: ", stopNames.get(i), stopNames.get(i + 1));
            String input = reader.readLine().trim();
            int minutes = input.isEmpty() ? 5 : Integer.parseInt(input);
            travelTimes.add(minutes);
            builder.travelTime(minutes);
        }

        // 시간표
        System.out.println();
        System.out.print("첫차 시간 [06:00]: ");
        String firstStr = reader.readLine().trim();
        if (!firstStr.isEmpty()) {
            builder.firstDeparture(firstStr);
        }

        System.out.print("막차 시간 [23:00]: ");
        String lastStr = reader.readLine().trim();
        if (!lastStr.isEmpty()) {
            builder.lastDeparture(lastStr);
        }

        System.out.print("배차간격 (분) [10]: ");
        String headwayStr = reader.readLine().trim();
        if (!headwayStr.isEmpty()) {
            builder.headwayMinutes(Integer.parseInt(headwayStr));
        }

        // 노선 생성
        AddRouteModification mod = builder.build();
        String result = manager.addNewRoute(mod);
        System.out.println();
        System.out.println(result);
        scenarioRaptor = null;  // 재적용 필요
    }

    private void handleApply() {
        System.out.println("시나리오 적용 중...");
        long start = System.currentTimeMillis();

        ScenarioTransitData scenarioData = manager.apply();
        TransitData wrappedData = createTransitDataWrapper(scenarioData);

        // 기존 AccessEgressFinder 재사용 (OSM 매핑 재계산 방지)
        if (originalRaptor != null) {
            AccessEgressFinder existingFinder = originalRaptor.getAccessEgressFinder();
            scenarioRaptor = new KoreanRaptor(wrappedData, existingFinder);
        } else {
            scenarioRaptor = new KoreanRaptor(wrappedData, streetNetwork);
        }

        long elapsed = System.currentTimeMillis() - start;
        System.out.printf("✓ 시나리오 적용 완료 (%.2f초)%n", elapsed / 1000.0);
        System.out.println(scenarioData);
    }

    /**
     * ScenarioTransitData를 TransitData처럼 사용하기 위한 래퍼
     */
    private TransitData createTransitDataWrapper(ScenarioTransitData scenario) {
        // ScenarioTransitData의 데이터로 새 TransitData 생성
        int stopCount = scenario.getStopCount();
        String[] stopIds = new String[stopCount];
        String[] stopNames = new String[stopCount];
        double[] stopLats = new double[stopCount];
        double[] stopLons = new double[stopCount];

        for (int i = 0; i < stopCount; i++) {
            stopIds[i] = scenario.getStopId(i);
            stopNames[i] = scenario.getStopName(i);
            stopLats[i] = scenario.getStopLat(i);
            stopLons[i] = scenario.getStopLon(i);
        }

        int routeCount = scenario.getRouteCount();
        kr.otp.raptor.spi.KoreanRoute[] routes = new kr.otp.raptor.spi.KoreanRoute[routeCount];
        for (int i = 0; i < routeCount; i++) {
            routes[i] = scenario.getRoute(i);
        }

        // 환승 정보는 원본에서 가져옴
        @SuppressWarnings("unchecked")
        List<kr.otp.raptor.spi.KoreanTransfer>[] transfersFrom = new List[stopCount];
        @SuppressWarnings("unchecked")
        List<kr.otp.raptor.spi.KoreanTransfer>[] transfersTo = new List[stopCount];

        for (int i = 0; i < stopCount; i++) {
            transfersFrom[i] = new ArrayList<>();
            var iter = scenario.getTransfersFrom(i);
            while (iter.hasNext()) {
                transfersFrom[i].add(iter.next());
            }

            transfersTo[i] = new ArrayList<>();
            var iter2 = scenario.getTransfersTo(i);
            while (iter2.hasNext()) {
                transfersTo[i].add(iter2.next());
            }
        }

        // routesByStop 계산
        int[][] routesByStop = new int[stopCount][];
        for (int i = 0; i < stopCount; i++) {
            routesByStop[i] = scenario.getRoutesByStop(i);
        }

        return new TransitData(
            stopCount,
            stopIds,
            stopNames,
            stopLats,
            stopLons,
            routes,
            transfersFrom,
            transfersTo,
            routesByStop,
            scenario.getServiceStartTime(),
            scenario.getServiceEndTime()
        );
    }

    private void handleSearch(String args) {
        if (scenarioRaptor == null) {
            System.out.println("시나리오가 적용되지 않았습니다. 'apply' 명령어를 먼저 실행하세요.");
            return;
        }

        double[] params = parseSearchParams(args);
        if (params == null) return;

        searchAndPrint(scenarioRaptor, params[0], params[1], params[2], params[3], (int) params[4], "시나리오");
    }

    private void handleCompare(String args) {
        double[] params = parseSearchParams(args);
        if (params == null) return;

        // 원본 검색 (기존 raptor 재사용)
        KoreanRaptor origRaptor;
        if (originalRaptor != null) {
            origRaptor = originalRaptor;
        } else {
            origRaptor = new KoreanRaptor(originalData, streetNetwork);
        }

        System.out.println("=== 원본 ===");
        List<RaptorPath<KoreanTripSchedule>> originalPaths =
            searchAndPrint(origRaptor, params[0], params[1], params[2], params[3], (int) params[4], "원본");

        // 시나리오 검색
        if (scenarioRaptor == null) {
            handleApply();
        }

        System.out.println("=== 시나리오 ===");
        List<RaptorPath<KoreanTripSchedule>> scenarioPaths =
            searchAndPrint(scenarioRaptor, params[0], params[1], params[2], params[3], (int) params[4], "시나리오");

        // 비교 결과
        printComparison(originalPaths, scenarioPaths);
    }

    private double[] parseSearchParams(String args) {
        String[] parts = args.split("\\s+");
        if (parts.length < 5) {
            System.out.println("사용법: search <출발lat> <출발lon> <도착lat> <도착lon> <시간>");
            System.out.println("예: search 37.5547 126.9707 37.4979 127.0276 09:00");
            return null;
        }

        try {
            double fromLat = Double.parseDouble(parts[0]);
            double fromLon = Double.parseDouble(parts[1]);
            double toLat = Double.parseDouble(parts[2]);
            double toLon = Double.parseDouble(parts[3]);
            int departureTime = parseTime(parts[4]);

            return new double[]{fromLat, fromLon, toLat, toLon, departureTime};
        } catch (NumberFormatException e) {
            System.out.println("숫자 형식 오류: " + e.getMessage());
            return null;
        }
    }

    private List<RaptorPath<KoreanTripSchedule>> searchAndPrint(
            KoreanRaptor raptor, double fromLat, double fromLon,
            double toLat, double toLon, int departureTime, String label) {

        long start = System.currentTimeMillis();
        List<RaptorPath<KoreanTripSchedule>> paths =
            raptor.routeMultiCriteria(fromLat, fromLon, toLat, toLon, departureTime);
        long elapsed = System.currentTimeMillis() - start;

        if (paths.isEmpty()) {
            System.out.printf("[%s] 경로 없음 (%.3f초)%n", label, elapsed / 1000.0);
            return paths;
        }

        // 필터링 및 정렬
        List<RaptorPath<KoreanTripSchedule>> filtered = paths.stream()
            .filter(p -> p.startTime() >= departureTime)
            .sorted(Comparator.comparingInt(RaptorPath::startTime))
            .limit(maxResults)
            .collect(Collectors.toList());

        System.out.printf("[%s] %d개 경로 (%.3f초)%n", label, filtered.size(), elapsed / 1000.0);

        int num = 1;
        for (RaptorPath<KoreanTripSchedule> path : filtered) {
            printPathShort(num++, path, raptor);
        }

        return filtered;
    }

    private void printPathShort(int num, RaptorPath<KoreanTripSchedule> path, KoreanRaptor raptor) {
        int duration = path.durationInSeconds() / 60;
        int transfers = path.numberOfTransfers();

        StringBuilder route = new StringBuilder();
        PathLeg<?> leg = path.accessLeg();
        while (leg != null) {
            if (leg.isTransitLeg()) {
                TransitPathLeg<KoreanTripSchedule> transitLeg = (TransitPathLeg<KoreanTripSchedule>) leg;
                if (route.length() > 0) route.append(" → ");
                route.append(transitLeg.trip().getRouteShortName());
            }
            leg = leg.isEgressLeg() ? null : leg.nextLeg();
        }

        System.out.printf("  %d. %s출발 %d분, 환승%d회: %s%n",
            num, formatTime(path.startTime()), duration, transfers, route);
    }

    private void printComparison(List<RaptorPath<KoreanTripSchedule>> original,
                                  List<RaptorPath<KoreanTripSchedule>> scenario) {
        System.out.println();
        System.out.println("=== 비교 결과 ===");
        System.out.println("┌─────────┬──────────┬──────────┬─────────┐");
        System.out.println("│         │ 원본     │ 시나리오 │ 차이    │");
        System.out.println("├─────────┼──────────┼──────────┼─────────┤");

        int origDur = original.isEmpty() ? -1 : original.get(0).durationInSeconds() / 60;
        int scenDur = scenario.isEmpty() ? -1 : scenario.get(0).durationInSeconds() / 60;
        String durDiff = (origDur >= 0 && scenDur >= 0) ?
            String.format("%+d분", scenDur - origDur) : "N/A";
        System.out.printf("│ 최단시간│ %4s분   │ %4s분   │ %7s │%n",
            origDur >= 0 ? origDur : "N/A",
            scenDur >= 0 ? scenDur : "N/A",
            durDiff);

        int origTrans = original.isEmpty() ? -1 : original.get(0).numberOfTransfers();
        int scenTrans = scenario.isEmpty() ? -1 : scenario.get(0).numberOfTransfers();
        String transDiff = (origTrans >= 0 && scenTrans >= 0) ?
            String.format("%+d회", scenTrans - origTrans) : "N/A";
        System.out.printf("│ 환승횟수│ %4s회   │ %4s회   │ %7s │%n",
            origTrans >= 0 ? origTrans : "N/A",
            scenTrans >= 0 ? scenTrans : "N/A",
            transDiff);

        System.out.printf("│ 경로수  │ %4d개   │ %4d개   │ %+4d개  │%n",
            original.size(), scenario.size(), scenario.size() - original.size());

        System.out.println("└─────────┴──────────┴──────────┴─────────┘");
    }

    private void handleRouteSearch(String args) {
        if (args.isEmpty()) {
            System.out.println("사용법: route <검색어>");
            return;
        }

        RouteSearcher.SearchResult result = manager.searchRoutes(args);
        System.out.println(result);

        if (!result.isEmpty() && result.getRouteCount() <= 10) {
            System.out.println("매칭 노선:");
            for (int idx : result.getRouteIndices()) {
                var route = originalData.getRoute(idx);
                System.out.printf("  [%d] %s (%d 트립)%n",
                    idx, route.getRouteShortName(), route.getTripCount());
            }
        }
    }

    private void handleStopSearch(String args) {
        if (args.isEmpty()) {
            System.out.println("사용법: stop <검색어>");
            return;
        }

        List<StopSearcher.StopInfo> results = manager.searchStops(args, 10);

        if (results.isEmpty()) {
            System.out.println("매칭되는 정류장이 없습니다.");
            return;
        }

        System.out.printf("'%s' 검색 결과 (%d개):%n", args, results.size());
        for (StopSearcher.StopInfo stop : results) {
            System.out.printf("  %s%n", stop);
        }
    }

    private void handleSetMaxResults(String args) {
        try {
            maxResults = Integer.parseInt(args.replace("=", ""));
            System.out.println("결과 수를 " + maxResults + "개로 변경했습니다.");
        } catch (NumberFormatException e) {
            System.out.println("숫자 형식 오류. 예: n=10");
        }
    }

    private int parseTime(String timeStr) {
        String[] parts = timeStr.split(":");
        int h = Integer.parseInt(parts[0]);
        int m = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
        return h * 3600 + m * 60;
    }

    private String formatTime(int seconds) {
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }
}
