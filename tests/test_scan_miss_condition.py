"""Scan-miss IF condition triggers only after a sustained missing target."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen_detector_prototype import evaluate_condition, image_paths_for_rule


def patterned(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(10, 12), dtype=np.uint8)


def frame_with_template(template: np.ndarray, present: bool) -> np.ndarray:
    frame = np.zeros((60, 70), dtype=np.uint8)
    if present:
        frame[24:34, 31:43] = template
    return frame


def check(condition: dict, frame: np.ndarray, context: dict, now: float) -> bool:
    context["now"] = now
    return evaluate_condition(
        condition,
        frame,
        np.repeat(frame[:, :, None], 3, axis=2),
        {"target.png": TEMPLATE},
        0,
        0,
        0,
        context,
    )


TEMPLATE = patterned(42)


def main() -> None:
    present = frame_with_template(TEMPLATE, True)
    missing = frame_with_template(TEMPLATE, False)
    condition = {
        "type": "scan_miss",
        "seconds": 2,
        "cooldown_seconds": 5,
        "target": {
            "type": "image",
            "operator": "appears",
            "template": "target.png",
            "threshold": 0.99,
        },
    }
    context = {"condition_state": {}}

    assert check(condition, present, context, 0.0) is False
    assert check(condition, missing, context, 10.0) is False
    assert check(condition, missing, context, 11.9) is False
    assert check(condition, missing, context, 12.0) is True
    assert check(condition, missing, context, 13.0) is False
    assert check(condition, missing, context, 17.0) is True

    assert check(condition, present, context, 18.0) is False
    assert check(condition, missing, context, 20.0) is False
    assert check(condition, missing, context, 21.9) is False
    assert check(condition, missing, context, 22.0) is True

    rule = {
        "program": [{
            "type": "if",
            "condition": condition,
            "then": [],
            "else": [],
        }]
    }
    assert image_paths_for_rule(rule) == {"target.png"}
    print("Scan miss condition OK")


if __name__ == "__main__":
    main()
