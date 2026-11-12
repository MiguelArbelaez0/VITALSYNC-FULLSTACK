# Temporary isolated E2E environment. Containers/network are always removed; volumes survive.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$env:VITALSYNC_POSTGRES_PORT='5589'
$env:VITALSYNC_BACKEND_PORT='8189'
$env:VITALSYNC_FRONTEND_PORT='5289'
$env:POSTGRES_DB='vitalsync_test'
$env:POSTGRES_USER='vitalsync'
$env:POSTGRES_PASSWORD='local_demo_change_me'
$env:DEMO_MODE='true'
$composeArgs = @('-p','vitalsync-doctor-check','-f','docker-compose.yml','-f','infrastructure/compose.test.yml')
$configText = docker compose @composeArgs config --format json
if ($LASTEXITCODE -ne 0) { throw 'Configuracion de pruebas invalida.' }
$config = ($configText -join "`n") | ConvertFrom-Json
if ($config.volumes.vitalsync_data.name -ne 'vitalsync-doctor-check_vitalsync_data' -or $config.services.db.environment.POSTGRES_DB -ne 'vitalsync_test') { throw 'Las pruebas no pueden usar los datos principales.' }
$testExit = 1
try {
    docker compose @composeArgs up -d --build --wait
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar el stack aislado.' }
    # Verify existing test credentials; never replace a stored password.
    docker exec vitalsync-doctor-check-backend-1 python -c "from app.db.session import SessionLocal; from app.models.entities import User; from app.core.security import passwords; from sqlalchemy import select; db=SessionLocal(); assert db.bind.url.database=='vitalsync_test'; u=db.scalar(select(User).where(User.email=='medico@vitalsync.demo')); assert u and u.role=='DOCTOR'; assert passwords.verify('DoctorE2E2026!',u.password_hash), 'Configure explicitly the isolated demo password before testing'; db.close()"
    if ($LASTEXITCODE -ne 0) { throw 'La cuenta aislada no acepta la clave de pruebas. Configurala explicitamente con app.doctor_demo --set-password en el entorno de pruebas; no se cambio ninguna clave.' }
    $env:E2E_BASE_URL='http://localhost:5289'
    $env:E2E_LIFECYCLE_ISOLATED='true'
    $env:E2E_DOCTOR_CONTAINER='vitalsync-doctor-check-backend-1'
    Push-Location frontend
    try {
        npm run test:e2e -- e2e/doctor-portal.spec.ts
        $testExit = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    docker compose @composeArgs down --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo limpiar el stack temporal; revisa sus contenedores sin borrar volumenes.' }
}
exit $testExit
