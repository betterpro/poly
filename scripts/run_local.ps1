param(
    # Run both in the current terminal (dashboard in background). Default opens two windows.
    [switch]$SameWindow,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Stop-PortListener {
    param([int]$Port)
    Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            if ($_ -and $_ -ne 0) {
                Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            }
        }
}

if (-not (Test-Path ".env")) {
    throw ".env not found. Copy .env.example to .env and fill in values first."
}

if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "Ensuring Redis is up (docker compose)..."
    docker compose up -d redis | Out-Null
}

Write-Host "Running database migrations..."
python -m alembic upgrade head
$env:SKIP_STARTUP_MIGRATIONS = "1"

Write-Host "Stopping any existing dashboard on port $Port..."
Stop-PortListener -Port $Port
Start-Sleep -Seconds 1

$dashboardArgs = @(
    "-m", "uvicorn", "polymarket_mm_bot.dashboard.app:app",
    "--host", "0.0.0.0", "--port", "$Port"
)
$botCommand = @"
Set-Location '$Root'
`$env:SKIP_STARTUP_MIGRATIONS = '1'
`$env:PAPER_TRADING = 'true'
`$env:LIVE_TRADING_CONFIRMED = 'false'
python -m polymarket_mm_bot.main
"@

function Stop-BackgroundDashboard {
    if ($script:DashboardProcess -and -not $script:DashboardProcess.HasExited) {
        Write-Host "Stopping dashboard..."
        Stop-Process -Id $script:DashboardProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "Dashboard: http://localhost:$Port"
Write-Host ""

if ($SameWindow) {
    Write-Host "Starting dashboard (background) and bot (foreground). Press Ctrl+C to stop both."
    $script:DashboardProcess = Start-Process python `
        -ArgumentList $dashboardArgs `
        -PassThru `
        -WindowStyle Hidden `
        -WorkingDirectory $Root

    Start-Sleep -Seconds 2
    if ($script:DashboardProcess.HasExited) {
        throw "Dashboard failed to start. Check that port $Port is free."
    }

    try {
        $env:PAPER_TRADING = "true"
        $env:LIVE_TRADING_CONFIRMED = "false"
        python -m polymarket_mm_bot.main
    }
    finally {
        Stop-BackgroundDashboard
    }
}
else {
    Write-Host "Opening two terminals: dashboard + paper bot."
    Write-Host "Close each window (or Ctrl+C) to stop that service."
    Write-Host ""

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$Root'; `$env:SKIP_STARTUP_MIGRATIONS = '1'; Write-Host 'Dashboard -> http://localhost:$Port'; python -m uvicorn polymarket_mm_bot.dashboard.app:app --host 0.0.0.0 --port $Port"
    )

    Start-Sleep -Seconds 1

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        $botCommand
    )
}
