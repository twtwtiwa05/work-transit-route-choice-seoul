package kr.otp.scenario;

import kr.otp.raptor.spi.KoreanRoute;
import kr.otp.raptor.spi.KoreanTimeTable;
import kr.otp.raptor.spi.KoreanTripPattern;
import kr.otp.raptor.spi.KoreanTripSchedule;

import java.util.ArrayList;
import java.util.List;

/**
 * 신규 노선 추가 수정.
 *
 * 새로운 노선을 추가합니다.
 * - 기존 정류장들을 연결
 * - 정류장 간 소요시간 지정
 * - 운행 시간표 지정 (첫차, 막차, 배차간격)
 */
public class AddRouteModification implements Modification {

    // 노선 정보
    private final String routeId;
    private final String routeShortName;
    private final int routeType;  // GTFS route_type (1=지하철, 3=버스)

    // 정류장 정보
    private final List<Integer> stopIndices;
    private final List<String> stopNames;

    // 소요시간 (정류장 간, 분 단위)
    private final List<Integer> travelTimesMinutes;

    // 시간표
    private final int firstDepartureSeconds;  // 첫차 (초)
    private final int lastDepartureSeconds;   // 막차 (초)
    private final int headwaySeconds;         // 배차간격 (초)

    // 생성된 트립 수
    private final int tripCount;

    // 생성된 노선 (캐시)
    private KoreanRoute generatedRoute;

    public AddRouteModification(
            String routeId,
            String routeShortName,
            int routeType,
            List<Integer> stopIndices,
            List<String> stopNames,
            List<Integer> travelTimesMinutes,
            int firstDepartureSeconds,
            int lastDepartureSeconds,
            int headwaySeconds) {

        this.routeId = routeId;
        this.routeShortName = routeShortName;
        this.routeType = routeType;
        this.stopIndices = new ArrayList<>(stopIndices);
        this.stopNames = new ArrayList<>(stopNames);
        this.travelTimesMinutes = new ArrayList<>(travelTimesMinutes);
        this.firstDepartureSeconds = firstDepartureSeconds;
        this.lastDepartureSeconds = lastDepartureSeconds;
        this.headwaySeconds = headwaySeconds;

        // 트립 수 계산
        int span = lastDepartureSeconds - firstDepartureSeconds;
        this.tripCount = (span / headwaySeconds) + 1;
    }

    @Override
    public Type getType() {
        return Type.ADD_ROUTE;
    }

    @Override
    public String getDescription() {
        return String.format("신규 노선 '%s' 추가 (%d개 정류장, %d개 트립)",
            routeShortName, stopIndices.size(), tripCount);
    }

    @Override
    public int getAffectedRouteCount() {
        return 1;
    }

    @Override
    public int getAffectedTripCount() {
        return tripCount;
    }

    public String getRouteId() {
        return routeId;
    }

    public String getRouteShortName() {
        return routeShortName;
    }

    public int getRouteType() {
        return routeType;
    }

    public List<Integer> getStopIndices() {
        return stopIndices;
    }

    public List<String> getStopNames() {
        return stopNames;
    }

    public int getTripCount() {
        return tripCount;
    }

    /**
     * 노선 생성
     *
     * @param patternIndex 패턴 인덱스
     * @return 생성된 노선
     */
    public KoreanRoute generateRoute(int patternIndex) {
        if (generatedRoute != null &&
            ((KoreanTripPattern) generatedRoute.pattern()).patternIndex() == patternIndex) {
            return generatedRoute;
        }

        // 1. 패턴 생성
        int[] stopIndexArray = stopIndices.stream().mapToInt(Integer::intValue).toArray();
        int slackIndex = getSlackIndex(routeType);

        KoreanTripPattern pattern = new KoreanTripPattern(
            patternIndex,
            stopIndexArray,
            slackIndex,
            getRouteTypeString(routeType) + "_" + routeShortName
        );

        // 2. 트립 스케줄 생성
        List<KoreanTripSchedule> schedules = new ArrayList<>();
        int stopCount = stopIndices.size();

        // 정류장 간 소요시간 (초)
        int[] travelSeconds = new int[stopCount - 1];
        for (int i = 0; i < stopCount - 1; i++) {
            if (i < travelTimesMinutes.size()) {
                travelSeconds[i] = travelTimesMinutes.get(i) * 60;
            } else {
                travelSeconds[i] = 5 * 60;  // 기본 5분
            }
        }

        // 정차 시간 (초)
        int dwellTime = 30;  // 기본 30초

        // 트립 생성
        int tripIndex = 0;
        for (int departure = firstDepartureSeconds; departure <= lastDepartureSeconds; departure += headwaySeconds) {
            int[] arrivals = new int[stopCount];
            int[] departures = new int[stopCount];

            arrivals[0] = departure;
            departures[0] = departure;

            for (int s = 1; s < stopCount; s++) {
                arrivals[s] = departures[s - 1] + travelSeconds[s - 1];
                departures[s] = arrivals[s] + (s < stopCount - 1 ? dwellTime : 0);
            }

            KoreanTripSchedule schedule = new KoreanTripSchedule(
                departure,
                arrivals,
                departures,
                pattern,
                "NEW_" + routeId + "_" + tripIndex,
                routeShortName
            );

            schedules.add(schedule);
            tripIndex++;
        }

        // 3. 시간표 생성
        KoreanTimeTable timeTable = new KoreanTimeTable(
            schedules.toArray(new KoreanTripSchedule[0])
        );

        // 4. 노선 생성
        generatedRoute = new KoreanRoute(
            pattern,
            timeTable,
            routeId,
            routeShortName,
            routeShortName,
            routeType
        );

        return generatedRoute;
    }

    /**
     * route_type에서 slackIndex 변환
     */
    private int getSlackIndex(int routeType) {
        switch (routeType) {
            case 0:  // Tram
            case 1:  // Subway
            case 2:  // Rail
                return 0;  // SLACK_SUBWAY
            case 3:  // Bus
            default:
                return 1;  // SLACK_BUS
        }
    }

    /**
     * route_type 문자열 변환
     */
    private String getRouteTypeString(int routeType) {
        switch (routeType) {
            case 0: return "TRAM";
            case 1: return "SUBWAY";
            case 2: return "RAIL";
            case 3: return "BUS";
            default: return "OTHER";
        }
    }

    @Override
    public String toString() {
        return String.format("AddRouteModification[%s, stops=%d, trips=%d, %s~%s, 간격=%d분]",
            routeShortName, stopIndices.size(), tripCount,
            formatTime(firstDepartureSeconds), formatTime(lastDepartureSeconds),
            headwaySeconds / 60);
    }

    private String formatTime(int seconds) {
        int h = seconds / 3600;
        int m = (seconds % 3600) / 60;
        return String.format("%02d:%02d", h, m);
    }

    /**
     * 빌더 클래스
     */
    public static class Builder {
        private String routeId;
        private String routeShortName;
        private int routeType = 3;  // 기본: 버스
        private List<Integer> stopIndices = new ArrayList<>();
        private List<String> stopNames = new ArrayList<>();
        private List<Integer> travelTimesMinutes = new ArrayList<>();
        private int firstDepartureSeconds = 6 * 3600;  // 06:00
        private int lastDepartureSeconds = 23 * 3600;  // 23:00
        private int headwaySeconds = 10 * 60;  // 10분

        public Builder routeId(String routeId) {
            this.routeId = routeId;
            return this;
        }

        public Builder routeShortName(String name) {
            this.routeShortName = name;
            return this;
        }

        public Builder routeType(int type) {
            this.routeType = type;
            return this;
        }

        public Builder addStop(int stopIndex, String stopName) {
            this.stopIndices.add(stopIndex);
            this.stopNames.add(stopName);
            return this;
        }

        public Builder travelTime(int minutes) {
            this.travelTimesMinutes.add(minutes);
            return this;
        }

        public Builder travelTimes(List<Integer> minutes) {
            this.travelTimesMinutes.addAll(minutes);
            return this;
        }

        public Builder schedule(int firstHour, int firstMinute,
                               int lastHour, int lastMinute,
                               int headwayMinutes) {
            this.firstDepartureSeconds = firstHour * 3600 + firstMinute * 60;
            this.lastDepartureSeconds = lastHour * 3600 + lastMinute * 60;
            this.headwaySeconds = headwayMinutes * 60;
            return this;
        }

        public Builder firstDeparture(String time) {
            String[] parts = time.split(":");
            int h = Integer.parseInt(parts[0]);
            int m = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
            this.firstDepartureSeconds = h * 3600 + m * 60;
            return this;
        }

        public Builder lastDeparture(String time) {
            String[] parts = time.split(":");
            int h = Integer.parseInt(parts[0]);
            int m = parts.length > 1 ? Integer.parseInt(parts[1]) : 0;
            this.lastDepartureSeconds = h * 3600 + m * 60;
            return this;
        }

        public Builder headwayMinutes(int minutes) {
            this.headwaySeconds = minutes * 60;
            return this;
        }

        public AddRouteModification build() {
            if (routeId == null) {
                routeId = "NEW_ROUTE_" + System.currentTimeMillis();
            }
            if (routeShortName == null) {
                routeShortName = routeId;
            }

            return new AddRouteModification(
                routeId,
                routeShortName,
                routeType,
                stopIndices,
                stopNames,
                travelTimesMinutes,
                firstDepartureSeconds,
                lastDepartureSeconds,
                headwaySeconds
            );
        }
    }

    public static Builder builder() {
        return new Builder();
    }
}
