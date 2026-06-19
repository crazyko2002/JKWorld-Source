"""Build SightFlow Player and Studio Windows distributions."""

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


def build(name: str, entrypoint: str) -> Path:
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
    player = build("SightFlowPlayer", "player_gui.py")
    studio = build("SightFlowStudio", "screen_flow_gui.py")
    print(f"Built: {player}")
    print(f"Built: {studio}")


if __name__ == "__main__":
    main()

