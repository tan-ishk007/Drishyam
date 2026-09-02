param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath
)

$ErrorActionPreference = 'Stop'
$updated = $false
$lines = Get-Content -LiteralPath $RuntimeEnvPath | ForEach-Object {
  if ($_ -match '^REDIS_URL=(.*)$') {
    $value = $matches[1].Trim().Trim('"')
    if ($value.StartsWith('rediss://') -and -not $value.Contains('ssl_cert_reqs=')) {
      $separator = if ($value.Contains('?')) { '&' } else { '?' }
      $updated = $true
      return 'REDIS_URL=' + $value + $separator + 'ssl_cert_reqs=CERT_REQUIRED'
    }
  }
  return $_
}

if ($updated) {
  [System.IO.File]::WriteAllLines($RuntimeEnvPath, [string[]]$lines)
  Write-Output 'REDIS_TLS_CONFIGURATION_UPDATED'
}
else {
  Write-Output 'REDIS_TLS_CONFIGURATION_ALREADY_PRESENT'
}
