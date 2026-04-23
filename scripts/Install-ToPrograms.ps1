param(
    [string]$InstallRoot,
    [string]$InstallPath,
    [string]$AppName = "Thoughtbench",
    [switch]$Replace
)

$ErrorActionPreference = "Stop"

function Test-AppInstallDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$AppName
    )

    $exePath = Join-Path $Path "$AppName.exe"
    $internalDir = Join-Path $Path "_internal"
    return (Test-Path -LiteralPath $exePath -PathType Leaf) -and
        (Test-Path -LiteralPath $internalDir -PathType Container)
}

function Assert-SafeReplaceTarget {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [Parameter(Mandatory = $true)]
        [string]$InstallRootPath,
        [Parameter(Mandatory = $true)]
        [string]$AppName
    )

    $targetPath = $TargetPath.TrimEnd('\')
    $rootPath = $InstallRootPath.TrimEnd('\')
    $driveRoot = [System.IO.Path]::GetPathRoot($targetPath).TrimEnd('\')
    $expectedLeaf = $AppName

    if ($targetPath.Equals($driveRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace drive root: $targetPath"
    }

    if ($targetPath.Equals($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace install root directly: $targetPath. Use -InstallRoot `"$targetPath`" or -InstallPath `"$targetPath\$AppName`"."
    }

    if (-not $targetPath.StartsWith($rootPath + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace target outside install root: $targetPath"
    }

    if (-not (Split-Path -Leaf $targetPath).Equals($expectedLeaf, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace '$targetPath' because the final folder is not '$expectedLeaf'. Use -InstallPath ending in '\$AppName'."
    }

    if (-not (Test-AppInstallDirectory -Path $targetPath -AppName $AppName)) {
        throw "Refusing to replace '$targetPath' because it does not look like an existing $AppName install."
    }
}

function Update-ShortcutIcon {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ShortcutPath,
        [Parameter(Mandatory = $true)]
        [string]$TargetExe,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    if (-not (Test-Path -LiteralPath $ShortcutPath -PathType Leaf)) {
        return $false
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetExe
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = "$TargetExe,0"
    $shortcut.Save()
    return $true
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$defaultInstallRoot = Join-Path $env:LOCALAPPDATA "Programs"
if ($InstallRoot -and $InstallPath) {
    throw "Use either -InstallRoot or -InstallPath, not both."
}

if (-not $InstallRoot -and -not $InstallPath) {
    $InstallRoot = $defaultInstallRoot
}

$sourceDir = Join-Path $repoRoot "dist\$AppName"
$sourceExe = Join-Path $sourceDir "$AppName.exe"
if ($InstallPath) {
    $targetDir = $InstallPath
    $InstallRoot = Split-Path -Parent $targetDir
} else {
    $targetDir = Join-Path $InstallRoot $AppName
}
$targetExe = Join-Path $targetDir "$AppName.exe"

if (-not (Test-Path $sourceExe)) {
    throw "Build output not found at $sourceExe. Run .\scripts\Build.ps1 first."
}

if (-not (Test-Path $InstallRoot)) {
    New-Item -ItemType Directory -Path $InstallRoot | Out-Null
}

if ((Test-Path $targetDir) -and $Replace) {
    $resolvedTarget = Resolve-Path -LiteralPath $targetDir
    $resolvedRoot = Resolve-Path -LiteralPath $InstallRoot
    Assert-SafeReplaceTarget -TargetPath $resolvedTarget.Path -InstallRootPath $resolvedRoot.Path -AppName $AppName
    Remove-Item -LiteralPath $resolvedTarget.Path -Recurse -Force
}

if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir | Out-Null
}

Copy-Item -Path (Join-Path $sourceDir "*") -Destination $targetDir -Recurse -Force

$pinnedTaskbarShortcut = Join-Path $env:APPDATA "Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\$AppName.lnk"
$updatedPinnedShortcut = Update-ShortcutIcon `
    -ShortcutPath $pinnedTaskbarShortcut `
    -TargetExe $targetExe `
    -WorkingDirectory $targetDir

Write-Host ""
Write-Host "Installed $AppName to:"
Write-Host "  $targetDir"
Write-Host ""
Write-Host "Executable:"
Write-Host "  $targetExe"
if ($updatedPinnedShortcut) {
    Write-Host ""
    Write-Host "Updated pinned taskbar shortcut icon:"
    Write-Host "  $pinnedTaskbarShortcut"
    Write-Host ""
    Write-Host "If the taskbar still shows the old icon, unpin and repin the app or restart Explorer."
}
