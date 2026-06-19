"""Publish and update versioned JK世界 data bundles."""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from app_paths import APP_ROOT


DEFAULT_SETTINGS = {
    "enabled": True,
    "manifest_url": (
        "https://api.github.com/repos/crazyko2002/JKWorld-Downloads/"
        "contents/published/manifest.json?ref=main"
    ),
    "asset_base_url": (
        "https://raw.githubusercontent.com/"
        "crazyko2002/JKWorld-Downloads/main/published/"
    ),
    "distribution_repository": "https://github.com/crazyko2002/JKWorld-Downloads.git",
    "timeout_seconds": 10,
}
PUBLISH_ITEMS = ("config.yaml", "macro_config.yaml", "templates", "recordings", "numpad")
LogFn = Callable[[str], None]


@dataclass(frozen=True)
class UpdateResult:
    updated: bool
    version: str
    files_changed: int
    message: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_update_settings(root: Path = APP_ROOT) -> dict:
    path = root / "update_settings.json"
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    settings = dict(DEFAULT_SETTINGS)
    settings.update(json.loads(path.read_text(encoding="utf-8")))
    return settings


def installed_flow_version(root: Path = APP_ROOT) -> str:
    path = root / ".flow_version"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "0"


def find_git_repository(start: Path = APP_ROOT) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _download_json(url: str, timeout: float) -> dict:
    request = Request(url, headers={
        "User-Agent": "JKWorld-Updater/1",
        "Accept": "application/vnd.github.raw+json",
    })
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_bytes(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": "JKWorld-Updater/1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ValueError(f"Unsafe update path: {relative}")
    return target


def check_and_apply_updates(
    root: Path = APP_ROOT,
    log: LogFn = print,
) -> UpdateResult:
    root = root.resolve()
    settings = load_update_settings(root)
    if not settings.get("enabled", True):
        return UpdateResult(False, installed_flow_version(root), 0, "Updates disabled")
    manifest_url = str(settings["manifest_url"])
    timeout = float(settings.get("timeout_seconds", 10))
    separator = "&" if "?" in manifest_url else "?"
    manifest = _download_json(
        f"{manifest_url}{separator}_={time.time_ns()}",
        timeout,
    )
    version = str(manifest.get("flow_version", "0"))
    current = installed_flow_version(root)
    files = manifest.get("files", [])
    if not isinstance(files, list):
        raise ValueError("Invalid flow manifest")
    base_url = str(
        settings.get("asset_base_url")
        or (manifest_url.rsplit("/", 1)[0] + "/")
    )
    if not base_url.endswith("/"):
        base_url += "/"
    bundle = manifest.get("bundle")
    bundle_files: dict[str, bytes] | None = None
    if bundle:
        bundle_url = base_url + quote(str(bundle["source"]), safe="/")
        bundle_data = _download_bytes(bundle_url, timeout)
        actual_bundle_hash = hashlib.sha256(bundle_data).hexdigest()
        if actual_bundle_hash != str(bundle["sha256"]).lower():
            raise ValueError("Flow bundle hash mismatch")
        with zipfile.ZipFile(BytesIO(bundle_data)) as archive:
            bundle_files = {
                name: archive.read(name)
                for name in archive.namelist()
                if not name.endswith("/")
            }
    changed: list[tuple[Path, bytes]] = []
    for item in files:
        relative = str(item["path"]).replace("\\", "/")
        expected = str(item["sha256"]).lower()
        target = _safe_target(root, relative)
        if target.exists() and sha256_file(target) == expected:
            continue
        if bundle_files is not None:
            if relative not in bundle_files:
                raise ValueError(f"Missing from Flow bundle: {relative}")
            data = bundle_files[relative]
        else:
            source_url = base_url + quote(str(item["source"]), safe="/")
            data = _download_bytes(source_url, timeout)
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"Hash mismatch: {relative}")
        changed.append((target, data))
    if not changed and current == version:
        return UpdateResult(False, version, 0, "Flow already up to date")
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        staging = Path(temporary)
        staged_files: list[tuple[Path, Path]] = []
        for target, data in changed:
            staged = staging / target.relative_to(root.resolve())
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(data)
            staged_files.append((staged, target))
        for staged, target in staged_files:
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
            log(f"Updated: {target.relative_to(root)}")
    (root / ".flow_version").write_text(version, encoding="utf-8")
    return UpdateResult(True, version, len(changed), f"Flow updated to {version}")


def prepare_published_bundle(
    root: Path = APP_ROOT,
    version: str | None = None,
    output_root: Path | None = None,
) -> Path:
    output_root = output_root or root
    published = output_root / "published"
    if published.exists():
        shutil.rmtree(published)
    files_root = published / "files"
    files_root.mkdir(parents=True)
    manifest_files = []
    for item_name in PUBLISH_ITEMS:
        source = root / item_name
        if not source.exists():
            continue
        sources = [source] if source.is_file() else sorted(
            path for path in source.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        )
        for path in sources:
            relative = path.relative_to(root)
            destination = files_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = path.read_bytes()
            if path.suffix.lower() in {".yaml", ".yml", ".json", ".txt"}:
                data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            destination.write_bytes(data)
            manifest_files.append({
                "path": relative.as_posix(),
                "source": f"files/{relative.as_posix()}",
                "sha256": sha256_file(destination),
                "size": destination.stat().st_size,
            })
    flow_version = version or datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S")
    bundles = published / "bundles"
    bundles.mkdir()
    safe_version = "".join(
        char for char in flow_version if char.isalnum() or char in ".-_"
    )
    bundle_path = bundles / f"flow-{safe_version}.zip"
    with zipfile.ZipFile(
        bundle_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for item in manifest_files:
            archive.write(files_root / item["path"], arcname=item["path"])
    manifest = {
        "schema_version": 1,
        "flow_version": flow_version,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "bundle": {
            "source": f"bundles/{bundle_path.name}",
            "sha256": sha256_file(bundle_path),
            "size": bundle_path.stat().st_size,
        },
        "files": manifest_files,
    }
    manifest_path = published / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path


def publish_bundle_to_git(
    root: Path = APP_ROOT,
    version: str | None = None,
    log: LogFn = print,
    repository_root: Path | None = None,
) -> Path:
    del repository_root
    manifest = prepare_published_bundle(root, version)
    settings = load_update_settings(root)
    distribution_repository = str(settings["distribution_repository"])
    flow_version = json.loads(manifest.read_text(encoding="utf-8"))["flow_version"]
    with tempfile.TemporaryDirectory() as directory:
        checkout = Path(directory) / "distribution"
        subprocess.run(
            ["git", "clone", distribution_repository, str(checkout)],
            check=True,
        )
        destination = checkout / "published"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(root / "published", destination)
        subprocess.run(["git", "add", "published"], cwd=checkout, check=True)
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=checkout,
            check=False,
        )
        if status.returncode == 0:
            log("No Flow changes to publish.")
            return manifest
        subprocess.run(
            ["git", "commit", "-m", f"publish flows {flow_version}"],
            cwd=checkout,
            check=True,
        )
        subprocess.run(["git", "push"], cwd=checkout, check=True)
    log(f"Published Flow version {flow_version}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.publish:
        path = publish_bundle_to_git(version=args.version)
    else:
        path = prepare_published_bundle(version=args.version)
    print(path.relative_to(APP_ROOT))


if __name__ == "__main__":
    main()
