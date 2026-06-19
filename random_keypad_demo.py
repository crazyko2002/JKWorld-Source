"""Standalone user-owned random keypad OCR/click demonstration."""

from __future__ import annotations

from dataclasses import dataclass
import random
import threading
import tkinter as tk

import cv2
import numpy as np
from PIL import Image, ImageTk


WINDOW_TITLE = "JK世界 Random Keypad Demo"
CANVAS_WIDTH = 420
CANVAS_HEIGHT = 500
QUESTION_REGION = (32, 112, 148, 72)


@dataclass(frozen=True)
class DemoChallenge:
    answer: str
    layout: tuple[str, ...]


def generate_challenge(rng: random.Random | None = None) -> DemoChallenge:
    rng = rng or random.SystemRandom()
    digits = list("0123456789")
    rng.shuffle(digits)
    answer = f"{rng.randrange(10)}{rng.randrange(10)}"
    return DemoChallenge(answer=answer, layout=tuple(digits))


def render_challenge(
    challenge: DemoChallenge,
) -> tuple[np.ndarray, dict[str, object]]:
    rng = np.random.default_rng(sum(ord(x) for x in challenge.answer))
    image = np.full(
        (CANVAS_HEIGHT, CANVAS_WIDTH, 3), (226, 151, 62), dtype=np.uint8
    )
    cv2.rectangle(image, (0, 0), (419, 72), (235, 135, 45), -1)
    cv2.putText(
        image, "RANDOM KEYPAD LAB", (22, 45),
        cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image, "Read this:", (32, 102),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
        cv2.LINE_AA,
    )

    qx, qy, qw, qh = QUESTION_REGION
    question = np.empty((qh, qw, 3), dtype=np.uint8)
    base = rng.integers(145, 205, size=(qh, qw), dtype=np.uint8)
    question[:, :, 0] = np.clip(base + 35, 0, 255)
    question[:, :, 1] = np.clip(base - 18, 0, 255)
    question[:, :, 2] = np.clip(base - 35, 0, 255)
    for _ in range(260):
        x = int(rng.integers(0, qw))
        y = int(rng.integers(0, qh))
        color = int(rng.integers(80, 220))
        question[y, x] = (color, color, color)
    cv2.putText(
        question, challenge.answer, (33, 53),
        cv2.FONT_HERSHEY_COMPLEX, 1.45, (35, 38, 40), 2,
        cv2.LINE_AA,
    )
    image[qy:qy + qh, qx:qx + qw] = question

    button_boxes: list[tuple[int, int, int, int]] = []
    start_x, start_y = 218, 92
    button_w, button_h = 54, 58
    gap_x, gap_y = 62, 70
    for index, digit in enumerate(challenge.layout):
        row, column = divmod(index, 3)
        x = start_x + column * gap_x
        y = start_y + row * gap_y
        button_boxes.append((x, y, button_w, button_h))
        cv2.rectangle(
            image, (x - 2, y - 2),
            (x + button_w + 2, y + button_h + 2),
            (130, 77, 20), -1,
        )
        cv2.rectangle(
            image, (x, y), (x + button_w, y + button_h),
            (244, 244, 244), -1,
        )
        cv2.putText(
            image, digit, (x + 13, y + 43),
            cv2.FONT_HERSHEY_SIMPLEX, 1.35, (58, 58, 58), 3,
            cv2.LINE_AA,
        )
    cv2.putText(
        image, "Digits reshuffle after every success.", (30, 432),
        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1,
        cv2.LINE_AA,
    )
    return image, {
        "question": QUESTION_REGION,
        "buttons": button_boxes,
    }


class RandomKeypadDemo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.resizable(False, False)
        self.challenge = generate_challenge()
        self.entered = ""
        self.regions: dict[str, object] = {}

        self.canvas = tk.Canvas(
            self,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT,
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        controls = tk.Frame(self, bg="#156bc2")
        controls.pack(fill="x")
        self.status = tk.Label(
            controls,
            text="Ready",
            fg="white",
            bg="#156bc2",
            font=("Segoe UI", 11, "bold"),
        )
        self.status.pack(side="left", padx=12, pady=12)
        tk.Button(
            controls, text="NEW", command=self.new_challenge,
            width=9,
        ).pack(side="right", padx=6, pady=8)
        tk.Button(
            controls, text="AUTO SOLVE", command=self.auto_solve,
            width=12,
        ).pack(side="right", padx=6, pady=8)
        self.render()

    def render(self) -> None:
        image_bgr, self.regions = render_challenge(self.challenge)
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(image_rgb))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

    def new_challenge(self) -> None:
        self.challenge = generate_challenge()
        self.entered = ""
        self.status.configure(text="Ready", fg="white")
        self.render()

    def on_canvas_click(self, event) -> None:
        for digit, (x, y, width, height) in zip(
            self.challenge.layout, self.regions["buttons"]
        ):
            if x <= event.x <= x + width and y <= event.y <= y + height:
                self.entered += digit
                self.status.configure(text=f"Entered: {self.entered}")
                if len(self.entered) == 2:
                    if self.entered == self.challenge.answer:
                        self.status.configure(text="SUCCESS", fg="#63ff7d")
                        self.after(700, self.new_challenge)
                    else:
                        self.status.configure(
                            text=f"WRONG: {self.entered}", fg="#ff7777"
                        )
                        self.entered = ""
                return

    def auto_solve(self) -> None:
        self.status.configure(text="Scanning...", fg="#ffe667")

        def worker():
            try:
                from random_keypad_solver import solve_demo
                report = solve_demo()
                self.after(
                    0,
                    lambda: self.status.configure(
                        text=(
                            f"Solved {report.answer} "
                            f"in {report.elapsed_seconds * 1000:.0f}ms"
                        ),
                        fg="#63ff7d",
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc: self.status.configure(
                        text=f"ERROR: {error}", fg="#ff7777"
                    ),
                )

        self.after(
            250,
            lambda: threading.Thread(
                target=worker, daemon=True, name="demo-auto-solver"
            ).start(),
        )


if __name__ == "__main__":
    RandomKeypadDemo().mainloop()
