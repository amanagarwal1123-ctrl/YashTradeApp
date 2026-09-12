<#
.SYNOPSIS
  Owner-run: dry-run and then apply the scoped same-ID owner role repair (customer -> admin) for
  phone 9999813334 / canonical ID bcdf18c9-dc87-4d46-b580-30cf519103df ONLY.

.DESCRIPTION
  Wraps backend\tools\recover_owner_admin.py with the target fixed to the authorised account, so no
  other user can be touched by mistake. The MongoDB connection string is requested with a HIDDEN
  prompt and passed through a process-scoped environment variable that is removed afterwards.

  Safeguards preserved by the underlying command: verified database name, unique active identity,
  dry-run by default (no writes), reviewed report hash, restorable-backup reference, maintenance
  confirmation, intent record before the single atomic update, old-session invalidation, audit
  receipt, idempotent replay.

.EXAMPLE
  # 1) DRY RUN (no writes) — read the printed report and keep its report_sha256
  .\Recover-OwnerAdmin.ps1 -DbName jewellers_prod -OperationId owner-admin-recovery-20260912 -Operator 'owner'

.EXAMPLE
  # 2) APPLY — identical operation ID, plus the reviewed hash and your backup reference
  .\Recover-OwnerAdmin.ps1 -DbName jewellers_prod -OperationId owner-admin-recovery-20260912 -Operator 'owner' `
      -Apply -ApprovedReportSha256 <hash from step 1> -BackupRef 'emergent-db-backup-2026-09-12' -MaintenanceConfirmed

.EXAMPLE
  # 3) CONFIRM — dry run again; expect already_admin = true for the same ID
  .\Recover-OwnerAdmin.ps1 -DbName jewellers_prod -OperationId owner-admin-recovery-20260912 -Operator 'owner'
#>
param(
    [Parameter(Mandatory)][string]$DbName,
    [Parameter(Mandatory)][string]$OperationId,
    [Parameter(Mandatory)][string]$Operator,
    [string]$Reason = 'Owner authorised same-ID customer-to-admin correction for 9999813334',
    [switch]$Apply,
    [string]$ApprovedReportSha256 = '',
    [string]$BackupRef = '',
    [switch]$MaintenanceConfirmed
)
$ErrorActionPreference = 'Stop'
$Phone = '9999813334'
$UserId = 'bcdf18c9-dc87-4d46-b580-30cf519103df'

if ($Apply -and (-not $ApprovedReportSha256 -or -not $BackupRef -or -not $MaintenanceConfirmed)) {
    throw '-Apply requires -ApprovedReportSha256 <hash from the dry run>, -BackupRef <verified restorable backup> and -MaintenanceConfirmed.'
}
$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $backend '.operator-venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Operator environment missing. Run .\Setup-Operator.ps1 first." }

Write-Host ("Target: phone {0}, canonical ID {1}, database '{2}', mode {3}" -f $Phone, $UserId, $DbName, $(if ($Apply) { 'APPLY' } else { 'DRY RUN (no writes)' }))
$secure = Read-Host -AsSecureString 'Paste the PRODUCTION MongoDB connection string (input is hidden)'
$plain = [System.Net.NetworkCredential]::new('', $secure).Password
if (-not $plain.StartsWith('mongodb')) { throw 'That does not look like a MongoDB connection string (must start with mongodb:// or mongodb+srv://).' }

$arguments = @('tools\recover_owner_admin.py', '--phone', $Phone, '--user-id', $UserId, '--expected-db', $DbName,
               '--operation-id', $OperationId, '--operator', $Operator, '--reason', $Reason)
if ($Apply) { $arguments += @('--apply', '--approved-report-sha256', $ApprovedReportSha256, '--backup-ref', $BackupRef, '--maintenance-confirmed') }

$exitCode = 1
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
exit $exitCode
