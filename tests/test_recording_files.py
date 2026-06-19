"""Recording files preserve explicit key-down/key-up events and are selectable."""

from pathlib import Path
import sys
import tempfile

import yaml
from pynput import keyboard

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import macro_recorder


def main() -> None:
    legacy = [
        {"time": 0.0, "action": "down", "key": "w"},
        {"time": 0.4, "action": "up", "key": "w"},
    ]
    normalized = macro_recorder.normalize_events(legacy)
    assert [event["action"] for event in normalized] == [
        "key_down", "key_up",
    ]
    assert macro_recorder.normalize_key(
        keyboard.KeyCode.from_char("\x1a")
    ) is None
    assert macro_recorder.normalize_events([
        {"time": 0.2, "action": "down", "key": "\x1a"},
    ]) == []
    balance = macro_recorder.analyze_event_balance(normalized)
    assert balance["key_down_count"] == 1
    assert balance["key_up_count"] == 1
    assert balance["balanced"] is True

    original_dir = macro_recorder.RECORDINGS_DIR
    with tempfile.TemporaryDirectory(prefix="recording_files_") as directory:
        macro_recorder.RECORDINGS_DIR = Path(directory)
        try:
            path = macro_recorder.save_recording(
                "Move Right",
                legacy,
                recorder_diagnostics={
                    "raw_callbacks": 2,
                    "recorded_events": 2,
                    "ignored_callbacks": 0,
                },
            )
            assert path.name == "Move Right.yaml"
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert raw["event_count"] == 2
            assert raw["balanced"] is True
            assert raw["events"][0]["action"] == "key_down"
            assert raw["events"][1]["action"] == "key_up"
            assert raw["recorder_diagnostics"]["ignored_callbacks"] == 0
            loaded = macro_recorder.load_recording(path)
            assert loaded["events"] == normalized
        finally:
            macro_recorder.RECORDINGS_DIR = original_dir
    print("Recording file down/up format OK")


if __name__ == "__main__":
    main()
