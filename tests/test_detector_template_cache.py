"""Detector reuses template matching results within the same frame."""

from pathlib import Path
import sys
import tempfile

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_detector_prototype as detector  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        template_path = root / "target.png"
        template_path.write_bytes(b"fake")
        config_path = root / "config.yaml"
        config_path.write_text(yaml.safe_dump({
            "dry_run": True,
            "poll_interval_ms": 50,
            "rules": [
                {
                    "name": "first",
                    "enabled": True,
                    "template": str(template_path),
                    "threshold": 0.5,
                    "consecutive_hits": 1,
                    "actions": [{"type": "wait", "seconds": 0}],
                },
                {
                    "name": "second",
                    "enabled": True,
                    "template": str(template_path),
                    "threshold": 0.5,
                    "consecutive_hits": 1,
                    "actions": [{"type": "wait", "seconds": 0}],
                },
            ],
        }), encoding="utf-8")

        original_load_templates = detector.load_templates
        original_monitor_from_config = detector.monitor_from_config
        original_find_template = detector.find_template
        original_mss = detector.mss.mss
        calls = 0

        class FakeMss:
            monitors = {1: {"left": 0, "top": 0, "width": 32, "height": 32}}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def grab(self, _monitor):
                return np.zeros((32, 32, 4), dtype=np.uint8)

        def counted_find_template(frame_gray, template):
            nonlocal calls
            calls += 1
            return 1.0, (4, 5)

        detector.load_templates = lambda _rules: {str(template_path): np.ones((4, 4), dtype=np.uint8)}
        detector.monitor_from_config = lambda _sct, _region: (
            {"left": 0, "top": 0, "width": 32, "height": 32},
            0,
            0,
        )
        detector.find_template = counted_find_template
        detector.mss.mss = FakeMss
        try:
            detector.run_detector(config_path, once=True, log=lambda _message: None)
        finally:
            detector.load_templates = original_load_templates
            detector.monitor_from_config = original_monitor_from_config
            detector.find_template = original_find_template
            detector.mss.mss = original_mss

        assert calls == 1, calls
    print("Detector template cache OK")


if __name__ == "__main__":
    main()
