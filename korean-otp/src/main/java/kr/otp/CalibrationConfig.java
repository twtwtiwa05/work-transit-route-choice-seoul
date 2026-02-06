package kr.otp;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 보정 파라미터 외부 설정.
 *
 * calibration_config.json에서 로드하거나 기본값 사용.
 * Jackson 의존 없이 수동 JSON 파싱.
 */
public class CalibrationConfig {

    private final int transferCostSeconds;
    private final int firstBoardCostSeconds;
    private final double waitReluctance;
    private final double walkReluctance;
    private final int searchWindowSeconds;

    private CalibrationConfig(int transferCostSeconds, int firstBoardCostSeconds,
                              double waitReluctance, double walkReluctance,
                              int searchWindowSeconds) {
        this.transferCostSeconds = transferCostSeconds;
        this.firstBoardCostSeconds = firstBoardCostSeconds;
        this.waitReluctance = waitReluctance;
        this.walkReluctance = walkReluctance;
        this.searchWindowSeconds = searchWindowSeconds;
    }

    public static CalibrationConfig defaults() {
        return new CalibrationConfig(120, 60, 1.0, 1.0, 1800);
    }

    /**
     * JSON 파일에서 설정 로드. 누락된 필드는 기본값 사용.
     */
    public static CalibrationConfig fromJsonFile(Path path) throws IOException {
        int transferCost = 120;
        int firstBoardCost = 60;
        double waitRel = 1.0;
        double walkRel = 1.0;
        int searchWindow = 1800;

        try (BufferedReader reader = Files.newBufferedReader(path)) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line.trim());
            }
            String json = sb.toString();

            transferCost = parseIntValue(json, "transferCostSeconds", transferCost);
            firstBoardCost = parseIntValue(json, "firstBoardCostSeconds", firstBoardCost);
            waitRel = parseDoubleValue(json, "waitReluctance", waitRel);
            walkRel = parseDoubleValue(json, "walkReluctance", walkRel);
            searchWindow = parseIntValue(json, "searchWindowSeconds", searchWindow);
        }

        return new CalibrationConfig(transferCost, firstBoardCost, waitRel, walkRel, searchWindow);
    }

    private static int parseIntValue(String json, String key, int defaultValue) {
        String val = extractValue(json, key);
        if (val == null) return defaultValue;
        try {
            return Integer.parseInt(val);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    private static double parseDoubleValue(String json, String key, double defaultValue) {
        String val = extractValue(json, key);
        if (val == null) return defaultValue;
        try {
            return Double.parseDouble(val);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    /**
     * 간단한 JSON 값 추출: "key": value 또는 "key": "value"
     */
    private static String extractValue(String json, String key) {
        String pattern = "\"" + key + "\"";
        int idx = json.indexOf(pattern);
        if (idx < 0) return null;

        int colonIdx = json.indexOf(':', idx + pattern.length());
        if (colonIdx < 0) return null;

        // 콜론 뒤 공백 스킵
        int start = colonIdx + 1;
        while (start < json.length() && json.charAt(start) == ' ') start++;
        if (start >= json.length()) return null;

        // 값 끝 찾기 (쉼표, }, 또는 문자열 끝)
        int end = start;
        while (end < json.length() && json.charAt(end) != ',' && json.charAt(end) != '}') end++;

        return json.substring(start, end).trim();
    }

    public int getTransferCostSeconds() { return transferCostSeconds; }
    public int getFirstBoardCostSeconds() { return firstBoardCostSeconds; }
    public double getWaitReluctance() { return waitReluctance; }
    public double getWalkReluctance() { return walkReluctance; }
    public int getSearchWindowSeconds() { return searchWindowSeconds; }

    @Override
    public String toString() {
        return String.format("CalibrationConfig{transfer=%ds, firstBoard=%ds, wait=%.2f, walk=%.2f, window=%ds}",
            transferCostSeconds, firstBoardCostSeconds, waitReluctance, walkReluctance, searchWindowSeconds);
    }
}
