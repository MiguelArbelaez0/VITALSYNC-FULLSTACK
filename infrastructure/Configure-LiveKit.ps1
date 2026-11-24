param(
  [string]$EnvPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env")
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EnvPath)) {
  throw "No existe .env. Copia primero .env.example a .env."
}

$lines = @(Get-Content -LiteralPath $EnvPath)
function Get-EnvValue([string]$Name) {
  $line = $lines | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
  if ($line) { return $line.Substring($Name.Length + 1).Trim('"', "'") }
  return ""
}
function Set-EnvValue([string]$Name, [string]$Value) {
  $pattern = "^$([regex]::Escape($Name))=.*$"
  $found = $false
  for ($i = 0; $i -lt $script:lines.Count; $i++) {
    if ($script:lines[$i] -match $pattern) { $script:lines[$i] = "$Name=$Value"; $found = $true }
  }
  if (-not $found) { $script:lines += "$Name=$Value" }
}
function New-Secret([int]$Count) {
  $bytes = New-Object byte[] $Count
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
}

$key = Get-EnvValue "LIVEKIT_API_KEY"
$secret = Get-EnvValue "LIVEKIT_API_SECRET"
if ($key -notmatch '^[A-Za-z0-9_-]{12,}$') { $key = "vs_" + [guid]::NewGuid().ToString("N") }
if ($secret -notmatch '^[A-Za-z0-9_-]{32,}$') { $secret = New-Secret 48 }

Set-EnvValue "LIVEKIT_ENABLED" "true"
Set-EnvValue "LIVEKIT_API_KEY" $key
Set-EnvValue "LIVEKIT_API_SECRET" $secret
Set-EnvValue "LIVEKIT_API_URL" "http://livekit:7880"
Set-EnvValue "LIVEKIT_PUBLIC_URL" "ws://localhost:7880"
Set-EnvValue "LIVEKIT_TOKEN_TTL_SECONDS" "600"
Set-Content -LiteralPath $EnvPath -Value $lines -Encoding utf8
Write-Output "Configuración local de LiveKit guardada en .env. Los secretos no se muestran ni se incluyen en Git."
