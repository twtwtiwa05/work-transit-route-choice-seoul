package kr.otp.scenario;

/**
 * 시나리오 수정 작업의 기본 인터페이스.
 *
 * 모든 수정 타입(배차간격, 노선비활성화, 노선추가 등)은 이 인터페이스를 구현.
 */
public interface Modification {

    /**
     * 수정 타입 열거형
     */
    enum Type {
        HEADWAY,        // 배차간격 조정
        TRIP_COUNT,     // 배차수 조정
        DISABLE_ROUTE,  // 노선 비활성화
        ADD_ROUTE       // 신규 노선 추가
    }

    /**
     * 수정 타입 반환
     */
    Type getType();

    /**
     * 사람이 읽을 수 있는 설명 반환
     * 예: "2호선: 배차간격 2.0배"
     */
    String getDescription();

    /**
     * 영향받는 노선 수 반환
     */
    int getAffectedRouteCount();

    /**
     * 영향받는 트립 수 반환
     */
    int getAffectedTripCount();
}
