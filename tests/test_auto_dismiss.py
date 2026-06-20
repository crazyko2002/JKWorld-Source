"""Auto dismiss presses ESC/ENTER on a safe interval while running."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auto_dismiss import AutoDismissController, normalize_dismiss_key  # noqa: E402


class FakeBackend:
    def __init__(self):
        self.calls = []

    def press(self, key):
        self.calls.append(key)


def main() -> None:
    assert normalize_dismiss_key("escape") == "esc"
    assert normalize_dismiss_key("ENTER") == "enter"

    backend = FakeBackend()
    logs = []
    controller = AutoDismissController(backend=backend, log=logs.append)
    controller.start(enabled=False, key="enter", interval_seconds=60)
    assert backend.calls == []

    controller.start(enabled=True, key="escape", interval_seconds=60)
    controller.trigger_once()
    assert backend.calls == ["esc"]
    assert logs[-1] == "Auto dismiss pressed ESC."

    controller.stop()
    assert controller.thread is None

    print("Auto dismiss controller OK")


if __name__ == "__main__":
    main()
