"""A device block is rewritten on its entity the way Home Assistant runs it.

The previous conversion knew a dozen trigger types and two condition types.
The rest came out wrong while Home Assistant's validator accepted it: a
binary_sensor `is_open` became a state condition with no `state:`, a ZHA button
press a state trigger with no `to:` on the device's first entity, a light
`brightness_increase` a call to `light.brightness_increase`, and a trigger's
`id:` -- the one `trigger.id` reads -- was dropped. Every expectation below is
taken from the domain's own device_trigger / device_condition / device_action
module in Home Assistant 2026.9.

    pytest custom_components/config_auditor/tests/test_device_conversion.py -v
"""
from __future__ import annotations

import contextlib
import copy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor import device_conversion as dc
from custom_components.config_auditor.tests.conftest import MockHass, MockRegistryEntry

pytest.importorskip("homeassistant", reason="the tables mirror Home Assistant's modules")


@pytest.fixture
def hass():
    hass = MockHass()
    hass.add_registry_entry(MockRegistryEntry("binary_sensor.door", registry_id="aaa111"))
    return hass


def _device(domain: str, kind: str, entity: str | None = None, **extra) -> dict:
    block = {"device_id": "dev1", "domain": domain, "type": kind, **extra}
    if entity:
        block["entity_id"] = entity
    return block


def _trigger(domain, kind, entity=None, **extra):
    return {"trigger": "device", **_device(domain, kind, entity, **extra)}


def _condition(domain, kind, entity=None, **extra):
    return {"condition": "device", **_device(domain, kind, entity, **extra)}


# ═══════════════════════════════════════════════════════════════════════════
# Triggers
# ═══════════════════════════════════════════════════════════════════════════

class TestTriggers:
    @pytest.mark.parametrize("trigger, expected", [
        # binary_sensor: HA's own TURNED_ON / TURNED_OFF lists, every device class
        (_trigger("binary_sensor", "opened", "binary_sensor.door"),
         {"trigger": "state", "entity_id": "binary_sensor.door", "to": "on"}),
        (_trigger("binary_sensor", "not_opened", "binary_sensor.door"),
         {"trigger": "state", "entity_id": "binary_sensor.door", "to": "off"}),
        (_trigger("binary_sensor", "no_motion", "binary_sensor.hall"),
         {"trigger": "state", "entity_id": "binary_sensor.hall", "to": "off"}),
        (_trigger("light", "turned_on", "light.kitchen"),
         {"trigger": "state", "entity_id": "light.kitchen", "to": "on"}),
        # any change of state, not of an attribute
        (_trigger("switch", "changed_states", "switch.pump"),
         {"trigger": "state", "entity_id": "switch.pump", "to": None}),
        (_trigger("media_player", "playing", "media_player.tv"),
         {"trigger": "state", "entity_id": "media_player.tv", "to": "playing"}),
        (_trigger("alarm_control_panel", "armed_away", "alarm_control_panel.home"),
         {"trigger": "state", "entity_id": "alarm_control_panel.home", "to": "armed_away"}),
        (_trigger("cover", "opened", "cover.garage"),
         {"trigger": "state", "entity_id": "cover.garage", "to": "open"}),
        (_trigger("lock", "unlocked", "lock.front"),
         {"trigger": "state", "entity_id": "lock.front", "to": "unlocked"}),
        (_trigger("vacuum", "docked", "vacuum.robot"),
         {"trigger": "state", "entity_id": "vacuum.robot", "to": "docked"}),
        (_trigger("select", "current_option_changed", "select.mode", to="eco", **{"from": "comfort"}),
         {"trigger": "state", "entity_id": "select.mode", "from": "comfort", "to": "eco"}),
        # a button trigger has no `to:` -- the state is the press time
        (_trigger("button", "pressed", "button.ring"),
         {"trigger": "state", "entity_id": "button.ring"}),
        (_trigger("device_tracker", "enters", "device_tracker.phone", zone="zone.home"),
         {"trigger": "zone", "entity_id": "device_tracker.phone", "zone": "zone.home", "event": "enter"}),
        (_trigger("sensor", "temperature", "sensor.salon", above=20),
         {"trigger": "numeric_state", "entity_id": "sensor.salon", "above": 20}),
        (_trigger("climate", "current_temperature_changed", "climate.salon", below=18),
         {"trigger": "numeric_state", "entity_id": "climate.salon",
          "attribute": "current_temperature", "below": 18}),
        (_trigger("humidifier", "target_humidity_changed", "humidifier.room", above=40),
         {"trigger": "numeric_state", "entity_id": "humidifier.room", "attribute": "humidity", "above": 40}),
        (_trigger("cover", "position", "cover.garage", above=50),
         {"trigger": "numeric_state", "entity_id": "cover.garage", "attribute": "current_position", "above": 50}),
    ])
    def test_converted_as_home_assistant_attaches_it(self, hass, trigger, expected):
        conversion = dc.convert_trigger(hass, trigger)
        assert conversion.new == expected, conversion.note

    def test_hvac_mode_changed_fires_from_every_other_mode_only(self, hass):
        conversion = dc.convert_trigger(
            hass, _trigger("climate", "hvac_mode_changed", "climate.salon", to="heat")
        )
        assert conversion.new["to"] == "heat"
        assert conversion.new["from"] == ["off", "cool", "heat_cool", "auto", "dry", "fan_only"]

    def test_the_trigger_id_and_the_duration_survive(self, hass):
        """`trigger.id` is what a `choose:` reads; losing it breaks the automation."""
        conversion = dc.convert_trigger(hass, _trigger(
            "binary_sensor", "opened", "binary_sensor.door",
            id="door_open", alias="Door", enabled=False, **{"for": {"minutes": 2}},
        ))
        assert conversion.new == {
            "trigger": "state", "entity_id": "binary_sensor.door", "to": "on",
            "for": {"minutes": 2}, "id": "door_open", "alias": "Door", "enabled": False,
        }

    def test_for_is_dropped_where_home_assistant_ignores_it(self, hass):
        conversion = dc.convert_trigger(
            hass, _trigger("cover", "position", "cover.garage", above=50, **{"for": "00:01:00"})
        )
        assert "for" not in conversion.new

    def test_the_platform_key_follows_the_one_the_device_trigger_used(self, hass):
        trigger = {"platform": "device", **_device("light", "turned_off", "light.kitchen")}
        assert dc.convert_trigger(hass, trigger).new["platform"] == "state"

    def test_a_registry_uuid_is_resolved_to_its_entity(self, hass):
        """What HA's editor writes: the registry entry's id, not the entity_id."""
        conversion = dc.convert_trigger(hass, _trigger("binary_sensor", "opened", "aaa111"))
        assert conversion.new["entity_id"] == "binary_sensor.door"

    @pytest.mark.parametrize("trigger, reason", [
        # an integration's own event: nothing to watch on an entity
        ({"trigger": "device", "device_id": "dev1", "domain": "zha",
          "type": "remote_button_short_press", "subtype": "turn_on"}, "zha integration itself"),
        ({"trigger": "device", "device_id": "dev1", "domain": "mqtt",
          "type": "button_short_press", "subtype": "button_1", "discovery_id": "x"}, "mqtt integration itself"),
        (_trigger("light", "flickered", "light.kitchen"), "no entity-based equivalent"),
        (_trigger("binary_sensor", "opened", "ffff0000"), "no longer in the registry"),
        (_trigger("light", "turned_on", "switch.pump"), "not a light entity"),
        (_trigger("sensor", "temperature", "sensor.salon"), "no entity-based equivalent"),
        (_trigger("device_tracker", "enters", "device_tracker.phone"), "no entity-based equivalent"),
    ])
    def test_what_has_no_equivalent_stays_with_its_reason(self, hass, trigger, reason):
        conversion = dc.convert_trigger(hass, trigger)
        assert conversion.new is None
        assert reason in conversion.note


# ═══════════════════════════════════════════════════════════════════════════
# Conditions
# ═══════════════════════════════════════════════════════════════════════════

class TestConditions:
    @pytest.mark.parametrize("condition, expected", [
        # the case the validator caught: `is_open` had no state mapping
        (_condition("binary_sensor", "is_open", "binary_sensor.door"),
         {"condition": "state", "entity_id": "binary_sensor.door", "state": "on"}),
        (_condition("binary_sensor", "is_no_motion", "binary_sensor.hall"),
         {"condition": "state", "entity_id": "binary_sensor.hall", "state": "off"}),
        (_condition("switch", "is_off", "switch.pump", **{"for": {"minutes": 5}}),
         {"condition": "state", "entity_id": "switch.pump", "state": "off", "for": {"minutes": 5}}),
        # fan's own condition ignores `for`
        (_condition("fan", "is_on", "fan.ceiling", **{"for": {"minutes": 5}}),
         {"condition": "state", "entity_id": "fan.ceiling", "state": "on"}),
        (_condition("vacuum", "is_cleaning", "vacuum.robot"),
         {"condition": "state", "entity_id": "vacuum.robot", "state": ["cleaning", "returning"]}),
        (_condition("alarm_control_panel", "is_armed_custom_bypass", "alarm_control_panel.home"),
         {"condition": "state", "entity_id": "alarm_control_panel.home", "state": "armed_custom_bypass"}),
        (_condition("lock", "is_jammed", "lock.front"),
         {"condition": "state", "entity_id": "lock.front", "state": "jammed"}),
        (_condition("device_tracker", "is_not_home", "device_tracker.phone"),
         {"condition": "not", "conditions": [
             {"condition": "state", "entity_id": "device_tracker.phone", "state": "home"}]}),
        (_condition("climate", "is_hvac_mode", "climate.salon", hvac_mode="heat"),
         {"condition": "state", "entity_id": "climate.salon", "state": "heat"}),
        (_condition("climate", "is_preset_mode", "climate.salon", preset_mode="eco"),
         {"condition": "state", "entity_id": "climate.salon", "attribute": "preset_mode", "state": "eco"}),
        (_condition("humidifier", "is_mode", "humidifier.room", mode="sleep"),
         {"condition": "state", "entity_id": "humidifier.room", "attribute": "mode", "state": "sleep"}),
        (_condition("select", "selected_option", "select.mode", option="eco"),
         {"condition": "state", "entity_id": "select.mode", "state": "eco"}),
        (_condition("cover", "is_tilt_position", "cover.blind", below=30),
         {"condition": "numeric_state", "entity_id": "cover.blind",
          "attribute": "current_tilt_position", "below": 30}),
        (_condition("sensor", "is_temperature", "sensor.salon", above=19, below=24),
         {"condition": "numeric_state", "entity_id": "sensor.salon", "above": 19, "below": 24}),
    ])
    def test_converted_as_home_assistant_evaluates_it(self, hass, condition, expected):
        conversion = dc.convert_condition(hass, condition)
        assert conversion.new == expected, conversion.note

    def test_alias_and_enabled_survive(self, hass):
        conversion = dc.convert_condition(
            hass, _condition("light", "is_on", "light.kitchen", alias="Lit", enabled=False)
        )
        assert conversion.new["alias"] == "Lit" and conversion.new["enabled"] is False

    def test_a_climate_mode_condition_without_its_mode_stays(self, hass):
        conversion = dc.convert_condition(hass, _condition("climate", "is_hvac_mode", "climate.salon"))
        assert conversion.new is None


# ═══════════════════════════════════════════════════════════════════════════
# Actions
# ═══════════════════════════════════════════════════════════════════════════

class TestActions:
    @pytest.mark.parametrize("action, expected", [
        # `brightness_increase` is not a service; HA calls light.turn_on
        (_device("light", "brightness_increase", "light.kitchen"),
         {"action": "light.turn_on", "target": {"entity_id": "light.kitchen"},
          "data": {"brightness_step_pct": 10}}),
        (_device("light", "turn_on", "light.kitchen", brightness_pct=40),
         {"action": "light.turn_on", "target": {"entity_id": "light.kitchen"},
          "data": {"brightness_pct": 40}}),
        (_device("light", "flash", "light.kitchen"),
         {"action": "light.turn_on", "target": {"entity_id": "light.kitchen"}, "data": {"flash": "short"}}),
        (_device("switch", "toggle", "switch.pump"),
         {"action": "switch.toggle", "target": {"entity_id": "switch.pump"}}),
        (_device("cover", "open", "cover.garage"),
         {"action": "cover.open_cover", "target": {"entity_id": "cover.garage"}}),
        # the device action calls it `position` for the tilt too
        (_device("cover", "set_tilt_position", "cover.blind", position=40),
         {"action": "cover.set_cover_tilt_position", "target": {"entity_id": "cover.blind"},
          "data": {"tilt_position": 40}}),
        (_device("alarm_control_panel", "arm_away", "alarm_control_panel.home", code="1234"),
         {"action": "alarm_control_panel.alarm_arm_away",
          "target": {"entity_id": "alarm_control_panel.home"}, "data": {"code": "1234"}}),
        (_device("vacuum", "clean", "vacuum.robot"),
         {"action": "vacuum.start", "target": {"entity_id": "vacuum.robot"}}),
        (_device("select", "select_next", "select.mode"),
         {"action": "select.select_next", "target": {"entity_id": "select.mode"}, "data": {"cycle": True}}),
        (_device("climate", "set_hvac_mode", "climate.salon", hvac_mode="heat"),
         {"action": "climate.set_hvac_mode", "target": {"entity_id": "climate.salon"},
          "data": {"hvac_mode": "heat"}}),
        (_device("number", "set_value", "number.volume", value=12),
         {"action": "number.set_value", "target": {"entity_id": "number.volume"}, "data": {"value": 12}}),
        (_device("button", "press", "button.ring"),
         {"action": "button.press", "target": {"entity_id": "button.ring"}}),
    ])
    def test_converted_as_home_assistant_calls_it(self, hass, action, expected):
        conversion = dc.convert_action(hass, action, service_key="action")
        assert conversion.new == expected, conversion.note

    def test_editor_metadata_never_reaches_the_service_data(self, hass):
        """Every unknown key used to be poured into `data:`, `metadata: {}` included."""
        action = _device("light", "turn_off", "light.kitchen", metadata={}, alias="Off", continue_on_error=True)
        assert dc.convert_action(hass, action, service_key="action").new == {
            "action": "light.turn_off", "target": {"entity_id": "light.kitchen"},
            "alias": "Off", "continue_on_error": True,
        }

    def test_the_service_key_is_the_one_asked_for(self, hass):
        action = _device("lock", "unlock", "lock.front")
        assert dc.convert_action(hass, action, service_key="service").new["service"] == "lock.unlock"

    @pytest.mark.parametrize("action, reason", [
        ({"device_id": "dev1", "domain": "zwave_js", "type": "set_config_parameter",
          "endpoint": 0, "parameter": 3, "value": 1}, "zwave_js integration itself"),
        (_device("climate", "set_hvac_mode", "climate.salon"), "has no 'hvac_mode'"),
        (_device("light", "dance", "light.kitchen"), "no entity-based equivalent"),
    ])
    def test_what_has_no_equivalent_stays_with_its_reason(self, hass, action, reason):
        conversion = dc.convert_action(hass, action, service_key="action")
        assert conversion.new is None
        assert reason in conversion.note


# ═══════════════════════════════════════════════════════════════════════════
# target: device_id
# ═══════════════════════════════════════════════════════════════════════════

@contextlib.contextmanager
def _device_holds(*entity_ids):
    with patch.object(dc, "_device_entities", return_value=set(entity_ids)) as resolved:
        yield resolved


class TestDeviceTarget:
    def test_every_entity_of_the_service_domain_not_the_first_one(self, hass):
        """A device with two lights: the old conversion kept one of them."""
        action = {"action": "light.turn_on", "target": {"device_id": "dev1"}, "data": {"brightness_pct": 50}}
        with _device_holds("light.b", "light.a", "sensor.power", "switch.relay"):
            conversion = dc.convert_device_target(hass, action)
        assert conversion.new == {
            "action": "light.turn_on", "target": {"entity_id": ["light.a", "light.b"]},
            "data": {"brightness_pct": 50},
        }

    def test_the_entities_already_named_are_kept_first(self, hass):
        action = {"service": "light.turn_off", "target": {"device_id": ["dev1"], "entity_id": "light.hall"}}
        with _device_holds("light.a"):
            conversion = dc.convert_device_target(hass, action)
        assert conversion.new["target"] == {"entity_id": ["light.hall", "light.a"]}

    @pytest.mark.parametrize("action, held, reason", [
        ({"action": "homeassistant.turn_on", "target": {"device_id": "dev1"}}, ("light.a",), "every domain"),
        ({"action": "zwave_js.set_value", "target": {"device_id": "dev1"}}, ("light.a",), "no zwave_js entity"),
        ({"action": "light.turn_on", "target": {"device_id": "dev1"}}, ("sensor.power",), "no light entity"),
        ({"action": "light.turn_on", "target": {"device_id": "{{ d }}"}}, ("light.a",), "template"),
    ])
    def test_what_has_no_equivalent_stays_with_its_reason(self, hass, action, held, reason):
        with _device_holds(*held):
            conversion = dc.convert_device_target(hass, action)
        assert conversion.new is None
        assert reason in conversion.note

    def test_resolution_is_home_assistants_own(self, hass):
        """No home-made expansion: HA's resolver, with its child devices and filters."""
        selected = MagicMock(indirectly_referenced={"light.a", "sensor.x"})
        with patch(
            "homeassistant.helpers.target.async_extract_referenced_entity_ids",
            return_value=selected,
        ) as resolve:
            assert dc._device_entities(hass, ["dev1", "dev2"]) == {"light.a", "sensor.x"}
        selection = resolve.call_args.args[1]
        assert selection.device_ids == {"dev1", "dev2"}
        assert resolve.call_args.kwargs == {"expand_group": False}


# ═══════════════════════════════════════════════════════════════════════════
# Nested blocks: found where HA reads them, written back where they were
# ═══════════════════════════════════════════════════════════════════════════

LIGHT_ON = _condition("light", "is_on", "light.kitchen")
SWITCH_OFF = _condition("switch", "is_off", "switch.pump")
TOGGLE = _device("switch", "toggle", "switch.pump")

# Every nesting HA's config_validation reads, each spelled the short way where
# it has one: a single block in place of a list, `or:` for `condition: or`,
# `condition: [...]` for `and`, a list as a parallel branch.
NESTED = {
    "triggers": [{"triggers": [_trigger("light", "turned_on", "light.kitchen")]}],
    "conditions": [{"or": [LIGHT_ON]}],
    "actions": [
        {"choose": [{"conditions": LIGHT_ON, "sequence": [TOGGLE]}],
         "default": {"action": "light.turn_on", "target": {"device_id": "dev1"}}},
        {"if": [SWITCH_OFF],
         "then": [{"repeat": {
             "until": [{"condition": [SWITCH_OFF]}],
             "sequence": [{"wait_for_trigger": _trigger("switch", "turned_on", "switch.pump")}],
         }}],
         "else": [{"sequence": [LIGHT_ON]}]},
        {"parallel": [[TOGGLE], {"sequence": [TOGGLE]}]},
        {"variables": {"device_id": "not a block"}},
    ],
}


def _device_blocks(automation):
    return [
        (dc.location(b.path), b.role, dc.device_reference(b.role, b.config))
        for b in dc.iter_blocks(automation)
        if dc.device_reference(b.role, b.config)
    ]


class TestNestedBlocks:
    def test_every_device_block_is_found_with_its_role(self):
        assert _device_blocks(NESTED) == [
            ("trigger[0].triggers[0]", "trigger", "device_id"),
            ("condition[0].or[0]", "condition", "device_id"),
            ("action[0].choose[0].conditions[0]", "condition", "device_id"),
            ("action[0].choose[0].sequence[0]", "action", "device_id"),
            ("action[0].default[0]", "action", "target"),
            ("action[1].if[0]", "condition", "device_id"),
            ("action[1].then[0].repeat.until[0].condition[0]", "condition", "device_id"),
            ("action[1].then[0].repeat.sequence[0].wait_for_trigger[0]", "trigger", "device_id"),
            ("action[1].else[0].sequence[0]", "condition", "device_id"),
            ("action[2].parallel[0][0]", "action", "device_id"),
            ("action[2].parallel[1].sequence[0]", "action", "device_id"),
        ]

    def test_a_condition_used_as_an_action_step_is_converted_as_a_condition(self, hass):
        """It went to the action table, found no `is_on` action and was left alone."""
        found = dc.find(hass, {"actions": [LIGHT_ON]}, service_key="action")
        assert [(b.role, c.new) for b, c in found] == [
            ("condition", {"condition": "state", "entity_id": "light.kitchen", "state": "on"}),
        ]

    def test_every_location_reads_back_as_its_path(self):
        for block in dc.iter_blocks(NESTED):
            assert dc.parse_location(dc.location(block.path)) == block.path

    @pytest.mark.parametrize("text, path", [
        ("action[0]", ("action", 0)),
        ("action[3].target", ("action", 3)),  # the device_id-in-target issue's
        ("action[1].then[0].repeat.sequence[0]", ("action", 1, "then", 0, "repeat", "sequence", 0)),
        ("root", None),
        ("trigger", None),
        ("mode", None),
        ("action[x]", None),
    ])
    def test_a_location_names_a_block_or_nothing(self, text, path):
        assert dc.parse_location(text) == path

    def test_a_scope_keeps_the_blocks_under_it(self, hass):
        found = dc.find(hass, NESTED, service_key="action", scope=("action", 0, "choose"))
        assert [dc.location(b.path) for b, _ in found] == [
            "action[0].choose[0].conditions[0]", "action[0].choose[0].sequence[0]",
        ]

    def test_a_block_is_replaced_where_it_was(self):
        automation = copy.deepcopy(NESTED)
        path = ("action", 1, "then", 0, "repeat", "sequence", 0, "wait_for_trigger", 0)
        assert dc.replace(automation, path, {"trigger": "state", "entity_id": "switch.pump"})
        # One block in place of a list stays one block.
        assert automation["actions"][1]["then"][0]["repeat"]["sequence"][0] == {
            "wait_for_trigger": {"trigger": "state", "entity_id": "switch.pump"},
        }
        assert dc.replace(automation, ("action", 2, "parallel", 0, 0), {"action": "switch.toggle"})
        assert automation["actions"][2]["parallel"][0] == [{"action": "switch.toggle"}]
        replaced = {"action[1].then[0].repeat.sequence[0].wait_for_trigger[0]", "action[2].parallel[0][0]"}
        assert _device_blocks(automation) == [b for b in _device_blocks(NESTED) if b[0] not in replaced]

    @pytest.mark.parametrize("path", [
        ("action", 3),                           # no device there
        ("action", 0, "choose", 1, "sequence", 0),  # no second option
        ("action", 9),
        ("condition", 0, "and", 0),
        ("mode", 0),
    ])
    def test_a_path_that_leads_to_no_device_block_changes_nothing(self, path):
        automation = copy.deepcopy(NESTED)
        assert dc.replace(automation, path, {"action": "light.turn_on"}) is False
        assert automation == NESTED
