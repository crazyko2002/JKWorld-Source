$ErrorActionPreference = "Stop"
$venv = Join-Path $PSScriptRoot ".venv"

if (-not (Test-Path $venv)) {
    python -m venv $venv
}

$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install -q -r (Join-Path $PSScriptRoot "requirements.txt")
& $python (Join-Path $PSScriptRoot "screen_flow_gui.py")

