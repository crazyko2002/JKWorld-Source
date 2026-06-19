"""Regression tests for DirectInput routing and STOP actions."""

from pathlib import Path
import sys
import threading
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_detector_prototype as engine


class FakeDirectInput:
    def __init__(self):
        self.calls = []

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))

    def keyDown(self, key):
        self.calls.append(("down", key))

    def keyUp(self, key):
        self.calls.append(("up", key))

    def moveTo(self, x, y, duration=0):
        self.calls.append(("move_to", x, y, duration))

    def moveRel(self, x, y, duration=0):
        self.calls.append(("move_rel", x, y, duration))


def main() -> None:
    fake = FakeDirectInput()
    original = engine.pydirectinput
    engine.pydirectinput = fake
    try:
        engine.run_actions(
            [{
                "type": "click", "target": "fixed", "x": 321, "y": 456,
                "button": "left", "clicks": 1, "backend": "directinput",
            }],
            (0, 0), False, threading.Event(), lambda _: None,
        )
        assert fake.calls[0] == (
            "click",
            {"x": 321, "y": 456, "clicks": 1, "button": "left"},
        )

        engine.run_actions(
            [{
                "type": "hotkey", "keys": ["ctrl", "s"],
                "backend": "directinput",
            }],
            (0, 0), False, threading.Event(), lambda _: None,
        )
        assert fake.calls[-4:] == [
            ("down", "ctrl"), ("down", "s"),
            ("up", "s"), ("up", "ctrl"),
        ]

        engine.run_actions(
            [{
                "type": "move", "target": "park", "margin": 20,
                "duration": 0.1, "backend": "directinput",
            }],
            (0, 0), False, threading.Event(), lambda _: None,
            action_context={"screen_size": (1920, 1080)},
        )
        assert fake.calls[-1] == ("move_to", 1899, 1059, 0.1)

        engine.run_actions(
            [{
                "type": "move", "target": "relative", "x": -50, "y": 25,
                "duration": 0, "backend": "directinput",
            }],
            (0, 0), False, threading.Event(), lambda _: None,
        )
        assert fake.calls[-1] == ("move_rel", -50, 25, 0.0)
    finally:
        engine.pydirectinput = original

    try:
        engine.run_actions(
            [{"type": "stop", "scope": "flow"}],
            (0, 0), True, threading.Event(), lambda _: None,
        )
        raise AssertionError("STOP flow did not interrupt")
    except engine.StopCurrentFlow:
        pass

    stop_event = threading.Event()
    try:
        engine.run_actions(
            [{"type": "stop", "scope": "engine"}],
            (0, 0), True, stop_event, lambda _: None,
        )
        raise AssertionError("STOP engine did not interrupt")
    except engine.StopEngine:
        assert stop_event.is_set()

    logs: list[str] = []
    config = {
        "dry_run": True,
        "poll_interval_ms": 30,
        "rules": [
            {
                "name": "flow-stop",
                "enabled": True,
                "cooldown_seconds": 0.05,
                "program": [
                    {"type": "stop", "scope": "flow"},
                    {"type": "press", "key": "must-not-run"},
                ],
            },
            {
                "name": "next-flow",
                "enabled": True,
                "cooldown_seconds": 0.05,
                "program": [
                    {"type": "press", "key": "next-flow-ran"},
                    {"type": "stop", "scope": "engine"},
                ],
            },
        ],
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "stop-config.yaml"
        engine.save_config(path, config)
        engine.run_detector(path, log=logs.append)
    assert not any("must-not-run" in line for line in logs)
    assert any("next-flow-ran" in line for line in logs)
    assert any("Engine 已由 STOP" in line for line in logs)

    print("DirectInput routing and STOP actions OK")


if __name__ == "__main__":
    main()
