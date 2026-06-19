"""Simplified SightFlow Player for running published flows."""

from __future__ import annotations

import copy
import threading
from pathlib import Path

import customtkinter as ctk
from pynput import keyboard

from app_paths import APP_ROOT
from flow_distribution import check_and_apply_updates, installed_flow_version
from screen_detector_prototype import load_config, make_dpi_aware, run_detector, save_config


CONFIG_PATH = APP_ROOT / "config.yaml"
RUNTIME_CONFIG = APP_ROOT / ".player_runtime.yaml"
BG = "#0E1113"
PANEL = "#171B1E"
CARD = "#20262A"
TEXT = "#E7EEE9"
MUTED = "#8D9992"
ACCENT = "#B7F34A"
ORANGE = "#FF9F43"
RED = "#FF5D62"


class PlayerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SightFlow Player")
        self.geometry("680x520")
        self.minsize(600, 460)
        self.configure(fg_color=BG)
        self.worker: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.config_data: dict = {}
        self.flow_names: list[str] = []
        self.f10_latched = False
        self.listener = keyboard.Listener(
            on_press=self.emergency_key_down,
            on_release=self.emergency_key_up,
        )
        self.listener.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        self.reload_flows()
        self.after(200, self.check_updates)

    def build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(24, 12))
        ctk.CTkLabel(
            header,
            text="SIGHTFLOW PLAYER",
            font=("Bahnschrift", 27, "bold"),
            text_color=ACCENT,
        ).pack(side="left")
        self.version_label = ctk.CTkLabel(
            header,
            text=f"Flow {installed_flow_version()}",
            text_color=MUTED,
        )
        self.version_label.pack(side="right")

        card = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14)
        card.pack(fill="x", padx=28, pady=8)
        ctk.CTkLabel(
            card,
            text="選擇要執行的 Flow",
            text_color=TEXT,
            font=("Microsoft JhengHei UI", 15, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 8))
        self.flow_var = ctk.StringVar(value="未有 Flow")
        self.flow_menu = ctk.CTkOptionMenu(
            card,
            variable=self.flow_var,
            values=["未有 Flow"],
            fg_color=CARD,
            button_color=ORANGE,
            text_color=TEXT,
            height=42,
        )
        self.flow_menu.pack(fill="x", padx=22, pady=(0, 18))
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=22, pady=(0, 20))
        self.start_button = ctk.CTkButton(
            controls,
            text="START",
            command=self.start_selected,
            fg_color=ACCENT,
            hover_color="#9ED438",
            text_color="#111510",
            height=42,
        )
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(
            controls,
            text="STOP",
            command=self.stop,
            fg_color=CARD,
            hover_color=RED,
            text_color=TEXT,
            height=42,
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.pack(fill="x", padx=28, pady=(10, 4))
        self.status_label = ctk.CTkLabel(
            status_row,
            text="STOPPED · F10 emergency stop",
            text_color=MUTED,
            font=("Bahnschrift", 12, "bold"),
        )
        self.status_label.pack(side="left")
        self.update_button = ctk.CTkButton(
            status_row,
            text="CHECK UPDATE",
            width=140,
            command=self.check_updates,
            fg_color=CARD,
            hover_color=ORANGE,
            text_color=TEXT,
        )
        self.update_button.pack(side="right")

        self.log_box = ctk.CTkTextbox(
            self,
            fg_color="#090C0E",
            border_width=1,
            border_color="#30383D",
            text_color="#B8C4BD",
            font=("Cascadia Mono", 11),
            corner_radius=10,
        )
        self.log_box.pack(fill="both", expand=True, padx=28, pady=(8, 24))

    def reload_flows(self) -> None:
        try:
            self.config_data = load_config(CONFIG_PATH)
        except Exception as exc:
            self.config_data = {"rules": []}
            self.log(f"Cannot load Flow: {exc}")
        enabled = [
            rule for rule in self.config_data.get("rules", [])
            if rule.get("enabled", True)
        ]
        self.flow_names = [str(rule.get("name", "Untitled Flow")) for rule in enabled]
        values = self.flow_names or ["未有 Flow"]
        self.flow_menu.configure(values=values)
        if self.flow_var.get() not in values:
            self.flow_var.set(values[0])

    def check_updates(self) -> None:
        if self.worker and self.worker.is_alive():
            self.log("請先停止 Flow 才更新。")
            return
        self.update_button.configure(state="disabled", text="CHECKING...")

        def work():
            try:
                result = check_and_apply_updates(APP_ROOT, self.log)
                self.log(result.message)
                self.after(0, self.reload_flows)
                self.after(
                    0,
                    lambda: self.version_label.configure(
                        text=f"Flow {result.version}"
                    ),
                )
            except Exception as exc:
                self.log(f"Update unavailable: {exc}")
            finally:
                self.after(
                    0,
                    lambda: self.update_button.configure(
                        state="normal", text="CHECK UPDATE"
                    ),
                )

        threading.Thread(target=work, daemon=True, name="flow-updater").start()

    def start_selected(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        selected = self.flow_var.get()
        rules = [
            copy.deepcopy(rule)
            for rule in self.config_data.get("rules", [])
            if str(rule.get("name", "")) == selected
        ]
        if not rules:
            self.log("未有可執行 Flow。")
            return
        runtime = copy.deepcopy(self.config_data)
        runtime["rules"] = rules
        save_config(RUNTIME_CONFIG, runtime)
        self.stop_event = threading.Event()
        self.worker = threading.Thread(
            target=self.run_worker,
            daemon=True,
            name="sightflow-player-engine",
        )
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.status_label.configure(text=f"RUNNING · {selected}", text_color=ACCENT)

    def run_worker(self) -> None:
        try:
            run_detector(RUNTIME_CONFIG, stop_event=self.stop_event, log=self.log)
        except Exception as exc:
            self.log(f"ERROR: {exc}")
        finally:
            self.after(0, self.worker_finished)

    def worker_finished(self) -> None:
        self.start_button.configure(state="normal")
        self.status_label.configure(
            text="STOPPED · F10 emergency stop",
            text_color=MUTED,
        )
        self.f10_latched = False

    def stop(self) -> None:
        if self.stop_event:
            self.stop_event.set()
            self.status_label.configure(text="STOPPING", text_color=ORANGE)

    def emergency_key_down(self, key) -> None:
        if (
            key == keyboard.Key.f10
            and self.worker
            and self.worker.is_alive()
            and not self.f10_latched
        ):
            self.f10_latched = True
            self.stop()
            self.log("F10 emergency stop requested.")

    def emergency_key_up(self, key) -> None:
        if key == keyboard.Key.f10:
            self.f10_latched = False

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
        self.listener.stop()
        RUNTIME_CONFIG.unlink(missing_ok=True)
        self.destroy()


if __name__ == "__main__":
    make_dpi_aware()
    PlayerApp().mainloop()
