$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$originalPath = $env:PATH
# Isolate DLL discovery from unrelated tools (for example Poppler's incompatible ICU).
$env:PATH = (Join-Path $repo '.venv\Scripts') + ';' + (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
try {
    & '.\.venv\Scripts\python.exe' -m PyInstaller --clean --noconfirm --windowed --name InterRaterAnalyzer --paths src --collect-submodules docx --collect-submodules reportlab --collect-submodules matplotlib --collect-submodules pypdf --hidden-import PIL.Image --exclude-module pytest --exclude-module tkinter --distpath dist --workpath build --specpath packaging packaging/launcher.py
} finally {
    $env:PATH = $originalPath
}
if ($LASTEXITCODE -ne 0) { throw 'Application bundle failed' }
if (Test-Path -LiteralPath 'dist\InterRaterAnalyzer\_internal\icuuc.dll') {
    throw 'Unexpected private ICU library: the Windows 11 Qt bundle must use Windows ICU'
}
$previousQtPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = 'offscreen'
$acceptanceRoot = Join-Path $repo ('runtime-data\packaged-acceptance-' + [guid]::NewGuid().ToString())
try {
    $acceptanceProcess = Start-Process -FilePath '.\dist\InterRaterAnalyzer\InterRaterAnalyzer.exe' -ArgumentList ('--self-test "' + $acceptanceRoot + '"') -WindowStyle Hidden -PassThru
    $acceptanceProcess.WaitForExit()
    if ($acceptanceProcess.ExitCode -ne 0 -or !(Test-Path -LiteralPath (Join-Path $acceptanceRoot 'acceptance.json'))) {
        throw ('Packaged acceptance failed; inspect ' + $acceptanceRoot)
    }
} finally {
    $env:QT_QPA_PLATFORM = $previousQtPlatform
}
& '.\.tools\inno\ISCC.exe' packaging/analyzer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath '.\dist\installer\InterRaterAnalyzer-0.1.0-Setup.exe'
