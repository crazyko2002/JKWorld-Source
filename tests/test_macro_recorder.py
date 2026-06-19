"""Tests for recorded keyboard replay timing and repetition."""

from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import macro_recorder


class FakeDirectInput:
    def __init__(self):
        self.calls = []

    def keyDown(self, key):
        self.calls.append(("down", key))

    def keyUp(self, key):
        self.calls.append(("up", key))


def main() -> None:
    fake = FakeDirectInput()
    original = macro_recorder.pydirectinput
    macro_recorder.pydirectinput = fake
    events = [
        {"time": 0.0, "action": "down", "key": "w"},
        {"time": 0.01, "action": "down", "key": "space"},
        {"time": 0.02, "action": "up", "key": "space"},
        {"time": 0.03, "action": "up", "key": "w"},
    ]
    try:
        macro_recorder.replay_macro(
            events, repeat_count=2, repeat_delay=0,
            stop_event=threading.Event(), log=lambda _: None,
        )
    finally:
        macro_recorder.pydirectinput = original
    expected_once = [
        ("down", "w"), ("down", "space"),
        ("up", "space"), ("up", "w"),
    ]
    assert fake.calls == expected_once * 2, fake.calls

    stop = threading.Event()
    stop.set()
    fake.calls.clear()
    original = macro_recorder.pydirectinput
    macro_recorder.pydirectinput = fake
    try:
        macro_recorder.replay_macro(
            events, repeat_count=3, repeat_delay=0,
            stop_event=stop, log=lambda _: None,
        )
    finally:
        macro_recorder.pydirectinput = original
    assert fake.calls == []
    print("Macro replay and repeat count OK")


if __name__ == "__main__":
    main()
