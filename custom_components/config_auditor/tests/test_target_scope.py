"""A `target:` does not reach every entity behind it — the 1.8.0 field report.

Reported after the 1.8.0 release: the entity count jumped by more than three
hundred, and the weekly report opened on three sensors that a second opinion
said did not exist at all:

    sensor.node_50_successful_commands_rx (disabled_but_referenced)
    sensor.node_50_successful_commands_tx (disabled_but_referenced)
    sensor.node_50_commands_dropped_rx    (disabled_but_referenced)

They do exist. Z-Wave JS creates its RF-statistics sensors disabled, so they
sit in the entity registry and never reach the state machine — which is why
looking them up by state answered "no such entity". What was wrong is the
second half of the sentence: nothing referenced them. Two automations named
their *device*, and `_build_target_indexes` expanded a device target to every
registry entry of that device, disabled ones included.

Three fixes, one class each:

  1  the target indexes skip disabled entries — a target cannot reach one
  2  a target is narrowed by the domain of the service call it belongs to,
     the way Home Assistant narrows it
  3  zombie detection reads the registry, so a disabled entity is reported
     once, as disabled, instead of twice and contradictorily

    pytest custom_components/config_auditor/tests/test_target_scope.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import (
    MockDeviceEntry,
    MockHass,
    MockRegistryEntry,
)


def _hass(tmp_path) -> MockHass:
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    return hass


def _entity_analyzer(hass):
    with patch(
        "custom_components.config_auditor.entity_analyzer.TranslationHelper"
    ) as TH:
        TH.return_value.t = lambda key, **kw: key
        TH.return_value.async_load_language = AsyncMock()
        from custom_components.config_auditor.entity_analyzer import EntityAnalyzer

        analyzer = EntityAnalyzer(hass)
    analyzer._ignored_entity_ids = set()
    return analyzer


_NODE_50_DIAGNOSTICS = (
    "sensor.node_50_successful_commands_rx",
    "sensor.node_50_successful_commands_tx",
    "sensor.node_50_commands_dropped_rx",
)


def _node_50(hass) -> None:
    """The reporter's Z-Wave lock, as Z-Wave JS registers it."""
    hass.add_device(MockDeviceEntry("dev_node50", area_id="mudroom"))
    hass.add_registry_entry(
        MockRegistryEntry("lock.mudroom_door_lock", device_id="dev_node50")
    )
    hass.add_registry_entry(
        MockRegistryEntry("sensor.node_50_last_seen", device_id="dev_node50")
    )
    for diag in _NODE_50_DIAGNOSTICS:
        hass.add_registry_entry(
            MockRegistryEntry(diag, device_id="dev_node50", disabled_by="integration")
        )


# ══════════════════════════════════════════════════════════════════════════════
# 1 — a disabled entity is in no target index
# ══════════════════════════════════════════════════════════════════════════════

class TestDisabledEntitiesAreNotTargets:

    def test_disabled_entry_is_absent_from_all_three_indexes(self, tmp_path):
        hass = _hass(tmp_path)
        hass.add_device(MockDeviceEntry("dev1", area_id="salon"))
        hass.add_registry_entry(
            MockRegistryEntry("light.lamp", device_id="dev1", labels={"night"})
        )
        hass.add_registry_entry(
            MockRegistryEntry(
                "sensor.rf_stats",
                device_id="dev1",
                labels={"night"},
                disabled_by="integration",
            )
        )

        by_device, by_area, by_label = _entity_analyzer(hass)._build_target_indexes()

        assert by_device["dev1"] == {"light.lamp"}
        assert by_area["salon"] == {"light.lamp"}
        assert by_label["night"] == {"light.lamp"}

    @pytest.mark.asyncio
    async def test_the_reported_false_positive_is_gone(self, tmp_path):
        """The three node-50 sensors, against the shape of config that raised them."""
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.lock_at_night": {
                "triggers": [{"platform": "device", "device_id": "dev_node50",
                              "domain": "lock", "type": "unlocked"}],
                "actions": [{"action": "lock.lock",
                             "target": {"device_id": "dev_node50"}}],
            },
            "automation.notify_on_unlock": {
                "triggers": [{"platform": "device", "device_id": "dev_node50",
                              "domain": "lock", "type": "unlocked"}],
                "actions": [{"action": "notify.mobile_app",
                             "data": {"message": "open"}}],
            },
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_entity_registry()

        assert analyzer.issues == [], (
            "a device target never reaches a disabled entity, so none of the "
            "three RF-statistics sensors is 'disabled but referenced'"
        )
        for diag in _NODE_50_DIAGNOSTICS:
            assert diag not in analyzer._entity_references

    @pytest.mark.asyncio
    async def test_a_named_disabled_entity_is_still_reported(self, tmp_path):
        """The fix must not silence the real case the check was written for."""
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.reads_the_counter": {
                "conditions": [{
                    "condition": "numeric_state",
                    "entity_id": "sensor.node_50_commands_dropped_rx",
                    "above": 5,
                }],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_entity_registry()

        assert [i["type"] for i in analyzer.issues] == ["disabled_but_referenced"]
        assert analyzer.issues[0]["entity_id"] == "sensor.node_50_commands_dropped_rx"


# ══════════════════════════════════════════════════════════════════════════════
# 2 — a target is narrowed by the domain of its service call
# ══════════════════════════════════════════════════════════════════════════════

class TestTargetsAreScopedByServiceDomain:

    @pytest.mark.asyncio
    async def test_an_area_wide_light_call_does_not_reference_the_sensors(self, tmp_path):
        hass = _hass(tmp_path)
        hass.add_registry_entry(MockRegistryEntry("light.ceiling", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("sensor.humidity", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("update.tv_firmware", area_id="salon"))
        configs = {
            "automation.evening": {
                "actions": [{"service": "light.turn_on",
                             "target": {"area_id": "salon"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        refs = analyzer._entity_references
        assert "automation.evening" in refs["light.ceiling"]
        assert "sensor.humidity" not in refs, "light.turn_on cannot reach a sensor"
        assert "update.tv_firmware" not in refs

    @pytest.mark.asyncio
    async def test_the_new_action_key_scopes_the_same_way(self, tmp_path):
        hass = _hass(tmp_path)
        hass.add_registry_entry(MockRegistryEntry("light.ceiling", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("sensor.humidity", area_id="salon"))
        configs = {
            "automation.evening": {
                "actions": [{"action": "light.turn_on",
                             "target": {"area_id": "salon"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        assert "automation.evening" in analyzer._entity_references["light.ceiling"]
        assert "sensor.humidity" not in analyzer._entity_references

    @pytest.mark.asyncio
    async def test_a_device_trigger_is_scoped_by_its_own_domain(self, tmp_path):
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.on_unlock": {
                "triggers": [{"platform": "device", "device_id": "dev_node50",
                              "domain": "lock", "type": "unlocked"}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        refs = analyzer._entity_references
        assert "automation.on_unlock" in refs["lock.mudroom_door_lock"]
        assert "sensor.node_50_last_seen" not in refs, \
            "a lock device trigger does not reference the node's last_seen sensor"

    @pytest.mark.asyncio
    async def test_a_service_outside_the_entity_domains_keeps_the_whole_device(self, tmp_path):
        """`zwave_js.set_value` acts on the device, not through a zwave_js entity.

        Its domain holds no entity at all, so narrowing by it would resolve the
        target to nothing. The expansion is left alone instead — over-reporting
        a reference is recoverable, calling a used helper unused is not.
        """
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.tune_node": {
                "actions": [{"action": "zwave_js.set_value",
                             "target": {"device_id": "dev_node50"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        refs = analyzer._entity_references
        assert "automation.tune_node" in refs["lock.mudroom_door_lock"]
        assert "automation.tune_node" in refs["sensor.node_50_last_seen"]

    @pytest.mark.asyncio
    async def test_a_bare_target_without_a_service_is_unscoped(self, tmp_path):
        """Nothing in scope names a domain, so nothing narrows the expansion."""
        hass = _hass(tmp_path)
        hass.add_registry_entry(MockRegistryEntry("light.ceiling", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("sensor.humidity", area_id="salon"))
        configs = {"automation.plain": {"actions": [{"target": {"area_id": "salon"}}]}}

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        refs = analyzer._entity_references
        assert "automation.plain" in refs["light.ceiling"]
        assert "automation.plain" in refs["sensor.humidity"]

    @pytest.mark.asyncio
    async def test_scope_does_not_leak_between_sibling_actions(self, tmp_path):
        hass = _hass(tmp_path)
        hass.add_registry_entry(MockRegistryEntry("light.ceiling", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("switch.pump", area_id="salon"))
        configs = {
            "automation.two_calls": {
                "actions": [
                    {"service": "light.turn_on", "target": {"area_id": "salon"}},
                    {"service": "switch.turn_on", "target": {"area_id": "salon"}},
                ],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        refs = analyzer._entity_references
        assert "automation.two_calls" in refs["light.ceiling"]
        assert "automation.two_calls" in refs["switch.pump"]


# ══════════════════════════════════════════════════════════════════════════════
# 3 — a disabled entity is not a zombie
# ══════════════════════════════════════════════════════════════════════════════

class TestDisabledEntityIsNotAZombie:

    @pytest.mark.asyncio
    async def test_a_named_disabled_entity_is_not_reported_missing(self, tmp_path):
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.reads_the_counter": {
                "actions": [{"service": "system_log.write",
                             "data": {"message": "x"},
                             "entity_id": "sensor.node_50_commands_dropped_rx"}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_zombie_entities()

        assert analyzer.issues == [], (
            "the entity is in the registry, disabled — _analyze_entity_registry "
            "reports it, and saying it does not exist contradicts that"
        )

    @pytest.mark.asyncio
    async def test_a_genuinely_removed_entity_is_still_a_zombie(self, tmp_path):
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.stale": {
                "actions": [{"service": "light.turn_on",
                             "entity_id": "light.removed_last_year"}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_zombie_entities()

        assert [i["type"] for i in analyzer.issues] == ["zombie_entity"]
        assert analyzer.issues[0]["entity_id"] == "light.removed_last_year"

    @pytest.mark.asyncio
    async def test_one_issue_not_two_for_the_same_entity(self, tmp_path):
        """The pair used to fire together: 'does not exist' and 'is disabled'."""
        hass = _hass(tmp_path)
        _node_50(hass)
        configs = {
            "automation.reads_the_counter": {
                "conditions": [{"condition": "state",
                                "entity_id": "sensor.node_50_successful_commands_rx",
                                "state": "0"}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_zombie_entities()
        await analyzer._analyze_entity_registry()

        types = [i["type"] for i in analyzer.issues]
        assert types == ["disabled_but_referenced"], types
