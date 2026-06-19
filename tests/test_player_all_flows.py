"""Player can choose which enabled flows to run."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from player_gui import enabled_rules, flow_name, selected_rules  # noqa: E402


def main() -> None:
    config = {
        "rules": [
            {"name": "movement", "enabled": True},
            {"name": "recovery", "enabled": True},
            {"name": "disabled", "enabled": False},
        ]
    }
    assert [flow_name(rule) for rule in enabled_rules(config)] == [
        "movement",
        "recovery",
    ]
    assert [rule["name"] for rule in selected_rules(config, {1})] == ["recovery"]
    assert selected_rules(config, set()) == []
    print("Player selects enabled flows")


if __name__ == "__main__":
    main()
