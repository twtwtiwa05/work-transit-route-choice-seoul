$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
Set-Location -Path $PSScriptRoot
java -Xmx40G -jar build\libs\korean-raptor-1.0.0-SNAPSHOT-all.jar batch data\od_sample_10.csv batch_test_10.ndjson 4
