param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
$buildPathBefore = $env:PATH
$buildQtBefore = $env:QT_QPA_PLATFORM
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $buildPython = (Get-Command $Python -ErrorAction Stop).Source
    $ffmpegPath = (Get-Command ffmpeg -ErrorAction Stop).Source
    $ffprobePath = (Get-Command ffprobe -ErrorAction Stop).Source
    & $buildPython -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    # Avoid collecting incompatible DLLs from unrelated software in PATH.
    # In particular, Qt may require Windows' ICU rather than another app's ICU.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$(Split-Path -Parent $buildPython)"
    & $buildPython -m PyInstaller --noconfirm --clean --windowed --onedir --name AutoCredit `
        --add-binary "${ffmpegPath};bin" --add-binary "${ffprobePath};bin" `
        scripts/entry.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    $buildExe = Join-Path (Get-Location) 'dist\AutoCredit\AutoCredit.exe'
    $buildCheckDir = Join-Path (Get-Location) 'build\packaged-check'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $buildCheck = Start-Process -FilePath $buildExe -ArgumentList '--self-check', ('"{0}"' -f $buildCheckDir) -WindowStyle Hidden -PassThru
    if (-not $buildCheck.WaitForExit(60000)) {
        $buildCheck.Kill()
        throw 'Packaged self-check timed out. Build is not verified.'
    }
    if ($buildCheck.ExitCode -ne 0) { throw "Packaged self-check failed with exit code $($buildCheck.ExitCode)." }
    $buildReport = Get-Content -LiteralPath (Join-Path $buildCheckDir 'report.json') -Raw | ConvertFrom-Json
    if (-not $buildReport.ok) { throw "Packaged self-check failed: $($buildReport.error)" }
    Write-Host 'Packaged self-check passed (real MP4 export and Qt preview).'
    Write-Host 'Built dist\AutoCredit\AutoCredit.exe. Distribute the complete AutoCredit folder.'
} finally {
    $env:PATH = $buildPathBefore
    $env:QT_QPA_PLATFORM = $buildQtBefore
    Pop-Location
}
