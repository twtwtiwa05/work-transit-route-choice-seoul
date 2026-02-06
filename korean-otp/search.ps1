# Korean Raptor 경로 검색
# 사용법: .\search.ps1 출발위도 출발경도 도착위도 도착경도 시간 [결과수]
# 예시: .\search.ps1 37.5547 126.9707 37.4979 127.0276 09:00 5

# 콘솔 UTF-8 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"

Push-Location $PSScriptRoot

$jarFile = "build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar"

if ($args.Count -ge 5) {
    & "$env:JAVA_HOME\bin\java.exe" "-Xmx8G" "-Dfile.encoding=UTF-8" "-Dstdout.encoding=UTF-8" "-Dstderr.encoding=UTF-8" "-jar" $jarFile $args
} else {
    & "$env:JAVA_HOME\bin\java.exe" "-Xmx8G" "-Dfile.encoding=UTF-8" "-Dstdout.encoding=UTF-8" "-Dstderr.encoding=UTF-8" "-jar" $jarFile
}

Pop-Location
