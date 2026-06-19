"""JK世界 Studio without publishing controls."""

import os

os.environ["JKWORLD_ENABLE_PUBLISH"] = "0"

from screen_detector_prototype import make_dpi_aware  # noqa: E402
from screen_flow_gui import FlowApp  # noqa: E402


if __name__ == "__main__":
    make_dpi_aware()
    FlowApp().mainloop()

