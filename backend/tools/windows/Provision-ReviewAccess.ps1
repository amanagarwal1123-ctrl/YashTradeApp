<#
.SYNOPSIS
  Owner-run: provision, verify, rotate or revoke the isolated store-review accounts.

.DESCRIPTION
  Wraps backend\tools\provision_review_access.py. The MongoDB connection string is requested with a
  HIDDEN prompt and passed to the Python process through a process-scoped environment variable that is
  removed afterwards, so it never appears on the command line, in PowerShell history or in logs.
  Reviewer access keys are written ONLY to -NotePath (a private file outside the repository); nothing
  secret is printed. Without -NotePath the keys are printed once to this window instead.

.PARAMETER Environment   preview or production — recorded in the note and verification so accounts are never confused.
.PARAMETER DbName        The deployment's DB_NAME exactly as shown in Manage Publishes -> Secrets.
.PARAMETER ApiBaseUrl    Deployed backend base URL ending in /api (used by -Verify and recorded in the note).
.PARAMETER NotePath      New private file that receives the keys, e.g. "$env:USERPROFILE\Private\yash-review-production.txt".
.PARAMETER VerifyNote    RECOVERY / re-check: an EXISTING private note written earlier by this tool. Signs in with every key
                         stored in it against -ApiBaseUrl, signs out, proves reuse is rejected and APPENDS the results to
                         the note. Read-only: needs no MongoDB connection string and changes no account. STRICT: -ApiBaseUrl
                         must be the very backend recorded in the note's header (scheme, host, port and path); any other
                         target - or a note without a recorded backend - is refused before a single request is sent.

.EXAMPLE
  .\Provision-ReviewAccess.ps1 -Environment production -DbName jewellers_prod `
      -ApiBaseUrl https://yash-tryon-test.emergent.host/api -Provision -Seed -Status -Verify `
      -NotePath "$env:USERPROFILE\Private\yash-review-production.txt"

.EXAMPLE
  .\Provision-ReviewAccess.ps1 -Environment production -DbName jewellers_prod `
      -ApiBaseUrl https://yash-tryon-test.emergent.host/api -VerifyNote "$env:USERPROFILE\Private\yash-review-production.txt"

.EXAMPLE
  .\Provision-ReviewAccess.ps1 -Environment production -DbName jewellers_prod -Status

.EXAMPLE
  .\Provision-ReviewAccess.ps1 -Environment production -DbName jewellers_prod `
      -Rotate store-review-admin -ApiBaseUrl https://yash-tryon-test.emergent.host/api -Verify -NotePath "$env:USERPROFILE\Private\yash-review-rotated.txt"

.EXAMPLE
  .\Provision-ReviewAccess.ps1 -Environment production -DbName jewellers_prod -Revoke store-review-telecaller

.NOTES
  Exit codes (from the Python tool): 0 = done and, when -Verify/-VerifyNote was given, EVERY key proved end-to-end;
  1 = blocked before any change and before any network request (configuration, unsafe note path, wrong environment,
  -VerifyNote against a backend other than the one the note pins); 2 = keys were issued/kept but verification FAILED
  or was INCOMPLETE after a valid pre-flight - the note records which (sanitized); re-run the same -VerifyNote command
  after fixing the cause.
#>
param(
    [Parameter(Mandatory)][ValidateSet('preview', 'production')][string]$Environment,
    [Parameter(Mandatory)][string]$DbName,
    [string]$ApiBaseUrl = '',
    [string]$NotePath = '',
    [string]$VerifyNote = '',
    [switch]$Provision,
    [switch]$Seed,
    [switch]$ResetData,
    [switch]$Status,
    [switch]$Verify,
    [string]$Rotate = '',
    [string]$Revoke = ''
)
$ErrorActionPreference = 'Stop'
if (($Verify -or $VerifyNote) -and -not $ApiBaseUrl) { throw '-Verify / -VerifyNote need -ApiBaseUrl (deployed backend URL ending in /api).' }
if ($VerifyNote -and ($Provision -or $Seed -or $ResetData -or $Status -or $Rotate -or $Revoke -or $NotePath -or $Verify)) {
    throw '-VerifyNote is a read-only re-check of an existing note; run it on its own (with -ApiBaseUrl).'
}
if (-not ($Provision -or $Seed -or $ResetData -or $Status -or $Rotate -or $Revoke -or $VerifyNote)) { throw 'Choose at least one action: -Provision -Seed -ResetData -Status -Rotate <id> -Revoke <id> -VerifyNote <file>.' }
if ($Environment -eq 'production' -and ($Provision -or $Rotate) -and -not $NotePath) { throw 'Production issuance/rotation requires -NotePath (keys are never printed for production).' }

$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $backend '.operator-venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Operator environment missing. Run .\Setup-Operator.ps1 first." }
if ($NotePath) {
    $repoRoot = (Resolve-Path (Join-Path $backend '..')).Path
    $full = [System.IO.Path]::GetFullPath($NotePath)
    if ($full.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'NotePath must be OUTSIDE the repository folder.' }
    if (Test-Path $full) { throw 'NotePath already exists; choose a new file name.' }
}
if ($VerifyNote -and -not (Test-Path $VerifyNote)) { throw "VerifyNote file not found: $VerifyNote" }

$arguments = @('tools\provision_review_access.py', '--expected-db', $DbName, '--environment', $Environment)
if ($Provision) { $arguments += '--provision' }
if ($Seed) { $arguments += '--seed' }
if ($ResetData) { $arguments += '--reset-data' }
if ($Status) { $arguments += '--status' }
if ($Verify) { $arguments += '--verify' }
if ($ApiBaseUrl) { $arguments += @('--api-base-url', $ApiBaseUrl) }
if ($Rotate) { $arguments += @('--rotate', $Rotate) }
if ($Revoke) { $arguments += @('--revoke', $Revoke) }
if ($NotePath) { $arguments += @('--write-note', $NotePath) }
if ($VerifyNote) { $arguments += @('--verify-note', $VerifyNote) }

$exitCode = 1
if ($VerifyNote) {
    # Read-only re-verification: no database access, so no connection string is requested or exposed.
    Push-Location $backend
    try {
        & $python @arguments
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} else {
    $secure = Read-Host -AsSecureString 'Paste the MongoDB connection string for this deployment (input is hidden)'
    $plain = [System.Net.NetworkCredential]::new('', $secure).Password
    if (-not $plain.StartsWith('mongodb')) { throw 'That does not look like a MongoDB connection string (must start with mongodb:// or mongodb+srv://).' }
    try {
        $env:MONGO_URL = $plain
        $env:DB_NAME = $DbName
        Push-Location $backend
        try {
            & $python @arguments
            $exitCode = $LASTEXITCODE
        } finally {
            Pop-Location
        }
    } finally {
        Remove-Item Env:MONGO_URL, Env:DB_NAME -ErrorAction SilentlyContinue
        $plain = $null
        $secure = $null
        [GC]::Collect()
    }
}
if ($NotePath -and (Test-Path $NotePath)) {
    Write-Host ''
    Write-Host "Reviewer keys were written ONLY to: $NotePath" -ForegroundColor Yellow
    Write-Host 'Keep that file private (password manager / encrypted drive). Never commit, screenshot or paste it into chat.' -ForegroundColor Yellow
}
switch ($exitCode) {
    0 { if ($Verify -or $VerifyNote) { Write-Host 'Verification: every key proved (sign-in, role, scope, sign-out, reuse rejected).' -ForegroundColor Green } }
    1 { Write-Host 'Blocked before any change - read the JSON line above for the reason.' -ForegroundColor Red }
    2 { Write-Host 'Keys were issued/kept but verification FAILED or is INCOMPLETE. The note records the outcome; fix the cause, then re-run with -VerifyNote <that note>.' -ForegroundColor Red }
    default { Write-Host "Tool exited with code $exitCode." -ForegroundColor Red }
}
exit $exitCode
