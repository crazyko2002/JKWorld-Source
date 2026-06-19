"""High-fidelity keyboard recording and timed replay."""

from __future__ import annotations

import ctypes
from datetime import datetime
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable

import pydirectinput
import yaml
from pynput import keyboard

from screen_detector_prototype import ROOT


MACRO_CONFIG = ROOT / "macro_config.yaml"
RECORDINGS_DIR = ROOT / "recordings"
LogFn = Callable[[str], None]
pydirectinput.PAUSE = 0.0

REMOVED_CONFIG_KEYS = {
    "trigger_image", "threshold", "cooldown", "scan_interval_ms",
    "capture_mode", "capture_fps", "capture_target",
}

SPECIAL_KEYS = {
    "ctrl_l": "ctrlleft",
    "ctrl_r": "ctrlright",
    "shift_l": "shiftleft",
    "shift_r": "shiftright",
    "alt_l": "altleft",
    "alt_r": "altright",
    "cmd": "win",
    "cmd_l": "winleft",
    "cmd_r": "winright",
    "page_up": "pageup",
    "page_down": "pagedown",
}

VK_KEY_NAMES = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter",
    0x1B: "escape", 0x20: "space", 0x21: "pageup",
    0x22: "pagedown", 0x23: "end", 0x24: "home",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x2D: "insert", 0x2E: "delete", 0x5B: "winleft",
    0x5C: "winright", 0x6A: "multiply", 0x6B: "add",
    0x6D: "subtract", 0x6E: "decimal", 0x6F: "divide",
    0x90: "numlock", 0x91: "scrolllock",
    0xA0: "shiftleft", 0xA1: "shiftright",
    0xA2: "ctrlleft", 0xA3: "ctrlright",
    0xA4: "altleft", 0xA5: "altright",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-",
    0xBE: ".", 0xBF: "/", 0xC0: "`", 0xDB: "[",
    0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
VK_KEY_NAMES.update({0x30 + number: str(number) for number in range(10)})
VK_KEY_NAMES.update({
    0x41 + index: chr(ord("a") + index) for index in range(26)
})
VK_KEY_NAMES.update({0x60 + number: f"num{number}" for number in range(10)})
VK_KEY_NAMES.update({0x70 + index: f"f{index + 1}" for index in range(24)})

pydirectinput.KEYBOARD_MAPPING.update({
    "num0": 0x52, "num1": 0x4F, "num2": 0x50, "num3": 0x51,
    "num4": 0x4B, "num5": 0x4C, "num6": 0x4D, "num7": 0x47,
    "num8": 0x48, "num9": 0x49,
})


def default_config() -> dict[str, Any]:
    return {
        "repeat_count": 1,
        "repeat_delay": 0.5,
        "speed_percent": 100,
        "selected_recording": "",
        "events": [],
    }


def load_macro_config() -> dict[str, Any]:
    if not MACRO_CONFIG.exists():
        return default_config()
    with MACRO_CONFIG.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    result = default_config()
    result.update(config)
    for key in REMOVED_CONFIG_KEYS:
        result.pop(key, None)
    result["events"] = normalize_events(result.get("events", []))
    return result


def save_macro_config(config: dict[str, Any]) -> None:
    cleaned = dict(config)
    for key in REMOVED_CONFIG_KEYS:
        cleaned.pop(key, None)
    with MACRO_CONFIG.open("w", encoding="utf-8") as file:
        yaml.safe_dump(cleaned, file, allow_unicode=True, sort_keys=False)


def sanitize_recording_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip())
    cleaned = cleaned.rstrip(". ")
    return cleaned or datetime.now().strftime("recording_%Y%m%d_%H%M%S")


def normalize_event_action(action: str) -> str:
    if action in {"down", "key_down"}:
        return "key_down"
    if action in {"up", "key_up"}:
        return "key_up"
    raise ValueError(f"Unsupported recording event action: {action}")


def normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for event in events:
        key_name = str(event.get("key", ""))
        if not key_name or any(ord(character) < 32 for character in key_name):
            continue
        normalized.append({
            "time": round(float(event.get("time", 0)), 6),
            "action": normalize_event_action(str(event.get("action", ""))),
            "key": key_name,
        })
    return normalized


def analyze_event_balance(events: list[dict[str, Any]]) -> dict[str, Any]:
    held: set[str] = set()
    down_count = 0
    up_count = 0
    for event in normalize_events(events):
        key_name = event["key"]
        if event["action"] == "key_down":
            down_count += 1
            held.add(key_name)
        else:
            up_count += 1
            held.discard(key_name)
    return {
        "key_down_count": down_count,
        "key_up_count": up_count,
        "balanced": not held,
        "keys_still_down": sorted(held),
    }


def save_recording(
    name: str,
    events: list[dict[str, Any]],
    recorder_diagnostics: dict[str, int] | None = None,
) -> Path:
    normalized = normalize_events(events)
    if not normalized:
        raise ValueError("No recording events")
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_recording_name(name)
    path = RECORDINGS_DIR / f"{safe_name}.yaml"
    payload = {
        "version": 1,
        "name": safe_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": round(float(normalized[-1]["time"]), 6),
        "event_count": len(normalized),
        **analyze_event_balance(normalized),
        "events": normalized,
    }
    if recorder_diagnostics is not None:
        payload["recorder_diagnostics"] = {
            str(key): int(value)
            for key, value in recorder_diagnostics.items()
        }
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(payload, file, allow_unicode=True, sort_keys=False)
    return path


def load_recording(configured_path: str | Path) -> dict[str, Any]:
    path = Path(configured_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"Recording file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    events = normalize_events(payload.get("events", []))
    if not events:
        raise ValueError(f"Recording has no usable events: {path.name}")
    payload["events"] = events
    payload["_path"] = path
    return payload


def list_recordings() -> list[str]:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in sorted(
            RECORDINGS_DIR.glob("*.yaml"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    ]


def normalize_key(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            char = key.char
            if not any(ord(character) < 32 for character in char):
                return char.lower() if len(char) == 1 and char.isalpha() else char
        virtual_key = getattr(key, "vk", None)
        if virtual_key is not None:
            return VK_KEY_NAMES.get(int(virtual_key), f"vk_{int(virtual_key)}")
        return None
    name = getattr(key, "name", None)
    if not name:
        return None
    return SPECIAL_KEYS.get(name, name)


class KeyboardRecorder:
    def __init__(self, on_stopped: Callable[[list[dict[str, Any]]], None]):
        self.on_stopped = on_stopped
        self.events: list[dict[str, Any]] = []
        self.held: set[str] = set()
        self.held_order: list[str] = []
        self.started_at = 0.0
        self.listener: keyboard.Listener | None = None
        self.recording = False
        self.lock = threading.Lock()
        self.raw_callback_count = 0
        self.ignored_callback_count = 0
        self.duplicate_down_count = 0
        self.orphan_up_count = 0

    def start(self) -> None:
        with self.lock:
            self.events = []
            self.held = set()
            self.held_order = []
            self.raw_callback_count = 0
            self.ignored_callback_count = 0
            self.duplicate_down_count = 0
            self.orphan_up_count = 0
            self.started_at = time.perf_counter()
            self.recording = True
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.listener.start()
        wait_until_ready = getattr(self.listener, "wait", None)
        if wait_until_ready is not None:
            wait_until_ready()

    def _append_event_locked(self, action: str, key_name: str) -> None:
        self.events.append({
            "time": round(time.perf_counter() - self.started_at, 6),
            "action": normalize_event_action(action),
            "key": key_name,
        })

    def _event(self, action: str, key_name: str) -> None:
        with self.lock:
            self._append_event_locked(action, key_name)

    def _transition(self, action: str, key_name: str) -> None:
        with self.lock:
            if not self.recording:
                return
            if action == "key_down":
                if key_name in self.held:
                    self.duplicate_down_count += 1
                    return
                self.held.add(key_name)
                self.held_order.append(key_name)
            else:
                if key_name not in self.held:
                    self.orphan_up_count += 1
                    return
                self.held.remove(key_name)
                if key_name in self.held_order:
                    self.held_order.remove(key_name)
            self._append_event_locked(action, key_name)

    def _on_press(self, key) -> bool | None:
        with self.lock:
            self.raw_callback_count += 1
        key_name = normalize_key(key)
        if key_name == "f8":
            self.stop()
            return False
        if key_name in {"f9", None}:
            if key_name is None:
                with self.lock:
                    self.ignored_callback_count += 1
            return None
        self._transition("key_down", key_name)
        return None

    def _on_release(self, key) -> bool | None:
        with self.lock:
            self.raw_callback_count += 1
        key_name = normalize_key(key)
        if key_name in {"f8", "f9", None}:
            if key_name is None:
                with self.lock:
                    self.ignored_callback_count += 1
            return None
        self._transition("key_up", key_name)
        return None

    def held_snapshot(self) -> set[str]:
        with self.lock:
            return set(self.held)

    def diagnostics(self) -> dict[str, int]:
        with self.lock:
            return {
                "raw_callbacks": self.raw_callback_count,
                "recorded_events": len(self.events),
                "ignored_callbacks": self.ignored_callback_count,
                "duplicate_downs": self.duplicate_down_count,
                "orphan_ups": self.orphan_up_count,
            }

    def stop(self) -> None:
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            for key_name in reversed(self.held_order):
                self._append_event_locked("key_up", key_name)
            self.held.clear()
            self.held_order.clear()
            events = list(self.events)
        if self.listener:
            self.listener.stop()
        self.on_stopped(events)


def replay_macro(
    events: list[dict[str, Any]],
    repeat_count: int,
    repeat_delay: float,
    stop_event: threading.Event,
    log: LogFn = print,
    speed_percent: float = 100.0,
    preserve_lead_in: bool = True,
    backend: Any | None = None,
) -> dict[str, float]:
    events = normalize_events(events)
    if not events:
        raise ValueError("No keyboard events to replay")
    held: set[str] = set()
    total_lateness = 0.0
    max_lateness = 0.0
    dispatched = 0
    speed = max(1.0, float(speed_percent)) / 100.0
    first_event_time = (
        0.0 if preserve_lead_in else float(events[0].get("time", 0))
    )
    input_backend = backend or pydirectinput

    def wait_until(deadline: float) -> bool:
        while True:
            if stop_event.is_set():
                return False
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            if remaining > 0.003:
                if stop_event.wait(remaining - 0.002):
                    return False
            else:
                time.sleep(0)

    def send_key(action: str, key_name: str) -> None:
        method = (
            input_backend.keyDown
            if action == "key_down"
            else input_backend.keyUp
        )
        try:
            method(key_name, _pause=False)
        except TypeError:
            method(key_name)

    overall_start = time.perf_counter()
    timer_resolution_enabled = False
    try:
        timer_resolution_enabled = (
            ctypes.windll.winmm.timeBeginPeriod(1) == 0
        )
    except Exception:
        pass
    try:
        for repeat_index in range(max(1, repeat_count)):
            if stop_event.is_set():
                break
            log(f"Playback {repeat_index + 1}/{repeat_count}")
            repeat_start = time.perf_counter()
            for event in events:
                event_time = (
                    float(event.get("time", 0)) - first_event_time
                ) / speed
                deadline = repeat_start + max(0, event_time)
                if not wait_until(deadline):
                    break
                lateness = max(0.0, time.perf_counter() - deadline)
                total_lateness += lateness
                max_lateness = max(max_lateness, lateness)
                dispatched += 1
                key_name = str(event["key"])
                if event["action"] == "key_down":
                    send_key("key_down", key_name)
                    held.add(key_name)
                else:
                    send_key("key_up", key_name)
                    held.discard(key_name)
            if stop_event.is_set():
                break
            if repeat_index < repeat_count - 1:
                if stop_event.wait(repeat_delay):
                    break
    finally:
        for key_name in list(held):
            send_key("key_up", key_name)
        actual_duration = time.perf_counter() - overall_start
        average_lateness = (
            total_lateness / dispatched if dispatched else 0.0
        )
        log(
            "Playback timing: "
            f"speed={speed_percent:g}%, "
            f"average={average_lateness * 1000:.1f}ms, "
            f"maximum={max_lateness * 1000:.1f}ms"
        )
        if timer_resolution_enabled:
            ctypes.windll.winmm.timeEndPeriod(1)
    return {
        "actual_duration": actual_duration,
        "average_lateness": average_lateness,
        "max_lateness": max_lateness,
        "events_dispatched": float(dispatched),
    }
