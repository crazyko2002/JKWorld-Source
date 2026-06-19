"""Advanced Flow exposes the recorder as an embedded child window."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import customtkinter as ctk  # noqa: E402
import macro_recorder  # noqa: E402
import macro_recorder_gui  # noqa: E402
import screen_flow_gui  # noqa: E402


def main() -> None:
    assert issubclass(
        macro_recorder_gui.MacroRecorderWindow,
        ctk.CTkToplevel,
    )
    assert hasattr(screen_flow_gui.FlowApp, "open_recorder")
    defaults = macro_recorder.default_config()
    assert "trigger_image" not in defaults
    assert "capture_mode" not in defaults
    assert not hasattr(macro_recorder, "DatasetCapture")
    assert not hasattr(macro_recorder, "monitor_and_replay")
    print("Advanced Flow recorder integration OK")


if __name__ == "__main__":
    main()
