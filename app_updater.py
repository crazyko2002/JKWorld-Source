"""Self-update support for the packaged JKWorld NoBrain app."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile
from typing import Any, Callable
from urllib.request import Request, urlopen

from flow_distribution import load_update_settings
from version_utils import should_update_version, version_numbers


LogFn = Callable[[str], None]
APP_VERSION_FILE = ".app_version"
UPDATE_DIR = "_jkworld_app_update"
DATA_ITEMS = {
    ".flow_version",
    ".player_runtime.yaml",
    ".studio_runtime.yaml",
    "config.yaml",
    "macro_config.yaml",
    "logs",
    "numpad",
    "published",
    "recordings",
    "templates",
}


@dataclass(frozen=True)
class AppUpdateResult:
    updated: bool
    restart_required: bool
    current_version: str
    latest_version: str
    message: str


def installed_app_version(root: Path) -> str:
    path = root / APP_VERSION_FILE
    if not path.exists():
        return "dev"
    return path.read_text(encoding="utf-8").strip() or "dev"


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def should_update_app(current: str, latest: str) -> bool:
    if not version_numbers(current):
        return False
    return should_update_version(current, latest)


def _download_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={
        "User-Agent": "JKWorld-App-Updater/1",
        "Accept": "application/vnd.github+json",
    })
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_bytes(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": "JKWorld-App-Updater/1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def find_release_asset(release: dict[str, Any], asset_name: str) -> dict[str, Any]:
    for asset in release.get("assets", []):
        if str(asset.get("name", "")).lower() == asset_name.lower():
            return asset
    raise ValueError(f"Release asset not found: {asset_name}")


def _prepare_update_package(root: Path, zip_data: bytes, latest_version: str) -> Path:
    update_root = root / UPDATE_DIR
    if update_root.exists():
        shutil.rmtree(update_root)
    package_root = update_root / "package"
    package_root.mkdir(parents=True)
    zip_path = update_root / "app.zip"
    zip_path.write_bytes(zip_data)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(package_root)
    (package_root / APP_VERSION_FILE).write_text(latest_version, encoding="utf-8")
    return package_root


def _write_update_script(root: Path, package_root: Path) -> Path:
    script_path = root / UPDATE_DIR / "apply_update.ps1"
    skipped = ", ".join(f'"{item}"' for item in sorted(DATA_ITEMS))
    script = f"""param(
    [int]$ProcessId,
    [string]$TargetRoot,
    [string]$PackageRoot,
    [string]$Relaunch
)
$ErrorActionPreference = "Stop"
$skipNames = @({skipped})
try {{
    Wait-Process -Id $ProcessId -Timeout 90 -ErrorAction SilentlyContinue
}} catch {{}}
Start-Sleep -Milliseconds 800
Get-ChildItem -LiteralPath $PackageRoot -Force | ForEach-Object {{
    if (-not ($skipNames -contains $_.Name)) {{
        $destination = Join-Path $TargetRoot $_.Name
        if (Test-Path -LiteralPath $destination) {{
            Remove-Item -LiteralPath $destination -Recurse -Force
        }}
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    }}
}}
$versionFile = Join-Path $PackageRoot "{APP_VERSION_FILE}"
if (Test-Path -LiteralPath $versionFile) {{
    Copy-Item -LiteralPath $versionFile -Destination (Join-Path $TargetRoot "{APP_VERSION_FILE}") -Force
}}
Start-Process -FilePath $Relaunch -WorkingDirectory $TargetRoot
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


def _launch_update_script(script_path: Path, root: Path) -> None:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-ProcessId",
        str(os.getpid()),
        "-TargetRoot",
        str(root),
        "-PackageRoot",
        str(root / UPDATE_DIR / "package"),
        "-Relaunch",
        str(sys.executable),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(command, cwd=root, creationflags=creationflags)


def check_and_prepare_app_update(
    root: Path,
    log: LogFn = print,
) -> AppUpdateResult:
    root = root.resolve()
    settings = load_update_settings(root)
    current = installed_app_version(root)
    if not settings.get("app_update_enabled", True):
        return AppUpdateResult(False, False, current, current, "App updates disabled")
    if not is_packaged_app():
        return AppUpdateResult(False, False, current, current, "Source mode app update skipped")
    timeout = float(settings.get("timeout_seconds", 10))
    release_api_url = str(settings["app_release_api_url"])
    separator = "&" if "?" in release_api_url else "?"
    release = _download_json(
        f"{release_api_url}{separator}_={time.time_ns()}",
        timeout,
    )
    latest = str(release.get("tag_name") or release.get("name") or "").strip()
    if not latest:
        raise ValueError("Release version missing")
    if not should_update_app(current, latest):
        return AppUpdateResult(False, False, current, latest, f"App already up to date ({current})")
    asset_name = str(settings.get("nobrain_asset_name", "JKWorld-NoBrain.zip"))
    asset = find_release_asset(release, asset_name)
    url = str(asset.get("browser_download_url", ""))
    if not url:
        raise ValueError(f"Release asset has no download URL: {asset_name}")
    log(f"Downloading app update {latest}...")
    zip_data = _download_bytes(url, timeout)
    expected_size = int(asset.get("size") or 0)
    if expected_size and len(zip_data) != expected_size:
        raise ValueError("App update size mismatch")
    digest = asset.get("digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        actual = hashlib.sha256(zip_data).hexdigest()
        expected = digest.split(":", 1)[1].lower()
        if actual != expected:
            raise ValueError("App update hash mismatch")
    package_root = _prepare_update_package(root, zip_data, latest)
    script_path = _write_update_script(root, package_root)
    _launch_update_script(script_path, root)
    return AppUpdateResult(
        True,
        True,
        current,
        latest,
        f"App update {current} -> {latest} downloaded. Restarting NoBrain...",
    )
