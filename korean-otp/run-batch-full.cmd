@echo off
chcp 65001 > nul
setlocal

REM ═══════════════════════════════════════════════════════════════
REM  OTP Batch Router - 프로덕션 실행 스크립트 (1.26M OD)
REM
REM  사용법:
REM    run-batch-full.cmd                    → 기본 설정으로 실행
REM    run-batch-full.cmd <input> <output>   → 사용자 지정 파일
REM
REM  예상 소요: ~8시간 (43.4 req/s 기준)
REM  체크포인트 지원: 중단 후 재실행 시 자동 이어하기
REM ═══════════════════════════════════════════════════════════════

set JAVA_HOME=C:\Program Files\Java\jdk-21
set PATH=%JAVA_HOME%\bin;%PATH%

cd /d "%~dp0"

REM 기본값 설정
set INPUT_FILE=data\od_pairs_filtered.csv
set OUTPUT_FILE=batch_result_iter0.ndjson
set THREADS=16

REM 인자가 제공된 경우 사용
if not "%~1"=="" set INPUT_FILE=%~1
if not "%~2"=="" set OUTPUT_FILE=%~2
if not "%~3"=="" set THREADS=%~3

echo.
echo ===================================================================
echo  OTP Batch Router - Production Run
echo ===================================================================
echo  Input:   %INPUT_FILE%
echo  Output:  %OUTPUT_FILE%
echo  Threads: %THREADS%
echo  Memory:  40GB (G1GC)
echo ===================================================================
echo.

REM 입력 파일 존재 확인
if not exist "%INPUT_FILE%" (
    echo [ERROR] 입력 파일이 없습니다: %INPUT_FILE%
    echo.
    echo main\output\od_pairs_filtered.csv를 data\ 디렉토리에 복사하세요:
    echo   copy ..\main\output\od_pairs_filtered.csv data\od_pairs_filtered.csv
    echo.
    pause
    exit /b 1
)

REM JAR 파일 확인
if not exist "build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar" (
    echo [ERROR] JAR 파일이 없습니다.
    echo gradlew.bat fatJar 를 먼저 실행하세요.
    pause
    exit /b 1
)

REM 체크포인트 파일 존재 시 알림
if exist "%OUTPUT_FILE%.progress" (
    echo [INFO] 체크포인트 발견 - 이전 진행에서 이어서 실행합니다.
    echo.
)

REM 실행
java ^
    -Xmx40G ^
    -XX:+UseG1GC ^
    -XX:MaxGCPauseMillis=200 ^
    -XX:+ParallelRefProcEnabled ^
    -Dfile.encoding=UTF-8 ^
    -jar build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar ^
    batch "%INPUT_FILE%" "%OUTPUT_FILE%" %THREADS%

echo.
echo ===================================================================
echo  배치 실행 완료
echo  출력 파일: %OUTPUT_FILE%
echo ===================================================================
pause
