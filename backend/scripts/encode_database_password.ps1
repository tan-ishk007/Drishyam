param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $RuntimeEnvPath -PathType Leaf)) {
  Write-Output 'RUNTIME_ENV_FILE_MISSING'
  exit 1
}

$securePassword = Read-Host 'Enter the Supabase database password (input remains hidden)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
  $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  $encodedPassword = [uri]::EscapeDataString($plainPassword)
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$updated = $false
$lines = Get-Content -LiteralPath $RuntimeEnvPath | ForEach-Object {
  if ($_ -match '^DATABASE_URL=(.*)$') {
    $value = $matches[1].Trim().Trim('"')
    if ($value -match '^(postgresql\+psycopg://[^:]+:)(.*)(@[^@]+\.pooler\.supabase\.com:\d+/[^?]+.*)$') {
      $updated = $true
      return 'DATABASE_URL=' + $matches[1] + $encodedPassword + $matches[3]
    }
  }
  return $_
}

$plainPassword = $null
$encodedPassword = $null

if (-not $updated) {
  Write-Output 'DATABASE_URI_PATTERN_NOT_RECOGNIZED'
  exit 1
}

[System.IO.File]::WriteAllLines($RuntimeEnvPath, [string[]]$lines)
Write-Output 'DATABASE_PASSWORD_ENCODING_UPDATED'
