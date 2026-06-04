param(
    [switch]$CheckOnly,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$solution = Join-Path $root "Thoughtbench.CSharp.sln"

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Test-Command($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Invoke-NativeCommand([scriptblock]$Command, [string]$FailureMessage) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

Write-Step "Checking .NET SDK"
if (-not (Test-Command "dotnet")) {
    throw "dotnet was not found. Install the .NET 10 SDK or newer."
}

Invoke-NativeCommand { $script:sdks = & dotnet --list-sdks } "Unable to list installed .NET SDKs."
Write-Host $sdks
$hasDotnet10Sdk = $sdks | Where-Object { $_ -match '^10\.' } | Select-Object -First 1
if (-not $hasDotnet10Sdk) {
    throw "This branch targets .NET 10. Install the .NET 10 SDK or make sure it is available on PATH."
}

Write-Step "Checking NVIDIA driver"
if (Test-Command "nvidia-smi") {
    & nvidia-smi
} else {
    Write-Warning "nvidia-smi was not found. ONNX CUDA may fail until NVIDIA drivers are installed."
}

Write-Step "Restoring C# solution"
Invoke-NativeCommand { & dotnet restore $solution } "Failed to restore C# solution."

if ($CheckOnly) {
    Write-Host ""
    Write-Host "C# setup check complete."
    exit 0
}

Write-Step "Building C# solution"
Invoke-NativeCommand { & dotnet build $solution --no-restore } "Failed to build C# solution."

if ($Launch) {
    Write-Step "Launching Thoughtbench.App"
    Invoke-NativeCommand { & dotnet run --project (Join-Path $root "src\Thoughtbench.App\Thoughtbench.App.csproj") --no-build } "Thoughtbench.App exited with an error."
}
