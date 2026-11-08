$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$exists = docker compose exec -T postgres psql -U vitalsync -d vitalsync -tAc "SELECT 1 FROM pg_database WHERE datname='vitalsync_test'"
if ($LASTEXITCODE -ne 0) { throw 'Inicia PostgreSQL de VITALSYNC primero.' }
if (($exists -join '').Trim() -ne '1') {
    docker compose exec -T postgres psql -U vitalsync -d vitalsync -c 'CREATE DATABASE vitalsync_test'
    if ($LASTEXITCODE -ne 0) { throw 'No fue posible crear vitalsync_test.' }
}
docker compose run --rm -v "${PWD}/backend:/app" backend python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas del backend.' }
