"""Simplified JKWorld Player for selecting and running published flows."""

from __future__ import annotations

import copy
import threading

import customtkinter as ctk
from pynput import keyboard

from app_paths import APP_ROOT
from app_updater import check_and_prepare_app_update, installed_app_version
from auto_dismiss import AutoDismissController
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


def enabled_rules(config: dict) -> list[dict]:
    return [
        rule
        for rule in config.get("rules", [])
        if rule.get("enabled", True)
    ]


def flow_name(rule: dict, index: int | None = None) -> str:
    name = str(rule.get("name") or "").strip()
    if name:
        return name
    if index is None:
        return "Untitled Flow"
    return f"Untitled Flow {index + 1}"


def selected_rules(config: dict, selected_indexes: set[int]) -> list[dict]:
    return [
        rule
        for index, rule in enumerate(enabled_rules(config))
        if index in selected_indexes
    ]


class PlayerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("JKWorld NoBrain")
        self.geometry("720x620")
        self.minsize(620, 520)
        self.configure(fg_color=BG)
        self.worker: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.config_data: dict = {}
        self.enabled_flow_rules: list[dict] = []
        self.flow_names: list[str] = []
        self.flow_checkboxes: list[ctk.CTkCheckBox] = []
        self.selected_flow_indexes: set[int] = set()
        self.auto_dismiss = AutoDismissController(log=self.log)
        self.auto_dismiss_enabled = ctk.BooleanVar(value=False)
        self.auto_dismiss_key = ctk.StringVar(value="esc")
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
            text="JKWorld NoBrain",
            font=("Bahnschrift", 27, "bold"),
            text_color=ACCENT,
        ).pack(side="left")
        self.version_label = ctk.CTkLabel(
            header,
            text=self.version_text(),
            text_color=MUTED,
        )
        self.version_label.pack(side="right")

        card = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=8)
        card.pack(fill="x", padx=28, pady=8)
        self.flow_summary = ctk.CTkLabel(
            card,
            text="Loading flows...",
            text_color=TEXT,
            font=("Microsoft JhengHei UI", 15, "bold"),
        )
        self.flow_summary.pack(anchor="w", padx=22, pady=(20, 8))

        list_header = ctk.CTkFrame(card, fg_color="transparent")
        list_header.pack(fill="x", padx=22, pady=(0, 8))
        ctk.CTkLabel(
            list_header,
            text="Available flows",
            text_color=MUTED,
            font=("Bahnschrift", 12, "bold"),
        ).pack(side="left")
        ctk.CTkButton(
            list_header,
            text="ALL",
            command=self.select_all_flows,
            fg_color=CARD,
            hover_color="#2C3439",
            text_color=TEXT,
            width=58,
            height=28,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            list_header,
            text="CLEAR",
            command=self.clear_flow_selection,
            fg_color=CARD,
            hover_color="#2C3439",
            text_color=TEXT,
            width=68,
            height=28,
        ).pack(side="right")

        self.flow_list = ctk.CTkScrollableFrame(
            card,
            fg_color="#111619",
            corner_radius=8,
            height=150,
        )
        self.flow_list.pack(fill="x", padx=22, pady=(0, 14))

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(fill="x", padx=22, pady=(0, 20))
        self.start_button = ctk.CTkButton(
            controls,
            text="START SELECTED",
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
            text="STOPPED | F10 emergency stop",
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
            corner_radius=8,
        )
        self.log_box.pack(fill="both", expand=True, padx=28, pady=(8, 24))

    def reload_flows(self) -> None:
        previous_names = {
            self.flow_names[index]
            for index in self.selected_flow_indexes
            if index < len(self.flow_names)
        }
        try:
            self.config_data = load_config(CONFIG_PATH)
        except Exception as exc:
            self.config_data = {"rules": []}
            self.log(f"Cannot load Flow: {exc}")

        self.enabled_flow_rules = enabled_rules(self.config_data)
        self.flow_names = [
            flow_name(rule, index)
            for index, rule in enumerate(self.enabled_flow_rules)
        ]
        if previous_names:
            self.selected_flow_indexes = {
                index
                for index, name in enumerate(self.flow_names)
                if name in previous_names
            }
        else:
            self.selected_flow_indexes = set(range(len(self.flow_names)))
        if not self.selected_flow_indexes and self.flow_names:
            self.selected_flow_indexes = set(range(len(self.flow_names)))

        self.render_flow_list()
        self.refresh_flow_summary()

    def render_flow_list(self) -> None:
        for widget in self.flow_list.winfo_children():
            widget.destroy()
        self.flow_checkboxes = []

        if not self.flow_names:
            ctk.CTkLabel(
                self.flow_list,
                text="No enabled flows found.",
                text_color=MUTED,
                anchor="w",
            ).pack(fill="x", padx=10, pady=10)
            return

        for index, name in enumerate(self.flow_names):
            checkbox = ctk.CTkCheckBox(
                self.flow_list,
                text=name,
                command=lambda idx=index: self.toggle_flow(idx),
                fg_color=ACCENT,
                hover_color="#9ED438",
                checkmark_color="#111510",
                text_color=TEXT,
                border_color="#52605A",
            )
            checkbox.pack(fill="x", padx=10, pady=5)
            if index in self.selected_flow_indexes:
                checkbox.select()
            else:
                checkbox.deselect()
            self.flow_checkboxes.append(checkbox)

    def refresh_flow_summary(self) -> None:
        if self.flow_names:
            selected_count = len(self.selected_flow_indexes)
            self.flow_summary.configure(
                text=f"{selected_count}/{len(self.flow_names)} flows selected"
            )
            return
        self.flow_summary.configure(text="No enabled flows")

    def version_text(self) -> str:
        return (
            f"App {installed_app_version(APP_ROOT)} | "
            f"Flow {installed_flow_version(APP_ROOT)}"
        )

    def toggle_flow(self, index: int) -> None:
        if index in self.selected_flow_indexes:
            self.selected_flow_indexes.remove(index)
        else:
            self.selected_flow_indexes.add(index)
        self.refresh_flow_summary()

    def select_all_flows(self) -> None:
        self.selected_flow_indexes = set(range(len(self.flow_names)))
        for checkbox in self.flow_checkboxes:
            checkbox.select()
        self.refresh_flow_summary()

    def clear_flow_selection(self) -> None:
        self.selected_flow_indexes.clear()
        for checkbox in self.flow_checkboxes:
            checkbox.deselect()
        self.refresh_flow_summary()

    def check_updates(self) -> None:
        if self.worker and self.worker.is_alive():
            self.log("Stop the running flows before checking for updates.")
            return
        self.update_button.configure(state="disabled", text="CHECKING...")

        def work():
            try:
                app_result = check_and_prepare_app_update(APP_ROOT, self.log)
                self.log(app_result.message)
                if app_result.restart_required:
                    self.after(
                        0,
                        lambda: self.update_button.configure(
                            state="disabled", text="RESTARTING..."
                        ),
                    )
                    self.after(500, self.destroy)
                    return
                result = check_and_apply_updates(APP_ROOT, self.log)
                self.log(result.message)
                self.after(0, self.reload_flows)
                self.after(
                    0,
                    lambda: self.version_label.configure(
                        text=self.version_text()
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
        rules = selected_rules(self.config_data, self.selected_flow_indexes)
        if not rules:
            self.log("Select at least one flow before starting.")
            return

        runtime = copy.deepcopy(self.config_data)
        runtime["rules"] = rules
        save_config(RUNTIME_CONFIG, runtime)
        self.stop_event = threading.Event()
        self.worker = threading.Thread(
            target=self.run_worker,
            daemon=True,
            name="jkworld-player-engine",
        )
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.status_label.configure(
            text=f"RUNNING | {len(rules)} FLOWS",
            text_color=ACCENT,
        )

    def run_worker(self) -> None:
        try:
            run_detector(RUNTIME_CONFIG, stop_event=self.stop_event, log=self.log)
        except Exception as exc:
            self.log(f"ERROR: {exc}")
        finally:
            self.after(0, self.worker_finished)

    def worker_finished(self) -> None:
        self._stop_auto_dismiss()
        self.start_button.configure(state="normal")
        self.status_label.configure(
            text="STOPPED | F10 emergency stop",
            text_color=MUTED,
        )
        self.f10_latched = False

    def stop(self) -> None:
        if self.stop_event:
            self.stop_event.set()
            self._stop_auto_dismiss()
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
        self._stop_auto_dismiss()
        self.listener.stop()
        RUNTIME_CONFIG.unlink(missing_ok=True)
        self.destroy()

    def _stop_auto_dismiss(self) -> None:
        controller = self.__dict__.get("auto_dismiss")
        if controller is not None:
            controller.stop()


if __name__ == "__main__":
    make_dpi_aware()
    PlayerApp().mainloop()
