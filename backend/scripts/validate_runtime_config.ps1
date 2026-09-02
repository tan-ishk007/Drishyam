param(
  [Parameter(Mandatory = $true)]
  [string]$RuntimeEnvPath
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $RuntimeEnvPath -PathType Leaf)) {
  Write-Output 'RUNTIME_ENV_FILE_MISSING'
  exit 1
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $RuntimeEnvPath) {
  $trimmed = $line.Trim()
  if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
  if ($trimmed -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    $values[$matches[1]] = $matches[2].Trim()
  }
}

$required = @(
  'DATABASE_URL', 'REDIS_URL', 'STORAGE_BACKEND', 'SUPABASE_URL',
  'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_STORAGE_BUCKET', 'SECRET_KEY',
  'OTP_PEPPER', 'ALLOWED_ORIGINS'
)

$checks = [ordered]@{}
foreach ($name in $required) {
  $checks[$name] = $values.ContainsKey($name) -and $values[$name].Length -gt 0
}

if ($checks['DATABASE_URL']) {
  $value = $values['DATABASE_URL']
  $databaseScheme = $value.StartsWith('postgresql+psycopg://')
  $databasePooler = $value.Contains('pooler.supabase.com')
  $databaseTls = $value.Contains('sslmode=require')
  $databasePlaceholder = -not $value.Contains('YOUR-')
  $databaseProjectPlaceholder = -not $value.Contains('PROJECT_REF')
  $databaseCredentialSeparators = ([regex]::Matches($value, '@')).Count -eq 1
  Write-Output ("DATABASE_URL_SCHEME={0}" -f $(if ($databaseScheme) { 'OK' } else { 'NEEDS_ATTENTION' }))
  Write-Output ("DATABASE_URL_POOLER={0}" -f $(if ($databasePooler) { 'OK' } else { 'NEEDS_ATTENTION' }))
  Write-Output ("DATABASE_URL_TLS={0}" -f $(if ($databaseTls) { 'OK' } else { 'NEEDS_ATTENTION' }))
  Write-Output ("DATABASE_URL_PLACEHOLDER={0}" -f $(if ($databasePlaceholder) { 'OK' } else { 'NEEDS_ATTENTION' }))
  Write-Output ("DATABASE_URL_PROJECT_REFERENCE={0}" -f $(if ($databaseProjectPlaceholder) { 'OK' } else { 'NEEDS_ATTENTION' }))
  Write-Output ("DATABASE_URL_CREDENTIAL_ENCODING={0}" -f $(if ($databaseCredentialSeparators) { 'OK' } else { 'NEEDS_ATTENTION' }))
  $checks['DATABASE_URL'] = $databaseScheme -and $databasePooler -and $databaseTls -and $databasePlaceholder -and $databaseProjectPlaceholder -and $databaseCredentialSeparators
}

if ($checks['REDIS_URL']) {
  $value = $values['REDIS_URL']
  $redisScheme = $value.StartsWith('rediss://')
  $redisHost = $value.Contains('upstash.io')
  $redisPlaceholder = -not $value.Contains('YOUR_')
  $redisTlsVerification = $value.Contains('ssl_cert_reqs=CERT_REQUIRED')
  Write-Output ("REDIS_URL_TLS_VERIFICATION={0}" -f $(if ($redisTlsVerification) { 'OK' } else { 'NEEDS_ATTENTION' }))
  $checks['REDIS_URL'] = $redisScheme -and $redisHost -and $redisPlaceholder -and $redisTlsVerification
}

if ($checks['STORAGE_BACKEND']) {
  $checks['STORAGE_BACKEND'] = $values['STORAGE_BACKEND'] -eq 'supabase'
}

if ($checks['SUPABASE_URL']) {
  $checks['SUPABASE_URL'] = $values['SUPABASE_URL'].StartsWith('https://') -and $values['SUPABASE_URL'].Contains('.supabase.co')
}

if ($checks['SUPABASE_SERVICE_ROLE_KEY']) {
  $value = $values['SUPABASE_SERVICE_ROLE_KEY']
  $checks['SUPABASE_SERVICE_ROLE_KEY'] = $value.StartsWith('sb_secret_') -and $value.Length -gt 32 -and -not $value.Contains('PASTE_')
}

if ($checks['SUPABASE_STORAGE_BUCKET']) {
  $checks['SUPABASE_STORAGE_BUCKET'] = $values['SUPABASE_STORAGE_BUCKET'] -eq 'drishyam-staging-private'
}

foreach ($name in @('SECRET_KEY', 'OTP_PEPPER')) {
  if ($checks[$name]) {
    $value = $values[$name]
    $checks[$name] = $value.Length -ge 32 -and -not $value.Contains('generate-') -and -not $value.Contains('replace-with-')
  }
}

if ($checks['ALLOWED_ORIGINS']) {
  $checks['ALLOWED_ORIGINS'] = $values['ALLOWED_ORIGINS'].Contains('http://localhost:5173')
}

$failed = @()
foreach ($name in $checks.Keys) {
  $status = if ($checks[$name]) { 'OK' } else { 'NEEDS_ATTENTION' }
  Write-Output ("{0}={1}" -f $name, $status)
  if (-not $checks[$name]) { $failed += $name }
}

if ($failed.Count -gt 0) {
  Write-Output 'RUNTIME_CONFIG_STATUS=NEEDS_ATTENTION'
  exit 1
}

Write-Output 'RUNTIME_CONFIG_STATUS=READY'
