param([string]$OutputDirectory = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VITALSYNC-RESPALDOS'))
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$configText = docker compose -p vitalsync config --format json
if ($LASTEXITCODE -ne 0) { throw 'Configuracion Compose invalida.' }
$config = ($configText -join "`n") | ConvertFrom-Json
if ($config.volumes.vitalsync_data.name -ne 'vitalsync_vitalsync_data' -or $config.services.db.environment.POSTGRES_DB -ne 'vitalsync') { throw 'La configuracion no apunta al volumen/base principales esperados.' }
$container = docker compose -p vitalsync ps -q db
if (-not $container) { throw 'El servicio db debe estar iniciado.' }
$mounts = (docker inspect $container --format '{{json .Mounts}}') | ConvertFrom-Json
if (-not ($mounts | Where-Object { $_.Name -eq 'vitalsync_vitalsync_data' -and $_.Destination -eq '/var/lib/postgresql/data' })) { throw 'El contenedor no usa el volumen principal.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $OutputDirectory ("vitalsync-$stamp.dump")
if (Test-Path -LiteralPath $target) { throw 'Ya existe ese respaldo; vuelve a ejecutar en otro segundo.' }
$remote = "/tmp/vitalsync-$stamp.dump"
$dbUser = $config.services.db.environment.POSTGRES_USER
$dbName = $config.services.db.environment.POSTGRES_DB
docker compose -p vitalsync exec -T db pg_dump -U $dbUser -d $dbName -Fc -f $remote
if ($LASTEXITCODE -ne 0) { throw 'pg_dump fallo; no se considera valido el respaldo.' }
docker compose -p vitalsync exec -T db pg_restore --exit-on-error --file=/dev/null $remote
if ($LASTEXITCODE -ne 0) { throw 'El archivo no pudo leerse completamente con pg_restore.' }
docker cp "${container}:$remote" $target
if ($LASTEXITCODE -ne 0) { throw 'No se pudo copiar el respaldo al equipo.' }
$sourceHash = ((docker compose -p vitalsync exec -T db sha256sum $remote) -split '\s+')[0]
if ($LASTEXITCODE -ne 0) { throw 'No se pudo obtener SHA256 del archivo original.' }
$hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $sourceHash) { throw 'SHA256 no coincide; revisa la copia del respaldo.' }
$manifest = [ordered]@{ file=$target; bytes=(Get-Item -LiteralPath $target).Length; sha256=$hash; database=$dbName; volume='vitalsync_vitalsync_data'; archive_read='PASS' }
$manifest | ConvertTo-Json | Set-Content -LiteralPath ($target + '.json') -Encoding UTF8
$manifest | ConvertTo-Json
