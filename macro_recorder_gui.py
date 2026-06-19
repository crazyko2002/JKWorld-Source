"""Keyboard recorder window opened from Advanced Flow."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk
from pynput import keyboard

from macro_recorder import (
    analyze_event_balance,
    KeyboardRecorder,
    load_macro_config,
    load_recording,
    replay_macro,
    save_macro_config,
    save_recording,
)
from screen_detector_prototype import ROOT


BG = "#0D1012"
PANEL = "#171B1E"
CARD = "#22282C"
LINE = "#333C40"
TEXT = "#EDF3EF"
MUTED = "#8D9992"
GREEN = "#B7F34A"
RED = "#FF5D62"
ORANGE = "#FF9F43"
BLUE = "#55B8FF"


class MacroRecorderWindow(ctk.CTkToplevel):
    """Recorder child window; Advanced Flow remains the main application."""

    def __init__(
        self,
        master,
        on_saved: Callable[[Path], None] | None = None,
    ):
        super().__init__(master)
        self.on_saved = on_saved
        self.title("JK世界 Recorder")
        self.geometry("760x760")
        self.minsize(680, 650)
        self.configure(fg_color=BG)
        self.transient(master)
        self.config_data = load_macro_config()
        save_macro_config(self.config_data)
        self.recorder = KeyboardRecorder(self.recording_stopped)
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.emergency_listener = keyboard.Listener(on_press=self.emergency_key)
        self.emergency_listener.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.load_values()
        self.after(50, self.lift)

    def build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent", height=72)
        header.pack(fill="x", padx=26, pady=(16, 6))
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="SIGHT", font=("Bahnschrift", 29, "bold"),
            text_color=TEXT,
        ).pack(side="left", pady=13)
        ctk.CTkLabel(
            header, text="REC", font=("Bahnschrift", 29, "bold"),
            text_color=RED,
        ).pack(side="left", pady=13)
        ctk.CTkLabel(
            header, text="KEYBOARD DOWN / UP RECORDER",
            font=("Bahnschrift", 10, "bold"), text_color=MUTED,
        ).pack(side="left", padx=14, pady=(26, 13))
        self.status = ctk.CTkLabel(
            header, text="READY", text_color=MUTED,
            font=("Bahnschrift", 12, "bold"),
        )
        self.status.pack(side="right")

        body = ctk.CTkScrollableFrame(
            self, fg_color=PANEL, corner_radius=14,
            scrollbar_button_color=LINE,
        )
        body.pack(fill="both", expand=True, padx=26, pady=(0, 12))

        self.record_button = ctk.CTkButton(
            body, text="START RECORDING", command=self.begin_recording,
            height=52, fg_color=RED, hover_color="#DB444A",
            text_color="#160809", font=("Bahnschrift", 15, "bold"),
        )
        self.record_button.pack(fill="x", padx=22, pady=(20, 8))
        self.countdown_label = ctk.CTkLabel(
            body, text="READY", height=78, fg_color="#0A0D0F",
            corner_radius=12, text_color=MUTED,
            font=("Bahnschrift", 32, "bold"),
        )
        self.countdown_label.pack(fill="x", padx=22)
        ctk.CTkLabel(
            body,
            text=(
                "3 秒倒數後開始。錄影時 GUI 不會隱藏。\n"
                "F8 = 完成錄影；F9 = 停止播放。"
            ),
            justify="left", text_color=MUTED,
            font=("Microsoft JhengHei UI", 12),
        ).pack(anchor="w", padx=24, pady=(8, 14))

        stats = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        stats.pack(fill="x", padx=22, pady=5)
        self.event_label = ctk.CTkLabel(
            stats, text="0 EVENTS", text_color=GREEN,
            font=("Bahnschrift", 18, "bold"),
        )
        self.event_label.pack(anchor="w", padx=16, pady=(12, 0))
        self.duration_label = ctk.CTkLabel(
            stats, text="Duration 0.00s", text_color=MUTED,
            font=("Cascadia Mono", 11),
        )
        self.duration_label.pack(anchor="w", padx=16, pady=(2, 12))

        form = ctk.CTkFrame(body, fg_color="transparent")
        form.pack(fill="x", padx=22, pady=(10, 4))
        self.recording_name_var = ctk.StringVar(
            value=time.strftime("recording_%Y%m%d_%H%M%S")
        )
        self.repeat_var = ctk.StringVar(value="1")
        self.repeat_delay_var = ctk.StringVar(value="0.5")
        self.speed_percent_var = ctk.StringVar(value="100")
        self.selected_recording_var = ctk.StringVar(value="")
        self.field(form, "Recording name", self.recording_name_var)

        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        left = ctk.CTkFrame(row, fg_color="transparent")
        right = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(0, 5))
        right.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.field(left, "Test repeat count", self.repeat_var)
        self.field(right, "Playback speed %", self.speed_percent_var)
        self.field(form, "Delay between repeats (seconds)", self.repeat_delay_var)

        file_buttons = ctk.CTkFrame(body, fg_color="transparent")
        file_buttons.pack(fill="x", padx=22, pady=7)
        ctk.CTkButton(
            file_buttons, text="SAVE AS FILE",
            command=self.save_recording_file,
            fg_color=BLUE, hover_color="#3595D7", text_color="#07131A",
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            file_buttons, text="LOAD FILE",
            command=self.load_recording_file,
            fg_color=CARD, hover_color=LINE, text_color=TEXT,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ctk.CTkLabel(
            body, textvariable=self.selected_recording_var,
            text_color=MUTED, wraplength=650,
            font=("Cascadia Mono", 9),
        ).pack(anchor="w", padx=24)

        ctk.CTkLabel(
            body, text="EVENT PREVIEW — DOWN / UP",
            text_color=MUTED, font=("Bahnschrift", 10, "bold"),
        ).pack(anchor="w", padx=24, pady=(12, 4))
        self.event_preview = ctk.CTkTextbox(
            body, height=150, fg_color="#0A0D0F",
            border_width=1, border_color=LINE,
            text_color="#B8C4BD", font=("Cascadia Mono", 10),
        )
        self.event_preview.pack(fill="x", padx=22)

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.pack(fill="x", padx=22, pady=(12, 16))
        self.play_button = ctk.CTkButton(
            controls, text="TEST PLAY", command=self.test_play,
            fg_color=CARD, hover_color=LINE, text_color=GREEN,
            border_width=1, border_color=LINE, height=40,
        )
        self.play_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            controls, text="STOP (F9)", command=self.stop_all,
            fg_color=CARD, hover_color=RED, text_color=TEXT, height=40,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.log_box = ctk.CTkTextbox(
            self, height=84, fg_color="#080A0C",
            border_width=1, border_color=LINE, text_color="#B8C4BD",
            font=("Cascadia Mono", 10),
        )
        self.log_box.pack(fill="x", padx=26, pady=(0, 18))
        self.log("Recorder ready.")

    def field(self, parent, label: str, variable: ctk.StringVar) -> None:
        ctk.CTkLabel(
            parent, text=label, text_color=MUTED,
            font=("Microsoft JhengHei UI", 11),
        ).pack(anchor="w", pady=(5, 3))
        ctk.CTkEntry(
            parent, textvariable=variable, fg_color=CARD,
            border_color=LINE, text_color=TEXT, height=32,
        ).pack(fill="x")

    def load_values(self) -> None:
        selected = str(self.config_data.get("selected_recording", ""))
        self.selected_recording_var.set(selected or "No recording selected")
        if selected:
            self.recording_name_var.set(Path(selected).stem)
        self.repeat_var.set(str(self.config_data.get("repeat_count", 1)))
        self.repeat_delay_var.set(
            str(self.config_data.get("repeat_delay", 0.5))
        )
        self.speed_percent_var.set(
            str(self.config_data.get("speed_percent", 100))
        )
        self.update_stats()
        self.update_event_preview()

    def save_settings(self) -> bool:
        try:
            self.config_data["repeat_count"] = max(
                1, int(self.repeat_var.get())
            )
            self.config_data["repeat_delay"] = max(
                0, float(self.repeat_delay_var.get())
            )
            self.config_data["speed_percent"] = max(
                1, float(self.speed_percent_var.get())
            )
            save_macro_config(self.config_data)
            return True
        except ValueError:
            messagebox.showerror(
                "Invalid settings",
                "Repeat, delay and speed must be valid numbers.",
                parent=self,
            )
            return False

    def begin_recording(self) -> None:
        if self.recorder.recording or not self.save_settings():
            return
        self.stop_all()
        self.record_button.configure(state="disabled")
        self.status.configure(text="GET READY", text_color=ORANGE)
        self.record_countdown(3)

    def record_countdown(self, seconds: int) -> None:
        if seconds > 0:
            self.countdown_label.configure(
                text=str(seconds), text_color=ORANGE,
                fg_color="#2A2118",
            )
            self.record_button.configure(text=f"GET READY — {seconds}")
            self.after(1000, lambda: self.record_countdown(seconds - 1))
            return
        self.recorder.start()
        self.countdown_label.configure(
            text="RECORDING", text_color=RED, fg_color="#2B1517",
        )
        self.record_button.configure(text="RECORDING — PRESS F8")
        self.status.configure(text="RECORDING", text_color=RED)
        self.log("Recording started.")

    def recording_stopped(self, events) -> None:
        self.config_data["events"] = events
        diagnostics = self.recorder.diagnostics()
        self.log(
            "Recorder diagnostics: "
            f"raw={diagnostics['raw_callbacks']}, "
            f"saved={diagnostics['recorded_events']}, "
            f"ignored={diagnostics['ignored_callbacks']}, "
            f"repeat-down={diagnostics['duplicate_downs']}, "
            f"orphan-up={diagnostics['orphan_ups']}"
        )
        try:
            output = save_recording(
                self.recording_name_var.get(),
                events,
                recorder_diagnostics=diagnostics,
            )
            relative = str(output.relative_to(ROOT)).replace("\\", "/")
            self.config_data["selected_recording"] = relative
            self.selected_recording_var.set(relative)
            if self.on_saved:
                self.on_saved(output)
        except Exception as exc:
            self.log(f"Recording save failed: {exc}")
        save_macro_config(self.config_data)
        self.after(0, self.finish_recording_ui)

    def finish_recording_ui(self) -> None:
        self.record_button.configure(
            state="normal", text="START RECORDING"
        )
        self.countdown_label.configure(
            text="SAVED", text_color=GREEN, fg_color="#182319",
        )
        self.status.configure(text="RECORDED", text_color=GREEN)
        self.update_stats()
        self.update_event_preview()
        self.log(f"Saved {len(self.config_data.get('events', []))} events.")

    def update_stats(self) -> None:
        events = self.config_data.get("events", [])
        duration = float(events[-1]["time"]) if events else 0
        balance = analyze_event_balance(events)
        state = "BALANCED" if balance["balanced"] else "CHECK KEYS"
        self.event_label.configure(
            text=(
                f"{len(events)} EVENTS — "
                f"DOWN {balance['key_down_count']} — "
                f"UP {balance['key_up_count']}"
            )
        )
        self.duration_label.configure(
            text=f"Duration {duration:.3f}s — {state}"
        )

    def update_event_preview(self) -> None:
        events = self.config_data.get("events", [])
        self.event_preview.delete("1.0", "end")
        for event in events[-120:]:
            action = (
                "DOWN" if event.get("action") in {"down", "key_down"}
                else "UP  "
            )
            self.event_preview.insert(
                "end",
                f"{float(event.get('time', 0)):9.6f}s  "
                f"{action}  {event.get('key', '')}\n",
            )
        self.event_preview.see("end")

    def save_recording_file(self) -> None:
        events = self.config_data.get("events", [])
        if not events:
            messagebox.showerror(
                "Nothing to save", "Record keyboard input first.", parent=self
            )
            return
        try:
            output = save_recording(self.recording_name_var.get(), events)
            relative = str(output.relative_to(ROOT)).replace("\\", "/")
            self.config_data["selected_recording"] = relative
            self.selected_recording_var.set(relative)
            save_macro_config(self.config_data)
            if self.on_saved:
                self.on_saved(output)
            self.log(f"Saved: {relative}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)

    def load_recording_file(self) -> None:
        value = filedialog.askopenfilename(
            parent=self,
            title="Load Recording",
            initialdir=str(ROOT / "recordings"),
            filetypes=[
                ("JK世界 Recording", "*.yaml"),
                ("All files", "*.*"),
            ],
        )
        if not value:
            return
        try:
            payload = load_recording(value)
            path = Path(value)
            try:
                relative = str(
                    path.resolve().relative_to(ROOT.resolve())
                ).replace("\\", "/")
            except ValueError:
                relative = str(path)
            self.config_data["events"] = payload["events"]
            self.config_data["selected_recording"] = relative
            self.recording_name_var.set(path.stem)
            self.selected_recording_var.set(relative)
            save_macro_config(self.config_data)
            self.update_stats()
            self.update_event_preview()
            self.log(f"Loaded: {path.name}")
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc), parent=self)

    def test_play(self) -> None:
        if not self.save_settings():
            return
        events = self.config_data.get("events", [])
        if not events:
            messagebox.showerror(
                "Nothing to play", "Record or load a file first.", parent=self
            )
            return
        self.start_worker(
            lambda: replay_macro(
                events,
                int(self.config_data["repeat_count"]),
                float(self.config_data["repeat_delay"]),
                self.stop_event,
                self.log,
                speed_percent=float(self.config_data["speed_percent"]),
            )
        )

    def start_worker(self, target) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.stop_event = threading.Event()

        def runner() -> None:
            try:
                target()
            except Exception as exc:
                self.log(f"ERROR: {exc}")
            finally:
                self.after(0, self.worker_finished)

        self.worker = threading.Thread(
            target=runner, daemon=True, name="recorder-test-play"
        )
        self.worker.start()
        self.status.configure(text="PLAYING", text_color=GREEN)
        self.play_button.configure(state="disabled")

    def worker_finished(self) -> None:
        self.status.configure(text="READY", text_color=MUTED)
        self.play_button.configure(state="normal")

    def emergency_key(self, key) -> None:
        if key == keyboard.Key.f9:
            self.stop_all()

    def stop_all(self) -> None:
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.after(
                0,
                lambda: self.status.configure(
                    text="STOPPING", text_color=ORANGE
                ),
            )

    def log(self, message: str) -> None:
        def append() -> None:
            self.log_box.insert("end", f"> {message}\n")
            self.log_box.see("end")

        if threading.current_thread() is threading.main_thread():
            append()
        else:
            self.after(0, append)

    def on_close(self) -> None:
        self.stop_all()
        if self.recorder.recording:
            self.recorder.stop()
        self.emergency_listener.stop()
        self.save_settings()
        self.destroy()
