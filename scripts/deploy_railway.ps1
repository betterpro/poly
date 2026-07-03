param(
    [switch]$ImportVars,
    [switch]$Deploy
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is not installed. Install with: npm install -g @railway/cli"
    }
}

Require-Command railway

Write-Host @"

Railway setup (one-time)
========================
1. Create a Railway project and connect this GitHub repo.
2. Add PostgreSQL: + New -> Database -> PostgreSQL (keep default name Postgres).
3. Add two app services in the same project, named exactly:
     dashboard  -> web service (generate a public domain)
     bot        -> worker (no public domain needed)
4. For each app service, open Settings -> Config-as-code and set:
     dashboard: /deploy/railway/dashboard.railway.toml
     bot:       /deploy/railway/bot.railway.toml
5. In the project Variables tab, set shared vars from deploy/railway/production.env.example.
   Required:
     DATABASE_URL=${{Postgres.DATABASE_PRIVATE_URL}}
     DASHBOARD_PASSWORD=<strong password>
   Or run: .\scripts\deploy_railway.ps1 -ImportVars  (after railway link)
6. Create a project token (Project Settings -> Tokens) and set GitHub secret RAILWAY_TOKEN.
7. Disable Railway's default GitHub auto-deploy if you want CI-only deploys
   (this repo uses .github/workflows/deploy-railway.yml on push to master).

"@

if ($ImportVars) {
    $envFile = Join-Path $PWD "deploy\railway\production.env.example"
    if (-not (Test-Path $envFile)) {
        throw "Missing $envFile"
    }
    Write-Host "Importing shared variables from production.env.example..."
    railway variable import --file $envFile --yes
    Write-Host "Done. Set DASHBOARD_PASSWORD in the Railway dashboard and seal secrets."
}

if ($Deploy) {
    Write-Host "Deploying dashboard and bot..."
    railway up --service dashboard --detach
    railway up --service bot --detach
    Write-Host "Deploy triggered. Check the Railway dashboard for status."
}
