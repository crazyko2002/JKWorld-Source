"""OCR results are exported as append-only JSONL plus latest JSON."""

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_result_log import export_ocr_result  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        record = export_ocr_result(
            result="62",
            elapsed_seconds=0.073,
            match_score=0.94,
            capture_region=(10, 20, 477, 314),
            output_dir=output,
        )

        latest = json.loads(
            (output / "ocr_latest.json").read_text(encoding="utf-8")
        )
        history = [
            json.loads(line)
            for line in (
                output / "ocr_results.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]

    assert latest["result"] == "62"
    assert latest["elapsed_ms"] == 73.0
    assert latest["match_score"] == 0.94
    assert latest["capture_region"] == [10, 20, 477, 314]
    assert history == [latest]
    assert record == latest
    print("OCR result JSON log OK")


if __name__ == "__main__":
    main()
