$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$envPath = Join-Path $PWD ".env"
if (-not (Test-Path $envPath)) {
    throw ".env not found. Copy .env.example to .env and fill in values first."
}

Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"')
        Set-Item -Path "env:$name" -Value $value
    }
}

if (-not $env:DIGITAL_OCEAN_API_KEY) {
    throw "DIGITAL_OCEAN_API_KEY is missing from .env"
}

$doctl = Get-Command doctl -ErrorAction SilentlyContinue
if (-not $doctl) {
    throw "doctl is not installed. Run: winget install DigitalOcean.Doctl"
}

doctl auth init --access-token $env:DIGITAL_OCEAN_API_KEY | Out-Null

$DropletName = "polymarket-mm-bot"
$Region = "tor1"
$Size = "s-1vcpu-2gb"
$Image = "docker-20-04"
$SshKeyId = "38701609"
$RemoteDir = "/opt/polymarket-mm-bot"

$existing = doctl compute droplet list --format Name --no-header | Where-Object { $_ -eq $DropletName }
if (-not $existing) {
    Write-Host "Creating droplet $DropletName in $Region..."
    doctl compute droplet create $DropletName `
        --region $Region `
        --size $Size `
        --image $Image `
        --ssh-keys $SshKeyId `
        --wait
} else {
    Write-Host "Droplet $DropletName already exists."
}

$dropletId = (doctl compute droplet list --format ID,Name --no-header | Where-Object { $_ -match "^(\d+)\s+$DropletName$" } | ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
if (-not $dropletId) {
    throw "Could not find droplet ID for $DropletName"
}

$ip = doctl compute droplet get $dropletId --format PublicIPv4 --no-header
if (-not $ip) {
    throw "Droplet has no public IP yet."
}

Write-Host "Droplet IP: $ip"

$firewallName = "$DropletName-fw"
$existingFw = doctl compute firewall list --format Name --no-header | Where-Object { $_ -eq $firewallName }
if (-not $existingFw) {
    Write-Host "Creating firewall..."
    doctl compute firewall create `
        --name $firewallName `
        --droplet-ids $dropletId `
        --inbound-rules "protocol:tcp,ports:22,source_addresses:0.0.0.0/0,source_addresses:::/0 protocol:tcp,ports:8000,source_addresses:0.0.0.0/0,source_addresses:::/0" `
        --outbound-rules "protocol:tcp,ports:all,destination_addresses:0.0.0.0/0,destination_addresses:::/0 protocol:udp,ports:all,destination_addresses:0.0.0.0/0,destination_addresses:::/0 protocol:icmp,destination_addresses:0.0.0.0/0,destination_addresses:::/0" | Out-Null
}

$archive = Join-Path $env:TEMP "polymarket-mm-bot.tgz"
if (Test-Path $archive) { Remove-Item $archive -Force }

Write-Host "Packaging project..."
tar -czf $archive `
    --exclude=.git `
    --exclude=.venv `
    --exclude=venv `
    --exclude=__pycache__ `
    --exclude=.pytest_cache `
    --exclude=.ruff_cache `
    -C $PWD .

Write-Host "Uploading to droplet..."
ssh -o StrictHostKeyChecking=accept-new "root@$ip" "mkdir -p $RemoteDir"
scp $archive "root@${ip}:${RemoteDir}/app.tgz"
scp $envPath "root@${ip}:${RemoteDir}/.env"

Write-Host "Building and starting services..."
$remoteScript = @"
set -euo pipefail
cd $RemoteDir
rm -rf app && mkdir app
tar -xzf app.tgz -C app
cp .env app/.env
cd app
sed -i 's|postgresql://|postgresql+psycopg://|g' .env
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi
$COMPOSE -f docker-compose.prod.yml up -d --build
$COMPOSE -f docker-compose.prod.yml run --rm bot alembic upgrade head
$COMPOSE -f docker-compose.prod.yml ps
"@

ssh "root@$ip" $remoteScript

Write-Host ""
Write-Host "Deployment complete."
Write-Host "Dashboard: http://$ip:8000/health"
