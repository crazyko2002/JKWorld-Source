"""Playback uses absolute timestamps so backend overhead does not accumulate."""

from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import macro_recorder


class SlowBackend:
    def __init__(self):
        self.calls = []

    def keyDown(self, key, **kwargs):
        self.calls.append(("down", key, time.perf_counter()))
        time.sleep(0.004)

    def keyUp(self, key, **kwargs):
        self.calls.append(("up", key, time.perf_counter()))
        time.sleep(0.004)


def main() -> None:
    backend = SlowBackend()
    original = macro_recorder.pydirectinput
    macro_recorder.pydirectinput = backend
    events = [
        {
            "time": 0.25 + index * 0.012,
            "action": "key_down" if index % 2 == 0 else "key_up",
            "key": "w",
        }
        for index in range(30)
    ]
    started = time.perf_counter()
    try:
        metrics = macro_recorder.replay_macro(
            events, 1, 0, threading.Event(), lambda _: None,
            preserve_lead_in=False,
        )
    finally:
        macro_recorder.pydirectinput = original
    elapsed = time.perf_counter() - started
    expected = events[-1]["time"] - events[0]["time"]

    # Leading idle time is trimmed and 4ms backend cost does not accumulate.
    assert elapsed < expected + 0.035, (elapsed, expected)
    assert metrics["max_lateness"] < 0.04, metrics
    assert len(backend.calls) == len(events)

    backend.calls.clear()
    started = time.perf_counter()
    original = macro_recorder.pydirectinput
    macro_recorder.pydirectinput = backend
    try:
        macro_recorder.replay_macro(
            [
                {"time": 0.04, "action": "key_down", "key": "w"},
                {"time": 0.24, "action": "key_up", "key": "w"},
            ],
            1, 0, threading.Event(), lambda _: None,
            speed_percent=200,
            preserve_lead_in=True,
        )
    finally:
        macro_recorder.pydirectinput = original
    scaled_elapsed = time.perf_counter() - started
    assert 0.11 <= scaled_elapsed <= 0.15, scaled_elapsed
    print(
        f"Absolute macro timing OK: expected={expected:.3f}s "
        f"actual={elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()
