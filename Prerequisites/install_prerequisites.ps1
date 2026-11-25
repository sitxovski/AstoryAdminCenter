# Copyright (c) 2026 @sitxovski (Discord)
# Astory Admin Center - install what is needed. Run on the DEVELOPMENT PC, and once more on the GAME SERVER with -Server.
#   install_prerequisites.bat            development PC (deploy the panel, run the Discord / Telegram bot)
#   install_prerequisites.bat -Server    game server (the panel service runs there)
#   add -Yes to install everything without questions
param([switch]$Server, [switch]$Yes)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\_setup\install_common.ps1')
if (-not (Test-Winget)) { exit 1 }

$pkgs = @(
    @{ Name = 'Python 3.13'; Id = 'Python.Python.3.13'; Why = 'the panel service, deploy scripts and the bot are Python' },
    @{ Name = 'Microsoft ODBC Driver 17 for SQL Server'; Id = 'Microsoft.msodbcsql.17'; Why = 'pyodbc connects to SQL Server with it (config: sql_driver)' }
)
if ($Server) {
    $pkgs += @{ Name = 'Tailscale (optional)'; Id = 'Tailscale.Tailscale'; Why = 'private VPN address for the panel and SSH' }
} else {
    $pkgs += @{ Name = 'Git'; Id = 'Git.Git'; Why = 'getting the sources' }
    $pkgs += @{ Name = 'Tailscale (optional)'; Id = 'Tailscale.Tailscale'; Why = 'reach the server by its VPN address' }
}
$failed = Install-Packages -Packages $pkgs -Yes:$Yes
$pyok = Install-PythonRequirements (Join-Path $PSScriptRoot 'requirements.txt')

$manual = @()
if ($Server) {
    $manual += 'SQL Server 2019 Express (the version Astory runs on - not 2022): https://www.microsoft.com/download/details.aspx?id=101064 -> Custom: instance SQLEXPRESS, Mixed Mode authentication, server collation Cyrillic_General_CI_AS, then enable TCP/IP 1433 in SQL Server Configuration Manager.'
    $manual += 'SQL Server with the game databases: see Astory Server (https://github.com/sitxovski/AstoryServer) Prerequisites\setup_server.ps1.'
    $manual += 'OpenSSH Server (as Administrator): Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 ; Start-Service sshd ; Set-Service sshd -StartupType Automatic. Put your PC public key into C:\ProgramData\ssh\administrators_authorized_keys.'
    $manual += 'SQL Server: enable TCP/IP on port 1433 (SQL Server Configuration Manager) and restore / attach the game databases.'
    $manual += 'Install Python for the Administrator account (or set ASTORY_SERVER_PYTHON in _setup\configure.bat to your python.exe).'
} else {
    $manual += 'Create an SSH key: ssh-keygen -t ed25519 -f %USERPROFILE%\.ssh\<ASTORY_SSH_KEY_NAME> and copy the .pub file to the server (see the server step above).'
    $manual += 'Run _setup\configure.bat (addresses, paths, keys), then: python AstoryAdminCenter\deploy\deploy_admin_center.py'
}
Show-Manual $manual
if ($failed) { Write-Host ('Failed: ' + ($failed -join ', ')) -ForegroundColor Red }
if (-not $pyok) { Write-Host 'Python packages were not installed - see the message above.' -ForegroundColor Yellow }
