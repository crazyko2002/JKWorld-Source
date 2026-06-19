"""Visual IF / ELSE flow builder for SightFlow."""

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from macro_recorder import list_recordings
from pynput import keyboard

from flow_distribution import publish_bundle_to_git
from screen_detector_prototype import (
    ROOT,
    capture_template,
    describe_action,
    describe_condition,
    load_config,
    make_dpi_aware,
    run_detector,
    save_config,
)


CONFIG_PATH = ROOT / "config.yaml"
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG = "#0E1113"
PANEL = "#171B1E"
CARD = "#20262A"
LINE = "#30383D"
TEXT = "#E7EEE9"
MUTED = "#8D9992"
ACCENT = "#B7F34A"
ORANGE = "#FF9F43"
BLUE = "#55B8FF"
RED = "#FF5D62"

KEY_CHOICES = (
    ["up", "down", "left", "right"]
    + list("abcdefghijklmnopqrstuvwxyz")
    + [str(number) for number in range(10)]
    + [f"f{number}" for number in range(1, 13)]
    + [
        "space", "enter", "escape", "tab", "backspace", "delete",
        "home", "end", "pageup", "pagedown", "insert",
        "shift", "ctrl", "alt",
    ]
)


class ActionDialog(ctk.CTkToplevel):
    TYPES = [
        "click", "press", "hotkey", "type", "wait", "move",
        "play_record", "ocr_read", "ocr_click", "ocr_keypad", "stop",
    ]

    def __init__(self, master, action: dict[str, Any] | None = None):
        super().__init__(master)
        self.result: dict[str, Any] | None = None
        self.original = copy.deepcopy(action or {"type": "click", "target": "match"})
        self.title("Action Editor")
        self.geometry("540x700")
        self.minsize(500, 560)
        self.configure(fg_color=BG)
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        dialog_header(self, "ACTION", "設定動作，以及執行前要等待幾耐。", ACCENT)
        self.body = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
        self.body.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.type_var = ctk.StringVar(value=self.original.get("type", "click"))
        self.delay_var = ctk.StringVar(value=str(self.original.get("delay", 0)))
        self.backend_var = ctk.StringVar(
            value=self.original.get("backend", "directinput")
        )
        packed_field(
            self.body, "Action 類型",
            ctk.CTkOptionMenu(
                self.body, variable=self.type_var, values=self.TYPES,
                command=self.change_action_type,
                fg_color=CARD, button_color=ACCENT,
                button_hover_color="#9ED438", text_color=TEXT,
            ),
        )
        packed_field(
            self.body, "動作前等待（秒）",
            ctk.CTkEntry(
                self.body, textvariable=self.delay_var,
                fg_color=CARD, border_color=LINE, text_color=TEXT,
            ),
        )
        self.dynamic = ctk.CTkScrollableFrame(
            self.body,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=LINE,
            scrollbar_button_hover_color=ACCENT,
        )
        self.dynamic.pack(fill="both", expand=True, padx=(18, 8), pady=(8, 12))
        self.vars: dict[str, ctk.StringVar] = {}
        self.render_fields()
        dialog_footer(self, self.save)

    def change_action_type(self, kind: str) -> None:
        self.render_fields()

    def dynamic_field(self, key: str, label: str, default: Any = "") -> None:
        var = ctk.StringVar(value=str(self.original.get(key, default)))
        self.vars[key] = var
        label_widget(self.dynamic, label).pack(anchor="w", pady=(12, 4))
        ctk.CTkEntry(
            self.dynamic, textvariable=var, fg_color=CARD,
            border_color=LINE, text_color=TEXT,
        ).pack(fill="x")

    def render_fields(self) -> None:
        for child in self.dynamic.winfo_children():
            child.destroy()
        self.vars = {}
        kind = self.type_var.get()
        if kind in {
            "click", "press", "hotkey", "type", "move", "play_record",
            "ocr_keypad", "ocr_click",
        }:
            self.vars["backend"] = self.backend_var
            label_widget(
                self.dynamic,
                "Input backend",
            ).pack(anchor="w", pady=(12, 4))
            backend_values = ["directinput", "pyautogui"]
            ctk.CTkOptionMenu(
                self.dynamic, variable=self.backend_var,
                values=backend_values,
                fg_color=CARD, button_color=ORANGE, text_color=TEXT,
            ).pack(fill="x")
        if kind == "click":
            self.dynamic_field("target", "目標：match 或 fixed", "match")
            self.dynamic_field("x", "固定 X（target=fixed）", 0)
            self.dynamic_field("y", "固定 Y（target=fixed）", 0)
            self.dynamic_field("clicks", "Click 次數", 1)
            self.dynamic_field("button", "left / right / middle", "left")
        elif kind == "press":
            selected_key = str(self.original.get("key", "enter"))
            choices = list(KEY_CHOICES)
            if selected_key not in choices:
                choices.insert(0, selected_key)
            self.key_var = ctk.StringVar(value=selected_key)
            self.vars["key"] = self.key_var
            label_widget(
                self.dynamic, "按鍵（方向上鍵選 up）"
            ).pack(anchor="w", pady=(12, 4))
            ctk.CTkOptionMenu(
                self.dynamic,
                variable=self.key_var,
                values=choices,
                fg_color=CARD,
                button_color=BLUE,
                button_hover_color="#3595D7",
                text_color=TEXT,
            ).pack(fill="x")
            self.dynamic_field("presses", "次數", 1)
        elif kind == "hotkey":
            self.dynamic_field("keys", "以 + 分隔，例如 ctrl+shift+s", "ctrl+s")
        elif kind == "type":
            self.dynamic_field("text", "輸入文字", "")
        elif kind == "wait":
            self.dynamic_field("seconds", "等候秒數", 0.5)
        elif kind == "move":
            default_target = (
                self.original.get("target", "fixed")
                if self.original.get("type") == "move"
                else "park"
            )
            self.move_target_var = ctk.StringVar(value=str(default_target))
            self.vars["target"] = self.move_target_var
            label_widget(self.dynamic, "Move mode").pack(
                anchor="w", pady=(12, 4)
            )
            ctk.CTkOptionMenu(
                self.dynamic,
                variable=self.move_target_var,
                values=["park", "fixed", "relative", "match"],
                fg_color=CARD,
                button_color=BLUE,
                button_hover_color="#3595D7",
                text_color=TEXT,
            ).pack(fill="x")
            ctk.CTkLabel(
                self.dynamic,
                text=(
                    "park: move to bottom-right to clear hover\n"
                    "fixed: screen X/Y · relative: move by X/Y · "
                    "match: detected image centre"
                ),
                text_color=MUTED,
                font=("Microsoft JhengHei UI", 11),
                justify="left",
            ).pack(anchor="w", pady=(7, 0))
            self.dynamic_field("x", "X / relative X", 0)
            self.dynamic_field("y", "Y / relative Y", 0)
            self.dynamic_field("margin", "Park corner margin", 20)
            self.dynamic_field("duration", "移動時間（秒）", 0.2)
        elif kind == "play_record":
            recordings = list_recordings()
            selected = str(self.original.get("recording_file", ""))
            if not selected and recordings:
                selected = recordings[0]
            self.recording_file_var = ctk.StringVar(
                value=selected or "(未有 recording file)"
            )
            self.vars["recording_file"] = self.recording_file_var
            ctk.CTkLabel(
                self.dynamic,
                text="選擇 Simple Recorder 儲存的 keyboard recording 檔案。",
                text_color=ACCENT,
                font=("Microsoft JhengHei UI", 12),
                wraplength=420,
                justify="left",
            ).pack(anchor="w", pady=(14, 4))
            label_widget(self.dynamic, "Recording File").pack(
                anchor="w", pady=(12, 4)
            )
            ctk.CTkOptionMenu(
                self.dynamic,
                variable=self.recording_file_var,
                values=recordings or ["(未有 recording file)"],
                fg_color=CARD,
                button_color=BLUE,
                button_hover_color="#3595D7",
                text_color=TEXT,
            ).pack(fill="x")
            self.dynamic_field("repeat_count", "播放次數", 1)
            self.dynamic_field("repeat_delay", "每次播放間隔（秒）", 0.5)
            self.dynamic_field(
                "speed_percent",
                "播放速度 %（100=原速；較大會縮短按鍵持續時間）",
                100,
            )
        elif kind == "ocr_read":
            ctk.CTkLabel(
                self.dynamic,
                text=(
                    "只辨識兩位數並輸出 OCR result；不會執行 click。"
                    "\n結果會放入 flow context 的 ocr_text。"
                ),
                text_color=ACCENT,
                font=("Microsoft JhengHei UI", 12),
                wraplength=420,
                justify="left",
            ).pack(anchor="w", pady=(14, 4))
        elif kind == "ocr_click":
            ctk.CTkLabel(
                self.dynamic,
                text=(
                    "讀 logs/ocr_latest.json 的 result，"
                    "用 numpad/ 內 0-9 template 搵掣再 click。"
                    "\n唔會再做 OCR。"
                ),
                text_color=ACCENT,
                font=("Microsoft JhengHei UI", 12),
                wraplength=420,
                justify="left",
            ).pack(anchor="w", pady=(14, 4))
            self.dynamic_field(
                "click_interval",
                "每次 click 間隔（秒；留空用 config 預設）",
                self.original.get("click_interval", ""),
            )
            self.dynamic_field(
                "numpad_dir",
                "numpad template 資料夾",
                self.original.get("numpad_dir", "numpad"),
            )
        elif kind == "ocr_keypad":
            ctk.CTkLabel(
                self.dynamic,
                text="偵測 Tales Runner 驗證碼視窗，OCR 兩位數並 click 隨機 keypad。",
                text_color=ACCENT,
                font=("Microsoft JhengHei UI", 12),
                wraplength=420,
                justify="left",
            ).pack(anchor="w", pady=(14, 4))
            self.dynamic_field(
                "click_interval",
                "每次 click 間隔（秒；留空用 config 預設）",
                self.original.get("click_interval", ""),
            )
        elif kind == "stop":
            self.dynamic_field(
                "scope", "停止範圍：flow 或 engine", "flow"
            )

    def save(self) -> None:
        try:
            result: dict[str, Any] = {
                "type": self.type_var.get(),
                "delay": float(self.delay_var.get() or 0),
            }
            for key, var in self.vars.items():
                value: Any = var.get()
                if key in {
                    "x", "y", "clicks", "presses", "repeat_count", "margin",
                }:
                    value = int(value or 0)
                elif key in {
                    "seconds", "duration", "repeat_delay", "speed_percent",
                    "click_interval",
                }:
                    if str(value).strip() == "":
                        continue
                    value = float(value or 0)
                elif key == "keys":
                    value = [part.strip() for part in value.split("+") if part.strip()]
                result[key] = value
            if (
                result.get("type") == "play_record"
                and result.get("recording_file") == "(未有 recording file)"
            ):
                raise ValueError("請先在 Simple Recorder 儲存 recording file")
            if result.get("type") == "ocr_keypad":
                result["mode"] = "captcha"
            self.result = result
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("格式錯誤", str(exc), parent=self)


class ConditionDialog(ctk.CTkToplevel):
    TYPES = [
        "image", "captcha", "image_any", "time", "elapsed", "pixel", "group", "always",
    ]

    def __init__(
        self,
        master,
        condition: dict[str, Any] | None = None,
        simple_only: bool = False,
    ):
        super().__init__(master)
        self.result: dict[str, Any] | None = None
        self.original = copy.deepcopy(condition or {"type": "image"})
        self.group_conditions = copy.deepcopy(self.original.get("conditions", []))
        self.image_group = copy.deepcopy(self.original.get("templates", []))
        self.simple_only = simple_only
        self.title("Condition Editor")
        self.geometry("590x700")
        self.configure(fg_color=BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        dialog_header(
            self, "IF CONDITION",
            "條件成立行 THEN；唔成立行 ELSE。", BLUE,
        )
        self.body = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
        self.body.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        values = [value for value in self.TYPES if not simple_only or value != "group"]
        self.type_var = ctk.StringVar(value=self.original.get("type", values[0]))
        packed_field(
            self.body, "Condition 類型",
            ctk.CTkOptionMenu(
                self.body, variable=self.type_var, values=values,
                command=lambda _: self.render_fields(),
                fg_color=CARD, button_color=BLUE,
                button_hover_color="#3595D7", text_color=TEXT,
            ),
        )
        self.dynamic = ctk.CTkScrollableFrame(
            self.body, fg_color="transparent", corner_radius=0,
        )
        self.dynamic.pack(fill="both", expand=True, padx=12, pady=8)
        self.vars: dict[str, ctk.StringVar] = {}
        self.render_fields()
        dialog_footer(self, self.save, "儲存 Condition", BLUE)

    def field(self, key: str, label: str, default: Any = "") -> None:
        var = ctk.StringVar(value=str(self.original.get(key, default)))
        self.vars[key] = var
        label_widget(self.dynamic, label).pack(anchor="w", pady=(11, 4))
        ctk.CTkEntry(
            self.dynamic, textvariable=var, fg_color=CARD,
            border_color=LINE, text_color=TEXT,
        ).pack(fill="x")

    def option(self, key: str, label: str, values: list[str], default: str) -> None:
        var = ctk.StringVar(value=str(self.original.get(key, default)))
        self.vars[key] = var
        label_widget(self.dynamic, label).pack(anchor="w", pady=(11, 4))
        ctk.CTkOptionMenu(
            self.dynamic, variable=var, values=values,
            fg_color=CARD, button_color=LINE, text_color=TEXT,
        ).pack(fill="x")

    def render_fields(self) -> None:
        for child in self.dynamic.winfo_children():
            child.destroy()
        self.vars = {}
        kind = self.type_var.get()
        if kind == "image":
            self.option(
                "operator", "判斷", ["appears", "not_appears"], "appears",
            )
            self.field("template", "圖片路徑", "")
            row = ctk.CTkFrame(self.dynamic, fg_color="transparent")
            row.pack(fill="x", pady=8)
            ctk.CTkButton(
                row, text="CAPTURE SCREEN", command=self.capture_image,
                fg_color=ORANGE, hover_color="#DF8737", text_color="#17110A",
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkButton(
                row, text="BROWSE", command=self.browse_image,
                fg_color=CARD, hover_color=LINE, text_color=TEXT,
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))
            self.field("threshold", "相似度門檻（0.5–0.99）", 0.9)
        elif kind == "captcha":
            ctk.CTkLabel(
                self.dynamic,
                text=(
                    "偵測 Tales Runner「輸入驗證碼」視窗。"
                    "預設用 templates/captcha_reference.png；"
                    "命中後可直接跑 ocr_keypad captcha action。"
                ),
                justify="left",
                text_color=ACCENT,
                font=("Microsoft JhengHei UI", 12),
                wraplength=420,
            ).pack(anchor="w", pady=(10, 5))
            self.field(
                "template",
                "參考圖片路徑",
                "templates/captcha_reference.png",
            )
            self.field("threshold", "相似度門檻（0.75–0.95）", 0.82)
        elif kind == "image_any":
            ctk.CTkLabel(
                self.dynamic,
                text=(
                    "只要以下其中一張圖片命中，就會執行 THEN。\n"
                    "適合同一畫面有動畫、顏色或狀態變化。"
                ),
                justify="left", text_color=ACCENT,
                font=("Microsoft JhengHei UI", 12),
            ).pack(anchor="w", pady=(10, 5))
            self.field("threshold", "共用相似度門檻（0.5–0.99）", 0.85)
            self.image_group_box = ctk.CTkFrame(
                self.dynamic, fg_color="#111518",
            )
            self.image_group_box.pack(fill="x", pady=8)
            self.render_image_group()
            row = ctk.CTkFrame(self.dynamic, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkButton(
                row, text="+ CAPTURE IMAGE",
                command=self.capture_group_image,
                fg_color=ORANGE, hover_color="#DF8737",
                text_color="#17110A",
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkButton(
                row, text="+ BROWSE IMAGES",
                command=self.browse_group_images,
                fg_color=CARD, hover_color=LINE, text_color=TEXT,
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))
        elif kind == "time":
            self.option(
                "operator", "判斷", ["after", "before", "between"], "after",
            )
            self.field("time", "時間（HH:MM，after / before）", "12:00")
            self.field("start", "開始時間（between）", "09:00")
            self.field("end", "結束時間（between）", "18:00")
        elif kind == "elapsed":
            self.option("operator", "判斷", [">=", "<"], ">=")
            self.field("seconds", "Flow 開始後秒數", 5)
        elif kind == "pixel":
            self.option(
                "operator", "判斷", ["matches", "not_matches"], "matches",
            )
            for key, label, default in [
                ("x", "螢幕 X", 0), ("y", "螢幕 Y", 0),
                ("r", "Red（0–255）", 255), ("g", "Green（0–255）", 255),
                ("b", "Blue（0–255）", 255), ("tolerance", "容許色差", 10),
            ]:
                self.field(key, label, default)
        elif kind == "group":
            self.option("mode", "組合方式", ["all", "any"], "all")
            ctk.CTkLabel(
                self.dynamic,
                text="ALL = 所有條件成立（AND）\nANY = 任一條件成立（OR）",
                justify="left", text_color=MUTED,
                font=("Microsoft JhengHei UI", 11),
            ).pack(anchor="w", pady=(10, 6))
            self.group_box = ctk.CTkFrame(self.dynamic, fg_color="#111518")
            self.group_box.pack(fill="x", pady=6)
            self.render_group()
            ctk.CTkButton(
                self.dynamic, text="+ ADD SUB-CONDITION",
                command=self.add_subcondition,
                fg_color=CARD, hover_color=LINE, text_color=BLUE,
            ).pack(fill="x", pady=8)
        else:
            ctk.CTkLabel(
                self.dynamic, text="此條件永遠成立。",
                text_color=MUTED, font=("Microsoft JhengHei UI", 13),
            ).pack(pady=40)

    def render_group(self) -> None:
        for child in self.group_box.winfo_children():
            child.destroy()
        if not self.group_conditions:
            ctk.CTkLabel(
                self.group_box, text="未有子條件", text_color=MUTED,
            ).pack(pady=18)
        for index, condition in enumerate(self.group_conditions):
            row = ctk.CTkFrame(self.group_box, fg_color=CARD)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(
                row, text=describe_condition(condition), anchor="w",
                text_color=TEXT, wraplength=350,
            ).pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkButton(
                row, text="✎", width=32, fg_color="transparent",
                hover_color=LINE, command=lambda i=index: self.edit_subcondition(i),
            ).pack(side="left")
            ctk.CTkButton(
                row, text="×", width=32, fg_color="transparent",
                hover_color="#442428", text_color=RED,
                command=lambda i=index: self.remove_subcondition(i),
            ).pack(side="left", padx=(0, 4))

    def render_image_group(self) -> None:
        for child in self.image_group_box.winfo_children():
            child.destroy()
        if not self.image_group:
            ctk.CTkLabel(
                self.image_group_box,
                text="未有圖片 — 請 Capture 或 Browse",
                text_color=MUTED,
            ).pack(pady=18)
            return
        for index, configured_path in enumerate(self.image_group):
            row = ctk.CTkFrame(self.image_group_box, fg_color=CARD)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(
                row,
                text=f"{index + 1:02}  {Path(configured_path).name}",
                anchor="w", text_color=TEXT,
                font=("Microsoft JhengHei UI", 11),
            ).pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkButton(
                row, text="×", width=32, fg_color="transparent",
                hover_color="#442428", text_color=RED,
                command=lambda i=index: self.remove_group_image(i),
            ).pack(side="right", padx=4)

    def remove_group_image(self, index: int) -> None:
        self.image_group.pop(index)
        self.render_image_group()

    def capture_group_image(self) -> None:
        output = self.capture_to_file(f"group_{int(time.time() * 1000)}")
        if output:
            relative = str(output.relative_to(ROOT)).replace("\\", "/")
            if relative not in self.image_group:
                self.image_group.append(relative)
            self.render_image_group()

    def browse_group_images(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="選擇 Image Group 圖片",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")],
        )
        for path in paths:
            selected = Path(path)
            try:
                selected = selected.resolve().relative_to(ROOT.resolve())
            except ValueError:
                pass
            value = str(selected).replace("\\", "/")
            if value not in self.image_group:
                self.image_group.append(value)
        if paths:
            self.render_image_group()

    def add_subcondition(self) -> None:
        self.grab_release()
        dialog = ConditionDialog(self, simple_only=True)
        self.wait_window(dialog)
        self.grab_set()
        if dialog.result:
            self.group_conditions.append(dialog.result)
            self.render_group()

    def edit_subcondition(self, index: int) -> None:
        self.grab_release()
        dialog = ConditionDialog(
            self, self.group_conditions[index], simple_only=True,
        )
        self.wait_window(dialog)
        self.grab_set()
        if dialog.result:
            self.group_conditions[index] = dialog.result
            self.render_group()

    def remove_subcondition(self, index: int) -> None:
        self.group_conditions.pop(index)
        self.render_group()

    def capture_image(self) -> None:
        output = self.capture_to_file(f"condition_{int(time.time())}")
        if output:
            self.vars["template"].set(
                str(output.relative_to(ROOT)).replace("\\", "/")
            )

    def capture_to_file(self, name: str) -> Path | None:
        self.grab_release()
        ancestors = []
        current = self.master
        while current is not None:
            if hasattr(current, "withdraw"):
                ancestors.append(current)
            current = getattr(current, "master", None)
        self.withdraw()
        for window in ancestors:
            window.withdraw()
        self.update()
        output = None
        try:
            output = capture_template(name)
        except Exception as exc:
            messagebox.showerror("擷取失敗", str(exc))
        finally:
            for window in reversed(ancestors):
                window.deiconify()
            self.deiconify()
            self.lift()
            self.grab_set()
        return output

    def browse_image(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="選擇條件圖片",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")],
        )
        if path:
            selected = Path(path)
            try:
                selected = selected.resolve().relative_to(ROOT.resolve())
            except ValueError:
                pass
            self.vars["template"].set(str(selected).replace("\\", "/"))

    def save(self) -> None:
        try:
            kind = self.type_var.get()
            result: dict[str, Any] = {"type": kind}
            if kind == "group":
                if not self.group_conditions:
                    raise ValueError("條件組最少需要一個子條件")
                result["mode"] = self.vars["mode"].get()
                result["conditions"] = self.group_conditions
            elif kind == "image_any":
                if not self.image_group:
                    raise ValueError("Image Group 最少需要一張圖片")
                result["threshold"] = float(self.vars["threshold"].get())
                result["templates"] = list(self.image_group)
            else:
                for key, var in self.vars.items():
                    value: Any = var.get()
                    if key in {"x", "y", "r", "g", "b", "tolerance"}:
                        value = int(value)
                    elif key in {"seconds", "threshold"}:
                        value = float(value)
                    result[key] = value
                if kind == "image" and not result.get("template"):
                    raise ValueError("請 Capture 或選擇圖片")
            self.result = result
            self.destroy()
        except ValueError as exc:
            messagebox.showerror("格式錯誤", str(exc), parent=self)


def label_widget(parent, text: str):
    return ctk.CTkLabel(
        parent, text=text, text_color=MUTED,
        font=("Microsoft JhengHei UI", 12),
    )


def packed_field(parent, label: str, widget) -> None:
    label_widget(parent, label).pack(anchor="w", padx=18, pady=(14, 5))
    widget.pack(fill="x", padx=18)


def dialog_header(parent, title: str, subtitle: str, color: str) -> None:
    ctk.CTkLabel(
        parent, text=title, font=("Bahnschrift", 26, "bold"), text_color=color,
    ).pack(anchor="w", padx=28, pady=(24, 4))
    ctk.CTkLabel(
        parent, text=subtitle, font=("Microsoft JhengHei UI", 13),
        text_color=MUTED,
    ).pack(anchor="w", padx=28, pady=(0, 18))


def dialog_footer(
    parent, save_command, save_text: str = "儲存 Action", color: str = ACCENT,
) -> None:
    footer = ctk.CTkFrame(parent, fg_color="transparent")
    footer.pack(fill="x", padx=24, pady=(0, 22))
    ctk.CTkButton(
        footer, text="取消", command=parent.destroy, width=110,
        fg_color=CARD, hover_color=LINE, text_color=TEXT,
    ).pack(side="left")
    ctk.CTkButton(
        footer, text=save_text, command=save_command, width=170,
        fg_color=color, hover_color=LINE, text_color="#111510",
    ).pack(side="right")


class FlowApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SightFlow — IF / ELSE Automation")
        self.geometry("1280x820")
        self.minsize(1100, 720)
        self.configure(fg_color=BG)
        self.config_data = self.load_and_migrate()
        self.selected_index = 0 if self.config_data["rules"] else -1
        self.stop_event: threading.Event | None = None
        self.worker: threading.Thread | None = None
        self.recorder_window = None
        self.f10_stop_latched = False
        self.emergency_listener = keyboard.Listener(
            on_press=self.emergency_key_down,
            on_release=self.emergency_key_up,
        )
        self.emergency_listener.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.refresh_flow_list()
        self.load_selected()

    def load_and_migrate(self) -> dict[str, Any]:
        try:
            config = load_config(CONFIG_PATH)
        except Exception:
            config = {}
        config.setdefault("dry_run", True)
        config.setdefault("poll_interval_ms", 50)
        config.setdefault("region", None)
        config.setdefault("rules", [])
        config.setdefault("local_ocr", {
            "captcha": {
                "template": "templates/captcha_reference.png",
                "threshold": 0.82,
                "click_interval": 0.15,
            },
        })
        local_ocr = config["local_ocr"]
        local_ocr.setdefault("captcha", {
            "template": "templates/captcha_reference.png",
            "threshold": 0.82,
            "click_interval": 0.15,
        })
        has_captcha_flow = any(
            str(rule.get("name", "")) == "驗證碼自動輸入"
            for rule in config["rules"]
        )
        if not has_captcha_flow and (ROOT / "templates" / "captcha_reference.png").exists():
            config["rules"].append({
                "name": "驗證碼自動輸入",
                "enabled": True,
                "cooldown_seconds": 0.5,
                "program": [{
                    "type": "if",
                    "condition": {
                        "type": "captcha",
                        "template": "templates/captcha_reference.png",
                        "threshold": 0.82,
                    },
                    "then": [{
                        "type": "ocr_keypad",
                        "mode": "captcha",
                        "backend": "directinput",
                        "click_interval": 0.15,
                    }],
                    "else": [],
                }],
            })
        for rule in config["rules"]:
            if "program" not in rule:
                actions = rule.pop("actions", [])
                if rule.get("template"):
                    rule["program"] = [{
                        "type": "if",
                        "condition": {
                            "type": "image",
                            "operator": "appears",
                            "template": rule.get("template", ""),
                            "threshold": rule.get("threshold", 0.9),
                        },
                        "then": actions,
                        "else": [],
                    }]
                else:
                    rule["program"] = actions
            rule.setdefault("cooldown_seconds", 0.05)
        save_config(CONFIG_PATH, config)
        return config

    def build_ui(self) -> None:
        header = ctk.CTkFrame(self, height=72, fg_color=BG)
        header.pack(fill="x", padx=22, pady=(12, 4))
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="SIGHT", font=("Bahnschrift", 29, "bold"),
            text_color=TEXT,
        ).pack(side="left", pady=15)
        ctk.CTkLabel(
            header, text="FLOW", font=("Bahnschrift", 29, "bold"),
            text_color=ACCENT,
        ).pack(side="left", pady=15)
        ctk.CTkLabel(
            header, text="IF / ELSE AUTOMATION ENGINE",
            font=("Bahnschrift", 11, "bold"), text_color=MUTED,
        ).pack(side="left", padx=18, pady=(28, 15))
        ctk.CTkLabel(
            header, text="F10 = EMERGENCY STOP",
            font=("Bahnschrift", 10, "bold"), text_color=ORANGE,
        ).pack(side="left", padx=(2, 12), pady=(28, 15))
        self.status_label = ctk.CTkLabel(
            header, text="● STOPPED", text_color=MUTED,
            font=("Bahnschrift", 12, "bold"),
        )
        self.status_label.pack(side="right", padx=(14, 0))
        self.start_button = ctk.CTkButton(
            header, text="▶ START", width=120, height=38,
            fg_color=ACCENT, hover_color="#9ED438", text_color="#111510",
            font=("Bahnschrift", 13, "bold"), command=self.start,
        )
        self.start_button.pack(side="right", padx=6)
        ctk.CTkButton(
            header, text="■ STOP", width=100, height=38,
            fg_color=CARD, hover_color=RED, text_color=TEXT,
            command=self.stop,
        ).pack(side="right", padx=6)
        ctk.CTkButton(
            header, text="RECORDER", width=105, height=38,
            fg_color=RED, hover_color="#DB444A", text_color="#160809",
            command=self.open_recorder,
        ).pack(side="right", padx=6)
        self.publish_button = ctk.CTkButton(
            header, text="PUBLISH", width=100, height=38,
            fg_color=ORANGE, hover_color="#DF8737", text_color="#171009",
            command=self.publish_flows,
        )
        self.publish_button.pack(side="right", padx=6)

        work = ctk.CTkFrame(self, fg_color="transparent")
        work.pack(fill="both", expand=True, padx=22, pady=4)
        work.grid_columnconfigure(0, weight=0, minsize=230)
        work.grid_columnconfigure(1, weight=0, minsize=280)
        work.grid_columnconfigure(2, weight=1)
        work.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(work, fg_color=PANEL, corner_radius=12)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.settings = ctk.CTkFrame(work, fg_color=PANEL, corner_radius=12)
        self.settings.grid(row=0, column=1, sticky="nsew", padx=8)
        self.logic = ctk.CTkFrame(work, fg_color=PANEL, corner_radius=12)
        self.logic.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.build_sidebar()
        self.build_settings()
        self.build_logic()
        self.log_box = ctk.CTkTextbox(
            self, height=100, fg_color="#090C0E", border_width=1,
            border_color=LINE, text_color="#B8C4BD",
            font=("Cascadia Mono", 11), corner_radius=10,
        )
        self.log_box.pack(fill="x", padx=22, pady=(10, 18))
        self.log("Ready. 用 + IF 建立條件分支，THEN / ELSE 可繼續加 IF。")

    def title_block(self, parent, number: str, title: str, subtitle: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(17, 10))
        ctk.CTkLabel(
            row, text=number, width=30, height=30, fg_color=ACCENT,
            text_color="#111510", corner_radius=15,
            font=("Bahnschrift", 12, "bold"),
        ).pack(side="left")
        copy_frame = ctk.CTkFrame(row, fg_color="transparent")
        copy_frame.pack(side="left", padx=9)
        ctk.CTkLabel(
            copy_frame, text=title, text_color=TEXT,
            font=("Bahnschrift", 16, "bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            copy_frame, text=subtitle, text_color=MUTED,
            font=("Microsoft JhengHei UI", 10),
        ).pack(anchor="w")

    def build_sidebar(self) -> None:
        self.title_block(self.sidebar, "01", "FLOWS", "Independent programs")
        self.flow_list = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
        )
        self.flow_list.pack(fill="both", expand=True, padx=9)
        ctk.CTkButton(
            self.sidebar, text="+ NEW FLOW", command=self.add_flow,
            fg_color=CARD, hover_color=LINE, text_color=ACCENT,
        ).pack(fill="x", padx=13, pady=(8, 5))
        ctk.CTkButton(
            self.sidebar, text="DELETE FLOW", command=self.delete_flow,
            fg_color="transparent", hover_color="#3A2022", text_color=RED,
        ).pack(fill="x", padx=13, pady=(0, 13))

    def build_settings(self) -> None:
        self.title_block(self.settings, "02", "SETTINGS", "Flow execution")
        body = ctk.CTkScrollableFrame(
            self.settings,
            fg_color="transparent",
            scrollbar_button_color=LINE,
            scrollbar_button_hover_color=MUTED,
        )
        body.pack(fill="both", expand=True, padx=16)
        self.name_var = ctk.StringVar()
        self.cooldown_var = ctk.StringVar(value="0.05")
        self.scan_interval_var = ctk.StringVar(value="50")
        self.enabled_var = ctk.BooleanVar(value=True)
        self.dry_var = ctk.BooleanVar(value=True)
        label_widget(body, "Flow 名稱").pack(anchor="w", pady=(8, 5))
        ctk.CTkEntry(
            body, textvariable=self.name_var, fg_color=CARD,
            border_color=LINE, text_color=TEXT,
        ).pack(fill="x")
        label_widget(body, "每輪最短間隔（秒）").pack(anchor="w", pady=(16, 5))
        ctk.CTkEntry(
            body, textvariable=self.cooldown_var, fg_color=CARD,
            border_color=LINE, text_color=TEXT,
        ).pack(fill="x")
        label_widget(
            body, "全域畫面掃描間隔（ms，建議 30–50）"
        ).pack(anchor="w", pady=(16, 5))
        ctk.CTkEntry(
            body, textvariable=self.scan_interval_var, fg_color=CARD,
            border_color=LINE, text_color=TEXT,
        ).pack(fill="x")
        ctk.CTkSwitch(
            body, text="啟用此 Flow", variable=self.enabled_var,
            progress_color=ACCENT, text_color=TEXT,
        ).pack(anchor="w", pady=(22, 8))
        ctk.CTkSwitch(
            body, text="測試模式（不操作滑鼠鍵盤）", variable=self.dry_var,
            progress_color=ORANGE, text_color=TEXT,
        ).pack(anchor="w", pady=8)
        ctk.CTkFrame(body, height=1, fg_color=LINE).pack(fill="x", pady=20)
        ctk.CTkLabel(
            body,
            text=(
                "條件種類\n"
                "• Image 出現／消失\n"
                "• 指定時間／時段\n"
                "• Flow 經過時間\n"
                "• Pixel 顏色\n"
                "• AND／OR 條件組\n\n"
                "IF 入面可再放 IF，支援無限層 THEN / ELSE。"
            ),
            justify="left", anchor="w", text_color=MUTED,
            font=("Microsoft JhengHei UI", 12),
        ).pack(fill="x")
        ctk.CTkButton(
            body, text="SAVE FLOW", command=self.save_current,
            fg_color=ACCENT, hover_color="#9ED438", text_color="#111510",
            height=40,
        ).pack(side="bottom", fill="x", pady=16)

    def build_logic(self) -> None:
        self.title_block(self.logic, "03", "PROGRAM", "IF → THEN / ELSE")
        self.program_scroll = ctk.CTkScrollableFrame(
            self.logic, fg_color="transparent", corner_radius=0,
        )
        self.program_scroll.pack(fill="both", expand=True, padx=12)
        footer = ctk.CTkFrame(self.logic, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(
            footer, text="+ ACTION", command=lambda: self.add_action([]),
            fg_color=CARD, hover_color=LINE, text_color=ACCENT,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            footer, text="+ IF / ELSE", command=lambda: self.add_if([]),
            fg_color=BLUE, hover_color="#3595D7", text_color="#09141B",
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def refresh_flow_list(self) -> None:
        for child in self.flow_list.winfo_children():
            child.destroy()
        for index, rule in enumerate(self.config_data["rules"]):
            selected = index == self.selected_index
            ctk.CTkButton(
                self.flow_list,
                text=("● " if rule.get("enabled", True) else "○ ") + rule["name"],
                anchor="w", height=42,
                fg_color="#2B3428" if selected else "transparent",
                hover_color=CARD,
                text_color=ACCENT if selected else TEXT,
                command=lambda i=index: self.select_flow(i),
            ).pack(fill="x", pady=3)

    def select_flow(self, index: int) -> None:
        self.save_current(silent=True)
        self.selected_index = index
        self.refresh_flow_list()
        self.load_selected()

    def current_rule(self) -> dict[str, Any] | None:
        if 0 <= self.selected_index < len(self.config_data["rules"]):
            return self.config_data["rules"][self.selected_index]
        return None

    def add_flow(self) -> None:
        self.save_current(silent=True)
        self.config_data["rules"].append({
            "name": f"Flow {len(self.config_data['rules']) + 1}",
            "enabled": True, "cooldown_seconds": 0.05, "program": [],
        })
        self.selected_index = len(self.config_data["rules"]) - 1
        self.refresh_flow_list()
        self.load_selected()

    def delete_flow(self) -> None:
        rule = self.current_rule()
        if not rule:
            return
        if not messagebox.askyesno("刪除 Flow", f"確定刪除「{rule['name']}」？"):
            return
        self.config_data["rules"].pop(self.selected_index)
        self.selected_index = min(
            self.selected_index, len(self.config_data["rules"]) - 1,
        )
        save_config(CONFIG_PATH, self.config_data)
        self.refresh_flow_list()
        self.load_selected()

    def load_selected(self) -> None:
        rule = self.current_rule()
        if not rule:
            self.name_var.set("")
            self.render_program()
            return
        self.name_var.set(rule.get("name", ""))
        self.cooldown_var.set(str(rule.get("cooldown_seconds", 0.05)))
        self.scan_interval_var.set(
            str(self.config_data.get("poll_interval_ms", 50))
        )
        self.enabled_var.set(bool(rule.get("enabled", True)))
        self.dry_var.set(bool(self.config_data.get("dry_run", True)))
        self.render_program()

    def save_current(self, silent: bool = False) -> bool:
        rule = self.current_rule()
        if not rule:
            return False
        try:
            rule["name"] = self.name_var.get().strip() or "Untitled Flow"
            rule["enabled"] = self.enabled_var.get()
            rule["cooldown_seconds"] = max(0.05, float(self.cooldown_var.get()))
            self.config_data["poll_interval_ms"] = max(
                20, int(self.scan_interval_var.get())
            )
            self.config_data["dry_run"] = self.dry_var.get()
            save_config(CONFIG_PATH, self.config_data)
            self.refresh_flow_list()
            if not silent:
                self.log(f"已儲存 Flow「{rule['name']}」。")
            return True
        except ValueError:
            if not silent:
                messagebox.showerror("格式錯誤", "執行間隔必須是數字。")
            return False

    def sequence_at(self, path: list[tuple[int, str]]) -> list[dict[str, Any]]:
        rule = self.current_rule()
        if not rule:
            return []
        sequence = rule.setdefault("program", [])
        for node_index, branch in path:
            sequence = sequence[node_index].setdefault(branch, [])
        return sequence

    def render_program(self) -> None:
        for child in self.program_scroll.winfo_children():
            child.destroy()
        rule = self.current_rule()
        if not rule or not rule.get("program"):
            ctk.CTkLabel(
                self.program_scroll,
                text="EMPTY PROGRAM\n\n先加入 IF / ELSE 或 ACTION",
                text_color=MUTED, font=("Bahnschrift", 14, "bold"),
            ).pack(pady=80)
            return
        self.render_sequence(
            self.program_scroll, rule["program"], [], 0,
        )

    def render_sequence(
        self,
        parent,
        sequence: list[dict[str, Any]],
        path: list[tuple[int, str]],
        depth: int,
    ) -> None:
        for index, node in enumerate(sequence):
            if node.get("type") == "if":
                self.render_if_node(parent, node, path, index, depth)
            else:
                self.render_action_node(parent, node, path, index, depth)

    def node_tools(self, parent, path, index, edit_command) -> None:
        for symbol, command, color in [
            ("↑", lambda: self.move_node(path, index, -1), TEXT),
            ("↓", lambda: self.move_node(path, index, 1), TEXT),
            ("✎", edit_command, TEXT),
            ("×", lambda: self.remove_node(path, index), RED),
        ]:
            ctk.CTkButton(
                parent, text=symbol, width=30, height=28,
                fg_color="transparent", hover_color=LINE,
                text_color=color, command=command,
            ).pack(side="left", padx=1)

    def render_action_node(self, parent, action, path, index, depth) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=CARD, border_width=1, border_color=LINE,
            corner_radius=9,
        )
        card.pack(fill="x", padx=(depth * 10, 0), pady=5)
        ctk.CTkLabel(
            card, text="DO", width=44, text_color=ACCENT,
            font=("Bahnschrift", 13, "bold"),
        ).pack(side="left", padx=(6, 0), pady=12)
        ctk.CTkLabel(
            card, text=describe_action(action), anchor="w",
            text_color=TEXT, font=("Microsoft JhengHei UI", 12, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=6)
        tools = ctk.CTkFrame(card, fg_color="transparent")
        tools.pack(side="right", padx=6)
        self.node_tools(
            tools, path, index,
            lambda: self.edit_action(path, index),
        )

    def render_if_node(self, parent, node, path, index, depth) -> None:
        shell = ctk.CTkFrame(
            parent, fg_color="#141B20", border_width=1,
            border_color="#315167", corner_radius=10,
        )
        shell.pack(fill="x", padx=(depth * 10, 0), pady=7)
        head = ctk.CTkFrame(shell, fg_color="#19262E", corner_radius=8)
        head.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(
            head, text="IF", width=42, text_color=BLUE,
            font=("Bahnschrift", 15, "bold"),
        ).pack(side="left", padx=(5, 0), pady=10)
        ctk.CTkLabel(
            head, text=describe_condition(node.get("condition", {})),
            anchor="w", wraplength=450, text_color=TEXT,
            font=("Microsoft JhengHei UI", 12, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=5)
        tools = ctk.CTkFrame(head, fg_color="transparent")
        tools.pack(side="right", padx=5)
        self.node_tools(
            tools, path, index,
            lambda: self.edit_condition(path, index),
        )
        for branch, title, color in [
            ("then", "THEN — 條件成立", ACCENT),
            ("else", "ELSE — 條件不成立", ORANGE),
        ]:
            branch_box = ctk.CTkFrame(shell, fg_color="#101518", corner_radius=8)
            branch_box.pack(fill="x", padx=12, pady=(2, 8))
            ctk.CTkLabel(
                branch_box, text=title, text_color=color,
                font=("Bahnschrift", 11, "bold"),
            ).pack(anchor="w", padx=10, pady=(8, 3))
            child_path = path + [(index, branch)]
            children = node.setdefault(branch, [])
            if children:
                self.render_sequence(
                    branch_box, children, child_path, depth + 1,
                )
            else:
                ctk.CTkLabel(
                    branch_box, text="No steps", text_color=MUTED,
                ).pack(anchor="w", padx=12, pady=5)
            add_row = ctk.CTkFrame(branch_box, fg_color="transparent")
            add_row.pack(fill="x", padx=8, pady=(2, 8))
            ctk.CTkButton(
                add_row, text="+ ACTION", height=28,
                fg_color=CARD, hover_color=LINE, text_color=ACCENT,
                command=lambda p=child_path: self.add_action(p),
            ).pack(side="left", padx=(0, 4))
            ctk.CTkButton(
                add_row, text="+ IF", height=28,
                fg_color=CARD, hover_color=LINE, text_color=BLUE,
                command=lambda p=child_path: self.add_if(p),
            ).pack(side="left")

    def add_action(self, path) -> None:
        if not self.current_rule():
            messagebox.showinfo("未有 Flow", "請先建立 Flow。")
            return
        dialog = ActionDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.sequence_at(path).append(dialog.result)
            self.render_program()
            self.save_current(silent=True)

    def add_if(self, path) -> None:
        if not self.current_rule():
            messagebox.showinfo("未有 Flow", "請先建立 Flow。")
            return
        dialog = ConditionDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.sequence_at(path).append({
                "type": "if", "condition": dialog.result,
                "then": [], "else": [],
            })
            self.render_program()
            self.save_current(silent=True)

    def edit_action(self, path, index) -> None:
        sequence = self.sequence_at(path)
        dialog = ActionDialog(self, sequence[index])
        self.wait_window(dialog)
        if dialog.result:
            sequence[index] = dialog.result
            self.render_program()
            self.save_current(silent=True)

    def edit_condition(self, path, index) -> None:
        sequence = self.sequence_at(path)
        dialog = ConditionDialog(self, sequence[index].get("condition"))
        self.wait_window(dialog)
        if dialog.result:
            sequence[index]["condition"] = dialog.result
            self.render_program()
            self.save_current(silent=True)

    def remove_node(self, path, index) -> None:
        self.sequence_at(path).pop(index)
        self.render_program()
        self.save_current(silent=True)

    def move_node(self, path, index, offset) -> None:
        sequence = self.sequence_at(path)
        target = index + offset
        if 0 <= target < len(sequence):
            sequence[index], sequence[target] = sequence[target], sequence[index]
            self.render_program()
            self.save_current(silent=True)

    def validate_condition(self, condition: dict[str, Any]) -> str | None:
        if condition.get("type") == "image":
            value = condition.get("template", "")
            path = Path(value)
            if not path.is_absolute():
                path = ROOT / path
            if not value or not path.exists():
                return f"圖片條件檔案不存在：{value}"
        if condition.get("type") == "image_any":
            values = condition.get("templates", [])
            if not values:
                return "Image Group 未有圖片"
            for value in values:
                path = Path(value)
                if not path.is_absolute():
                    path = ROOT / path
                if not path.exists():
                    return f"Image Group 圖片不存在：{value}"
        if condition.get("type") == "group":
            for child in condition.get("conditions", []):
                problem = self.validate_condition(child)
                if problem:
                    return problem
        return None

    def validate_program(self, nodes: list[dict[str, Any]]) -> str | None:
        for node in nodes:
            if node.get("type") == "if":
                problem = self.validate_condition(node.get("condition", {}))
                if problem:
                    return problem
                problem = self.validate_program(node.get("then", []))
                if problem:
                    return problem
                problem = self.validate_program(node.get("else", []))
                if problem:
                    return problem
        return None

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.save_current():
            return
        active = [r for r in self.config_data["rules"] if r.get("enabled", True)]
        if not active:
            messagebox.showerror("未能啟動", "最少要啟用一個 Flow。")
            return
        for rule in active:
            problem = self.validate_program(rule.get("program", []))
            if problem:
                messagebox.showerror("未能啟動", f"Flow「{rule['name']}」：{problem}")
                return
        self.stop_event = threading.Event()
        self.worker = threading.Thread(
            target=self.run_worker, daemon=True, name="sightflow-engine",
        )
        self.worker.start()
        self.status_label.configure(text="● RUNNING", text_color=ACCENT)
        self.start_button.configure(state="disabled")

    def run_worker(self) -> None:
        try:
            run_detector(CONFIG_PATH, stop_event=self.stop_event, log=self.log)
        except Exception as exc:
            self.log(f"ERROR: {exc}")
        finally:
            self.after(0, self.worker_finished)

    def worker_finished(self) -> None:
        self.status_label.configure(text="● STOPPED", text_color=MUTED)
        self.start_button.configure(state="normal")
        self.f10_stop_latched = False

    def emergency_key_down(self, key) -> None:
        if (
            key == keyboard.Key.f10
            and self.worker
            and self.worker.is_alive()
            and not self.f10_stop_latched
        ):
            self.f10_stop_latched = True
            if self.stop_event:
                self.stop_event.set()
            self.log("F10 緊急停止：正在停止所有 Flow。")
            self.after(
                0,
                lambda: self.status_label.configure(
                    text="● F10 STOPPING", text_color=RED,
                ),
            )

    def emergency_key_up(self, key) -> None:
        if key == keyboard.Key.f10:
            self.f10_stop_latched = False

    def open_recorder(self) -> None:
        from macro_recorder_gui import MacroRecorderWindow

        if (
            self.recorder_window is not None
            and self.recorder_window.winfo_exists()
        ):
            self.recorder_window.deiconify()
            self.recorder_window.lift()
            self.recorder_window.focus_force()
            return
        self.recorder_window = MacroRecorderWindow(
            self,
            on_saved=lambda path: self.log(
                f"Recorder saved：{path.name}"
            ),
        )

    def publish_flows(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showerror(
                "Publish Flow",
                "請先停止執行中的 Flow。",
                parent=self,
            )
            return
        if not self.save_current():
            return
        if not (ROOT / ".git").exists():
            messagebox.showerror(
                "Publish Flow",
                "目前資料夾不是 Git repository。",
                parent=self,
            )
            return
        self.publish_button.configure(state="disabled", text="PUBLISHING...")

        def work():
            try:
                manifest = publish_bundle_to_git(ROOT, log=self.log)
                self.log(f"Publish complete: {manifest}")
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Publish Flow",
                        "最新 Flow 已推送到 GitHub。",
                        parent=self,
                    ),
                )
            except Exception as exc:
                self.log(f"Publish failed: {exc}")
                self.after(
                    0,
                    lambda error=str(exc): messagebox.showerror(
                        "Publish Flow",
                        error,
                        parent=self,
                    ),
                )
            finally:
                self.after(
                    0,
                    lambda: self.publish_button.configure(
                        state="normal", text="PUBLISH"
                    ),
                )

        threading.Thread(
            target=work,
            daemon=True,
            name="flow-publisher",
        ).start()

    def stop(self) -> None:
        if self.stop_event:
            self.stop_event.set()
            self.status_label.configure(text="● STOPPING", text_color=ORANGE)

    def log(self, message: str) -> None:
        def append():
            self.log_box.insert("end", f"> {message}\n")
            self.log_box.see("end")
        if threading.current_thread() is threading.main_thread():
            append()
        else:
            self.after(0, append)

    def on_close(self) -> None:
        self.stop()
        self.emergency_listener.stop()
        self.save_current(silent=True)
        self.destroy()


if __name__ == "__main__":
    make_dpi_aware()
    FlowApp().mainloop()
