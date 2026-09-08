"""Tests for ScanTimer — the scan instrumentation behind audit 5-3.

5-3 asks whether the scan should move off the event loop. Nothing measured it,
so the plan's "10 to 30 seconds" was an estimate. ScanTimer answers the question
from the user's own installation: one INFO line per scan, slowest stage first.

Two halves. The first pins the class: what it records, what it reports, and the
distinction that makes the numbers honest — sequential stages add up to the
total, the six analyzers inside the `asyncio.gather` phase do not. The second is
a source guard: every `await` in the scan must sit inside a timer stage, so an
analyzer added later cannot go unmeasured and quietly skew the answer.

    pytest custom_components/config_auditor/tests/test_scan_timer.py -v
"""
from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor import ScanTimer

_INIT = Path(__file__).parent.parent / "__init__.py"


# ── Half one: the class ──────────────────────────────────────────────────────

class TestStageRecording:
    """What lands in the timer, and what does not."""

    def test_stage_records_its_duration(self, monkeypatch):
        clock = iter([100.0, 100.0, 102.5])
        monkeypatch.setattr(
            "custom_components.config_auditor.monotonic", lambda: next(clock)
        )
        timer = ScanTimer()
        with timer.stage("entities"):
            pass
        assert timer._stages == {"entities": 2.5}

    def test_the_same_label_twice_accumulates(self, monkeypatch):
        clock = iter([0.0, 0.0, 1.0, 10.0, 12.0])
        monkeypatch.setattr(
            "custom_components.config_auditor.monotonic", lambda: next(clock)
        )
        timer = ScanTimer()
        with timer.stage("recorder"):
            pass
        with timer.stage("recorder"):
            pass
        assert timer._stages == {"recorder": 3.0}

    def test_a_stage_that_raises_is_still_recorded_and_still_raises(self, monkeypatch):
        """Every analyzer call in the scan sits in a try/except. A crash must
        leave its duration behind — a stage that blew up after 4 seconds is
        exactly what one would want to see — and must still reach that except."""
        clock = iter([0.0, 0.0, 4.0])
        monkeypatch.setattr(
            "custom_components.config_auditor.monotonic", lambda: next(clock)
        )
        timer = ScanTimer()
        with pytest.raises(ValueError):
            with timer.stage("dashboards"):
                raise ValueError("analyzer crashed")
        assert timer._stages == {"dashboards": 4.0}

    def test_overlapping_stays_out_of_the_sequential_bucket(self, monkeypatch):
        """Summing an overlapping analyzer into the total would inflate it:
        its clock runs while its siblings hold the loop."""
        clock = iter([0.0, 0.0, 3.0])
        monkeypatch.setattr(
            "custom_components.config_auditor.monotonic", lambda: next(clock)
        )
        timer = ScanTimer()
        with timer.overlapping("performance"):
            pass
        assert timer._stages == {}
        assert timer._overlapping == {"performance": 3.0}


class TestLogLine:
    """The one line a user reads to decide whether 5-3 is worth two days."""

    @staticmethod
    def _timed(monkeypatch, stages: dict, overlapping: dict, total: float):
        """Build a timer holding these durations, with `total` on the clock."""
        monkeypatch.setattr("custom_components.config_auditor.monotonic", lambda: 0.0)
        timer = ScanTimer()
        timer._stages = dict(stages)
        timer._overlapping = dict(overlapping)
        monkeypatch.setattr("custom_components.config_auditor.monotonic", lambda: total)
        return timer

    def test_one_info_line_slowest_first(self, monkeypatch, caplog):
        timer = self._timed(
            monkeypatch,
            {"entities": 5.2, "automations": 3.1, "parallel phase": 2.8},
            {},
            11.4,
        )
        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()

        info = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(info) == 1, "one scan must produce one timing line"
        msg = info[0].getMessage()
        assert "scan finished in 11.4s" in msg
        assert msg.index("entities") < msg.index("automations") < msg.index("parallel phase"), (
            f"stages must be ranked slowest first, got: {msg}"
        )

    def test_the_untimed_glue_is_reported_as_other(self, monkeypatch, caplog):
        """Filtering, haca_id tagging and the health score run between stages.
        They are pure Python on the event loop, so they are the point of 5-3 —
        they must not vanish into the gap between the total and the stages."""
        timer = self._timed(monkeypatch, {"entities": 1.0}, {}, 4.0)
        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()
        assert "other 3.0s" in caplog.records[0].getMessage()

    def test_a_stage_under_a_tenth_of_a_second_is_not_named(self, monkeypatch, caplog):
        """Twelve entries reading 0.0s would bury the one that matters."""
        timer = self._timed(
            monkeypatch, {"entities": 4.0, "history": 0.02, "redundancy": 0.0}, {}, 4.1
        )
        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()
        msg = caplog.records[0].getMessage()
        assert "entities 4.0s" in msg
        assert "history" not in msg and "redundancy" not in msg

    def test_a_scan_with_nothing_to_report_still_says_so(self, monkeypatch, caplog):
        timer = self._timed(monkeypatch, {"entities": 0.01}, {}, 0.02)
        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()
        assert "every stage under 0.1s" in caplog.records[0].getMessage()

    def test_the_parallel_breakdown_is_debug_and_carries_its_caveat(
        self, monkeypatch, caplog
    ):
        """Six wall-clock numbers that do not add up are a trap without the
        caveat, and too noisy for INFO on every scan."""
        timer = self._timed(
            monkeypatch,
            {"parallel phase": 2.8},
            {"recorder": 2.7, "performance": 2.1},
            3.0,
        )
        with caplog.at_level(logging.DEBUG, logger="custom_components.config_auditor"):
            timer.log()

        debug = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug) == 1
        msg = debug[0].getMessage()
        assert "overlap" in msg and "do not add up" in msg
        assert msg.index("recorder") < msg.index("performance")

        info = [r for r in caplog.records if r.levelno == logging.INFO][0].getMessage()
        assert "recorder" not in info, (
            "an overlapping analyzer must not reach the INFO line, where the "
            "numbers are read as adding up to the total"
        )

    def test_no_debug_line_when_nothing_ran_in_parallel(self, monkeypatch, caplog):
        timer = self._timed(monkeypatch, {"entities": 1.0}, {}, 1.5)
        with caplog.at_level(logging.DEBUG, logger="custom_components.config_auditor"):
            timer.log()
        assert not [r for r in caplog.records if r.levelno == logging.DEBUG]


# ── Half two: the scan is fully instrumented ─────────────────────────────────

def _scan_function() -> ast.AsyncFunctionDef:
    """The `async_update_data` closure inside async_setup_entry."""
    tree = ast.parse(_INIT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_update_data":
            return node
    pytest.fail("async_update_data not found in __init__.py")


def _is_timer_with(node: ast.AST) -> bool:
    """A `with timer.stage(...)` / `with timer.overlapping(...)` block."""
    if not isinstance(node, (ast.With, ast.AsyncWith)):
        return False
    for item in node.items:
        call = item.context_expr
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in ("stage", "overlapping")
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "timer"
        ):
            return True
    return False


def _untimed_awaits(node: ast.AST, inside_timer: bool = False) -> list[int]:
    """Line numbers of every `await` not enclosed in a timer block."""
    found: list[int] = []
    timed = inside_timer or _is_timer_with(node)
    if isinstance(node, ast.Await) and not timed:
        found.append(node.lineno)
    for child in ast.iter_child_nodes(node):
        found += _untimed_awaits(child, timed)
    return found


class TestTheWholeScanIsMeasured:
    """A stage nobody times is a stage that hides in `other`."""

    def test_every_await_in_the_scan_sits_in_a_timer_stage(self):
        untimed = _untimed_awaits(_scan_function())
        assert not untimed, (
            "these awaits in async_update_data are outside any timer.stage() / "
            f"timer.overlapping() block, at __init__.py lines {untimed} — an "
            "analyzer added without a stage lands in 'other' and the timing "
            "line stops pointing at the culprit"
        )

    def test_the_timer_is_created_and_logged_exactly_once(self):
        scan = _scan_function()
        created = [
            n for n in ast.walk(scan)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "ScanTimer"
        ]
        logged = [
            n for n in ast.walk(scan)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "log" and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "timer"
        ]
        assert len(created) == 1, "one scan, one timer"
        assert len(logged) == 1, "one scan, one timing line"

    def test_the_gather_phase_is_timed_as_one_sequential_stage(self):
        """Without it the parallel work would land in `other`, and the six
        overlapping numbers would be all the user has to go on."""
        scan = _scan_function()
        gathers = [
            n for n in ast.walk(scan)
            if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "gather"
        ]
        assert len(gathers) == 1, "the scan has exactly one gather phase"
        assert 'timer.stage("parallel phase")' in _INIT.read_text(encoding="utf-8")
