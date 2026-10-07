# Run this yourself in an interactive PowerShell terminal.
# Passwords are read by SSH from your terminal, never by this script or Git.
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')][string]$HostAlias,
    [switch]$SetupKey
)
$ErrorActionPreference = 'Stop'
$taskKey = Join-Path $env:USERPROFILE '.ssh/ledger_lab_ed25519'
if ($SetupKey) {
    if (-not (Test-Path -LiteralPath $taskKey)) {
        Write-Host 'Creating a dedicated local SSH key outside the repository.'
        Write-Host 'Choose a passphrase; if you set one, load the key in your SSH agent for subsequent automatic access.'
        & ssh-keygen -t ed25519 -f $taskKey -C 'ledger-phase1'
        if ($LASTEXITCODE -ne 0) { throw 'SSH key generation failed.' }
    }
    if (-not (Test-Path -LiteralPath ($taskKey + '.pub'))) { throw 'Public key missing; do not overwrite an existing private key.' }
    Write-Host 'Registering ONLY this public key in the account authorized_keys. SSH may ask for your server password.'
    & python (Join-Path $PSScriptRoot 'setup_lab_key.py') --host $HostAlias --public-key ($taskKey + '.pub')
    if ($LASTEXITCODE -ne 0) { throw 'Public-key registration failed. No FEMU command was run.' }
}
if (-not (Test-Path -LiteralPath $taskKey)) {
    Write-Host 'Opening an ordinary password SSH session. To prepare automatic access later, use -SetupKey.'
    & ssh -o StrictHostKeyChecking=yes $HostAlias
} else {
    & ssh -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i $taskKey $HostAlias
}
