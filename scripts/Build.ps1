param(
    [switch]$SkipInstall,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found at .venv. Create it first, then install the project requirements."
}

if ($Clean) {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
}

if (-not $SkipInstall) {
    & $python -m pip install -r requirements-build.txt
}

$iconPng = Join-Path $repoRoot "assets\app-icon.png"
$iconIco = Join-Path $repoRoot "assets\app-icon.ico"

if (Test-Path $iconPng) {
    & $python "scripts\make_icon.py" --input $iconPng --output $iconIco
} elseif (-not (Test-Path $iconIco)) {
    throw "Missing icon. Add assets\app-icon.png, or provide assets\app-icon.ico, then run the build again."
}

& $python -m PyInstaller --noconfirm "Thoughtbench.spec"

Write-Host ""
Write-Host "Build complete: dist\Thoughtbench\Thoughtbench.exe"
