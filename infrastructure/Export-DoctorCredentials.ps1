param([Parameter(Mandatory=$true)][int]$DeliveryId, [string]$AdminEmail='admin@vitalsync.demo')
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskDir = Join-Path ([Environment]::GetFolderPath('Desktop')) ('VITALSYNC-CREDENCIALES/medico-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskDir | Out-Null
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl.SetOwner($owner)
foreach ($identity in @($owner, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
  $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
}
Set-Acl -LiteralPath $taskDir -AclObject $acl
$containerFile = '/tmp/medical-' + [guid]::NewGuid().ToString('N') + '.credentials.json'
docker compose -p vitalsync exec backend python -m app.medical_credentials --actor-email $AdminEmail --delivery-id $DeliveryId --output $containerFile
if ($LASTEXITCODE -ne 0) { throw 'No se emitió la entrega; revisa la indicación del operador.' }
$localFile = Join-Path $taskDir 'medico.credentials.json'
docker cp "vitalsync-backend-1:$containerFile" $localFile
if ($LASTEXITCODE -ne 0) { throw "La entrega sigue protegida dentro del contenedor en $containerFile; recupera ese archivo sin emitir otra entrega." }
$containerHash = docker exec vitalsync-backend-1 python -c "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('$containerFile').read_bytes()).hexdigest())"
if ((Get-FileHash -LiteralPath $localFile -Algorithm SHA256).Hash.ToLower() -ne $containerHash.Trim()) { throw 'La copia no coincide; conserva ambas para revisión.' }
docker exec vitalsync-backend-1 python -c "from pathlib import Path; Path('$containerFile').unlink()"
Write-Output "Archivo privado verificado: $localFile"
Write-Output 'Entrégalo únicamente al titular. No lo adjuntes a Git ni a reportes.'
