param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath
)

$ErrorActionPreference = 'Stop'
$lines = Get-Content -LiteralPath $RuntimeEnvPath
$found = $false
$updated = $lines | ForEach-Object {
  if ($_ -match '^ALLOW_LOCAL_CONSOLE_EMAIL=') {
    $found = $true
    return 'ALLOW_LOCAL_CONSOLE_EMAIL=true'
  }
  return $_
}

if (-not $found) {
  $updated += 'ALLOW_LOCAL_CONSOLE_EMAIL=true'
}

[System.IO.File]::WriteAllLines($RuntimeEnvPath, [string[]]$updated)
Write-Output 'LOCAL_CONSOLE_MAILBOX_ENABLED'
