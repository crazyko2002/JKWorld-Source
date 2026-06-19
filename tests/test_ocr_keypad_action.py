"""Advanced Flow can auto-solve the game captcha keypad."""

from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ocr_keypad_action as keypad_action
import screen_detector_prototype as engine
from captcha_keypad_solver import CaptchaMatch, CaptchaReadReport


def main() -> None:
    calls: list[tuple[int, int]] = []
    engine_config = {
        "local_ocr": {
            "result_log_dir": "logs",
            "captcha": {
                "template": "templates/captcha_reference.png",
                "threshold": 0.82,
                "click_interval": 0.05,
            },
        }
    }
    match = CaptchaMatch(
        score=0.95,
        left=100,
        top=200,
        width=477,
        height=314,
    )

    original = keypad_action.solve_captcha_match
    original_read = keypad_action.read_captcha_match
    exported = []
    original_export = keypad_action.export_ocr_result
    keypad_action.export_ocr_result = lambda **kwargs: exported.append(
        kwargs
    ) or kwargs
    keypad_action.read_captcha_match = lambda *_args, **_kwargs: (
        CaptchaReadReport(
            answer="42",
            keypad={"4": (10, 20), "2": (30, 40)},
            match=match,
            elapsed_seconds=0.04,
        )
    )
    keypad_action.solve_captcha_match = lambda *_args, **_kwargs: type(
        "Report",
        (),
        {
            "answer": "42",
            "match": match,
            "elapsed_seconds": 0.05,
        },
    )()
    try:
        read_answer = keypad_action.read_ocr_keypad_action(
            {"type": "ocr_keypad", "mode": "captcha"},
            engine_config,
            lambda _: None,
            captcha_match=match,
        )
        assert read_answer == "42"
        assert calls == []
        assert exported[-1]["result"] == "42"
        assert exported[-1]["match_score"] == 0.95
        assert exported[-1]["capture_region"] == (
            100, 200, 477, 314,
        )

        context = {"captcha_match": match}
        engine.run_actions(
            [{"type": "ocr_read"}],
            (0, 0),
            False,
            threading.Event(),
            lambda _: None,
            engine_config=engine_config,
            action_context=context,
        )
        assert context["ocr_text"] == "42"
        assert calls == []

        answer = keypad_action.run_ocr_keypad_action(
            {"type": "ocr_keypad", "mode": "captcha"},
            engine_config,
            lambda x, y: calls.append((x, y)),
            lambda _: None,
            captcha_match=match,
        )
        assert answer == "42"

        fake_backend = type("Backend", (), {
            "click": lambda self, **kwargs: calls.append(
                (kwargs["x"], kwargs["y"])
            ),
        })()
        original_backend = engine.input_backend_for_action
        engine.input_backend_for_action = lambda *_args, **_kwargs: fake_backend
        try:
            engine.run_actions(
                [{"type": "ocr_keypad", "mode": "captcha", "backend": "pyautogui"}],
                (0, 0),
                False,
                threading.Event(),
                lambda _: None,
                engine_config=engine_config,
                action_context={"captcha_match": match},
            )
        finally:
            engine.input_backend_for_action = original_backend
    finally:
        keypad_action.solve_captcha_match = original
        keypad_action.read_captcha_match = original_read
        keypad_action.export_ocr_result = original_export

    logs: list[str] = []
    engine.run_actions(
        [{"type": "ocr_keypad", "mode": "captcha", "backend": "directinput"}],
        (0, 0),
        True,
        threading.Event(),
        logs.append,
        engine_config=engine_config,
        action_context={"captcha_match": match},
    )
    assert any("[測試模式]" in line for line in logs)
    assert "OCR 遊戲驗證碼" in engine.describe_action({
        "type": "ocr_keypad",
        "mode": "captcha",
        "backend": "directinput",
    })
    print("Advanced ocr_keypad captcha action OK")


if __name__ == "__main__":
    main()
