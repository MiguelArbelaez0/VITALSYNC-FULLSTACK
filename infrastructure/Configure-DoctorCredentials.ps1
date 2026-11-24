$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $repoRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) { Copy-Item -LiteralPath (Join-Path $repoRoot '.env.example') -Destination $envPath }
$envText = [IO.File]::ReadAllText($envPath)
$existing = [regex]::Match($envText, '(?m)^DOCTOR_CREDENTIAL_KEY=([^\r\n]*)')
if ($existing.Success -and $existing.Groups[1].Value.Trim()) {
  Write-Output 'Se conserva la clave privada de entrega médica existente.'
  exit 0
}
$randomBytes = New-Object byte[] 32
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
$deliveryKey = [Convert]::ToBase64String($randomBytes).Replace('+','-').Replace('/','_')
if ($existing.Success) { $envText = [regex]::Replace($envText, '(?m)^DOCTOR_CREDENTIAL_KEY=[^\r\n]*', ('DOCTOR_CREDENTIAL_KEY=' + $deliveryKey)) }
else { $envText = $envText.TrimEnd() + "`r`nDOCTOR_CREDENTIAL_KEY=$deliveryKey`r`n" }
[IO.File]::WriteAllText($envPath, $envText)
Write-Output 'Clave privada de entrega médica guardada en .env; no se muestra ni se publica.'
