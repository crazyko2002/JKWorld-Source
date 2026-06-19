"""JK世界 Studio with publishing controls for the owner."""

import os

os.environ["JKWORLD_ENABLE_PUBLISH"] = "1"

from screen_detector_prototype import make_dpi_aware  # noqa: E402
from screen_flow_gui import FlowApp  # noqa: E402


if __name__ == "__main__":
    make_dpi_aware()
    FlowApp().mainloop()

