package kr.otp.core;

import kr.otp.CalibrationConfig;
import kr.otp.osm.StreetNetwork;
import kr.otp.raptor.data.TransitData;
import kr.otp.raptor.spi.KoreanAccessEgress;
import kr.otp.raptor.spi.KoreanTransitDataProvider;
import kr.otp.raptor.spi.KoreanTripSchedule;

import org.opentripplanner.raptor.RaptorService;
import org.opentripplanner.raptor.api.model.GeneralizedCostRelaxFunction;
import org.opentripplanner.raptor.api.model.RaptorAccessEgress;
import org.opentripplanner.raptor.api.model.RelaxFunction;
import org.opentripplanner.raptor.api.path.RaptorPath;
import org.opentripplanner.raptor.api.request.Optimization;
import org.opentripplanner.raptor.api.request.RaptorEnvironment;
import org.opentripplanner.raptor.api.request.RaptorProfile;
import org.opentripplanner.raptor.api.request.RaptorRequest;
import org.opentripplanner.raptor.api.request.RaptorRequestBuilder;
import org.opentripplanner.raptor.api.request.RaptorTuningParameters;
import org.opentripplanner.raptor.api.model.SearchDirection;
import org.opentripplanner.raptor.api.response.RaptorResponse;
import org.opentripplanner.raptor.configure.RaptorConfig;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Collection;
import java.util.List;

/**
 * 한국형 Raptor 경로탐색 엔진.
 *
 * OTP Raptor 모듈을 래핑하여 한국 GTFS 데이터로 경로 탐색을 수행.
 * 좌표 기반 검색을 지원하며, 내부적으로 가까운 정류장을 찾아 Raptor를 실행.
 *
 * 사용법:
 * <pre>
 * KoreanRaptor raptor = new KoreanRaptor(transitData);
 * List<RaptorPath<KoreanTripSchedule>> paths = raptor.route(
 *     fromLat, fromLon,
 *     toLat, toLon,
 *     departureTime
 * );
 * </pre>
 */
public class KoreanRaptor {

    private static final Logger LOG = LoggerFactory.getLogger(KoreanRaptor.class);

    // 설정 상수 - 성공률 최적화 (99%+ 목표)
    private static final double MAX_ACCESS_WALK_METERS = 800.0;   // 출발지에서 정류장까지 최대 도보 거리 (400→800)
    private static final double MAX_EGRESS_WALK_METERS = 800.0;   // 정류장에서 목적지까지 최대 도보 거리 (400→800)
    private static final double WALK_SPEED_MPS = 1.2;             // 도보 속도 (m/s)
    private static final int MAX_RESULTS = 5;                     // 최대 결과 수
    private static final int MAX_ACCESS_STOPS = 30;               // 최대 출발 정류장 수
    private static final int MAX_EGRESS_STOPS = 30;               // 최대 도착 정류장 수

    // MULTI_CRITERIA 최적화 설정
    private static final int MC_ADDITIONAL_TRANSFERS = 3;         // MC 모드 추가 환승 제한 (3회)
    private static final double MC_RELAX_RATIO = 1.0;             // 비용 완화 없음 (정확한 파레토)
    private static final int MC_RELAX_SLACK = 0;                  // 슬랙 없음

    private final TransitData transitData;
    private final KoreanTransitDataProvider provider;
    private final RaptorService<KoreanTripSchedule> raptorService;
    private final AccessEgressFinder accessEgressFinder;
    private final CalibrationConfig calibrationConfig;

    public KoreanRaptor(TransitData transitData) {
        this(transitData, (StreetNetwork) null);
    }

    public KoreanRaptor(TransitData transitData, StreetNetwork streetNetwork) {
        this(transitData, streetNetwork, CalibrationConfig.defaults());
    }

    public KoreanRaptor(TransitData transitData, StreetNetwork streetNetwork, CalibrationConfig calibrationConfig) {
        this.transitData = transitData;
        this.calibrationConfig = calibrationConfig;
        this.provider = new KoreanTransitDataProvider(transitData, calibrationConfig);

        // Raptor 설정 생성 (기본값 사용)
        RaptorConfig<KoreanTripSchedule> config = new RaptorConfig<>(
            new RaptorTuningParameters() {},  // 기본 튜닝 파라미터
            new RaptorEnvironment() {}        // 기본 환경
        );
        this.raptorService = new RaptorService<>(config);
        this.accessEgressFinder = new AccessEgressFinder(transitData, calibrationConfig.getWalkReluctance());

        // OSM 도로망 설정 (선택적)
        if (streetNetwork != null) {
            this.accessEgressFinder.setStreetNetwork(streetNetwork);
        }

        LOG.info("KoreanRaptor 초기화 완료: {} (OSM: {}, config: {})", provider, isUsingOsm(), calibrationConfig);
    }

    /**
     * 기존 AccessEgressFinder를 재사용하는 생성자 (시나리오 모드용).
     *
     * OSM 매핑을 다시 계산하지 않아 빠른 초기화 가능.
     *
     * @param transitData 대중교통 데이터
     * @param existingFinder 재사용할 AccessEgressFinder
     */
    public KoreanRaptor(TransitData transitData, AccessEgressFinder existingFinder) {
        this(transitData, existingFinder, CalibrationConfig.defaults());
    }

    public KoreanRaptor(TransitData transitData, AccessEgressFinder existingFinder, CalibrationConfig calibrationConfig) {
        this.transitData = transitData;
        this.calibrationConfig = calibrationConfig;
        this.provider = new KoreanTransitDataProvider(transitData, calibrationConfig);

        RaptorConfig<KoreanTripSchedule> config = new RaptorConfig<>(
            new RaptorTuningParameters() {},
            new RaptorEnvironment() {}
        );
        this.raptorService = new RaptorService<>(config);
        this.accessEgressFinder = existingFinder;

        LOG.info("KoreanRaptor 초기화 완료 (AccessEgressFinder 재사용): {} (OSM: {})", provider, isUsingOsm());
    }

    /**
     * AccessEgressFinder 반환 (시나리오 모드에서 재사용)
     */
    public AccessEgressFinder getAccessEgressFinder() {
        return accessEgressFinder;
    }

    /**
     * OSM 기반 도보 경로 사용 여부
     */
    public boolean isUsingOsm() {
        return accessEgressFinder.isUsingOsm();
    }

    /**
     * 좌표 기반 경로 탐색
     *
     * @param fromLat 출발지 위도
     * @param fromLon 출발지 경도
     * @param toLat   목적지 위도
     * @param toLon   목적지 경도
     * @param departureTime 출발 시간 (초, 자정 기준. 예: 09:00 = 32400)
     * @return 탐색된 경로 목록 (Pareto 최적)
     */
    public List<RaptorPath<KoreanTripSchedule>> route(
        double fromLat, double fromLon,
        double toLat, double toLon,
        int departureTime
    ) {
        long startTime = System.currentTimeMillis();

        // 1. 출발지 근처 정류장 찾기 (Access) - 상위 N개만
        List<RaptorAccessEgress> accessPaths = accessEgressFinder.findAccess(
            fromLat, fromLon, MAX_ACCESS_WALK_METERS
        );
        if (accessPaths.isEmpty()) {
            LOG.warn("출발지 근처에 정류장이 없습니다: ({}, {})", fromLat, fromLon);
            return List.of();
        }
        if (accessPaths.size() > MAX_ACCESS_STOPS) {
            accessPaths = accessPaths.subList(0, MAX_ACCESS_STOPS);
        }

        // 2. 목적지 근처 정류장 찾기 (Egress) - 상위 N개만
        List<RaptorAccessEgress> egressPaths = accessEgressFinder.findEgress(
            toLat, toLon, MAX_EGRESS_WALK_METERS
        );
        if (egressPaths.isEmpty()) {
            LOG.warn("목적지 근처에 정류장이 없습니다: ({}, {})", toLat, toLon);
            return List.of();
        }
        if (egressPaths.size() > MAX_EGRESS_STOPS) {
            egressPaths = egressPaths.subList(0, MAX_EGRESS_STOPS);
        }

        LOG.debug("Access 정류장: {}개, Egress 정류장: {}개",
            accessPaths.size(), egressPaths.size());

        // 3. Raptor 요청 생성
        RaptorRequest<KoreanTripSchedule> request = buildRequest(
            accessPaths, egressPaths, departureTime
        );

        // 4. Raptor 실행
        RaptorResponse<KoreanTripSchedule> response = raptorService.route(request, provider);

        long elapsed = System.currentTimeMillis() - startTime;

        if (response.noConnectionFound()) {
            LOG.info("경로를 찾을 수 없습니다 ({}ms)", elapsed);
            return List.of();
        }

        Collection<RaptorPath<KoreanTripSchedule>> paths = response.paths();
        LOG.info("경로 {}개 발견 ({}ms)", paths.size(), elapsed);

        return List.copyOf(paths);
    }

    /**
     * MULTI_CRITERIA 모드 좌표 기반 경로 탐색
     *
     * 파레토 최적 경로를 반환합니다 (시간/환승/비용 trade-off).
     * STANDARD 모드보다 느리지만 (2~3초) 다양한 경로 옵션을 제공합니다.
     *
     * @param fromLat 출발지 위도
     * @param fromLon 출발지 경도
     * @param toLat   목적지 위도
     * @param toLon   목적지 경도
     * @param departureTime 출발 시간 (초, 자정 기준)
     * @return 파레토 최적 경로 목록 (시간/환승/비용 다양)
     */
    public List<RaptorPath<KoreanTripSchedule>> routeMultiCriteria(
        double fromLat, double fromLon,
        double toLat, double toLon,
        int departureTime
    ) {
        long startTime = System.currentTimeMillis();

        // 1. 출발지 근처 정류장 찾기
        List<RaptorAccessEgress> accessPaths = accessEgressFinder.findAccess(
            fromLat, fromLon, MAX_ACCESS_WALK_METERS
        );
        if (accessPaths.isEmpty()) {
            LOG.warn("출발지 근처에 정류장이 없습니다: ({}, {})", fromLat, fromLon);
            return List.of();
        }
        if (accessPaths.size() > MAX_ACCESS_STOPS) {
            accessPaths = accessPaths.subList(0, MAX_ACCESS_STOPS);
        }

        // 2. 목적지 근처 정류장 찾기
        List<RaptorAccessEgress> egressPaths = accessEgressFinder.findEgress(
            toLat, toLon, MAX_EGRESS_WALK_METERS
        );
        if (egressPaths.isEmpty()) {
            LOG.warn("목적지 근처에 정류장이 없습니다: ({}, {})", toLat, toLon);
            return List.of();
        }
        if (egressPaths.size() > MAX_EGRESS_STOPS) {
            egressPaths = egressPaths.subList(0, MAX_EGRESS_STOPS);
        }

        LOG.debug("MULTI_CRITERIA - Access: {}개, Egress: {}개",
            accessPaths.size(), egressPaths.size());

        // 3. MULTI_CRITERIA 요청 생성
        RaptorRequest<KoreanTripSchedule> request = buildMultiCriteriaRequest(
            accessPaths, egressPaths, departureTime
        );

        // 4. Raptor 실행
        RaptorResponse<KoreanTripSchedule> response = raptorService.route(request, provider);

        long elapsed = System.currentTimeMillis() - startTime;

        if (response.noConnectionFound()) {
            LOG.info("MULTI_CRITERIA 경로를 찾을 수 없습니다 ({}ms)", elapsed);
            return List.of();
        }

        Collection<RaptorPath<KoreanTripSchedule>> paths = response.paths();
        LOG.info("MULTI_CRITERIA 경로 {}개 발견 ({}ms)", paths.size(), elapsed);

        return List.copyOf(paths);
    }

    /**
     * 정류장 인덱스 기반 경로 탐색 (직접 지정)
     *
     * @param fromStopIndex 출발 정류장 인덱스
     * @param toStopIndex   도착 정류장 인덱스
     * @param departureTime 출발 시간 (초)
     * @return 탐색된 경로 목록
     */
    public List<RaptorPath<KoreanTripSchedule>> routeByStopIndex(
        int fromStopIndex,
        int toStopIndex,
        int departureTime
    ) {
        // Access: 출발 정류장에서 바로 탑승 (도보 0초)
        List<RaptorAccessEgress> accessPaths = List.of(
            new KoreanAccessEgress(fromStopIndex, 0, 0)
        );

        // Egress: 도착 정류장에서 바로 하차 (도보 0초)
        List<RaptorAccessEgress> egressPaths = List.of(
            new KoreanAccessEgress(toStopIndex, 0, 0)
        );

        RaptorRequest<KoreanTripSchedule> request = buildRequest(
            accessPaths, egressPaths, departureTime
        );

        RaptorResponse<KoreanTripSchedule> response = raptorService.route(request, provider);

        if (response.noConnectionFound()) {
            return List.of();
        }

        return List.copyOf(response.paths());
    }

    /**
     * Raptor 요청 빌드
     */
    private RaptorRequest<KoreanTripSchedule> buildRequest(
        List<RaptorAccessEgress> accessPaths,
        List<RaptorAccessEgress> egressPaths,
        int departureTime
    ) {
        RaptorRequestBuilder<KoreanTripSchedule> builder = new RaptorRequestBuilder<>();

        builder
            .profile(RaptorProfile.STANDARD)                  // 표준 모드 (빠름)
            .searchDirection(SearchDirection.FORWARD)   // 정방향 탐색
            .searchParams()
                .earliestDepartureTime(departureTime)
                .searchWindowInSeconds(calibrationConfig.getSearchWindowSeconds())
                .timetable(true)                        // 시간표 기반 검색
                .addAccessPaths(accessPaths)
                .addEgressPaths(egressPaths);

        // 추가 최적화: 최대 환승 횟수 제한
        builder.searchParams().numberOfAdditionalTransfers(3);  // 최대 3회 환승

        return builder.build();
    }

    /**
     * MULTI_CRITERIA Raptor 요청 빌드 (최적화 적용)
     *
     * 최적화 기법:
     * 1. relaxC1: 비용 10% + 300초 완화 → 파레토 세트 크기 감소
     * 2. 검색 범위 축소: 600초 윈도우, 2회 추가 환승
     * 3. PARETO_CHECK_AGAINST_DESTINATION: 목적지 기준 조기 가지치기
     */
    private RaptorRequest<KoreanTripSchedule> buildMultiCriteriaRequest(
        List<RaptorAccessEgress> accessPaths,
        List<RaptorAccessEgress> egressPaths,
        int departureTime
    ) {
        RaptorRequestBuilder<KoreanTripSchedule> builder = new RaptorRequestBuilder<>();

        // 파레토 비용 완화 함수: v' = v * 1.1 + 300초
        // → 비용이 10% + 300초 이내면 "지배되지 않음"으로 간주
        RelaxFunction relaxC1 = GeneralizedCostRelaxFunction.of(MC_RELAX_RATIO, MC_RELAX_SLACK);

        builder
            .profile(RaptorProfile.MULTI_CRITERIA)          // 파레토 최적 모드
            .searchDirection(SearchDirection.FORWARD)
            .enableOptimization(Optimization.PARETO_CHECK_AGAINST_DESTINATION)  // 목적지 최적화
            .searchParams()
                .earliestDepartureTime(departureTime)
                .searchWindowInSeconds(calibrationConfig.getSearchWindowSeconds())
                .timetable(true)
                .numberOfAdditionalTransfers(MC_ADDITIONAL_TRANSFERS)  // 2회 (축소)
                .addAccessPaths(accessPaths)
                .addEgressPaths(egressPaths);

        // MULTI_CRITERIA 설정: relaxC1 적용
        builder.withMultiCriteria(mc -> mc.withRelaxC1(relaxC1));

        return builder.build();
    }

    /**
     * 정류장 이름 조회
     */
    public String getStopName(int stopIndex) {
        return transitData.getStopName(stopIndex);
    }

    /**
     * 정류장 GTFS ID 조회
     */
    public String getStopId(int stopIndex) {
        return transitData.getStopId(stopIndex);
    }

    /**
     * 정류장 좌표 조회
     * @return [위도, 경도] 배열 또는 null
     */
    public double[] getStopCoords(int stopIndex) {
        return transitData.getStopCoords(stopIndex);
    }

    /**
     * 정류장 개수
     */
    public int getStopCount() {
        return transitData.getStopCount();
    }

    /**
     * 노선 개수
     */
    public int getRouteCount() {
        return transitData.getRouteCount();
    }

    /**
     * TransitData 반환
     */
    public TransitData getTransitData() {
        return transitData;
    }

    /**
     * Provider 반환
     */
    public KoreanTransitDataProvider getProvider() {
        return provider;
    }

    @Override
    public String toString() {
        return String.format("KoreanRaptor[stops=%d, routes=%d, trips=%d]",
            transitData.getStopCount(),
            transitData.getRouteCount(),
            transitData.getTotalTripCount());
    }
}
