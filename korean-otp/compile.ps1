$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
Push-Location $PSScriptRoot
& .\gradlew.bat compileJava
Pop-Location
