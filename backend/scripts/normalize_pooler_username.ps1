param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath,
  [Parameter(Mandatory = $true)]
  [string]$ProjectRef
)

$ErrorActionPreference = 'Stop'
$updated = $false
$lines = Get-Content -LiteralPath $RuntimeEnvPath | ForEach-Object {
  if ($_ -match '^DATABASE_URL=postgresql\+psycopg://postgres\.PROJECT_REF:') {
    $updated = $true
    return $_.Replace('postgres.PROJECT_REF:', ('postgres.' + $ProjectRef + ':'))
  }
  return $_
}

if ($updated) {
  [System.IO.File]::WriteAllLines($RuntimeEnvPath, [string[]]$lines)
  Write-Output 'POOLER_USERNAME_NORMALIZED'
}
else {
  Write-Output 'POOLER_USERNAME_ALREADY_CONFIGURED'
}
