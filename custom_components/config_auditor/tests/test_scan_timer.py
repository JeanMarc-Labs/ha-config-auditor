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
import asyncio
import logging
import sys
import time
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

    def test_nothing_is_said_about_the_loop_when_the_probe_never_ran(
        self, monkeypatch, caplog
    ):
        timer = self._timed(monkeypatch, {"entities": 1.0}, {}, 1.5)
        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()
        assert len([r for r in caplog.records if r.levelno == logging.INFO]) == 1


# ── The loop probe: is the scan holding the loop, or waiting for it? ─────────

class TestLoopProbe:
    """Wall-clock stage timings cannot tell a freeze from waiting one's turn.
    The probe is what separates them, and that distinction decides 5-3."""

    @pytest.mark.asyncio
    async def test_a_free_loop_produces_no_stalls(self):
        timer = ScanTimer()
        timer.start_loop_probe()
        await asyncio.sleep(0.3)          # the loop is ours alone here
        await timer.stop_loop_probe()
        assert timer._stalls == 0
        assert timer._worst_stall == 0.0

    @pytest.mark.asyncio
    async def test_a_blocked_loop_is_caught_and_attributed_to_its_stage(self):
        """The shape of a real stage: it yields, then holds the loop between
        two yields. entity_analyzer does exactly this, 17 times, for 12 to 50
        seconds."""
        timer = ScanTimer()
        timer.start_loop_probe()
        with timer.stage("entities"):
            await asyncio.sleep(0.15)     # the probe arms inside the stage
            time.sleep(0.4)               # the loop cannot run: this is a freeze
            await asyncio.sleep(0)
        await asyncio.sleep(0.15)
        await timer.stop_loop_probe()

        assert timer._stalls >= 1, "a 400 ms freeze must be seen"
        assert timer._worst_stall >= 0.3, (
            f"the freeze was ~0.4s, the probe reports {timer._worst_stall:.2f}s"
        )
        assert timer._stalled_for >= timer._worst_stall, (
            "the cumulative blocked time is what says how much of the scan HA "
            "spent unresponsive — it cannot be less than the worst single stall"
        )
        assert timer._worst_stall_stage == "entities", (
            "a freeze must name the stage that caused it, or the user cannot "
            "tell which analyzer to move off the loop"
        )

    @pytest.mark.asyncio
    async def test_the_stage_is_read_when_the_probe_sleeps_not_when_it_wakes(self):
        """Reading it on waking blames the wrong stage. The loop resumes the
        task that yielded before it resumes the probe, so a freeze at the end
        of a stage would be charged to whatever ran next — or to nothing."""
        timer = ScanTimer()
        timer.start_loop_probe()
        with timer.stage("entities"):
            await asyncio.sleep(0.15)
            time.sleep(0.4)
            await asyncio.sleep(0)
        # The stage is over and `_current` is back to None before the probe is
        # given a chance to run. It must still name "entities".
        assert timer._current is None
        await asyncio.sleep(0.15)
        await timer.stop_loop_probe()
        assert timer._worst_stall_stage == "entities"

    @pytest.mark.asyncio
    async def test_the_probe_stops_when_the_scan_does(self):
        timer = ScanTimer()
        timer.start_loop_probe()
        task = timer._probe
        await timer.stop_loop_probe()
        assert task.cancelled() or task.done(), "a probe left running wakes forever"
        assert timer._probe is None

    @pytest.mark.asyncio
    async def test_stopping_a_probe_that_never_started_is_harmless(self):
        await ScanTimer().stop_loop_probe()

    @pytest.mark.asyncio
    async def test_a_freeze_is_reported_with_its_stage(self, caplog):
        timer = ScanTimer()
        timer.start_loop_probe()
        with timer.stage("entities"):
            await asyncio.sleep(0.15)
            time.sleep(0.3)
            await asyncio.sleep(0)
        await asyncio.sleep(0.15)
        await timer.stop_loop_probe()

        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()
        loop_lines = [
            r.getMessage() for r in caplog.records if "event loop" in r.getMessage()
        ]
        assert len(loop_lines) == 1
        assert "blocked" in loop_lines[0] and "entities" in loop_lines[0]

    @pytest.mark.asyncio
    async def test_a_scan_that_never_froze_says_so_in_as_many_words(self, caplog):
        """The answer "21 seconds, and none of it blocked anything" is a real
        answer to 5-3 — silence would read as a missing measurement."""
        timer = ScanTimer()
        timer.start_loop_probe()
        await asyncio.sleep(0.2)
        await timer.stop_loop_probe()

        with caplog.at_level(logging.INFO, logger="custom_components.config_auditor"):
            timer.log()
        loop_lines = [
            r.getMessage() for r in caplog.records if "event loop" in r.getMessage()
        ]
        assert len(loop_lines) == 1
        assert "never blocked" in loop_lines[0]
        assert "waiting, not holding it" in loop_lines[0]

    def test_jitter_below_the_floor_is_not_a_freeze(self):
        """Ordinary scheduler lateness is milliseconds, and a 50 ms stall is
        invisible in the interface. Counting those would drown the real ones."""
        assert ScanTimer.LOOP_STALL_FLOOR >= 0.05
        assert ScanTimer.LOOP_PROBE_INTERVAL <= ScanTimer.LOOP_STALL_FLOOR

    def test_the_probe_gives_up_on_its_own(self):
        """The scan cancels it, but a scan that raises somewhere unguarded must
        not leave a task waking every 50 ms for the life of the process."""
        assert 0 < ScanTimer.MAX_PROBE_SECONDS <= 3600


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


def _awaits_the_timer(node: ast.AST) -> bool:
    """An `await timer.<something>()` — the timer's own teardown.

    `stop_loop_probe()` cancels the loop probe and is by construction outside
    every stage: it is what ends the measurement. It is the only await allowed
    to sit bare in the scan, and naming the exemption this narrowly is what
    keeps it from covering an analyzer.
    """
    return (
        isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "timer"
    )


def _untimed_awaits(node: ast.AST, inside_timer: bool = False) -> list[int]:
    """Line numbers of every `await` not enclosed in a timer block."""
    found: list[int] = []
    timed = inside_timer or _is_timer_with(node)
    if isinstance(node, ast.Await) and not timed and not _awaits_the_timer(node):
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
