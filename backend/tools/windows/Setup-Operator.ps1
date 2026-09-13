<#
.SYNOPSIS
  One-time setup of the owner's operator environment on Windows (no server is started).

.DESCRIPTION
  Creates backend\.operator-venv and installs only the packages needed by the two operator commands
  (tools\provision_review_access.py and tools\recover_owner_admin.py). Re-running is safe.

  Requirements: Windows 10/11, PowerShell 5.1 or 7+, Python 3.11 or newer from https://www.python.org/downloads/windows/
  (tick "Add python.exe to PATH" during installation), and a clone/download of this repository.

.EXAMPLE
  PS> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  PS> .\backend\tools\windows\Setup-Operator.ps1
#>
$ErrorActionPreference = 'Stop'
$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$venv = Join-Path $backend '.operator-venv'
$python = Join-Path $venv 'Scripts\python.exe'

function Find-Python {
    foreach ($candidate in @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3.11'), @('python'), @('python3'))) {
        try {
            $version = & $candidate[0] @($candidate[1..($candidate.Length - 1)] | Where-Object { $_ }) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]'3.11') { return $candidate }
        } catch { }
    }
    throw 'Python 3.11 or newer was not found. Install it from python.org and re-run this script.'
}

if (-not (Test-Path $python)) {
    $launcher = Find-Python
    Write-Host "Creating operator virtual environment at $venv"
    & $launcher[0] @($launcher[1..($launcher.Length - 1)] | Where-Object { $_ }) -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}

Write-Host 'Installing pinned operator dependencies (this does not install or start the API server)...'
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r (Join-Path $backend 'tools\requirements-operator.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection or proxy and re-run.' }

& $python -c "import motor, pymongo, bcrypt, jwt, PIL, httpx, fastapi, dotenv; print('Operator environment ready:', __import__('sys').version.split()[0])"
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }

Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Store-review accounts : .\backend\tools\windows\Provision-ReviewAccess.ps1 -Environment production -DbName <DB_NAME> -ApiBaseUrl https://<backend-host>/api -Provision -Seed -Verify -NotePath "$env:USERPROFILE\Private\yash-review-production.txt"'
Write-Host '  2. Owner admin recovery  : .\backend\tools\windows\Recover-OwnerAdmin.ps1 -DbName <DB_NAME> -OperationId owner-admin-recovery-<date> -Operator <your-name>'
Write-Host 'Both scripts ask for the MongoDB connection string with a hidden prompt; never type it on the command line.'
