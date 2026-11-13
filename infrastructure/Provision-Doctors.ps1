param([string]$OutputRoot=(Join-Path ([Environment]::GetFolderPath('Desktop')) 'VITALSYNC-CREDENCIALES'))
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$repoRoot=[IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\') + '\'
$resolved=[IO.Path]::GetFullPath($OutputRoot)
if (($resolved.TrimEnd('\')+'\').StartsWith($repoRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Las credenciales no se guardan dentro del repositorio.' }
$stamp=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)
$directory=Join-Path $resolved $stamp
New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
# Restrict the newly created folder before transferring any credential bytes.
$operatorSid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid=New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$acl.SetOwner($operatorSid)
foreach($sid in @($operatorSid,$systemSid)) {
    $rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $directory -AclObject $acl
$remote="/tmp/doctor-initial-$stamp.credentials.json"
$target=Join-Path $directory 'doctores.credentials.json'
docker compose -p vitalsync exec -T backend python -m app.provision_doctors --output $remote
if($LASTEXITCODE -ne 0) { throw 'El aprovisionamiento no se completó; no se exportaron claves.' }
$container=docker compose -p vitalsync ps -q backend
docker cp "${container}:$remote" $target
if($LASTEXITCODE -ne 0) { throw 'No se pudo copiar el archivo privado; el original permanece protegido dentro del contenedor.' }
$remoteHash=((docker compose -p vitalsync exec -T backend sha256sum $remote) -split '\s+')[0]
if($LASTEXITCODE -ne 0 -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $remoteHash) { throw 'No se pudo validar la copia privada de credenciales.' }
docker compose -p vitalsync exec -T backend python -c "from pathlib import Path; p=Path('$remote'); assert str(p).startswith('/tmp/doctor-initial-') and p.name.endswith('.credentials.json'); p.unlink()"
if($LASTEXITCODE -ne 0) { throw 'La copia local existe, pero no se pudo retirar el archivo temporal del contenedor.' }
Write-Host "Credenciales iniciales guardadas únicamente en el archivo local protegido: $target"
