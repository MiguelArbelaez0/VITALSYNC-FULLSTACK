$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Inicia Docker Desktop con el motor Linux.' }
if (-not (Test-Path -LiteralPath '.env')) { throw 'Falta .env. Prepara la configuracion local sin cambiar las credenciales existentes de PostgreSQL.' }
$configText = docker compose -p vitalsync config --format json
if ($LASTEXITCODE -ne 0) { throw 'Configuracion Compose invalida.' }
$config = ($configText -join "`n") | ConvertFrom-Json
if ($config.name -ne 'vitalsync' -or $config.volumes.vitalsync_data.name -ne 'vitalsync_vitalsync_data' -or -not $config.volumes.vitalsync_data.external) { throw 'El despliegue debe usar vitalsync y su volumen principal externo.' }
if ($config.services.db.environment.POSTGRES_DB -ne 'vitalsync') { throw 'La base principal esperada es vitalsync. Revisa la configuracion antes de iniciar.' }
docker volume inspect vitalsync_vitalsync_data --format '{{.Name}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No existe el volumen principal. Detenido para evitar una base vacia. Restaura un respaldo en un volumen revisado.' }
# Only the unified db service may be running against the principal PGDATA.
$holders = docker ps -q --filter 'volume=vitalsync_vitalsync_data'
if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar quien usa el volumen principal.' }
foreach ($holder in $holders) {
    $labelsText = docker inspect $holder --format '{{json .Config.Labels}}'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo inspeccionar un contenedor del volumen principal.' }
    $labels = ($labelsText -join "`n") | ConvertFrom-Json
    if ($labels.'com.docker.compose.project' -ne 'vitalsync' -or $labels.'com.docker.compose.service' -ne 'db') { throw "Otro contenedor usa el volumen principal: $holder. Deten la operacion para evitar dos servidores sobre PGDATA." }
}
docker compose -p vitalsync up -d --build --wait
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose no pudo iniciar VITALSYNC. Revisa docker compose -p vitalsync logs.' }
$frontendPort = $config.services.frontend.ports[0].published
$backendPort = $config.services.backend.ports[0].published
Write-Host "Login compartido: http://localhost:$frontendPort/login"
Write-Host "Paciente: http://localhost:$frontendPort/portal"
Write-Host "Medico: http://localhost:$frontendPort/doctor"
Write-Host "OpenAPI: http://localhost:$backendPort/docs"
