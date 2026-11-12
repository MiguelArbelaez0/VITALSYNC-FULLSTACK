$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$configText = docker compose -p vitalsync config --format json
if ($LASTEXITCODE -ne 0) { throw 'Compose invalido.' }
$config = ($configText -join "`n") | ConvertFrom-Json
$dbUser = $config.services.db.environment.POSTGRES_USER
$dbName = $config.services.db.environment.POSTGRES_DB
$exists = docker compose -p vitalsync exec -T db psql -U $dbUser -d $dbName -tAc "SELECT 1 FROM pg_database WHERE datname='vitalsync_test'"
if ($LASTEXITCODE -ne 0) { throw 'Inicia el proyecto unificado primero.' }
if (($exists -join '').Trim() -ne '1') {
    docker compose -p vitalsync exec -T db psql -U $dbUser -d $dbName -c 'CREATE DATABASE vitalsync_test'
    if ($LASTEXITCODE -ne 0) { throw 'No fue posible preparar la base de pruebas aislada.' }
}
$previousTestUrl = $env:TEST_DATABASE_URL
try {
    $env:TEST_DATABASE_URL = $config.services.backend.environment.DATABASE_URL -replace '/[^/]+$', '/vitalsync_test'
    docker compose -p vitalsync run --rm --no-deps -e TEST_DATABASE_URL -v "${PWD}/backend:/app" backend python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas del backend.' }
} finally {
    $env:TEST_DATABASE_URL = $previousTestUrl
}
