param([string]$PackageRoot = 'C:\Package', [string]$EvidenceRoot = 'C:\Evidence')
$ErrorActionPreference = 'Stop'
if ($env:USERNAME -ne 'WDAGUtilityAccount') {
    throw 'Run this install/uninstall acceptance script only inside Windows Sandbox.'
}
if (Get-NetAdapter -ErrorAction Stop | Where-Object Status -EQ 'Up') {
    throw 'Network adapter is enabled; launch the generated networking-disabled Sandbox configuration.'
}
$installer = Join-Path $PackageRoot 'dist\installer\InterRaterAnalyzer-0.1.0-Setup.exe'
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\InterRaterAnalyzer'
$process = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /NOICONS' -WindowStyle Hidden -PassThru
$process.WaitForExit()
if ($process.ExitCode -ne 0) { throw 'Clean installation failed' }
$evidence = Join-Path $EvidenceRoot ('run-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$env:QT_QPA_PLATFORM = 'offscreen'
$executable = Join-Path $installDir 'InterRaterAnalyzer.exe'
$process = Start-Process -FilePath $executable -ArgumentList ('--self-test "' + $evidence + '"') -WindowStyle Hidden -PassThru
$process.WaitForExit()
if ($process.ExitCode -ne 0) { throw 'Offline end-to-end acceptance failed; inspect evidence directory' }
$permanent = Join-Path $env:LOCALAPPDATA 'InterRaterAnalyzer'
New-Item -ItemType Directory -Path $permanent -Force | Out-Null
$sentinel = Join-Path $permanent 'permanent-data-retention.txt'
Set-Content -LiteralPath $sentinel -Value 'Must survive uninstall'
$uninstaller = Join-Path $installDir 'unins000.exe'
$process = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -WindowStyle Hidden -PassThru
$process.WaitForExit()
if (!(Test-Path -LiteralPath $sentinel)) { throw 'Uninstall removed permanent data' }
@{ passed = $true; clean_install = $true; uninstall_retains_data = $true; network = 'Windows Sandbox Networking Disable'; installer_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'installation.json')
