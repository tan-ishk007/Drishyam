param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath
)

$ErrorActionPreference = 'Stop'
$updated = $false
$lines = Get-Content -LiteralPath $RuntimeEnvPath | ForEach-Object {
  if ($_ -match '^postgresql\+psycopg://') {
    $updated = $true
    return 'DATABASE_URL=' + $_
  }
  return $_
}

if (-not $updated) {
  Write-Output 'DATABASE_URL_LABEL_NOT_NEEDED'
  exit 0
}

[System.IO.File]::WriteAllLines($RuntimeEnvPath, [string[]]$lines)
Write-Output 'DATABASE_URL_LABEL_RESTORED'
