package kr.otp.util;

import org.opentripplanner.raptor.spi.IntIterator;

import java.util.BitSet;
import java.util.NoSuchElementException;

/**
 * BitSet을 순회하는 IntIterator 구현.
 *
 * Raptor의 routeIndexIterator에서 사용.
 * BitSet의 설정된 비트 인덱스를 순차적으로 반환.
 *
 * OTP Raptor SPI의 IntIterator 인터페이스 구현.
 */
public class BitSetIntIterator implements IntIterator {

    private final BitSet bitSet;
    private int currentIndex;
    private int nextIndex;

    public BitSetIntIterator(BitSet bitSet) {
        this.bitSet = bitSet;
        this.currentIndex = -1;
        this.nextIndex = bitSet.nextSetBit(0);
    }

    /**
     * 다음 요소가 있는지 확인
     *
     * @return 다음 요소 존재 여부
     */
    @Override
    public boolean hasNext() {
        return nextIndex >= 0;
    }

    /**
     * 다음 값 반환하고 커서 이동
     *
     * @return 다음 인덱스 값
     */
    @Override
    public int next() {
        if (nextIndex < 0) {
            throw new NoSuchElementException("No more elements");
        }
        currentIndex = nextIndex;
        nextIndex = bitSet.nextSetBit(currentIndex + 1);
        return currentIndex;
    }

    /**
     * BitSet에서 설정된 비트 수 반환
     *
     * @return 설정된 비트 수
     */
    public int size() {
        return bitSet.cardinality();
    }

    /**
     * BitSet이 비어있는지 확인
     *
     * @return 비어있으면 true
     */
    public boolean isEmpty() {
        return bitSet.isEmpty();
    }

    /**
     * 새로운 Iterator 생성 (재사용 불가능하므로)
     *
     * @param bitSet 순회할 BitSet
     * @return 새로운 Iterator
     */
    public static BitSetIntIterator of(BitSet bitSet) {
        return new BitSetIntIterator(bitSet);
    }

    /**
     * int 배열로 변환
     *
     * @return 설정된 비트 인덱스 배열
     */
    public int[] toArray() {
        return bitSet.stream().toArray();
    }
}
