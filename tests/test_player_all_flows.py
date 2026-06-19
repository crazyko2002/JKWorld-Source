"""Player runs every enabled Flow together."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from player_gui import enabled_rules  # noqa: E402


def main() -> None:
    config = {
        "rules": [
            {"name": "movement", "enabled": True},
            {"name": "recovery", "enabled": True},
            {"name": "disabled", "enabled": False},
        ]
    }
    assert [rule["name"] for rule in enabled_rules(config)] == [
        "movement",
        "recovery",
    ]
    print("Player runs all enabled flows together")


if __name__ == "__main__":
    main()
