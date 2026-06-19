"""Advanced Flow can replay the latest Simple Recorder recording."""

from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import macro_recorder
import screen_detector_prototype as engine


def main() -> None:
    calls = []
    original_load = macro_recorder.load_macro_config
    original_load_file = macro_recorder.load_recording
    original_replay = macro_recorder.replay_macro
    macro_recorder.load_macro_config = lambda: {
        "events": [
            {"time": 0, "action": "down", "key": "w"},
            {"time": 0.1, "action": "up", "key": "w"},
        ]
    }
    selected_file = "recordings/chosen.yaml"
    macro_recorder.load_recording = lambda path: {
        "events": [
            {"time": 0, "action": "key_down", "key": "f1"},
            {"time": 0.1, "action": "key_up", "key": "f1"},
        ],
        "selected_path": path,
    }

    def fake_replay(
        events, repeat_count, repeat_delay, stop_event, log, **kwargs
    ):
        calls.append((events, repeat_count, repeat_delay, stop_event, kwargs))

    macro_recorder.replay_macro = fake_replay
    stop_event = threading.Event()
    try:
        engine.run_actions(
            [{
                "type": "play_record",
                "recording_file": selected_file,
                "repeat_count": 4,
                "repeat_delay": 0.25,
                "speed_percent": 105,
                "backend": "directinput",
            }],
            (0, 0),
            False,
            stop_event,
            lambda _: None,
        )
    finally:
        macro_recorder.load_macro_config = original_load
        macro_recorder.load_recording = original_load_file
        macro_recorder.replay_macro = original_replay

    assert len(calls) == 1
    assert calls[0][1] == 4
    assert calls[0][2] == 0.25
    assert calls[0][3] is stop_event
    assert calls[0][0][0]["key"] == "f1"
    assert calls[0][4]["speed_percent"] == 105
    assert calls[0][4]["backend"] is engine.pydirectinput
    assert "× 4" in engine.describe_action({
        "type": "play_record",
        "recording_file": selected_file,
        "repeat_count": 4,
        "repeat_delay": 0.25,
    })
    print("Advanced play_record action OK")


if __name__ == "__main__":
    main()
