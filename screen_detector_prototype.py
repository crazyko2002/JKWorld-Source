"""Screen template detector and action runner."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import cv2
import mss
import numpy as np
import pyautogui
import pydirectinput
import yaml

from app_paths import APP_ROOT


ROOT = APP_ROOT
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05
pydirectinput.FAILSAFE = True
pydirectinput.PAUSE = 0.05
LogFn = Callable[[str], None]


class StopCurrentFlow(Exception):
    """Stop only the current flow iteration."""


class StopEngine(Exception):
    """Stop the complete automation engine."""


@dataclass
class RuleState:
    hits: int = 0
    latched: bool = False
    last_triggered: float = 0.0
    started_at: float = 0.0
    condition_state: dict[str, Any] = field(default_factory=dict)


def make_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    if not isinstance(config.get("rules", []), list):
        raise ValueError("config.yaml 的 rules 必須是 list")
    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            config, file, allow_unicode=True, sort_keys=False, default_flow_style=False
        )


def read_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Read an image from a Windows path that may contain Unicode characters."""
    try:
        encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(encoded, flags)


def write_image(path: Path, image: np.ndarray) -> None:
    """Write an image to a Windows path that may contain Unicode characters."""
    suffix = path.suffix.lower() or ".png"
    success, encoded = cv2.imencode(suffix, image)
    if not success:
        raise OSError(f"未能將圖片編碼成 {suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(encoded.tobytes())
    except OSError as exc:
        raise OSError(f"未能寫入 templates 資料夾：{exc}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError("圖片寫入後不存在或檔案為空")


def monitor_from_config(
    sct: mss.mss, configured_region: list[int] | None
) -> tuple[dict[str, int], int, int]:
    primary = sct.monitors[1]
    if not configured_region:
        return dict(primary), primary["left"], primary["top"]
    if len(configured_region) != 4:
        raise ValueError("region 格式必須是 [left, top, width, height]")
    left, top, width, height = map(int, configured_region)
    return (
        {"left": left, "top": top, "width": width, "height": height},
        left,
        top,
    )


def walk_conditions(nodes: list[dict[str, Any]]):
    for node in nodes:
        if node.get("type") != "if":
            continue
        condition = node.get("condition", {})
        yield condition
        yield from walk_condition_group(condition)
        yield from walk_conditions(node.get("then", []))
        yield from walk_conditions(node.get("else", []))


def walk_condition_group(condition: dict[str, Any]):
    children = []
    if condition.get("type") == "group":
        children = condition.get("conditions", [])
    elif condition.get("type") == "scan_miss":
        target = condition.get("target", condition.get("condition", {}))
        children = [target] if isinstance(target, dict) else []
    for child in children:
        yield child
        yield from walk_condition_group(child)


def image_paths_for_rule(rule: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    if rule.get("program") is not None:
        for condition in walk_conditions(rule.get("program", [])):
            if condition.get("type") == "image" and condition.get("template"):
                paths.add(str(condition["template"]))
            elif condition.get("type") == "captcha":
                paths.add(str(condition.get(
                    "template", "templates/captcha_reference.png"
                )))
            elif condition.get("type") == "image_any":
                paths.update(
                    str(path) for path in condition.get("templates", []) if path
                )
    elif rule.get("template"):
        paths.add(str(rule["template"]))
    return paths


def scan_miss_target(condition: dict[str, Any]) -> dict[str, Any]:
    target = condition.get("target", condition.get("condition", {}))
    return target if isinstance(target, dict) else {}


def load_templates(rules: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        name = str(rule.get("name", "unnamed"))
        for configured_path in image_paths_for_rule(rule):
            path = Path(configured_path)
            if not path.is_absolute():
                path = ROOT / path
            image = read_image(path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise FileNotFoundError(f"Flow「{name}」讀不到圖片：{path}")
            templates[configured_path] = image
    return templates


def find_template(
    frame_gray: np.ndarray, template: np.ndarray
) -> tuple[float, tuple[int, int]]:
    if (
        template.shape[0] > frame_gray.shape[0]
        or template.shape[1] > frame_gray.shape[1]
    ):
        return 0.0, (0, 0)
    result = cv2.matchTemplate(frame_gray, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(result)
    return float(score), location


def sleep_interruptibly(seconds: float, stop_event: threading.Event) -> bool:
    return stop_event.wait(max(0, seconds))


def send_hotkey(backend: Any, keys: list[str]) -> None:
    if hasattr(backend, "hotkey"):
        backend.hotkey(*keys)
        return
    for key in keys:
        backend.keyDown(key)
    for key in reversed(keys):
        backend.keyUp(key)


def input_backend_for_action(
    action: dict[str, Any],
    log: LogFn = print,
) -> Any:
    backend_name = str(action.get("backend", "directinput"))
    if backend_name == "directinput":
        return pydirectinput
    if backend_name == "pyautogui":
        return pyautogui
    raise ValueError(f"不支援 input backend：{backend_name}")


def run_actions(
    actions: list[dict[str, Any]],
    match_center: tuple[int, int],
    dry_run: bool,
    stop_event: threading.Event | None = None,
    log: LogFn = print,
    engine_config: dict[str, Any] | None = None,
    action_context: dict[str, Any] | None = None,
) -> None:
    stop_event = stop_event or threading.Event()
    for action in actions:
        if stop_event.is_set():
            return
        delay = float(action.get("delay", 0))
        if delay:
            log(f"  等候 {delay:g} 秒")
            if sleep_interruptibly(delay, stop_event):
                return

        action_type = str(action.get("type", "wait"))
        if action_type == "stop":
            scope = str(action.get("scope", "flow"))
            log("  STOP：停止整個 Engine" if scope == "engine" else "  STOP：停止目前 Flow")
            if scope == "engine":
                stop_event.set()
                raise StopEngine
            raise StopCurrentFlow

        if action_type == "wait":
            seconds = float(action.get("seconds", 0.5))
            log(f"  等候 {seconds:g} 秒")
            if sleep_interruptibly(seconds, stop_event):
                return
            continue

        if dry_run:
            log(f"  [測試模式] {describe_action(action)}")
            continue

        if action_type == "ocr_read":
            from ocr_keypad_action import read_ocr_keypad_action

            answer = read_ocr_keypad_action(
                action,
                engine_config,
                log,
                captcha_match=(action_context or {}).get("captcha_match"),
            )
            if action_context is not None:
                action_context["ocr_text"] = answer
            log(f"  OCR recognized: {answer}")
            continue

        if action_type == "ocr_click":
            from ocr_keypad_action import click_ocr_keypad_action

            backend = input_backend_for_action(action, log)

            def click_at(x: int, y: int) -> None:
                backend.click(x=x, y=y, clicks=1, button="left")

            override = None
            if action_context is not None:
                override = action_context.get("ocr_text")
            click_ocr_keypad_action(
                action,
                engine_config,
                click_at,
                log,
                result_override=override,
            )
            log(f"  完成：{describe_action(action)}")
            continue

        if action_type == "ocr_keypad":
            from ocr_keypad_action import run_ocr_keypad_action

            backend = input_backend_for_action(action, log)

            def click_at(x: int, y: int) -> None:
                backend.click(x=x, y=y, clicks=1, button="left")

            run_ocr_keypad_action(
                action,
                engine_config,
                click_at,
                log,
                captcha_match=(action_context or {}).get("captcha_match"),
            )
            log(f"  完成：{describe_action(action)}")
            continue

        if action_type == "play_record":
            from macro_recorder import (
                load_macro_config,
                load_recording,
                replay_macro,
            )

            recording_file = str(action.get("recording_file", ""))
            macro = (
                load_recording(recording_file)
                if recording_file else load_macro_config()
            )
            events = macro.get("events", [])
            if not events:
                raise ValueError("未有錄製內容；請先在 JK世界 Recorder 錄製")
            repeat_count = max(1, int(action.get("repeat_count", 1)))
            repeat_delay = max(0, float(action.get("repeat_delay", 0.5)))
            speed_percent = max(1, float(action.get("speed_percent", 100)))
            log(
                f"  播放 Recording "
                f"「{Path(recording_file).name if recording_file else 'latest'}」"
                f"：{repeat_count} 次，"
                f"間隔 {repeat_delay:g} 秒，速度 {speed_percent:g}%"
            )
            backend = input_backend_for_action(action, log)
            replay_macro(
                events, repeat_count, repeat_delay, stop_event, log,
                speed_percent=speed_percent,
                backend=backend,
            )
            continue

        backend = input_backend_for_action(action, log)

        if action_type == "click":
            if action.get("target", "match") == "match":
                x, y = match_center
            else:
                x, y = int(action.get("x", 0)), int(action.get("y", 0))
            backend.click(
                x=x,
                y=y,
                clicks=int(action.get("clicks", 1)),
                button=str(action.get("button", "left")),
            )
        elif action_type == "move":
            target = str(action.get("target", "fixed"))
            duration = float(action.get("duration", 0.2))
            if target == "relative":
                backend.moveRel(
                    int(action.get("x", 0)),
                    int(action.get("y", 0)),
                    duration=duration,
                )
            else:
                if target == "match":
                    x, y = match_center
                elif target == "park":
                    screen_size = (action_context or {}).get("screen_size")
                    if screen_size is None:
                        size = pyautogui.size()
                        screen_size = (int(size.width), int(size.height))
                    margin = max(1, int(action.get("margin", 20)))
                    x = max(0, int(screen_size[0]) - margin - 1)
                    y = max(0, int(screen_size[1]) - margin - 1)
                else:
                    x = int(action.get("x", 0))
                    y = int(action.get("y", 0))
                backend.moveTo(x, y, duration=duration)
        elif action_type == "press":
            backend.press(
                str(action.get("key", "enter")),
                presses=int(action.get("presses", 1)),
                interval=float(action.get("interval", 0.05)),
            )
        elif action_type == "hotkey":
            send_hotkey(
                backend, [str(key) for key in action.get("keys", [])]
            )
        elif action_type == "type":
            backend.write(
                str(action.get("text", "")),
                interval=float(action.get("interval", 0.03)),
            )
        else:
            raise ValueError(f"不支援 action type：{action_type}")
        log(f"  完成：{describe_action(action)}")


def describe_action(action: dict[str, Any]) -> str:
    kind = action.get("type", "wait")
    backend_name = str(action.get("backend", "directinput"))
    backend_labels = {
        "directinput": "DirectInput",
        "pyautogui": "PyAutoGUI",
    }
    backend = (
        f" [{backend_labels.get(backend_name, backend_name)}]"
        if kind in {"click", "press", "hotkey", "type", "move", "play_record", "ocr_keypad", "ocr_click"}
        else ""
    )
    if kind == "stop":
        return (
            "停止整個 Engine" if action.get("scope", "flow") == "engine"
            else "停止目前 Flow"
        )
    if kind == "play_record":
        recording_name = Path(
            str(action.get("recording_file", "latest"))
        ).name
        return (
            f"播放 Recording「{recording_name}」"
            f" × {action.get('repeat_count', 1)}"
            f"（{action.get('speed_percent', 100)}%，"
            f"間隔 {action.get('repeat_delay', 0.5)}s）{backend}"
        )
    if kind == "ocr_read":
        return "OCR recognize only (no click)"
    if kind == "ocr_click":
        return f"讀 OCR JSON 並 click numpad{backend}"
    if kind == "ocr_keypad":
        return f"OCR 遊戲驗證碼：讀兩位數並自動 click{backend}"
    if kind == "click":
        target = "偵測位置" if action.get("target", "match") == "match" else (
            f"({action.get('x', 0)}, {action.get('y', 0)})"
        )
        return f"Click {target}{backend}"
    if kind == "press":
        return f"按鍵 {action.get('key', 'enter')}{backend}"
    if kind == "hotkey":
        return "快捷鍵 " + " + ".join(action.get("keys", [])) + backend
    if kind == "type":
        text = str(action.get("text", ""))
        return f"輸入「{text[:30]}」{backend}"
    if kind == "move":
        target = str(action.get("target", "fixed"))
        if target == "park":
            return f"移動滑鼠至停泊角落{backend}"
        if target == "relative":
            return (
                f"相對移動滑鼠 "
                f"({action.get('x', 0)}, {action.get('y', 0)}){backend}"
            )
        if target == "match":
            return f"移動滑鼠至偵測圖片{backend}"
        return (
            f"移動滑鼠至 ({action.get('x', 0)}, {action.get('y', 0)}){backend}"
        )
    return f"等候 {action.get('seconds', 0.5)} 秒"


def describe_condition(condition: dict[str, Any]) -> str:
    kind = condition.get("type", "always")
    negate = condition.get("operator") in {"not_appears", "not_matches"}
    if kind == "image":
        name = Path(str(condition.get("template", "未選圖片"))).name
        verb = "沒有出現" if negate else "出現"
        return f"圖片「{name}」{verb}"
    if kind == "captcha":
        name = Path(str(condition.get(
            "template", "templates/captcha_reference.png"
        ))).name
        return f"驗證碼視窗「{name}」出現"
    if kind == "image_any":
        count = len(condition.get("templates", []))
        return f"Image Group 任一圖片出現（{count} 張）"
    if kind == "time":
        operator = condition.get("operator", "after")
        if operator == "between":
            return f"時間在 {condition.get('start', '00:00')}–{condition.get('end', '23:59')}"
        return f"時間{('早於' if operator == 'before' else '到達')} {condition.get('time', '00:00')}"
    if kind == "elapsed":
        operator = condition.get("operator", ">=")
        return f"Flow 已運行 {operator} {condition.get('seconds', 1)} 秒"
    if kind == "pixel":
        verb = "不符合" if negate else "符合"
        return (
            f"Pixel ({condition.get('x', 0)}, {condition.get('y', 0)}) "
            f"{verb} RGB({condition.get('r', 0)}, {condition.get('g', 0)}, "
            f"{condition.get('b', 0)})"
        )
    if kind == "group":
        joiner = " AND " if condition.get("mode", "all") == "all" else " OR "
        return "(" + joiner.join(
            describe_condition(child) for child in condition.get("conditions", [])
        ) + ")"
    if kind == "scan_miss":
        seconds = float(condition.get("seconds", 60))
        cooldown = float(condition.get("cooldown_seconds", seconds))
        target = scan_miss_target(condition)
        return (
            f"Scan miss {seconds:g}s: {describe_condition(target)} "
            f"(cooldown {cooldown:g}s)"
        )
    return "永遠成立"


def parse_clock(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":", 1))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"時間格式錯誤：{value}")
    return hour * 60 + minute


def evaluate_condition(
    condition: dict[str, Any],
    frame_gray: np.ndarray,
    frame_bgr: np.ndarray,
    templates: dict[str, np.ndarray],
    offset_x: int,
    offset_y: int,
    started_at: float,
    context: dict[str, Any],
) -> bool:
    kind = condition.get("type", "always")
    if kind == "always":
        return True
    if kind == "group":
        children = condition.get("conditions", [])
        checks = [
            evaluate_condition(
                child, frame_gray, frame_bgr, templates,
                offset_x, offset_y, started_at, context
            )
            for child in children
        ]
        return all(checks) if condition.get("mode", "all") == "all" else any(checks)
    if kind == "scan_miss":
        target = scan_miss_target(condition)
        if not target:
            return False
        now = float(context.get("now", time.monotonic()))
        probe_context = dict(context)
        target_found = evaluate_condition(
            target, frame_gray, frame_bgr, templates,
            offset_x, offset_y, started_at, probe_context,
        )
        condition_state = context.setdefault("condition_state", {})
        state_key = f"scan_miss:{id(condition)}"
        state = condition_state.setdefault(
            state_key,
            {"missing_since": None, "last_triggered": None},
        )
        if target_found:
            state["missing_since"] = None
            context["scan_miss_duration"] = 0.0
            return False

        missing_since = state.get("missing_since")
        if missing_since is None:
            missing_since = now
            state["missing_since"] = missing_since
        missing_duration = now - float(missing_since)
        context["scan_miss_duration"] = missing_duration
        required_seconds = max(0.0, float(condition.get("seconds", 60)))
        if missing_duration < required_seconds:
            return False

        cooldown = max(0.0, float(condition.get(
            "cooldown_seconds", required_seconds,
        )))
        last_triggered = state.get("last_triggered")
        if (
            last_triggered is not None
            and now - float(last_triggered) < cooldown
        ):
            return False
        state["last_triggered"] = now
        return True
    if kind == "image":
        configured_path = str(condition.get("template", ""))
        template = templates.get(configured_path)
        if template is None:
            return False
        score, (x, y) = find_template(frame_gray, template)
        matched = score >= float(condition.get("threshold", 0.9))
        if matched:
            context["match_center"] = (
                offset_x + x + template.shape[1] // 2,
                offset_y + y + template.shape[0] // 2,
            )
            context["score"] = score
        if condition.get("operator", "appears") == "not_appears":
            return not matched
        return matched
    if kind == "captcha":
        from captcha_keypad_solver import CaptchaMatch, find_captcha_match

        configured_path = str(condition.get(
            "template", "templates/captcha_reference.png"
        ))
        template = templates.get(configured_path)
        if template is None:
            return False
        match = find_captcha_match(
            frame_gray,
            template,
            threshold=float(condition.get("threshold", 0.82)),
        )
        if match is None:
            return False
        context["captcha_match"] = CaptchaMatch(
            score=match.score,
            left=offset_x + match.left,
            top=offset_y + match.top,
            width=match.width,
            height=match.height,
        )
        context["match_center"] = (
            context["captcha_match"].left + context["captcha_match"].width // 2,
            context["captcha_match"].top + context["captcha_match"].height // 2,
        )
        context["score"] = match.score
        return True
    if kind == "image_any":
        threshold = float(condition.get("threshold", 0.9))
        best_score = -1.0
        best_match: tuple[str, np.ndarray, tuple[int, int]] | None = None
        for configured_path in condition.get("templates", []):
            configured_path = str(configured_path)
            template = templates.get(configured_path)
            if template is None:
                continue
            score, location = find_template(frame_gray, template)
            if score > best_score:
                best_score = score
                best_match = (configured_path, template, location)
        if best_match is None or best_score < threshold:
            return False
        configured_path, template, (x, y) = best_match
        context["match_center"] = (
            offset_x + x + template.shape[1] // 2,
            offset_y + y + template.shape[0] // 2,
        )
        context["score"] = best_score
        context["matched_image"] = configured_path
        return True
    if kind == "time":
        now = datetime.now()
        current = now.hour * 60 + now.minute
        operator = condition.get("operator", "after")
        if operator == "between":
            start = parse_clock(str(condition.get("start", "00:00")))
            end = parse_clock(str(condition.get("end", "23:59")))
            return start <= current <= end if start <= end else (
                current >= start or current <= end
            )
        target = parse_clock(str(condition.get("time", "00:00")))
        return current < target if operator == "before" else current >= target
    if kind == "elapsed":
        elapsed = time.monotonic() - started_at
        target = float(condition.get("seconds", 0))
        operator = condition.get("operator", ">=")
        return elapsed < target if operator == "<" else elapsed >= target
    if kind == "pixel":
        x = int(condition.get("x", 0)) - offset_x
        y = int(condition.get("y", 0)) - offset_y
        if not (0 <= x < frame_bgr.shape[1] and 0 <= y < frame_bgr.shape[0]):
            matched = False
        else:
            b, g, r = (int(value) for value in frame_bgr[y, x][:3])
            tolerance = int(condition.get("tolerance", 10))
            matched = (
                abs(r - int(condition.get("r", 0))) <= tolerance
                and abs(g - int(condition.get("g", 0))) <= tolerance
                and abs(b - int(condition.get("b", 0))) <= tolerance
            )
        if condition.get("operator", "matches") == "not_matches":
            return not matched
        return matched
    return False


def execute_program(
    nodes: list[dict[str, Any]],
    frame_gray: np.ndarray,
    frame_bgr: np.ndarray,
    templates: dict[str, np.ndarray],
    offset_x: int,
    offset_y: int,
    started_at: float,
    dry_run: bool,
    stop_event: threading.Event,
    log: LogFn,
    context: dict[str, Any] | None = None,
    engine_config: dict[str, Any] | None = None,
) -> None:
    if context is None:
        context = {}
    context.setdefault("match_center", (0, 0))
    for node in nodes:
        if stop_event.is_set():
            return
        if node.get("type") == "if":
            result = evaluate_condition(
                node.get("condition", {}),
                frame_gray, frame_bgr, templates,
                offset_x, offset_y, started_at, context,
            )
            log(f"  IF {describe_condition(node.get('condition', {}))} → {result}")
            if result and node.get("condition", {}).get("type") == "image_any":
                log(
                    f"    命中圖片："
                    f"{Path(str(context.get('matched_image', ''))).name} "
                    f"({float(context.get('score', 0)):.1%})"
                )
            branch = node.get("then", []) if result else node.get("else", [])
            execute_program(
                branch, frame_gray, frame_bgr, templates,
                offset_x, offset_y, started_at, dry_run,
                stop_event, log, context, engine_config,
            )
        else:
            run_actions(
                [node], context.get("match_center", (0, 0)),
                dry_run, stop_event, log, engine_config, context,
            )


def capture_template(name: str, log: LogFn = print) -> Path | None:
    safe_name = "".join(char for char in name if char.isalnum() or char in "-_")
    if not safe_name:
        raise ValueError("圖片名稱只可包含英文字母、數字、-、_")
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        frame = np.asarray(sct.grab(monitor))[:, :, :3]
    selection = cv2.selectROI(
        "Select trigger image - ENTER save / ESC cancel",
        frame,
        showCrosshair=True,
        fromCenter=False,
    )
    cv2.destroyAllWindows()
    x, y, width, height = map(int, selection)
    if width == 0 or height == 0:
        log("已取消擷取。")
        return None
    output_dir = ROOT / "templates"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f"{safe_name}.png"
    write_image(output, frame[y : y + height, x : x + width])
    log(f"已儲存圖片：templates/{output.name}")
    return output


def run_detector(
    config_path: Path,
    once: bool = False,
    stop_event: threading.Event | None = None,
    log: LogFn = print,
) -> None:
    stop_event = stop_event or threading.Event()
    config = load_config(config_path)
    rules = [rule for rule in config.get("rules", []) if rule.get("enabled", True)]
    if not rules:
        log("沒有已啟用的 Flow。")
        return
    templates = load_templates(rules)
    started = time.monotonic()
    states = {
        str(rule["name"]): RuleState(started_at=started)
        for rule in rules
    }
    dry_run = bool(config.get("dry_run", True))
    interval = max(float(config.get("poll_interval_ms", 50)) / 1000, 0.02)
    log(f"開始監察 {len(rules)} 個 Flow；測試模式={dry_run}")

    with mss.mss() as sct:
        monitor, offset_x, offset_y = monitor_from_config(
            sct, config.get("region")
        )
        while not stop_event.is_set():
            frame_bgr = np.asarray(sct.grab(monitor))[:, :, :3]
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            now = time.monotonic()
            for rule in rules:
                if stop_event.is_set():
                    break
                name = str(rule["name"])
                state = states[name]
                if rule.get("program") is not None:
                    cooldown = float(rule.get("cooldown_seconds", 0.5))
                    if now - state.last_triggered >= cooldown:
                        log(f"執行 Flow「{name}」")
                        try:
                            execute_program(
                                rule.get("program", []),
                                gray, frame_bgr, templates,
                                offset_x, offset_y, state.started_at,
                                dry_run, stop_event, log,
                                context={
                                    "match_center": (0, 0),
                                    "condition_state": state.condition_state,
                                    "now": now,
                                },
                                engine_config=config,
                            )
                        except StopCurrentFlow:
                            log(f"Flow「{name}」已由 STOP 中止本輪。")
                        except StopEngine:
                            log("Engine 已由 STOP Action 中止。")
                            break
                        except Exception as exc:
                            log(f"ERROR: Flow「{name}」：{exc}")
                        state.last_triggered = time.monotonic()
                    continue

                configured_path = str(rule.get("template", ""))
                template = templates[configured_path]
                score, (match_x, match_y) = find_template(gray, template)
                threshold = float(rule.get("threshold", 0.9))
                if score >= threshold:
                    state.hits += 1
                    needed = int(rule.get("consecutive_hits", 2))
                    cooldown = float(rule.get("cooldown_seconds", 3))
                    can_repeat = rule.get("trigger", "once_per_appearance") == "repeat"
                    ready = state.hits >= needed and (can_repeat or not state.latched)
                    if ready and now - state.last_triggered >= cooldown:
                        center = (
                            offset_x + match_x + template.shape[1] // 2,
                            offset_y + match_y + template.shape[0] // 2,
                        )
                        log(f"命中「{name}」 相似度 {score:.1%}，位置 {center}")
                        try:
                            run_actions(
                                rule.get("actions", []),
                                center,
                                dry_run,
                                stop_event,
                                log,
                                engine_config=config,
                            )
                        except StopCurrentFlow:
                            log(f"Flow「{name}」已由 STOP 中止本輪。")
                        except StopEngine:
                            log("Engine 已由 STOP Action 中止。")
                            break
                        state.last_triggered = time.monotonic()
                        state.latched = True
                else:
                    state.hits = 0
                    state.latched = False
            if once:
                break
            stop_event.wait(interval)
    log("監察已停止。")


def main() -> None:
    make_dpi_aware()
    parser = argparse.ArgumentParser(description="畫面偵測及自動 Action")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--capture", metavar="NAME")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.capture:
        capture_template(args.capture)
    else:
        run_detector(args.config.resolve(), args.once)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止。")
    except pyautogui.FailSafeException:
        print("\n已觸發滑鼠左上角緊急停止。")
