"""Periodic key press helper for dismissing blocking game dialogs."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import pydirectinput


LogFn = Callable[[str], None]


class AutoDismissController:
    def __init__(
        self,
        *,
        backend: Any = pydirectinput,
        log: LogFn = print,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backend = backend
        self.log = log
        self.time_source = time_source
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.enabled = False
        self.key = "esc"
        self.interval_seconds = 60.0

    def start(
        self,
        *,
        enabled: bool,
        key: str = "esc",
        interval_seconds: float = 60.0,
    ) -> None:
        self.stop()
        self.enabled = bool(enabled)
        self.key = normalize_dismiss_key(key)
        self.interval_seconds = max(1.0, float(interval_seconds))
        if not self.enabled:
            return
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="auto-dismiss",
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if (
            self.thread
            and self.thread.is_alive()
            and threading.current_thread() is not self.thread
        ):
            self.thread.join(timeout=0.2)
        self.thread = None

    def trigger_once(self) -> None:
        self.backend.press(self.key)
        self.log(f"Auto dismiss pressed {self.key.upper()}.")

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            self.trigger_once()


def normalize_dismiss_key(key: str) -> str:
    normalized = str(key or "esc").strip().lower()
    if normalized in {"escape", "esc"}:
        return "esc"
    if normalized in {"enter", "return"}:
        return "enter"
    raise ValueError("Auto dismiss key must be ESC or ENTER")
