Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Resolve-PythonCommand {
    foreach ($candidate in @("py", "python", "python3")) {
        try {
            if ($candidate -eq "py") {
                & $candidate -3 -c "print('ok')" 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { return @($candidate, "-3") }
            } else {
                & $candidate -c "print('ok')" 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { return @($candidate) }
            }
        } catch {
        }
    }
    throw "No usable Python interpreter found (tried: py, python, python3)."
}

$pyCmd = Resolve-PythonCommand
$pythonExe = $pyCmd[0]
$pythonArgs = @()
if ($pyCmd.Count -gt 1) {
    $pythonArgs = $pyCmd[1..($pyCmd.Count - 1)]
}

Write-Host "Using Python launcher: $($pyCmd -join ' ')"

# Create local virtual environment.
& $pythonExe @pythonArgs -m venv .venv

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment was created but python executable was not found at $venvPython"
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host "Environment ready."
Write-Host "Run benchmarks with:"
Write-Host "  .venv\\Scripts\\python.exe financial_sms_emoa\\scripts\\run_benchmarks.py"
Write-Host "  .venv\\Scripts\\python.exe project_brkga\\scripts\\run_benchmarks.py"
