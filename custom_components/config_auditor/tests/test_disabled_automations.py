"""An automation disabled in the entity registry is not audited as if it ran.

Reported on 1.8.1: HACA filed a high-severity finding — and so a Repairs
entry — on an automation its user believed deleted:

    automation.house_mode_disarm_returning_home (device_id_in_target):
    Action 4 uses device_id which breaks when device is re-added

The automation was not deleted. Its entity had been disabled (and hidden) in
the entity registry. Home Assistant never adds a disabled entity to its
platform, so the automation is never loaded: it cannot run, it has no state,
and it is missing from Settings → Automations, which lists the state machine.
Its configuration is still in automations.yaml, though, and HACA reads that
file directly — so every check ran on code that cannot execute, and an old
disabled copy next to its replacement made both "duplicates".

Now a disabled automation gets one low finding that says what it is, and
nothing it holds is reported, by the automation analyzer or by the entity
checks it used to trigger. What it references still counts as *used*: its
configuration would break if those entities went away.

    pytest custom_components/config_auditor/tests/test_disabled_automations.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import (
    MockHass,
    MockRegistryEntry,
)


def _t(key, **kw):
    """Translator stand-in that keeps the placeholders visible."""
    return f"{key} {sorted(kw.items())}" if kw else key


def _automation(entity_id, unique_id, *, disabled=False, labels=None) -> MockRegistryEntry:
    return MockRegistryEntry(
        entity_id,
        platform="automation",
        unique_id=unique_id,
        disabled_by="user" if disabled else None,
        labels=labels,
    )


# The reporter's automation, reduced to what matters: a device target.
_DISARM = {
    "alias": "House Mode - Disarm Returning Home",
    "description": "Unlock and disarm when someone comes home",
    "triggers": [{"trigger": "state", "entity_id": "person.alex", "to": "home"}],
    "actions": [
        {"action": "lock.unlock", "target": {"device_id": "dev_front_lock"}},
    ],
}


async def _scan(tmp_path, automations: list[dict], entries: list[MockRegistryEntry],
                states: dict[str, str] | None = None):
    (tmp_path / "automations.yaml").write_text(yaml.safe_dump(automations), encoding="utf-8")
    hass = MockHass(config_dir=str(tmp_path))
    for entry in entries:
        hass.add_registry_entry(entry)
    for entity_id, state in (states or {}).items():
        hass.add_state(entity_id, state)
    er_mock = MagicMock()
    er_mock.async_get.return_value = hass._entity_registry
    with patch("custom_components.config_auditor.automation_analyzer.TranslationHelper") as TH, \
         patch("custom_components.config_auditor.automation_analyzer.er", er_mock):
        TH.return_value.t = _t
        TH.return_value.async_load_language = AsyncMock()
        from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer
        analyzer = AutomationAnalyzer(hass)
        await analyzer.analyze_all()
    return analyzer


def _by_entity(analyzer, entity_id) -> list[dict]:
    return [i for i in analyzer.issues if i.get("entity_id") == entity_id]


# ══════════════════════════════════════════════════════════════════════════════
# The registry read
# ══════════════════════════════════════════════════════════════════════════════

class TestDisabledAutomationIds:

    def test_only_automations_whose_entity_is_disabled(self):
        from custom_components.config_auditor.registry_utils import disabled_automation_ids

        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        hass.add_registry_entry(_automation("automation.live", "2"))
        hass.add_registry_entry(MockRegistryEntry("sensor.rf_stats", disabled_by="integration"))
        # Hidden is not disabled: a hidden automation is loaded and runs.
        hidden = _automation("automation.hidden", "3")
        hidden.hidden_by = "user"
        hass.add_registry_entry(hidden)

        assert disabled_automation_ids(hass._entity_registry) == {"automation.old"}


# ══════════════════════════════════════════════════════════════════════════════
# The automation analyzer
# ══════════════════════════════════════════════════════════════════════════════

class TestAutomationAnalyzer:

    @pytest.mark.asyncio
    async def test_the_reported_finding_is_replaced_by_one_low_finding(self, tmp_path):
        analyzer = await _scan(
            tmp_path,
            [{"id": "1740080290926", **_DISARM}],
            [_automation("automation.house_modes_trigger_disarm_returning_home",
                         "1740080290926", disabled=True)],
        )

        issues = _by_entity(analyzer, "automation.house_modes_trigger_disarm_returning_home")
        assert [(i["type"], i["severity"]) for i in issues] == [("disabled_automation", "low")]
        assert "automations.yaml" in issues[0]["message"], "the message names the file it sits in"
        assert issues[0]["alias"] == "House Mode - Disarm Returning Home"
        assert issues[0] in analyzer.automation_issues

    @pytest.mark.asyncio
    async def test_the_old_copy_no_longer_makes_its_replacement_a_duplicate(self, tmp_path):
        """The usual shape: the old version disabled, its replacement beside it."""
        analyzer = await _scan(
            tmp_path,
            [{"id": "1740080290926", **_DISARM}, {"id": "1750000000000", **_DISARM}],
            [
                _automation("automation.house_modes_trigger_disarm_returning_home",
                            "1740080290926", disabled=True),
                _automation("automation.house_mode_disarm_returning_home", "1750000000000"),
            ],
        )

        types = {i["type"] for i in analyzer.issues}
        assert "duplicate_automation" not in types
        assert "probable_duplicate_automation" not in types
        live = {i["type"] for i in _by_entity(analyzer, "automation.house_mode_disarm_returning_home")}
        assert "device_id_in_target" in live, "the automation that runs is still audited"

    @pytest.mark.asyncio
    async def test_a_turned_off_automation_is_still_audited(self, tmp_path):
        """Off is not disabled: it is loaded, and one click turns it back on."""
        analyzer = await _scan(
            tmp_path,
            [{"id": "42", **_DISARM}],
            [_automation("automation.paused", "42")],
            states={"automation.paused": "off"},
        )
        types = {i["type"] for i in _by_entity(analyzer, "automation.paused")}
        assert "device_id_in_target" in types
        assert "disabled_automation" not in types

    @pytest.mark.asyncio
    async def test_haca_ignore_still_silences_everything(self, tmp_path):
        analyzer = await _scan(
            tmp_path,
            [{"id": "7", **_DISARM}],
            [_automation("automation.old", "7", disabled=True, labels={"haca_ignore"})],
        )
        assert _by_entity(analyzer, "automation.old") == []

    @pytest.mark.asyncio
    async def test_runtime_analyses_get_only_what_home_assistant_loads(self, tmp_path):
        analyzer = await _scan(
            tmp_path,
            [{"id": "1", **_DISARM}, {"id": "2", **_DISARM}],
            [_automation("automation.old", "1", disabled=True), _automation("automation.live", "2")],
        )
        assert set(analyzer.running_automation_configs) == {"automation.live"}
        # The file is unchanged: the secrets scan and the reference walk read all of it.
        assert set(analyzer.automation_configs) == {"automation.old", "automation.live"}
        assert "automation.old" not in {s["entity_id"] for s in analyzer.complexity_scores}


# ══════════════════════════════════════════════════════════════════════════════
# The entity checks a disabled automation used to trigger
# ══════════════════════════════════════════════════════════════════════════════

def _entity_analyzer(hass):
    with patch("custom_components.config_auditor.entity_analyzer.TranslationHelper") as TH:
        TH.return_value.t = _t
        TH.return_value.async_load_language = AsyncMock()
        from custom_components.config_auditor.entity_analyzer import EntityAnalyzer
        analyzer = EntityAnalyzer(hass)
    analyzer._ignored_entity_ids = set()
    analyzer._disabled_automation_ids = analyzer._load_disabled_automation_ids()
    return analyzer


def _uses(entity_id: str) -> dict:
    return {"actions": [{"action": "light.turn_on", "target": {"entity_id": entity_id}}]}


class TestEntityAnalyzer:

    @pytest.mark.asyncio
    async def test_a_missing_entity_only_a_disabled_automation_names_is_no_zombie(self):
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references({"automation.old": _uses("light.gone")}, {})
        await analyzer._analyze_zombie_entities()
        assert analyzer.issues == []

    @pytest.mark.asyncio
    async def test_a_zombie_lists_only_the_automations_that_run(self):
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        hass.add_registry_entry(_automation("automation.live", "2"))
        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(
            {"automation.old": _uses("light.gone"), "automation.live": _uses("light.gone")}, {}
        )
        await analyzer._analyze_zombie_entities()
        assert [(i["type"], i["automation_ids"]) for i in analyzer.issues] == [
            ("zombie_entity", ["automation.live"])
        ]

    @pytest.mark.asyncio
    async def test_a_disabled_entity_only_a_disabled_automation_names_is_not_reported(self):
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        hass.add_registry_entry(MockRegistryEntry("light.porch", disabled_by="user"))
        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references({"automation.old": _uses("light.porch")}, {})
        await analyzer._analyze_entity_registry()
        assert analyzer.issues == []

        # Guardrail: named by an automation that runs, it is reported as before.
        hass.add_registry_entry(_automation("automation.live", "2"))
        await analyzer._build_entity_references(
            {"automation.old": _uses("light.porch"), "automation.live": _uses("light.porch")}, {}
        )
        await analyzer._analyze_entity_registry()
        assert [(i["type"], i["entity_id"]) for i in analyzer.issues] == [
            ("disabled_but_referenced", "light.porch")
        ]

    @pytest.mark.asyncio
    async def test_a_missing_device_in_a_disabled_automation_is_not_reported(self):
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        hass.add_registry_entry(_automation("automation.live", "2"))
        analyzer = _entity_analyzer(hass)
        await analyzer._analyze_device_integrity({
            "automation.old": _DISARM,
            "automation.live": _DISARM,
        })
        assert [(i["type"], i["entity_id"]) for i in analyzer.issues] == [
            ("broken_device_reference", "automation.live")
        ]

    @pytest.mark.asyncio
    async def test_a_helper_only_a_disabled_automation_uses_is_said_so(self):
        """Still used — not 'unused' — but only by automations that do not run."""
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        hass.add_registry_entry(MockRegistryEntry("input_boolean.guest_mode"))
        hass.add_state("input_boolean.guest_mode", "off", {"friendly_name": "Guest mode"})
        configs = {"automation.old": {
            "conditions": [{"condition": "state", "entity_id": "input_boolean.guest_mode",
                            "state": "on"}],
        }}
        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_input_helpers(configs, {})
        types = {i["type"] for i in analyzer.issues if i["entity_id"] == "input_boolean.guest_mode"}
        assert types == {"helper_orphaned_disabled_only"}

    @pytest.mark.asyncio
    async def test_a_timer_only_a_disabled_automation_waits_for_is_not_reported(self):
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        hass.add_registry_entry(_automation("automation.live", "2"))
        hass.add_state("timer.laundry", "idle", {"duration": "0:45:00"})
        waits = {"triggers": [{"platform": "event", "event_type": "timer.finished",
                               "event_data": {"entity_id": "timer.laundry"}}]}

        analyzer = _entity_analyzer(hass)
        await analyzer._analyze_timer_helpers({"automation.old": waits}, {})
        assert analyzer.issues == []

        # Guardrail: an automation that runs and waits for it still raises it.
        await analyzer._analyze_timer_helpers({"automation.old": waits, "automation.live": waits}, {})
        assert [i["type"] for i in analyzer.issues] == ["timer_never_started"]

    @pytest.mark.asyncio
    async def test_analyze_all_reads_the_registry_itself(self):
        """The services.py rescan calls analyze_all without any extra argument."""
        hass = MockHass()
        hass.add_registry_entry(_automation("automation.old", "1", disabled=True))
        with patch("custom_components.config_auditor.entity_analyzer.TranslationHelper") as TH:
            TH.return_value.t = _t
            TH.return_value.async_load_language = AsyncMock()
            from custom_components.config_auditor.entity_analyzer import EntityAnalyzer
            analyzer = EntityAnalyzer(hass)
            issues = await analyzer.analyze_all({"automation.old": _uses("light.gone")}, {})
        assert analyzer._disabled_automation_ids == {"automation.old"}
        assert "zombie_entity" not in {i["type"] for i in issues}
