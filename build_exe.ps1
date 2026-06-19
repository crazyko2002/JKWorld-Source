$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    python -m venv (Join-Path $PSScriptRoot ".venv")
}

& $python -m pip install -q -r (Join-Path $PSScriptRoot "requirements.txt")
& $python -m pip install -q -r (Join-Path $PSScriptRoot "requirements-build.txt")
& $python (Join-Path $PSScriptRoot "scripts\build_exe.py")

