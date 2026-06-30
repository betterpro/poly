$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Import-DotEnv {
    param([string]$Path)
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"')
            Set-Item -Path "env:$name" -Value $value
        }
    }
}

Import-DotEnv (Join-Path $PWD ".env")

if (-not $env:DIGITAL_OCEAN_API_KEY) {
    throw "DIGITAL_OCEAN_API_KEY is missing from .env"
}

$doctl = Get-Command doctl -ErrorAction SilentlyContinue
if (-not $doctl) {
    throw "Install doctl first: winget install DigitalOcean.Doctl"
}

doctl auth init --access-token $env:DIGITAL_OCEAN_API_KEY | Out-Null

python deploy/generate_app_spec.py

$existingApp = doctl apps list --format Spec.Name --no-header | Where-Object { $_ -eq "polymarket-mm-bot" }
if ($existingApp) {
    $appId = (doctl apps list --format ID,Spec.Name --no-header | Where-Object { $_ -match "polymarket-mm-bot" } | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
    Write-Host "Updating existing App Platform app $appId..."
    doctl apps update $appId --spec deploy/app-spec.generated.yaml --wait
} else {
    Write-Host "Creating App Platform app..."
    doctl apps create --spec deploy/app-spec.generated.yaml --wait
}

$appId = (doctl apps list --format ID,Spec.Name --no-header | Where-Object { $_ -match "polymarket-mm-bot" } | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
$url = doctl apps get $appId --format DefaultIngress --no-header
Write-Host ""
Write-Host "App Platform deployment complete."
Write-Host "Dashboard: https://$url/health"
