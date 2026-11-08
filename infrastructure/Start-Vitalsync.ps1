$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Inicia Docker Desktop con el motor Linux antes de continuar.' }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
$settings = @{}
Get-Content -LiteralPath '.env' | ForEach-Object { if ($_ -match '^([A-Z_]+)=(.*)$') { $settings[$Matches[1]] = $Matches[2] } }
$ports = @($settings['VITALSYNC_FRONTEND_PORT'], $settings['VITALSYNC_BACKEND_PORT'], $settings['VITALSYNC_POSTGRES_PORT'])
$ownPorts = (docker compose ps --format json | ConvertFrom-Json | ForEach-Object { $_.Publishers | ForEach-Object { $_.PublishedPort } })
foreach ($port in $ports) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort ([int]$port) -ErrorAction SilentlyContinue
    if ($listener -and ([int]$port -notin $ownPorts)) { throw "Puerto $port ocupado por otro servicio. Cambia el puerto VITALSYNC correspondiente en .env." }
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose no pudo iniciar VITALSYNC. Revisa docker compose logs.' }
Write-Host "Portal: http://localhost:$($settings['VITALSYNC_FRONTEND_PORT'])"
Write-Host "OpenAPI: http://localhost:$($settings['VITALSYNC_BACKEND_PORT'])/docs"
