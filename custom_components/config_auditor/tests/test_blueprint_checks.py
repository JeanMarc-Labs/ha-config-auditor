"""Tests for the blueprint checks — audit 5-3, step 1b.

The per-scan instrumentation added in step 1 reported `blueprints 5.9s` out of
a 6.3 s automation analysis on the user's Raspberry Pi 3. The cause was in the
loop, not in the checks: for *every automation* built on a blueprint it built a
YAML loader class, re-read the blueprint file, and re-parsed it — on the event
loop. A blueprint exists to be reused, so that work was repeated once per
automation when once per file would do.

This file pins both halves: that the file is read once per blueprint and parsed
off the loop, and that every finding the checks used to produce still comes out
of them unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import custom_components.config_auditor.automation_analyzer as aa_mod
from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer
from custom_components.config_auditor.tests.conftest import MockHass


BLUEPRINT = """
blueprint:
  name: Motion light
  domain: automation
  input:
    motion_entity:
      name: Motion sensor
      selector:
        entity:
          filter:
            domain: binary_sensor
    light_target:
      name: Light
      selector:
        target:
          entity:
            domain: light
    no_motion_wait:
      name: Wait
      default: 120
      selector:
        number: {min: 0, max: 3600}
    advanced:
      name: Advanced options
      input:
        helper_entity:
          name: Helper
          default: null
          selector:
            entity: {}
        transition:
          name: Transition
          default: 1
triggers:
  - trigger: state
    entity_id: !input motion_entity
actions:
  - action: light.turn_on
    target: !input light_target
"""


class _CountingHass(MockHass):
    """Counts trips to the executor, and knows when it is inside one.

    Both are the measurement: one trip per blueprint rather than two per
    automation, and the YAML parse happening on that side of the boundary.
    """

    def __init__(self, config_dir):
        super().__init__(config_dir=str(config_dir))
        self.executor_jobs = 0
        self.inside_executor = False

    async def async_add_executor_job(self, func, *args):
        self.executor_jobs += 1
        self.inside_executor = True
        try:
            return func(*args)
        finally:
            self.inside_executor = False


class _Translator:
    def t(self, key, /, **kwargs):
        if not kwargs:
            return key
        return f"{key} " + " ".join(f"{k}={v}" for k, v in sorted(kwargs.items()))


def analyzer(hass, configs, ignored=()):
    """`_check_blueprint_issues` reads these four attributes and hass."""
    a = AutomationAnalyzer.__new__(AutomationAnalyzer)
    a.hass = hass
    a._automation_configs = configs
    a._ignored_entity_ids = set(ignored)
    a._translator = _Translator()
    a.issues = []
    return a


def write_blueprint(config_dir: Path, name: str, body: str = BLUEPRINT) -> None:
    folder = config_dir / "blueprints" / "automation"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body, encoding="utf-8")


def using(path: str, inputs, alias="An automation"):
    return {"alias": alias, "use_blueprint": {"path": path, "input": inputs}}


def types_of(issues):
    return [issue["type"] for issue in issues]


# ── One read per blueprint, and the parse off the event loop ─────────────────

class TestTheBlueprintIsReadOncePerFile:

    @pytest.mark.asyncio
    async def test_twenty_automations_on_one_blueprint_read_it_once(self, tmp_path):
        hass = _CountingHass(tmp_path)
        write_blueprint(tmp_path, "motion.yaml")
        configs = {
            f"automation.a{i}": using("motion.yaml", {"no_motion_wait": 60})
            for i in range(20)
        }
        a = analyzer(hass, configs)
        await a._check_blueprint_issues()

        assert hass.executor_jobs == 1, (
            f"one read for one blueprint, not {hass.executor_jobs} — a blueprint "
            "is reused by design, so re-reading it per automation is the whole bug"
        )

    @pytest.mark.asyncio
    async def test_each_distinct_blueprint_is_read_once(self, tmp_path):
        hass = _CountingHass(tmp_path)
        for name in ("motion.yaml", "presence.yaml", "sunset.yaml"):
            write_blueprint(tmp_path, name)
        configs = {
            f"automation.a{i}": using(
                ("motion.yaml", "presence.yaml", "sunset.yaml")[i % 3],
                {"no_motion_wait": 60},
            )
            for i in range(30)
        }
        a = analyzer(hass, configs)
        await a._check_blueprint_issues()
        assert hass.executor_jobs == 3

    @pytest.mark.asyncio
    async def test_a_missing_blueprint_is_not_looked_for_again(self, tmp_path):
        """A path that does not resolve is still one answer, cached like any
        other — ten automations on a removed blueprint used to be ten probes."""
        hass = _CountingHass(tmp_path)
        configs = {f"automation.a{i}": using("gone.yaml", {"x": 1}) for i in range(10)}
        a = analyzer(hass, configs)
        await a._check_blueprint_issues()

        assert hass.executor_jobs == 1
        assert types_of(a.issues) == ["blueprint_file_not_found"] * 10, (
            "caching the answer must not cost the other nine automations "
            "their finding"
        )

    @pytest.mark.asyncio
    async def test_the_yaml_is_parsed_inside_the_executor(self, tmp_path, monkeypatch):
        """The parse is the expensive half — about 13 ms for a 2 KB blueprint
        on a desktop, a quarter of a second on a Pi 3. On the event loop that
        is time Home Assistant answers nothing."""
        hass = _CountingHass(tmp_path)
        write_blueprint(tmp_path, "motion.yaml")

        parsed_inside = []
        real_load = aa_mod.yaml.load

        def _watched_load(*args, **kwargs):
            parsed_inside.append(hass.inside_executor)
            return real_load(*args, **kwargs)

        monkeypatch.setattr(aa_mod.yaml, "load", _watched_load)

        a = analyzer(hass, {"automation.a": using("motion.yaml", {"transition": 1})})
        await a._check_blueprint_issues()

        assert parsed_inside == [True], f"parsed on the loop: {parsed_inside}"

    def test_the_loader_is_built_once_for_the_module(self):
        """It used to be a fresh class per automation, with its multi-constructor
        registered again each time."""
        assert isinstance(aa_mod._AnyTagLoader, type)


# ── The findings themselves, unchanged ───────────────────────────────────────

class TestTheFindings:

    def _run(self, tmp_path, configs, ignored=(), states=()):
        hass = _CountingHass(tmp_path)
        for entity_id in states:
            hass.add_state(entity_id)
        write_blueprint(tmp_path, "motion.yaml")
        a = analyzer(hass, configs, ignored)
        return a

    @pytest.mark.asyncio
    async def test_a_blueprint_without_a_path(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": {
            "alias": "A", "use_blueprint": {"input": {"x": 1}}}})
        await a._check_blueprint_issues()
        assert types_of(a.issues) == ["blueprint_missing_path"]

    @pytest.mark.asyncio
    async def test_a_blueprint_file_that_is_not_there(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": using("nope.yaml", {"x": 1})})
        await a._check_blueprint_issues()
        assert types_of(a.issues) == ["blueprint_file_not_found"]
        assert "nope.yaml" in a.issues[0]["message"]

    @pytest.mark.asyncio
    async def test_a_blueprint_used_with_no_inputs_at_all(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": using("motion.yaml", {})})
        await a._check_blueprint_issues()
        assert types_of(a.issues) == ["blueprint_no_inputs"]

    @pytest.mark.asyncio
    async def test_a_required_input_left_empty(self, tmp_path):
        """`motion_entity` declares no default, so leaving it null is an error
        the blueprint itself cannot recover from."""
        a = self._run(tmp_path, {"automation.a": using(
            "motion.yaml", {"motion_entity": None})})
        await a._check_blueprint_issues()
        assert types_of(a.issues) == ["blueprint_empty_input"]
        assert a.issues[0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_an_optional_entity_input_pointing_at_nothing(self, tmp_path):
        """`helper_entity` is declared inside a nested input group — finding it
        at all means the group was flattened."""
        a = self._run(tmp_path, {"automation.a": using(
            "motion.yaml", {"helper_entity": "light.removed_last_year"})})
        await a._check_blueprint_issues()
        assert [i["severity"] for i in a.issues] == ["medium"]
        assert "light.removed_last_year" in a.issues[0]["message"]

    @pytest.mark.asyncio
    async def test_an_optional_entity_input_that_exists_is_fine(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": using(
            "motion.yaml", {"helper_entity": "light.hall"})}, states=["light.hall"])
        await a._check_blueprint_issues()
        assert a.issues == []

    @pytest.mark.asyncio
    async def test_an_entity_input_with_nothing_configured(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": using(
            "motion.yaml", {"helper_entity": []})})
        await a._check_blueprint_issues()
        assert [i["severity"] for i in a.issues] == ["low"]

    @pytest.mark.asyncio
    async def test_a_falsy_value_on_an_ordinary_input(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": using(
            "motion.yaml", {"transition": 0})})
        await a._check_blueprint_issues()
        assert [i["severity"] for i in a.issues] == ["low"]

    @pytest.mark.asyncio
    async def test_a_configured_input_raises_nothing(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": using(
            "motion.yaml", {"no_motion_wait": 300})})
        await a._check_blueprint_issues()
        assert a.issues == []

    @pytest.mark.asyncio
    async def test_an_automation_without_a_blueprint_is_not_checked(self, tmp_path):
        a = self._run(tmp_path, {"automation.a": {
            "alias": "Plain", "trigger": [], "action": []}})
        await a._check_blueprint_issues()
        assert a.issues == []

    @pytest.mark.asyncio
    async def test_an_ignored_automation_is_skipped(self, tmp_path):
        a = self._run(tmp_path,
                      {"automation.a": using("nope.yaml", {"x": 1})},
                      ignored=["automation.a"])
        await a._check_blueprint_issues()
        assert a.issues == []


class TestABlueprintThatCannotBeRead:
    """One bad file must cost its own automations their input checks, and
    nothing else."""

    @pytest.mark.asyncio
    async def test_malformed_yaml_skips_the_input_checks_without_raising(self, tmp_path):
        hass = _CountingHass(tmp_path)
        write_blueprint(tmp_path, "broken.yaml", "blueprint: [unclosed\n  - :::")
        a = analyzer(hass, {"automation.a": using("broken.yaml", {"whatever": None})})
        await a._check_blueprint_issues()
        assert a.issues == [], "no declared inputs known, so nothing to check"

    @pytest.mark.asyncio
    async def test_a_blueprint_that_is_not_a_mapping_is_survived(self, tmp_path):
        hass = _CountingHass(tmp_path)
        write_blueprint(tmp_path, "list.yaml", "- one\n- two\n")
        a = analyzer(hass, {"automation.a": using("list.yaml", {"whatever": None})})
        await a._check_blueprint_issues()
        assert a.issues == []

    @pytest.mark.asyncio
    async def test_input_tags_do_not_stop_the_parse(self, tmp_path):
        """`!input` is not a tag SafeLoader knows; a blueprint is full of them,
        and the checks only ever need the shape of the file."""
        hass = _CountingHass(tmp_path)
        write_blueprint(tmp_path, "motion.yaml")
        exists, required, entity = await a_read(hass, tmp_path, "motion.yaml")
        assert exists
        assert required == {"motion_entity", "light_target"}
        assert entity == {"motion_entity", "light_target", "helper_entity"}


async def a_read(hass, tmp_path, name):
    a = analyzer(hass, {})
    return await a._read_blueprint(
        tmp_path / "blueprints" / "automation" / name
    )
