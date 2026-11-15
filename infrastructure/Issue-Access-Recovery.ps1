param(
    [string]$Email,
    [switch]$AllPending,
    [string]$OutputRoot=(Join-Path ([Environment]::GetFolderPath('Desktop')) 'VITALSYNC-CREDENCIALES')
)
$ErrorActionPreference='Stop'
if($Email -and $AllPending){throw 'Elige una cuenta o el lote pendiente, no ambos.'}
if(-not $Email -and -not $AllPending){throw 'Indica -Email cuenta@dominio o confirma el lote con -AllPending.'}
Set-Location (Split-Path $PSScriptRoot -Parent)
$repoRoot=[IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\')+'\'
$resolved=[IO.Path]::GetFullPath($OutputRoot)
if(($resolved.TrimEnd('\')+'\').StartsWith($repoRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Los enlaces privados no se guardan dentro del repositorio.'}
$stamp=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6)
$directory=Join-Path $resolved $stamp
New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
$operatorSid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid=New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$acl.SetOwner($operatorSid)
foreach($sid in @($operatorSid,$systemSid)){$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))}
Set-Acl -LiteralPath $directory -AclObject $acl
$remote="/tmp/vitalsync-recovery-$stamp.json"
$target=Join-Path $directory 'recovery-links.json'
$argsList=@('compose','-p','vitalsync','exec','-T','backend','python','-m','app.access_recovery','--output',$remote)
if($Email){$argsList+=@('--email',$Email)}else{$argsList+='--all-pending'}
try{
    docker @argsList
    if($LASTEXITCODE -ne 0){throw 'No se emitieron enlaces privados.'}
    $container=docker compose -p vitalsync ps -q backend
    if($LASTEXITCODE -ne 0 -or -not $container){throw 'No se pudo encontrar el backend de VITALSYNC.'}
    docker cp "${container}:$remote" $target
    if($LASTEXITCODE -ne 0){throw 'No se pudo copiar el archivo protegido.'}
    $remoteHash=((docker compose -p vitalsync exec -T backend sha256sum $remote) -split '\s+')[0]
    if($LASTEXITCODE -ne 0 -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $remoteHash){throw 'No se pudo verificar el archivo privado.'}
    Write-Host "Enlaces de recuperación de un solo uso guardados en: $target"
    Write-Host 'Abre la dirección local que contiene el archivo; los enlaces vencen en 24 horas y la contraseña no cambia hasta que la persona los use.'
}finally{
    docker compose -p vitalsync exec -T backend python -c "from pathlib import Path; Path('$remote').unlink(missing_ok=True)" 2>$null | Out-Null
}
