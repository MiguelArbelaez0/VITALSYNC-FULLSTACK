param([string[]]$TestPaths = @())
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$configText = docker compose -p vitalsync config --format json
if ($LASTEXITCODE -ne 0) { throw 'Compose invalido.' }
$config = ($configText -join "`n") | ConvertFrom-Json
$dbUser = $config.services.db.environment.POSTGRES_USER
$dbName = $config.services.db.environment.POSTGRES_DB
$testDatabaseName = 'vitalsync_test_audit_' + (Get-Date -Format 'yyyyMMddHHmmss')
$create = docker compose -p vitalsync exec -T db psql -U $dbUser -d $dbName -c "CREATE DATABASE $testDatabaseName"
if ($LASTEXITCODE -ne 0) { throw 'No fue posible crear la base temporal aislada; no se truncaron bases existentes.' }
$previousTestUrl = $env:TEST_DATABASE_URL
$previousTestName = $env:VITALSYNC_TEST_DATABASE_NAME
try {
    $env:VITALSYNC_TEST_DATABASE_NAME = $testDatabaseName
    $env:TEST_DATABASE_URL = $config.services.backend.environment.DATABASE_URL -replace '/[^/]+$', "/$testDatabaseName"
    docker compose -p vitalsync run --rm --no-deps -e TEST_DATABASE_URL -e VITALSYNC_TEST_DATABASE_NAME -e LIVEKIT_ENABLED=false -e LIVEKIT_API_KEY= -e LIVEKIT_API_SECRET= -v "${PWD}/backend:/app" backend python -m pytest -q @TestPaths
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas del backend.' }
} finally {
    $env:TEST_DATABASE_URL = $previousTestUrl
    if ($null -eq $previousTestName) { Remove-Item Env:VITALSYNC_TEST_DATABASE_NAME -ErrorAction SilentlyContinue } else { $env:VITALSYNC_TEST_DATABASE_NAME = $previousTestName }
}
