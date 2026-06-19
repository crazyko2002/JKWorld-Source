$ErrorActionPreference = "Stop"
$venv = Join-Path $PSScriptRoot ".venv"

if (-not (Test-Path $venv)) {
    python -m venv $venv
}

$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install -q -r (Join-Path $PSScriptRoot "requirements.txt")

if ($args.Count -eq 0) {
    $env:JKWORLD_ENABLE_PUBLISH = "1"
    & $python (Join-Path $PSScriptRoot "studio_publisher_gui.py")
} elseif ($args[0] -eq "--advanced") {
    $env:JKWORLD_ENABLE_PUBLISH = "1"
    & $python (Join-Path $PSScriptRoot "studio_publisher_gui.py")
} else {
    & $python (Join-Path $PSScriptRoot "screen_detector_prototype.py") @args
}
