$ErrorActionPreference = "Stop"

$botDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$siteDir = Join-Path $botDir "site"
$python = "C:\Users\jade6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

New-Item -ItemType Directory -Force -Path $siteDir | Out-Null
Set-Location $siteDir
& $python -m http.server 8765 --bind 127.0.0.1

