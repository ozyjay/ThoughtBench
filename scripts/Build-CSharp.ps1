param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [switch]$SelfContained
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$appProject = Join-Path $root "src\Thoughtbench.App\Thoughtbench.App.csproj"
$cliProject = Join-Path $root "src\Thoughtbench.Cli\Thoughtbench.Cli.csproj"
$publishRoot = Join-Path $root "dist\csharp"
$selfContainedArg = if ($SelfContained) { "true" } else { "false" }

New-Item -ItemType Directory -Force -Path $publishRoot | Out-Null

dotnet restore (Join-Path $root "Thoughtbench.CSharp.sln")
dotnet publish $appProject -c $Configuration -r win-x64 --self-contained $selfContainedArg -o (Join-Path $publishRoot "app")
dotnet publish $cliProject -c $Configuration -r win-x64 --self-contained $selfContainedArg -o (Join-Path $publishRoot "cli")

Write-Host "Published C# artifacts to $publishRoot"
