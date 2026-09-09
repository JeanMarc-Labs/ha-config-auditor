"""Tests for the reference walk — audit 5-3, step 2(b).

`_build_entity_references` was 9.9 s of a 10.0 s entity analysis on the user's
Raspberry Pi 3, and the loop-latency probe of step 2 caught it as a single
9.8 s freeze: pure Python holding the event loop from end to end. Reading the
method line by line showed the heavy part touches no Home Assistant object at
all — the state machine and the registries are read once, into `known_ids` and
the three target indexes, for 7 ms of the 173 ms measured locally.

So the walk moved to a worker thread in one trip, and this file pins the three
things that makes true and keeps true: it really goes through the executor, it
really touches no hass from there, and it returns exactly what the inline
version put on the analyzer — strong and weak references kept apart, in source
order, plus the entity-shaped tokens of the safety net.

Step 2(c) then folded that safety net into the same walk. It used to be a
second pass over the same config — json.dumps, then the entity-token regex over
the text — and it was 32% of the method. The last class here is the equivalence
oracle for that fold: the old dump, run against the new walk on randomised
configs, plus one test per deliberate difference.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import random
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.entity_analyzer import (
    EntityAnalyzer,
    _iter_entity_tokens,
)
from custom_components.config_auditor.tests.conftest import MockHass


class _TrapHass(MockHass):
    """Counts trips to the executor and makes any hass access from one fatal.

    The job runs in a thread in production. Reading `hass.states` or a registry
    from there is not merely slow, it races the event loop — so the test does
    not check a convention, it takes the object away.
    """

    def __init__(self, config_dir):
        self.executor_jobs = 0
        self.inside_executor = False
        super().__init__(config_dir=str(config_dir))
        self.config.path = lambda *parts: os.path.join(str(config_dir), *parts)

    @property
    def states(self):
        if self.inside_executor:
            raise AssertionError("hass.states read from the worker thread")
        return self._states_proxy

    @states.setter
    def states(self, value):
        self._states_proxy = value

    @property
    def data(self):
        if self.inside_executor:
            raise AssertionError("hass.data read from the worker thread")
        return self._data_store

    @data.setter
    def data(self, value):
        self._data_store = value

    async def async_add_executor_job(self, func, *args):
        self.executor_jobs += 1
        self.inside_executor = True
        try:
            return func(*args)
        finally:
            self.inside_executor = False


def _entity_analyzer(hass):
    with patch(
        "custom_components.config_auditor.entity_analyzer.TranslationHelper"
    ) as TH:
        TH.return_value.t = lambda key, **kw: key
        TH.return_value.async_load_language = AsyncMock()
        analyzer = EntityAnalyzer(hass)
    analyzer._ignored_entity_ids = set()
    return analyzer


def _automation(entity_id: str) -> dict:
    return {
        "alias": entity_id,
        "triggers": [{"platform": "state", "entity_id": entity_id}],
        "actions": [{"service": "light.turn_on", "target": {"entity_id": entity_id}}],
    }


# ── Off the loop, and in one trip ────────────────────────────────────────────

class TestTheWalkRunsInTheExecutor:

    @pytest.mark.asyncio
    async def test_the_config_walk_happens_inside_the_job(self, tmp_path):
        hass = _TrapHass(tmp_path)
        hass.add_state("light.one", "on")
        analyzer = _entity_analyzer(hass)

        walked_inside = []
        real_walk = analyzer._walk_config

        def _watched_walk(config):
            walked_inside.append(hass.inside_executor)
            return real_walk(config)

        analyzer._walk_config = _watched_walk
        await analyzer._build_entity_references({"automation.a": _automation("light.one")}, {})

        assert walked_inside == [True], f"walked on the loop: {walked_inside}"

    @pytest.mark.asyncio
    async def test_two_hundred_sources_are_one_executor_job(self, tmp_path):
        """One trip, not one per source: a hop costs more than the walk of a
        single automation, and the freeze is the sum, not the peak."""
        hass = _TrapHass(tmp_path)
        hass.add_state("light.one", "on")
        analyzer = _entity_analyzer(hass)

        configs = {f"automation.a{i}": _automation("light.one") for i in range(200)}
        scripts = {f"script.s{i}": _automation("light.one") for i in range(50)}
        await analyzer._build_entity_references(configs, scripts)

        assert hass.executor_jobs == 1

    @pytest.mark.asyncio
    async def test_nothing_reads_hass_from_the_worker_thread(self, tmp_path):
        """_TrapHass raises on any access while the job runs, so this fails the
        day someone reaches for a state or a registry inside the walk."""
        hass = _TrapHass(tmp_path)
        for eid in ("light.one", "light.two", "sensor.temp"):
            hass.add_state(eid, "on")
        analyzer = _entity_analyzer(hass)

        configs = {
            "automation.explicit": _automation("light.one"),
            "automation.templated": {
                "alias": "T",
                "actions": [{"service": "notify.x", "data": {
                    "message": "{{ states('sensor.temp') }}"}}],
            },
            "automation.targeted": {
                "alias": "G",
                "actions": [{"service": "light.turn_on",
                             "target": {"area_id": "kitchen"}}],
            },
        }
        await analyzer._build_entity_references(configs, {})

        assert analyzer._entity_references.get("light.one") == ["automation.explicit"]
        assert analyzer._entity_references.get("sensor.temp") == ["automation.templated"]

    def test_the_job_cannot_reach_hass_by_construction(self):
        """A static half to the runtime one above: the body that runs in the
        thread must not name `hass` at all, however it got there."""
        tree = ast.parse(
            textwrap.dedent(inspect.getsource(EntityAnalyzer._resolve_references))
        )
        named = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert "hass" not in named, "the executor job reaches for hass"
        assert not inspect.iscoroutinefunction(EntityAnalyzer._resolve_references), (
            "it runs in a thread — an async def here would put it back on the loop"
        )
        assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Await, ast.AsyncFor))]


# ── The safety net, folded into the walk (step 2c) ───────────────────────────

def _dumped_tokens(config) -> set[str]:
    """The old safety net, kept as the oracle: dump the config, read the text."""
    try:
        return set(_iter_entity_tokens(json.dumps(config, default=str)))
    except Exception:  # noqa: BLE001 — what the old net did with a bad config
        return set()


_WORDS = [
    "light.kitchen", "input_boolean.holiday_mode", "sensor.outside_temp",
    "binary_sensor.motion_hall", "light.turn_on", "homeassistant.restart",
    "{{ states('sensor.power') }}", "{% if is_state('light.x','on') %}",
    "12:30:00", "an alias", "3.5", "not_an_id", "a.b", "TOKEN.upper",
    'a "quoted" word', "two\nlines", "trailing.", ".leading", "under_score.x9",
]
_KEYS = [
    "alias", "entity_id", "service", "data", "target", "sequence", "choose",
    "input_boolean.as_a_key", "device_id", "area_id", "value_template",
]


def _random_config(rng: random.Random, depth: int = 0):
    """A config shaped like the real ones, with the awkward scalars kept in."""
    roll = rng.random()
    if depth > 4 or roll < 0.35:
        return rng.choice([
            rng.choice(_WORDS), rng.randint(0, 9999), rng.random() * 100,
            True, False, None,
        ])
    if roll < 0.6:
        return [_random_config(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {
        rng.choice(_KEYS): _random_config(rng, depth + 1)
        for _ in range(rng.randint(1, 5))
    }


class TestTheSafetyNetMatchesTheOldDump:

    @pytest.mark.parametrize("seed", range(200))
    def test_random_configs_give_the_same_tokens(self, seed):
        rng = random.Random(seed)
        config = {"alias": "A", "actions": [_random_config(rng) for _ in range(6)]}
        analyzer = EntityAnalyzer.__new__(EntityAnalyzer)

        assert analyzer._walk_config(config)[3] == _dumped_tokens(config)

    def test_a_token_hiding_under_an_unexpected_key_is_still_found(self):
        analyzer = EntityAnalyzer.__new__(EntityAnalyzer)
        config = {"actions": [{"service": "notify.x", "data": {
            "whatever": "input_boolean.hidden", "input_number.as_a_key": 1}}]}

        tokens = analyzer._walk_config(config)[3]
        assert {"input_boolean.hidden", "input_number.as_a_key"} <= tokens
        assert tokens == _dumped_tokens(config)

    def test_a_value_that_cannot_be_rendered_costs_only_itself(self):
        """The dump was all-or-nothing: one unserialisable value and the whole
        config contributed no tokens at all. This is the better answer."""
        class _Unrenderable:
            def __repr__(self):
                raise RuntimeError("no")

        analyzer = EntityAnalyzer.__new__(EntityAnalyzer)
        config = {"a": "input_boolean.kept", "b": _Unrenderable()}

        assert analyzer._walk_config(config)[3] == {"input_boolean.kept"}
        assert _dumped_tokens(config) == set()

    def test_an_object_is_read_the_way_default_str_read_it(self):
        class _Rendered:
            def __str__(self):
                return "points at input_boolean.rendered"

        analyzer = EntityAnalyzer.__new__(EntityAnalyzer)
        config = {"a": _Rendered()}

        assert analyzer._walk_config(config)[3] == {"input_boolean.rendered"}
        assert analyzer._walk_config(config)[3] == _dumped_tokens(config)

    def test_below_the_depth_cap_the_net_stops_too(self):
        """The dump had no limit; the walk stops at thirty levels, and the net
        now shares that cap. A config nested that deep is pathological — the
        references stopped being collected there long before this."""
        analyzer = EntityAnalyzer.__new__(EntityAnalyzer)
        config: dict = {"deep": "input_boolean.at_the_bottom"}
        for _ in range(40):
            config = {"nest": config}

        assert analyzer._walk_config(config)[3] == set()
        assert _dumped_tokens(config) == {"input_boolean.at_the_bottom"}

    @pytest.mark.asyncio
    async def test_the_helper_fallback_walks_the_config_the_same_way(self, tmp_path):
        """`_analyze_input_helpers` rebuilds the net itself when it is driven
        without a reference pass. That fallback used to be a second copy of the
        json.dumps line; it calls the walk now, and a helper reachable only
        through the net must not be reported unused by either road."""
        hass = _TrapHass(tmp_path)
        hass.add_state("input_boolean.hidden", "off")
        analyzer = _entity_analyzer(hass)
        assert analyzer._all_config_entity_ids == set()

        configs = {"automation.a": {"alias": "A", "actions": [
            {"service": "notify.x", "data": {"whatever": "input_boolean.hidden"}},
        ]}}
        await analyzer._analyze_input_helpers(configs, {})

        assert [i for i in analyzer.issues if i["type"] == "helper_unused"] == []

    def test_a_non_ascii_id_no_longer_produces_a_truncated_token(self):
        """json.dumps escaped it — "sensor.café" became "sensor.caf\u00e9" and
        the regex read "sensor.caf" out of the escape. An entity id is
        slugified ASCII, so that token could never match a real entity."""
        analyzer = EntityAnalyzer.__new__(EntityAnalyzer)
        config = {"a": "sensor.café"}

        assert analyzer._walk_config(config)[3] == set()
        assert _dumped_tokens(config) == {"sensor.caf"}


# ── And returns exactly what the inline loop used to write ───────────────────

class TestWhatComesBack:

    @pytest.mark.asyncio
    async def test_strong_and_weak_are_not_swapped(self, tmp_path):
        """The one mistake the move could make invisibly: a template hit proves
        an entity is *used*, never that a missing one is still referenced, so
        it must stay out of the strong map that zombie detection reads."""
        hass = _TrapHass(tmp_path)
        hass.add_state("light.explicit", "on")
        hass.add_state("sensor.templated", "20")
        analyzer = _entity_analyzer(hass)

        configs = {
            "automation.a": {
                "alias": "A",
                "triggers": [{"platform": "state", "entity_id": "light.explicit"}],
                "actions": [{"service": "notify.x", "data": {
                    "message": "{{ states('sensor.templated') }}"}}],
            }
        }
        await analyzer._build_entity_references(configs, {})

        assert analyzer._strong_entity_references.get("light.explicit") == ["automation.a"]
        assert "sensor.templated" not in analyzer._strong_entity_references
        assert analyzer._entity_references.get("sensor.templated") == ["automation.a"]

    @pytest.mark.asyncio
    async def test_the_sources_stay_in_order(self, tmp_path):
        """Automations first, then scripts, each in config order — the panel
        renders the list as it comes."""
        hass = _TrapHass(tmp_path)
        hass.add_state("light.shared", "on")
        analyzer = _entity_analyzer(hass)

        configs = {f"automation.a{i}": _automation("light.shared") for i in range(5)}
        scripts = {f"script.s{i}": _automation("light.shared") for i in range(3)}
        await analyzer._build_entity_references(configs, scripts)

        assert analyzer._entity_references["light.shared"] == (
            [f"automation.a{i}" for i in range(5)] + [f"script.s{i}" for i in range(3)]
        )

    @pytest.mark.asyncio
    async def test_the_safety_net_still_comes_back(self, tmp_path):
        """Entity-shaped tokens under any key at all, which is what the unused
        helper checks read. It is built in the job like everything else."""
        hass = _TrapHass(tmp_path)
        analyzer = _entity_analyzer(hass)

        configs = {"automation.a": {"alias": "A", "actions": [
            {"service": "script.turn_on", "data": {"whatever": "input_boolean.hidden"}}
        ]}}
        await analyzer._build_entity_references(configs, {})

        assert "input_boolean.hidden" in analyzer._all_config_entity_ids
        assert "input_boolean.hidden" not in analyzer._entity_references

    @pytest.mark.asyncio
    async def test_a_second_scan_does_not_stack_on_the_first(self, tmp_path):
        """The maps are cleared at the top and filled from the job's result —
        a reference counted twice is a helper that never looks unused."""
        hass = _TrapHass(tmp_path)
        hass.add_state("light.one", "on")
        analyzer = _entity_analyzer(hass)

        configs = {"automation.a": _automation("light.one")}
        await analyzer._build_entity_references(configs, {})
        await analyzer._build_entity_references(configs, {})

        assert analyzer._entity_references["light.one"] == ["automation.a"]
        assert analyzer._strong_entity_references["light.one"] == ["automation.a"]

    @pytest.mark.asyncio
    async def test_a_template_cannot_invent_an_entity(self, tmp_path):
        """The filter that makes the weak map trustworthy, carried through the
        move: a dotted token is a reference only if it names an entity that
        exists. Otherwise every service call in a template — light.turn_on —
        would register as one."""
        hass = _TrapHass(tmp_path)
        hass.add_state("sensor.real", "20")
        analyzer = _entity_analyzer(hass)

        configs = {"automation.a": {"alias": "A", "actions": [
            {"service": "notify.x", "data": {"message":
                "{{ states('sensor.real') }} {{ states('sensor.imaginary') }}"}},
        ]}}
        await analyzer._build_entity_references(configs, {})

        assert analyzer._entity_references.get("sensor.real") == ["automation.a"]
        assert "sensor.imaginary" not in analyzer._entity_references
        assert "light.turn_on" not in analyzer._entity_references

    @pytest.mark.asyncio
    async def test_a_reference_that_disappears_is_forgotten(self, tmp_path):
        """The maps are cleared before the job, not overwritten after it: an
        automation deleted between two scans must take its references with it,
        or the entity it named looks used forever."""
        hass = _TrapHass(tmp_path)
        hass.add_state("light.one", "on")
        hass.add_state("light.two", "on")
        analyzer = _entity_analyzer(hass)

        await analyzer._build_entity_references({"automation.a": _automation("light.one")}, {})
        await analyzer._build_entity_references({"automation.b": _automation("light.two")}, {})

        assert "light.one" not in analyzer._entity_references
        assert "light.one" not in analyzer._strong_entity_references
        assert analyzer._entity_references.get("light.two") == ["automation.b"]

    @pytest.mark.asyncio
    async def test_an_unserialisable_config_does_not_stop_the_walk(self, tmp_path):
        """The safety net is best-effort; the references are not."""
        hass = _TrapHass(tmp_path)
        hass.add_state("light.one", "on")
        analyzer = _entity_analyzer(hass)

        class _Unserialisable:
            def __repr__(self):
                raise RuntimeError("not even str() works here")

        configs = {
            "automation.bad": {"alias": "B", "actions": [
                {"service": "light.turn_on", "target": {"entity_id": "light.one"},
                 "data": {"payload": _Unserialisable()}}
            ]},
            "automation.good": _automation("light.one"),
        }
        await analyzer._build_entity_references(configs, {})

        assert analyzer._entity_references["light.one"] == [
            "automation.bad", "automation.good",
        ]
