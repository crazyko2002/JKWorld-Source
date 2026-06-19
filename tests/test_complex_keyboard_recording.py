"""Recorder preserves raw VK combos, overlapping keys, and stop releases."""

from pathlib import Path
import sys
import threading

from pynput import keyboard

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import macro_recorder  # noqa: E402


def keycode(char, vk):
    return keyboard.KeyCode(vk=vk, char=char)


def main() -> None:
    lifecycle = []
    original_listener = macro_recorder.keyboard.Listener

    class FakeListener:
        def __init__(self, **callbacks):
            self.callbacks = callbacks

        def start(self):
            lifecycle.append("start")

        def wait(self):
            lifecycle.append("ready")

        def stop(self):
            lifecycle.append("stop")

    macro_recorder.keyboard.Listener = FakeListener
    ready_recorder = macro_recorder.KeyboardRecorder(lambda _events: None)
    try:
        ready_recorder.start()
        ready_recorder.stop()
    finally:
        macro_recorder.keyboard.Listener = original_listener
    assert lifecycle == ["start", "ready", "stop"], lifecycle

    stopped = []
    recorder = macro_recorder.KeyboardRecorder(stopped.append)
    recorder.recording = True
    recorder.started_at = macro_recorder.time.perf_counter()

    ctrl_z = keycode("\x1a", 0x5A)
    numpad_1 = keycode(None, 0x61)

    recorder._on_press(keyboard.Key.ctrl_l)
    recorder._on_press(ctrl_z)
    recorder._on_press(keyboard.Key.up)
    recorder._on_press(numpad_1)
    recorder._on_release(ctrl_z)
    recorder._on_release(keyboard.Key.ctrl_l)
    recorder._on_release(numpad_1)
    recorder.stop()  # Must synthesize only the still-held Up release.

    events = stopped[0]
    assert [(event["action"], event["key"]) for event in events] == [
        ("key_down", "ctrlleft"),
        ("key_down", "z"),
        ("key_down", "up"),
        ("key_down", "num1"),
        ("key_up", "z"),
        ("key_up", "ctrlleft"),
        ("key_up", "num1"),
        ("key_up", "up"),
    ], events
    assert macro_recorder.analyze_event_balance(events)["balanced"]
    diagnostics = recorder.diagnostics()
    assert diagnostics["ignored_callbacks"] == 0
    assert diagnostics["recorded_events"] == 8

    stressed = []
    stress_recorder = macro_recorder.KeyboardRecorder(stressed.append)
    stress_recorder.recording = True
    stress_recorder.started_at = macro_recorder.time.perf_counter()
    keys = [keyboard.KeyCode(vk=0x41 + index, char=chr(97 + index))
            for index in range(12)]
    all_pressed = threading.Barrier(len(keys))

    def overlap(key):
        stress_recorder._on_press(key)
        all_pressed.wait()
        stress_recorder._on_release(key)

    threads = [threading.Thread(target=overlap, args=(key,)) for key in keys]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stress_recorder.stop()
    stressed_events = stressed[0]
    assert len(stressed_events) == 24
    assert macro_recorder.analyze_event_balance(stressed_events)["balanced"]
    assert len({
        event["key"] for event in stressed_events
        if event["action"] == "key_down"
    }) == 12

    forced = []
    forced_recorder = macro_recorder.KeyboardRecorder(forced.append)
    forced_recorder.recording = True
    forced_recorder.started_at = macro_recorder.time.perf_counter()
    forced_recorder._on_press(keyboard.Key.up)
    forced_recorder._on_press(keyboard.Key.right)
    forced_recorder.stop()
    assert [(event["action"], event["key"]) for event in forced[0]] == [
        ("key_down", "up"),
        ("key_down", "right"),
        ("key_up", "right"),
        ("key_up", "up"),
    ]
    print("Complex simultaneous keyboard recording OK")


if __name__ == "__main__":
    main()
