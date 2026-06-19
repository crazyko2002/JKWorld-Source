"""F10 stops a running flow without requiring the GUI to have focus."""

from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pynput import keyboard  # noqa: E402

from screen_flow_gui import FlowApp  # noqa: E402


class RunningWorker:
    @staticmethod
    def is_alive() -> bool:
        return True


class StatusLabel:
    def __init__(self):
        self.values = {}

    def configure(self, **kwargs):
        self.values.update(kwargs)


def main() -> None:
    app = object.__new__(FlowApp)
    app.worker = RunningWorker()
    app.stop_event = threading.Event()
    app.f10_stop_latched = False
    app.status_label = StatusLabel()
    app.log = lambda _message: None
    app.after = lambda _delay, callback: callback()

    app.emergency_key_down(keyboard.Key.f10)
    assert app.stop_event.is_set()
    assert app.f10_stop_latched
    assert "F10" in app.status_label.values["text"]

    app.emergency_key_up(keyboard.Key.f10)
    assert not app.f10_stop_latched
    print("F10 emergency stop OK")


if __name__ == "__main__":
    main()
