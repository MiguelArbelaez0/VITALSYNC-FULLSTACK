# Run in a separate PowerShell process. All data belongs to a dedicated Docker project.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$env:VITALSYNC_POSTGRES_PORT='5589'
$env:VITALSYNC_BACKEND_PORT='8189'
$env:VITALSYNC_FRONTEND_PORT='5289'
$env:POSTGRES_DB='vitalsync_test'
$env:POSTGRES_USER='vitalsync'
$env:POSTGRES_PASSWORD='local_demo_change_me'
$env:DEMO_MODE='true'
docker compose -p vitalsync-doctor-check up -d --build --wait
if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar el stack aislado' }
# Test-only credential, set only in the explicitly named isolated container.
docker exec vitalsync-doctor-check-backend-1 python -c "from app.db.session import SessionLocal; from app.models.entities import User; from app.core.security import passwords; from sqlalchemy import select; db=SessionLocal(); u=db.scalar(select(User).where(User.email=='medico@vitalsync.demo')); assert u and u.role=='DOCTOR'; u.password_hash=passwords.hash('DoctorE2E2026!'); db.commit(); db.close()"
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la cuenta aislada' }
$env:E2E_BASE_URL='http://localhost:5289'
$env:E2E_LIFECYCLE_ISOLATED='true'
$env:E2E_DOCTOR_CONTAINER='vitalsync-doctor-check-backend-1'
Set-Location frontend
npm run test:e2e -- e2e/doctor-portal.spec.ts
exit $LASTEXITCODE
