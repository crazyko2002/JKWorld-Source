"""Build JK世界 Player and Studio Windows distributions."""

from __future__ import annotations

import shutil
from pathlib import Path

import PyInstaller.__main__


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ASSETS = (
    "config.yaml",
    "macro_config.yaml",
    "update_settings.json",
    "templates",
    "recordings",
    "numpad",
)


def build(name: str, entrypoint: str, executable_name: str) -> Path:
    PyInstaller.__main__.run([
        str(ROOT / entrypoint),
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        f"--name={name}",
        f"--distpath={DIST}",
        f"--workpath={ROOT / 'build' / name}",
        f"--specpath={ROOT / 'build'}",
        "--collect-all=customtkinter",
        "--collect-all=ddddocr",
        "--hidden-import=pynput.keyboard._win32",
        "--hidden-import=pynput.mouse._win32",
    ])
    output = DIST / name
    built_executable = output / f"{name}.exe"
    display_executable = output / executable_name
    if display_executable.exists():
        display_executable.unlink()
    built_executable.rename(display_executable)
    for item in ASSETS:
        source = ROOT / item
        destination = output / item
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return output


def main() -> None:
    DIST.mkdir(exist_ok=True)
    player = build(
        "JKWorldNoBrain",
        "player_gui.py",
        "JK世界 冇撚腦ver.exe",
    )
    studio = build("JKWorldStudio", "studio_gui.py", "JK世界 Studio.exe")
    publisher = build(
        "JKWorldStudioOwner",
        "studio_publisher_gui.py",
        "JK世界 Studio Owner.exe",
    )
    print(f"Built: {player}")
    print(f"Built: {studio}")
    print(f"Built: {publisher}")


if __name__ == "__main__":
    main()
