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

$ErrorActionPreference = "Stop"

$ModelUrl = "https://huggingface.co/$ModelId"
$NvidiaDriverUrl = "https://www.nvidia.com/Download/index.aspx"
$MinimumVramGb = 8
$RecommendedVramGb = 12
$RecommendedDiskGb = 40
$RequiredModelDrive = "D:"
$DefaultHuggingFaceHome = "D:\LLMProjects\HuggingFace"
$DefaultHuggingFaceHubCache = "D:\LLMProjects\HuggingFace\Hub"

$script:Checks = @()
$script:HardBlocker = $false
$script:SetupNeeded = $false
$script:NextStep = $null

function Add-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Detail,
        [Parameter(Mandatory = $true)]
        [string]$Status,
        [switch]$HardBlocker,
        [switch]$SetupNeeded,
        [string]$NextStep
    )

    $script:Checks += [PSCustomObject]@{
        Name = $Name
        Detail = $Detail
        Status = $Status
    }

    if ($HardBlocker) {
        $script:HardBlocker = $true
    }
    if ($SetupNeeded) {
        $script:SetupNeeded = $true
    }
    if ($NextStep -and -not $script:NextStep) {
        $script:NextStep = $NextStep
    }
}

function Write-Checks {
    Write-Host ""
    Write-Host "Local model readiness check"
    Write-Host ""

    foreach ($check in $script:Checks) {
        $left = "{0}: {1}" -f $check.Name, $check.Detail
        if ($left.Length -gt 58) {
            $left = $left.Substring(0, 55) + "..."
        }
        Write-Host ("{0,-62} {1}" -f $left, $check.Status)
    }
}

function Get-CommandPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function ConvertTo-ProcessArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Argument)

    if ($Argument -eq "") {
        return '""'
    }
    if ($Argument -notmatch '[\s"]') {
        return $Argument
    }

    $result = '"'
    $backslashes = 0
    foreach ($char in $Argument.ToCharArray()) {
        if ($char -eq '\') {
            $backslashes += 1
            continue
        }
        if ($char -eq '"') {
            $result += ('\' * (($backslashes * 2) + 1))
            $result += '"'
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            $result += ('\' * $backslashes)
            $backslashes = 0
        }
        $result += $char
    }
    if ($backslashes -gt 0) {
        $result += ('\' * ($backslashes * 2))
    }
    $result += '"'
    return $result
}

function Join-ProcessArguments {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    return (($Arguments | ForEach-Object { ConvertTo-ProcessArgument -Argument $_ }) -join " ")
}

function Invoke-Capture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 60
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $argumentListProperty = [System.Diagnostics.ProcessStartInfo].GetProperty("ArgumentList")
    if ($argumentListProperty) {
        foreach ($argument in $Arguments) {
            [void]$startInfo.ArgumentList.Add($argument)
        }
    } else {
        $startInfo.Arguments = Join-ProcessArguments -Arguments $Arguments
    }
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
    } catch {
        return [PSCustomObject]@{
            ExitCode = -1
            Output = @($_.Exception.Message)
        }
    }
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            $process.Kill()
        } catch {
        }
        return [PSCustomObject]@{
            ExitCode = -1
            Output = @("Timed out after $TimeoutSeconds seconds")
        }
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()

    $output = @()
    if ($stdout) {
        $output += ($stdout -split "`r?`n")
    }
    if ($stderr) {
        $output += ($stderr -split "`r?`n")
    }

    return [PSCustomObject]@{
        ExitCode = $process.ExitCode
        Output = $output
    }
}

function Test-Python312 {
    param([Parameter(Mandatory = $true)][string]$PyLauncherPath)

    $result = Invoke-Capture -FilePath $PyLauncherPath -Arguments @("-3.12", "-c", "import sys; print(sys.executable); print(sys.version.split()[0])")
    if ($result.ExitCode -ne 0) {
        return $null
    }

    $lines = @($result.Output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
    if ($lines.Count -lt 2) {
        return $null
    }

    return [PSCustomObject]@{
        Exe = $lines[0]
        Version = $lines[1]
    }
}

function Test-VenvPython {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return $null
    }

    $result = Invoke-Capture -FilePath $PythonPath -Arguments @("-c", "import sys; print(sys.version.split()[0])")
    if ($result.ExitCode -ne 0) {
        return $null
    }

    $version = @($result.Output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })[0]
    return [PSCustomObject]@{
        Exe = $PythonPath
        Version = $version
    }
}

function Install-Requirements {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [string]$RequirementsPath
    )

    Write-Host ""
    Write-Host "Installing Python dependencies. This can take a while..."
    & $PythonPath -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }

    & $PythonPath -m pip install -r $RequirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install requirements.txt."
    }
}

function Test-TorchCuda {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    $code = @"
import torch
print("version=" + torch.__version__)
print("cuda=" + str(torch.cuda.is_available()))
if torch.cuda.is_available():
    capability = torch.cuda.get_device_capability(0)
    arch = "sm_{0}{1}".format(*capability)
    arch_list = torch.cuda.get_arch_list()
    print("name=" + torch.cuda.get_device_name(0))
    print("capability={0}.{1}".format(*capability))
    print("arch=" + arch)
    print("arch_list=" + ",".join(arch_list))
    print("arch_supported=" + str(arch in arch_list))
    try:
        value = (torch.ones(1, device="cuda") + 1).cpu().item()
        print("cuda_op=" + str(value))
    except Exception as exc:
        print("cuda_op_error=" + type(exc).__name__ + ": " + str(exc))
"@
    $result = Invoke-Capture -FilePath $PythonPath -Arguments @("-c", $code)
    if ($result.ExitCode -ne 0) {
        return [PSCustomObject]@{
            Ok = $false
            Detail = "PyTorch import failed"
            Output = ($result.Output -join "`n")
        }
    }

    $lines = @($result.Output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
    $values = @{}
    foreach ($line in $lines) {
        $separator = $line.IndexOf("=")
        if ($separator -gt 0) {
            $values[$line.Substring(0, $separator)] = $line.Substring($separator + 1)
        }
    }

    $cudaAvailable = $values["cuda"] -eq "True"
    $name = $values["name"]
    $capability = $values["capability"]
    $arch = $values["arch"]
    $archSupported = $values["arch_supported"] -eq "True"
    $cudaOpOk = $values.ContainsKey("cuda_op")

    if (-not $cudaAvailable) {
        $detail = "CUDA unavailable"
    } elseif (-not $archSupported) {
        $detail = "$name compute capability $capability is not supported by installed PyTorch"
    } elseif (-not $cudaOpOk) {
        $detail = "$name CUDA test failed"
    } elseif ($capability) {
        $detail = "$name (compute capability $capability)"
    } else {
        $detail = $name
    }

    return [PSCustomObject]@{
        Ok = ($cudaAvailable -and $archSupported -and $cudaOpOk)
        Detail = $detail
        Capability = $capability
        Arch = $arch
        Output = ($result.Output -join "`n")
    }
}

function Test-HuggingFaceLogin {
    param([Parameter(Mandatory = $true)][string]$HuggingFaceCliPath)

    $result = Invoke-Capture -FilePath $HuggingFaceCliPath -Arguments @("auth", "whoami") -TimeoutSeconds 15
    if ($result.ExitCode -ne 0) {
        $result = Invoke-Capture -FilePath $HuggingFaceCliPath -Arguments @("whoami") -TimeoutSeconds 15
    }
    if ($result.ExitCode -eq 0) {
        $name = @($result.Output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })[0]
        if ($name) {
            return [PSCustomObject]@{ Ok = $true; Detail = $name }
        }
        return [PSCustomObject]@{ Ok = $true; Detail = "logged in" }
    }

    return [PSCustomObject]@{ Ok = $false; Detail = "not logged in" }
}

function Test-IsWindows {
    if (Get-Variable -Name IsWindows -Scope Global -ErrorAction SilentlyContinue) {
        return $IsWindows
    }

    return [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
}

function Test-PathOnRequiredModelDrive {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    return $fullPath.StartsWith("$RequiredModelDrive\", [System.StringComparison]::OrdinalIgnoreCase)
}

function Ensure-HuggingFaceCache {
    param([switch]$Apply)

    $hubCache = $env:HF_HUB_CACHE
    if ([string]::IsNullOrWhiteSpace($hubCache)) {
        $hubCache = $env:HUGGINGFACE_HUB_CACHE
    }

    if ([string]::IsNullOrWhiteSpace($hubCache)) {
        $hubCache = if ([string]::IsNullOrWhiteSpace($env:HF_HOME)) {
            $DefaultHuggingFaceHubCache
        } else {
            Join-Path $env:HF_HOME "hub"
        }
    }

    if (-not (Test-PathOnRequiredModelDrive -Path $hubCache)) {
        Add-Check -Name "Hugging Face cache" -Detail "HF_HUB_CACHE=$hubCache" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Set HF_HUB_CACHE to $DefaultHuggingFaceHubCache so model files stay on $RequiredModelDrive."
        return $false
    }

    if ([string]::IsNullOrWhiteSpace($env:HF_HOME)) {
        if ($Apply) {
            [Environment]::SetEnvironmentVariable("HF_HOME", $DefaultHuggingFaceHome, "User")
            $env:HF_HOME = $DefaultHuggingFaceHome
        } else {
            Add-Check -Name "Hugging Face home" -Detail "HF_HOME is not set" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Set HF_HOME to $DefaultHuggingFaceHome so Hugging Face metadata also stays on $RequiredModelDrive."
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($env:HF_HOME) -and -not (Test-PathOnRequiredModelDrive -Path $env:HF_HOME)) {
        Add-Check -Name "Hugging Face home" -Detail "HF_HOME=$env:HF_HOME" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Set HF_HOME to $DefaultHuggingFaceHome so Hugging Face metadata also stays on $RequiredModelDrive."
        return $false
    }

    if ($Apply) {
        $hfHome = if ([string]::IsNullOrWhiteSpace($env:HF_HOME)) { $DefaultHuggingFaceHome } else { $env:HF_HOME }
        New-Item -ItemType Directory -Force -Path $hfHome | Out-Null
        New-Item -ItemType Directory -Force -Path $hubCache | Out-Null
        [Environment]::SetEnvironmentVariable("HF_HUB_CACHE", $hubCache, "User")
        $env:HF_HUB_CACHE = $hubCache
    }

    Add-Check -Name "Hugging Face cache" -Detail "HF_HUB_CACHE=$hubCache" -Status "OK"
    return $true
}

function Invoke-ModelDownload {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    $code = @"
from huggingface_hub import snapshot_download
snapshot_download("$ModelId")
print("Downloaded or found cached model: $ModelId")
"@

    Write-Host ""
    Write-Host "Checking/downloading model files..."
    & $PythonPath -c $code
    return $LASTEXITCODE
}

function Add-HuggingFaceCliCheck {
    param([Parameter(Mandatory = $true)][string]$CliPath)

    if (Test-Path -LiteralPath $CliPath -PathType Leaf) {
        $hfLogin = Test-HuggingFaceLogin -HuggingFaceCliPath $CliPath
        if ($hfLogin.Ok) {
            Add-Check -Name "Hugging Face login" -Detail $hfLogin.Detail -Status "OK"
        } else {
            Add-Check -Name "Hugging Face login" -Detail "optional, not logged in" -Status "SKIPPED"
        }
    } else {
        Add-Check -Name "Hugging Face login" -Detail "optional; hf CLI unavailable" -Status "SKIPPED"
    }
}

try {
    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $venvHfCli = Join-Path $repoRoot ".venv\Scripts\hf.exe"
    $legacyVenvHfCli = Join-Path $repoRoot ".venv\Scripts\huggingface-cli.exe"
    $requirementsPath = Join-Path $repoRoot "requirements.txt"
    $pascalRequirementsPath = Join-Path $repoRoot "requirements-pascal.txt"
    $gpuComputeCapability = $null

    if (-not (Test-IsWindows)) {
        Add-Check -Name "Windows" -Detail "not detected" -Status "NOT RECOMMENDED" -HardBlocker -NextStep "Run this helper on Windows, or use the manual setup path for your platform."
    } else {
        Add-Check -Name "Windows" -Detail "detected" -Status "OK"
    }

    $nvidiaSmi = Get-CommandPath -Name "nvidia-smi"
    if (-not $nvidiaSmi) {
        Add-Check -Name "GPU" -Detail "nvidia-smi not found" -Status "NOT RECOMMENDED" -HardBlocker -NextStep "Install or update the NVIDIA driver, then re-run this script: $NvidiaDriverUrl"
    } else {
        $gpuResult = Invoke-Capture -FilePath $nvidiaSmi -Arguments @("--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader,nounits")
        if ($gpuResult.ExitCode -ne 0) {
            Add-Check -Name "Driver" -Detail "nvidia-smi failed" -Status "NOT RECOMMENDED" -HardBlocker -NextStep "Install or update the NVIDIA driver, then re-run this script: $NvidiaDriverUrl"
        } else {
            $bestGpu = $null
            foreach ($line in $gpuResult.Output) {
                $text = "$line".Trim()
                if (-not $text) { continue }
                $parts = $text -split ","
                if ($parts.Count -lt 2) { continue }
                $computeCapText = if ($parts.Count -ge 3) { $parts[$parts.Count - 1].Trim() } else { $null }
                $memoryIndex = if ($parts.Count -ge 3) { $parts.Count - 2 } else { $parts.Count - 1 }
                $memoryMbText = $parts[$memoryIndex].Trim()
                $name = (($parts[0..($memoryIndex - 1)] -join ",").Trim())
                $memoryMb = 0
                if ([int]::TryParse($memoryMbText, [ref]$memoryMb)) {
                    if (-not $bestGpu -or $memoryMb -gt $bestGpu.MemoryMb) {
                        $bestGpu = [PSCustomObject]@{
                            Name = $name
                            MemoryMb = $memoryMb
                            ComputeCapability = $computeCapText
                        }
                    }
                }
            }

            if (-not $bestGpu) {
                Add-Check -Name "GPU" -Detail "could not read NVIDIA GPU details" -Status "NOT RECOMMENDED" -HardBlocker -NextStep "Check that the NVIDIA driver is installed and that nvidia-smi works in PowerShell."
            } else {
                $vramGb = [math]::Round($bestGpu.MemoryMb / 1024, 1)
                $gpuComputeCapability = $bestGpu.ComputeCapability
                if ($vramGb -lt $MinimumVramGb) {
                    Add-Check -Name "GPU" -Detail ("{0}, {1} GB VRAM" -f $bestGpu.Name, $vramGb) -Status "NOT RECOMMENDED" -HardBlocker -NextStep "Use a machine with an NVIDIA GPU with at least 8 GB VRAM, or run a smaller model."
                } elseif ($vramGb -lt $RecommendedVramGb) {
                    Add-Check -Name "GPU" -Detail ("{0}, {1} GB VRAM" -f $bestGpu.Name, $vramGb) -Status "LOW VRAM OK"
                } else {
                    Add-Check -Name "GPU" -Detail ("{0}, {1} GB VRAM" -f $bestGpu.Name, $vramGb) -Status "OK"
                }
                Add-Check -Name "Driver" -Detail "NVIDIA driver detected" -Status "OK"
            }
        }
    }

    $driveRoot = [System.IO.Path]::GetPathRoot($repoRoot.Path)
    $drive = Get-PSDrive -Name $driveRoot.TrimEnd(":\") -ErrorAction SilentlyContinue
    if ($drive) {
        $freeGb = [math]::Round($drive.Free / 1GB, 1)
        if ($freeGb -lt $RecommendedDiskGb) {
            Add-Check -Name "Disk space" -Detail "$freeGb GB free" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Free up disk space before downloading model files and installing dependencies."
        } else {
            Add-Check -Name "Disk space" -Detail "$freeGb GB free" -Status "OK"
        }
    } else {
        Add-Check -Name "Disk space" -Detail "could not check" -Status "UNKNOWN"
    }

    $venvInfo = Test-VenvPython -PythonPath $venvPython
    $venvReady = $venvInfo -and $venvInfo.Version.StartsWith("3.12.")
    $pyLauncher = Get-CommandPath -Name "py"
    $python312 = $null
    if (-not $pyLauncher) {
        if ($venvReady) {
            Add-Check -Name "Python 3.12" -Detail ".venv uses $($venvInfo.Version)" -Status "OK"
        } else {
            Add-Check -Name "Python 3.12" -Detail "py launcher not found" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Install Python 3.12 from python.org, then re-run this script."
        }
    } else {
        $python312 = Test-Python312 -PyLauncherPath $pyLauncher
        if (-not $python312 -or -not $python312.Version.StartsWith("3.12.")) {
            if ($venvReady) {
                Add-Check -Name "Python 3.12" -Detail ".venv uses $($venvInfo.Version)" -Status "OK"
            } else {
                Add-Check -Name "Python 3.12" -Detail "missing" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Install Python 3.12 from python.org, then re-run this script."
            }
        } else {
            Add-Check -Name "Python 3.12" -Detail $python312.Version -Status "OK"
        }
    }

    if ($venvReady) {
        Add-Check -Name "Virtual environment" -Detail ".venv ready" -Status "OK"
    } elseif ($CheckOnly) {
        Add-Check -Name "Virtual environment" -Detail "missing or not Python 3.12" -Status "WILL CREATE" -SetupNeeded -NextStep "Run .\scripts\Setup-Thoughtbench.ps1 without -CheckOnly to create the virtual environment."
    } elseif ($python312) {
        Write-Host ""
        Write-Host "Creating .venv with Python 3.12..."
        & $pyLauncher -3.12 -m venv (Join-Path $repoRoot ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create .venv with Python 3.12."
        }
        $venvInfo = Test-VenvPython -PythonPath $venvPython
        if (-not $venvInfo) {
            throw "Created .venv, but could not run its Python executable."
        }
        Add-Check -Name "Virtual environment" -Detail ".venv created" -Status "OK"
    }

    if ($gpuComputeCapability) {
        $computeCapabilityValue = 0.0
        if ([double]::TryParse($gpuComputeCapability, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$computeCapabilityValue)) {
            if ($computeCapabilityValue -lt 7.5) {
                $requirementsPath = $pascalRequirementsPath
                Add-Check -Name "PyTorch package set" -Detail "CUDA 11.8 for compute capability $gpuComputeCapability" -Status "PASCAL"
            } else {
                Add-Check -Name "PyTorch package set" -Detail "CUDA 12.8 for compute capability $gpuComputeCapability" -Status "CURRENT"
            }
        }
    }

    $torchOk = $false
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $torchCheck = Test-TorchCuda -PythonPath $venvPython
        if ($torchCheck.Ok) {
            $torchOk = $true
            Add-Check -Name "PyTorch CUDA" -Detail $torchCheck.Detail -Status "OK"
        } elseif ($CheckOnly) {
            Add-Check -Name "PyTorch CUDA" -Detail $torchCheck.Detail -Status "ACTION NEEDED" -SetupNeeded -NextStep "Run .\scripts\Setup-Thoughtbench.ps1 without -CheckOnly to install compatible PyTorch packages."
        } elseif (-not $script:HardBlocker) {
            Install-Requirements -PythonPath $venvPython -RequirementsPath $requirementsPath
            $torchCheck = Test-TorchCuda -PythonPath $venvPython
            if ($torchCheck.Ok) {
                $torchOk = $true
                Add-Check -Name "PyTorch CUDA" -Detail $torchCheck.Detail -Status "OK"
            } else {
                Add-Check -Name "PyTorch CUDA" -Detail $torchCheck.Detail -Status "ACTION NEEDED" -SetupNeeded -NextStep "PyTorch installed, but this GPU is still not usable by the installed CUDA wheel. Re-run setup, or install a PyTorch build that supports this GPU."
            }
        }
    } else {
        Add-Check -Name "PyTorch CUDA" -Detail "not checked yet" -Status "PENDING" -SetupNeeded
    }

    if (-not (Test-Path -LiteralPath $venvHfCli -PathType Leaf) -and (Test-Path -LiteralPath $legacyVenvHfCli -PathType Leaf)) {
        $venvHfCli = $legacyVenvHfCli
    }

    $huggingFaceCacheOk = Ensure-HuggingFaceCache -Apply:(-not $CheckOnly)

    Add-HuggingFaceCliCheck -CliPath $venvHfCli

    if ($PreDownloadModel -and -not $script:HardBlocker -and $torchOk -and $huggingFaceCacheOk) {
        $downloadExitCode = Invoke-ModelDownload -PythonPath $venvPython
        if ($downloadExitCode -eq 0) {
            Add-Check -Name "Model files" -Detail "downloaded or cached" -Status "OK"
        } else {
            Add-Check -Name "Model files" -Detail "download failed" -Status "ACTION NEEDED" -SetupNeeded -NextStep "Check $ModelUrl in a browser. If Hugging Face asks you to sign in, run .\.venv\Scripts\hf.exe auth login, then re-run with -PreDownloadModel."
        }
    } elseif ($PreDownloadModel -and -not $huggingFaceCacheOk) {
        Add-Check -Name "Model files" -Detail "cache path is not ready" -Status "PENDING" -SetupNeeded
    } elseif ($PreDownloadModel -and -not $torchOk) {
        Add-Check -Name "Model files" -Detail "not attempted" -Status "PENDING" -SetupNeeded
    }

    Write-Checks

    if ($script:HardBlocker) {
        Write-Host ""
        Write-Host "Result: not recommended"
        Write-Host ""
        Write-Host "Next step:"
        Write-Host "  $script:NextStep"
        exit 2
    }

    if ($script:SetupNeeded) {
        Write-Host ""
        Write-Host "Result: setup needed"
        if ($script:NextStep) {
            Write-Host ""
            Write-Host "Next step:"
            Write-Host "  $script:NextStep"
        }
        exit 1
    }

    Write-Host ""
    Write-Host "Result: ready"
    Write-Host ""
    Write-Host "Model loading:"
    Write-Host "  On GPUs below 12 GB VRAM, the app automatically uses 4-bit low-VRAM mode."
    Write-Host "  Override with THOUGHTBENCH_LOAD_MODE=auto, THOUGHTBENCH_LOAD_MODE=4bit, or THOUGHTBENCH_LOAD_MODE=bf16."

    if ($Launch) {
        Write-Host ""
        Write-Host "Launching Thoughtbench..."
        & $venvPython (Join-Path $repoRoot "app.py")
    }

    exit 0
} catch {
    Write-Host ""
    Write-Host "Result: unexpected script error"
    Write-Host ""
    Write-Host $_.Exception.Message
    exit 3
}
