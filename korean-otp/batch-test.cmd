@echo off
chcp 65001 >nul
setlocal

if "%JAVA_HOME%"=="" set JAVA_HOME=C:\Program Files\Java\jdk-21
set PATH=%JAVA_HOME%\bin;%PATH%

cd /d "%~dp0"

echo ============================================================
echo   배치 성능 테스트 (1000개 OD)
echo ============================================================
echo.

set INPUT=data/od_sample_1000.csv
set OUTPUT=batch_result.json
set THREADS=16

if not "%~1"=="" set INPUT=%~1
if not "%~2"=="" set OUTPUT=%~2
if not "%~3"=="" set THREADS=%~3

echo 입력: %INPUT%
echo 출력: %OUTPUT%
echo 스레드: %THREADS%
echo.

java -Xmx40G -cp "build/libs/korean-raptor-1.0.0-SNAPSHOT-all.jar" ^
     kr.otp.batch.BatchRouter "%INPUT%" "%OUTPUT%" %THREADS%

echo.
echo 테스트 완료!
pause
