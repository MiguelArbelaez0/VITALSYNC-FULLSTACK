# Disposable test services share the vitalsync project; NEVER reset the application database.
$ErrorActionPreference='Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$composeArgs=@('-p','vitalsync','-f','docker-compose.yml','-f','infrastructure/compose.test.yml')
$configText=docker compose @composeArgs config --format json
if($LASTEXITCODE -ne 0){throw 'Configuración de pruebas inválida'}
$config=($configText -join "`n") | ConvertFrom-Json
if($config.name -ne 'vitalsync' -or $config.services.'test-backend'.environment.DATABASE_URL -notmatch '/vitalsync_test$' -or $config.volumes.vitalsync_data.name -ne 'vitalsync_vitalsync_data'){throw 'Aislamiento incorrecto'}
$folder=Join-Path ([Environment]::GetFolderPath('Desktop')) ('VITALSYNC-CREDENCIALES/e2e-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$acl.SetOwner($sid)
foreach($identity in @($sid,(New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))){
 $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
}
Set-Acl -LiteralPath $folder -AclObject $acl
$testExit=1
try{
 docker compose @composeArgs up -d --no-deps --build --wait test-backend test-frontend
 if($LASTEXITCODE -ne 0){throw 'No se pudieron iniciar los servicios temporales'}
 docker cp backend/tests/bootstrap_e2e.py vitalsync-test-backend-1:/tmp/bootstrap_e2e.py
 if($LASTEXITCODE -ne 0){throw 'No se pudo copiar el fixture'}
 docker exec -e PYTHONPATH=/app vitalsync-test-backend-1 python /tmp/bootstrap_e2e.py
 if($LASTEXITCODE -ne 0){throw 'Falló el fixture de la base de pruebas'}
 $target=Join-Path $folder 'e2e.credentials.json'
 docker cp vitalsync-test-backend-1:/tmp/e2e.credentials.json $target
 if($LASTEXITCODE -ne 0){throw 'No se pudo entregar el fixture privado'}
 docker exec vitalsync-test-backend-1 python -c "from pathlib import Path; Path('/tmp/e2e.credentials.json').unlink()"
 $env:E2E_BASE_URL='http://localhost:5289'
 $env:E2E_LIFECYCLE_ISOLATED='true'
 $env:E2E_DOCTOR_CONTAINER='vitalsync-test-backend-1'
 $env:E2E_CREDENTIALS_FILE=$target
 Push-Location frontend
 try{npm run test:e2e; $testExit=$LASTEXITCODE}finally{Pop-Location}
}finally{
 docker compose @composeArgs rm -s -f test-backend test-frontend
 if($LASTEXITCODE -ne 0){throw 'Revisa los servicios temporales; no borres volúmenes'}
 Remove-Item Env:E2E_CREDENTIALS_FILE -ErrorAction SilentlyContinue
}
exit $testExit
