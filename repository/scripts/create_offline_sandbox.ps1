$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$evidence = Join-Path $repo 'runtime-data\offline-evidence'
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$repoXml = [System.Security.SecurityElement]::Escape($repo)
$evidenceXml = [System.Security.SecurityElement]::Escape($evidence)
$configuration = @"
<Configuration>
  <Networking>Disable</Networking>
  <MappedFolders>
    <MappedFolder><HostFolder>$repoXml</HostFolder><SandboxFolder>C:\Package</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$evidenceXml</HostFolder><SandboxFolder>C:\Evidence</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Package\scripts\offline_acceptance.ps1</Command></LogonCommand>
</Configuration>
"@
$path = Join-Path $repo 'runtime-data\offline-acceptance.wsb'
Set-Content -LiteralPath $path -Value $configuration
Write-Output $path
