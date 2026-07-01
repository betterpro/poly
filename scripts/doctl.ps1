$Doctl = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\DigitalOcean.Doctl_Microsoft.Winget.Source_8wekyb3d8bbwe\doctl.exe"
if (-not (Test-Path $Doctl)) {
    throw "doctl not found. Install with: winget install DigitalOcean.Doctl"
}
Set-Alias doctl $Doctl -Scope Global -Force
doctl @args
