@echo off
chcp 65001 > nul
setlocal

REM 100건 테스트 스크립트
set JAVA_HOME=C:\Program Files\Java\jdk-21
set PATH=%JAVA_HOME%\bin;%PATH%

cd /d "%~dp0"

echo.
echo === 100건 테스트 실행 ===
echo.

REM 100건만 추출
powershell -Command "Get-Content 'data\od_sample_1000.csv' -Head 101 | Set-Content 'data\od_test_100.csv' -Encoding UTF8"

java ^
    -Xmx40G ^
    -XX:+UseG1GC ^
    -Dfile.encoding=UTF-8 ^
    -jar build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar ^
    batch "data\od_test_100.csv" "test_result_100.ndjson" 8

echo.
echo === 테스트 완료 ===

REM 결과 검증
echo.
echo --- NDJSON 형식 확인 (첫 5줄 요약) ---
powershell -Command "$lines = Get-Content 'test_result_100.ndjson' -Head 5; foreach($line in $lines) { Write-Output ($line.Substring(0, [Math]::Min(200, $line.Length)) + '...') }"

echo.
echo --- summary 필드 확인 ---
powershell -Command "$line = Get-Content 'test_result_100.ndjson' -First 1; if($line -match 'summary') { Write-Output 'summary 필드 존재 확인' } else { Write-Output 'ERROR: summary 필드 없음!' }"

echo.
echo --- max 경로 수 확인 ---
powershell -Command "$lines = Get-Content 'test_result_100.ndjson'; $maxItins = 0; foreach($line in $lines) { $matches = [regex]::Matches($line, '\"startTime\"'); if($matches.Count -gt $maxItins) { $maxItins = $matches.Count } }; Write-Output \"최대 itinerary 수: $maxItins\""

pause
