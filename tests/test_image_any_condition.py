"""Image Group succeeds when at least one template is detected."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_detector_prototype as detector
from screen_detector_prototype import evaluate_condition, image_paths_for_rule


def patterned(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(12, 14), dtype=np.uint8)


def main() -> None:
    first = patterned(1)
    second = patterned(2)
    third = patterned(3)
    frame = np.zeros((80, 100), dtype=np.uint8)
    frame[30:42, 50:64] = second
    frame_bgr = np.repeat(frame[:, :, None], 3, axis=2)
    condition = {
        "type": "image_any",
        "threshold": 0.95,
        "templates": ["one.png", "two.png", "three.png"],
    }
    context = {}
    matched = evaluate_condition(
        condition,
        frame,
        frame_bgr,
        {"one.png": first, "two.png": second, "three.png": third},
        10,
        20,
        0,
        context,
    )
    assert matched is True
    assert context["matched_image"] == "two.png"
    assert context["match_center"] == (67, 56)
    assert context["score"] > 0.99

    rule = {
        "program": [{
            "type": "if",
            "condition": condition,
            "then": [],
            "else": [],
        }]
    }
    assert image_paths_for_rule(rule) == {
        "one.png", "two.png", "three.png",
    }

    calls = 0
    original_find_template = detector.find_template

    def counted_find_template(frame_gray, template):
        nonlocal calls
        calls += 1
        return original_find_template(frame_gray, template)

    detector.find_template = counted_find_template
    try:
        cache_context = {}
        image_condition = {
            "type": "image",
            "template": "two.png",
            "threshold": 0.95,
        }
        assert evaluate_condition(
            image_condition,
            frame,
            frame_bgr,
            {"two.png": second},
            10,
            20,
            0,
            cache_context,
        )
        assert evaluate_condition(
            image_condition,
            frame,
            frame_bgr,
            {"two.png": second},
            10,
            20,
            0,
            cache_context,
        )
    finally:
        detector.find_template = original_find_template
    assert calls == 1
    print("Image Group any-match condition OK")


if __name__ == "__main__":
    main()
