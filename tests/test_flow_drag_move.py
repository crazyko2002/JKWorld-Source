"""Flow blocks can move across nested Scratch-style containers."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen_flow_gui import FlowApp  # noqa: E402


def main() -> None:
    app = object.__new__(FlowApp)
    app.config_data = {
        "rules": [{
            "name": "Drag Test",
            "program": [
                {"type": "press", "key": "a"},
                {"type": "repeat", "times": 2, "steps": []},
                {
                    "type": "if",
                    "condition": {"type": "always"},
                    "then": [],
                    "else": [],
                },
            ],
        }],
    }
    app.selected_index = 0
    app.render_program = lambda: None
    app.save_current = lambda silent=True: True

    app.move_node_to_path([], 0, [(1, "steps")], 0)
    program = app.config_data["rules"][0]["program"]
    assert program[0]["type"] == "repeat"
    assert program[0]["steps"][0]["key"] == "a"

    app.move_node_to_path([(0, "steps")], 0, [(1, "then")], 0)
    program = app.config_data["rules"][0]["program"]
    assert program[1]["then"][0]["key"] == "a"
    assert program[0]["steps"] == []

    app.move_node_to_path([(1, "then")], 0, [], 2)
    program = app.config_data["rules"][0]["program"]
    assert program[2]["key"] == "a"
    assert program[1]["then"] == []

    assert app.is_own_child_path([], 0, [(0, "steps")])
    assert app.is_own_child_path([], 1, [(1, "then")])
    assert app.is_own_child_path([], 1, [(1, "else")])
    assert not app.is_own_child_path([], 1, [(0, "steps")])
    print("Flow drag move OK")


if __name__ == "__main__":
    main()
