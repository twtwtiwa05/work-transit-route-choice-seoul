@echo off
set JAVA_HOME=C:\Program Files\Java\jdk-21
set PATH=%JAVA_HOME%\bin;%PATH%
cd /d "%~dp0"
java -Xmx40G -jar build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar batch data\od_sample_10.csv batch_test_10.ndjson 4
pause
