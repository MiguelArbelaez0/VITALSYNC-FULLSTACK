param([switch]$UsePhysicalDevices, [switch]$GoogleProviderFixture,
      [ValidateSet('desktop','mobile')][string]$Project = 'desktop',
      [string]$Filter = 'LiveKit real media')
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (-not (Test-Path -LiteralPath '.env')) {
  Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
& .\infrastructure\Configure-LiveKit.ps1

$previousTestName = $env:VITALSYNC_TEST_DATABASE_NAME
$env:VITALSYNC_TEST_DATABASE_NAME = 'vitalsync_test_audit_' + (Get-Date -Format 'yyyyMMddHHmmss')
$composeArgs = @('-p','vitalsync','-f','docker-compose.yml','-f','infrastructure/compose.test.yml','-f','infrastructure/compose.video-test.yml')
if ($GoogleProviderFixture) { $composeArgs += @('-f','infrastructure/compose.google-test.yml') }
$configText = docker compose @composeArgs config --format json
if ($LASTEXITCODE -ne 0) { throw 'Compose de pruebas LiveKit inválido.' }
$config = ($configText -join "`n") | ConvertFrom-Json
if ($config.name -ne 'vitalsync' -or $config.volumes.vitalsync_data.name -ne 'vitalsync_vitalsync_data') { throw 'El test no está aislado dentro del proyecto y volumen esperados.' }
$dbUser = $config.services.db.environment.POSTGRES_USER
$dbName = $config.services.db.environment.POSTGRES_DB
$testName = $env:VITALSYNC_TEST_DATABASE_NAME
docker compose -p vitalsync exec -T db psql -U $dbUser -d $dbName -c "CREATE DATABASE $testName"
if ($LASTEXITCODE -ne 0) { throw 'No se creó la base de pruebas; no se modificó la base principal.' }

$folder = Join-Path ([Environment]::GetFolderPath('Desktop')) ('VITALSYNC-CREDENCIALES/e2e-livekit-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl.SetOwner($sid)
foreach ($identity in @($sid, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
  $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
}
Set-Acl -LiteralPath $folder -AclObject $acl
$testExit = 1
try {
  docker compose @composeArgs up -d --build --wait test-livekit test-backend test-frontend
  if ($LASTEXITCODE -ne 0) {
    docker compose @composeArgs logs --no-color test-livekit test-backend test-frontend
    throw 'No pudieron iniciarse los servicios temporales de videollamada.'
  }
  docker cp backend/tests/bootstrap_e2e.py vitalsync-test-backend-1:/tmp/bootstrap_e2e.py
  if ($LASTEXITCODE -ne 0) { throw 'No se pudo copiar el bootstrap a la base aislada.' }
  docker exec -e PYTHONPATH=/app vitalsync-test-backend-1 python /tmp/bootstrap_e2e.py
  if ($LASTEXITCODE -ne 0) { throw 'Falló la preparación de la base aislada.' }
  $credentialsFile = Join-Path $folder 'e2e.credentials.json'
  docker cp vitalsync-test-backend-1:/tmp/e2e.credentials.json $credentialsFile
  if ($LASTEXITCODE -ne 0) { throw 'No se pudieron guardar las credenciales del fixture fuera del repositorio.' }
  docker exec vitalsync-test-backend-1 python -c "from pathlib import Path; Path('/tmp/e2e.credentials.json').unlink()"
  $env:E2E_BASE_URL = 'http://localhost:5289'
  $env:E2E_LIVEKIT_REAL = 'true'
  if ($GoogleProviderFixture) { $env:E2E_GOOGLE_FIXTURE = 'true' }
  if ($UsePhysicalDevices) { $env:E2E_LIVEKIT_PHYSICAL = 'true' }
  $env:E2E_CREDENTIALS_FILE = $credentialsFile
  Push-Location frontend
  try { npm run test:e2e -- --grep $Filter --project $Project; $testExit = $LASTEXITCODE }
  finally { Pop-Location }
  if ($testExit -ne 0) { docker compose @composeArgs logs --no-color test-backend test-livekit }
}
finally {
  docker compose @composeArgs rm -s -f test-backend test-frontend test-livekit
  if (Test-Path -LiteralPath $folder) { Remove-Item -LiteralPath $folder -Recurse -Force }
  Remove-Item Env:E2E_LIVEKIT_REAL -ErrorAction SilentlyContinue
  Remove-Item Env:E2E_GOOGLE_FIXTURE -ErrorAction SilentlyContinue
  Remove-Item Env:E2E_LIVEKIT_PHYSICAL -ErrorAction SilentlyContinue
  Remove-Item Env:E2E_CREDENTIALS_FILE -ErrorAction SilentlyContinue
  Remove-Item Env:E2E_BASE_URL -ErrorAction SilentlyContinue
  if ($null -eq $previousTestName) { Remove-Item Env:VITALSYNC_TEST_DATABASE_NAME -ErrorAction SilentlyContinue } else { $env:VITALSYNC_TEST_DATABASE_NAME = $previousTestName }
}
exit $testExit
