param(
    [switch]$CheckOnly,
    [switch]$PreDownloadModel,
    [switch]$Launch,
    [ValidateSet(
        "google/gemma-4-E2B-it",
        "google/gemma-4-E4B-it",
        "google/gemma-4-26B-A4B-it",
        "google/gemma-4-31B-it",
        "Qwen/Qwen3-0.6B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-8B"
    )]
    [string]$ModelId = "google/gemma-4-E2B-it"
)

$target = Join-Path $PSScriptRoot "Setup-Thoughtbench.ps1"
$arguments = @{ ModelId = $ModelId }
if ($CheckOnly) { $arguments.CheckOnly = $true }
if ($PreDownloadModel) { $arguments.PreDownloadModel = $true }
if ($Launch) { $arguments.Launch = $true }

& $target @arguments
exit $LASTEXITCODE
