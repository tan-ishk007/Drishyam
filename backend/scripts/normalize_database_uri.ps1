param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $RuntimeEnvPath -PathType Leaf)) {
  Write-Output 'RUNTIME_ENV_FILE_MISSING'
  exit 1
}

$updated = $false
$lines = Get-Content -LiteralPath $RuntimeEnvPath | ForEach-Object {
  if ($_ -match '^DATABASE_URL=(.*)$') {
    $value = $matches[1].Trim().Trim('"')
    if ($value.StartsWith('DATABASE_URL=')) {
      $value = $value.Substring('DATABASE_URL='.Length).Trim().Trim('"')
    }
    if ($value -match '^postgresql(?:\+psycopg)?:/*(.*)$') {
      $databaseRemainder = $matches[1]
      $updated = $true
      return 'DATABASE_URL=postgresql+psycopg://' + $databaseRemainder
    }
  }
  return $_
}

if (-not $updated) {
  Write-Output 'DATABASE_URI_SCHEME_NOT_CHANGED'
  exit 1
}

[System.IO.File]::WriteAllLines($RuntimeEnvPath, [string[]]$lines)
Write-Output 'DATABASE_URI_SCHEME_NORMALIZED'
