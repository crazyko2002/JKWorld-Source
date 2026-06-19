"""Persistent, machine-readable output for OCR-only recognition."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from app_paths import APP_ROOT

ROOT = APP_ROOT
DEFAULT_OUTPUT_DIR = ROOT / "logs"
_WRITE_LOCK = threading.Lock()


def export_ocr_result(
    *,
    result: str,
    elapsed_seconds: float,
    match_score: float | None = None,
    capture_region: tuple[int, int, int, int] | list[int] | None = None,
    source: str = "ocr_read",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    if len(result) != 2 or not result.isdigit():
        raise ValueError("OCR result 必須係兩位數字")

    directory = Path(output_dir)
    if not directory.is_absolute():
        directory = ROOT / directory
    record: dict[str, Any] = {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="milliseconds"
        ),
        "status": "ok",
        "source": source,
        "result": result,
        "elapsed_ms": round(float(elapsed_seconds) * 1000, 3),
        "match_score": (
            round(float(match_score), 6)
            if match_score is not None else None
        ),
        "capture_region": (
            [int(value) for value in capture_region]
            if capture_region is not None else None
        ),
    }

    encoded = json.dumps(
        record, ensure_ascii=False, separators=(",", ":")
    )
    latest_encoded = json.dumps(
        record, ensure_ascii=False, indent=2
    ) + "\n"
    with _WRITE_LOCK:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "ocr_results.jsonl").open(
            "a", encoding="utf-8", newline="\n"
        ) as history:
            history.write(encoded + "\n")
            history.flush()

        temporary = directory / "ocr_latest.json.tmp"
        temporary.write_text(latest_encoded, encoding="utf-8")
        temporary.replace(directory / "ocr_latest.json")
    return record


def load_latest_ocr_result(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> str:
    directory = Path(output_dir)
    if not directory.is_absolute():
        directory = ROOT / directory
    path = directory / "ocr_latest.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到 OCR log：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = str(payload.get("result", "")).strip()
    if len(result) != 2 or not result.isdigit():
        raise ValueError(f"OCR log result 無效：{result!r}")
    return result
