"""Regression test: OpenCV direct file I/O fails in a Unicode workspace on Windows."""

from pathlib import Path
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen_detector_prototype import read_image, write_image


def main() -> None:
    source = np.zeros((24, 32, 3), dtype=np.uint8)
    source[:, :, 1] = 173
    with tempfile.TemporaryDirectory(prefix="圖片測試_") as directory:
        path = Path(directory) / "觸發圖片.png"
        write_image(path, source)
        loaded = read_image(path, cv2.IMREAD_COLOR)
        assert path.exists() and path.stat().st_size > 0
        assert loaded is not None
        assert loaded.shape == source.shape
        assert np.array_equal(loaded, source)
    print("Unicode image read/write OK")


if __name__ == "__main__":
    main()
