$ErrorActionPreference = "Stop"

$botDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\jade6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$serverScript = Join-Path $botDir "serve_report.ps1"

$listening = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $serverScript) -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Set-Location $botDir
& $python "ms_kakao_news_bot.py"
