@echo off
chcp 65001 >nul
echo ========================================
echo   Phase 4 Iteration 1: OTP 배치 실행
echo ========================================
echo.
echo 설정:
echo   walkReluctance = 5.25
echo   transferCostSeconds = 360
echo   OD 수: 1,263,225
echo   예상 소요: ~8시간
echo.
echo 시작 시간: %date% %time%
echo.

set JAVA_HOME=C:\Program Files\Java\jdk-21
set PATH=%JAVA_HOME%\bin;%PATH%

cd /d "%~dp0"

java -Xmx40G -XX:+UseG1GC -jar build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar batch data\od_pairs_filtered.csv batch_result_iter1.ndjson 16

echo.
echo ========================================
echo 완료 시간: %date% %time%
echo ========================================
echo.
echo 다음 단계:
echo   cd ..\main
echo   python scripts/calibration/calibration_orchestrator.py --step pipeline --iteration 1 --ndjson ..\korean-otp\batch_result_iter1.ndjson
echo.
pause
