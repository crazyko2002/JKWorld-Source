"""NoBrain app updater chooses newer release assets safely."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app_updater  # noqa: E402


def main() -> None:
    assert app_updater.should_update_app("v2.0.4", "v2.0.5")
    assert app_updater.should_update_app("2.0.4", "v2.1.0")
    assert not app_updater.should_update_app("v2.0.5", "v2.0.5")
    assert not app_updater.should_update_app("v2.1.0", "v2.0.9")
    assert not app_updater.should_update_app("dev", "v9.0.0")

    release = {
        "assets": [
            {"name": "JKWorld-Studio.zip"},
            {"name": "JKWorld-NoBrain.zip", "browser_download_url": "https://example.test/app.zip"},
        ],
    }
    asset = app_updater.find_release_asset(release, "JKWorld-NoBrain.zip")
    assert asset["browser_download_url"].endswith("/app.zip")

    skipped = app_updater.DATA_ITEMS
    assert "config.yaml" in skipped
    assert "templates" in skipped
    assert "recordings" in skipped
    assert "numpad" in skipped
    print("NoBrain app updater OK")


if __name__ == "__main__":
    main()
