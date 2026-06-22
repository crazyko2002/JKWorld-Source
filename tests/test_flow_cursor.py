"""Program flows advance one top-level step at a time."""

from pathlib import Path
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_detector_prototype as engine


def main() -> None:
    gray = np.zeros((20, 20), dtype=np.uint8)
    bgr = np.zeros((20, 20, 3), dtype=np.uint8)
    bgr[3, 4] = [30, 20, 10]  # BGR -> RGB(10, 20, 30)
    started = time.monotonic()
    context = {"match_center": (0, 0), "condition_state": {}}
    logs: list[str] = []
    stop_event = threading.Event()
    first = {
        "type": "if",
        "condition": {
            "type": "pixel",
            "operator": "matches",
            "x": 4,
            "y": 3,
            "r": 10,
            "g": 20,
            "b": 30,
            "tolerance": 0,
        },
        "then": [{"type": "press", "key": "first"}],
        "else": [],
    }
    second = {"type": "press", "key": "second"}

    assert engine.execute_program_step(
        first, gray, bgr, {}, 0, 0, started, True, stop_event, logs.append, context,
    ) is True
    assert any("first" in line for line in logs)
    assert not any("second" in line for line in logs)

    engine.execute_program_step(
        second, gray, bgr, {}, 0, 0, started, True, stop_event, logs.append, context,
    )
    assert any("second" in line for line in logs)

    waiting = {
        "type": "if",
        "condition": {
            "type": "pixel",
            "operator": "matches",
            "x": 1,
            "y": 1,
            "r": 255,
            "g": 255,
            "b": 255,
            "tolerance": 0,
        },
        "then": [{"type": "press", "key": "must-not-run"}],
        "else": [],
    }
    assert engine.execute_program_step(
        waiting, gray, bgr, {}, 0, 0, started, True, stop_event, logs.append, context,
    ) is False
    assert not any("must-not-run" in line for line in logs)

    try:
        engine.run_actions(
            [{"type": "restart_flow"}],
            (0, 0),
            True,
            stop_event,
            logs.append,
        )
        raise AssertionError("restart_flow did not interrupt")
    except engine.RestartFlow:
        pass

    try:
        engine.run_actions(
            [{"type": "goto_step", "step": 2}],
            (0, 0),
            True,
            stop_event,
            logs.append,
        )
        raise AssertionError("goto_step did not interrupt")
    except engine.GotoStep as jump:
        assert jump.step == 2

    repeat_logs: list[str] = []
    repeat_state: dict[str, dict[str, int]] = {}
    repeat_node = {
        "type": "repeat",
        "times": 2,
        "steps": [
            {"type": "press", "key": "repeat-a"},
            {"type": "press", "key": "repeat-b"},
        ],
    }
    assert engine.execute_program_step(
        repeat_node, gray, bgr, {}, 0, 0, started, True,
        stop_event, repeat_logs.append, context,
        repeat_state=repeat_state, step_key="program.0",
    ) is False
    assert engine.execute_program_step(
        repeat_node, gray, bgr, {}, 0, 0, started, True,
        stop_event, repeat_logs.append, context,
        repeat_state=repeat_state, step_key="program.0",
    ) is False
    assert engine.execute_program_step(
        repeat_node, gray, bgr, {}, 0, 0, started, True,
        stop_event, repeat_logs.append, context,
        repeat_state=repeat_state, step_key="program.0",
    ) is False
    assert engine.execute_program_step(
        repeat_node, gray, bgr, {}, 0, 0, started, True,
        stop_event, repeat_logs.append, context,
        repeat_state=repeat_state, step_key="program.0",
    ) is True
    assert repeat_state == {}
    assert sum("repeat-a" in line for line in repeat_logs) == 2
    assert sum("repeat-b" in line for line in repeat_logs) == 2

    pending_state = engine.RuleState(program_index=1)
    pending_state.repeat_state["program.0"] = {"iteration": 1, "step": 0}
    assert engine.flow_has_pending_work(
        {"program": [repeat_node]},
        pending_state,
    )
    pending_state.repeat_state.clear()
    assert not engine.flow_has_pending_work(
        {"program": [repeat_node]},
        pending_state,
    )

    waiting_repeat_state: dict[str, dict[str, int]] = {}
    waiting_repeat = {
        "type": "repeat",
        "times": 1,
        "steps": [waiting, {"type": "press", "key": "after-wait"}],
    }
    assert engine.execute_program_step(
        waiting_repeat, gray, bgr, {}, 0, 0, started, True,
        stop_event, logs.append, context,
        repeat_state=waiting_repeat_state, step_key="program.wait",
    ) is False
    assert waiting_repeat_state["program.wait"]["step"] == 0
    assert not any("after-wait" in line for line in logs)

    print("Flow cursor sequencing OK")


if __name__ == "__main__":
    main()
