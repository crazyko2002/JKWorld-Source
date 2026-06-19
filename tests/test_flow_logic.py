"""Regression tests for nested IF / ELSE flow execution."""

from pathlib import Path
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen_detector_prototype import evaluate_condition, execute_program


def main() -> None:
    gray = np.zeros((40, 40), dtype=np.uint8)
    bgr = np.zeros((40, 40, 3), dtype=np.uint8)
    bgr[10, 12] = [30, 20, 10]  # BGR -> RGB(10, 20, 30)
    context = {}
    started = time.monotonic() - 10

    condition = {
        "type": "group",
        "mode": "all",
        "conditions": [
            {"type": "elapsed", "operator": ">=", "seconds": 5},
            {
                "type": "pixel", "operator": "matches",
                "x": 12, "y": 10, "r": 10, "g": 20, "b": 30,
                "tolerance": 0,
            },
        ],
    }
    assert evaluate_condition(
        condition, gray, bgr, {}, 0, 0, started, context,
    )

    logs: list[str] = []
    program = [{
        "type": "if",
        "condition": condition,
        "then": [{"type": "press", "key": "enter"}],
        "else": [{
            "type": "if",
            "condition": {"type": "always"},
            "then": [{"type": "press", "key": "escape"}],
            "else": [],
        }],
    }]
    execute_program(
        program, gray, bgr, {}, 0, 0, started, True,
        threading.Event(), logs.append,
    )
    assert any("True" in line for line in logs)
    assert any("enter" in line for line in logs)
    assert not any("escape" in line for line in logs)
    print("Nested IF / ELSE logic OK")


if __name__ == "__main__":
    main()
