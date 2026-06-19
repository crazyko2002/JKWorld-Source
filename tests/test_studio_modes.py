"""Studio publishing controls are explicitly split by entrypoint."""

from pathlib import Path


def main() -> None:
    normal = Path("studio_gui.py").read_text(encoding="utf-8")
    publisher = Path("studio_publisher_gui.py").read_text(encoding="utf-8")
    assert 'JKWORLD_ENABLE_PUBLISH"] = "0"' in normal
    assert 'JKWORLD_ENABLE_PUBLISH"] = "1"' in publisher
    print("Studio publish and non-publish modes OK")


if __name__ == "__main__":
    main()
