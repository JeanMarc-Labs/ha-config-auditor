"""Every write of an automation, script or scene is checked the way HA's editor checks it.

`_safe_edit_and_reload` rolls a file back when the reload fails, but a reload
does not fail on one invalid automation: Home Assistant disables it, logs, and
succeeds. The MCP tool then reported success on an automation that was offline.
An entry is now validated first -- as Home Assistant will read it back from the
file -- and one it would reject is not written.

The panel's zombie-entity fix writes and reloads too, and goes through the same
`yaml_writer.async_write_and_reload`: it had neither the check nor the rollback.
The device_id, mode, template and description fixes leave the reload to the
user, so HA disabled a broken result only then; they go through
`yaml_writer.async_write_checked`.

    pytest custom_components/config_auditor/tests/test_write_validation.py -v
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor import yaml_writer as yw
from custom_components.config_auditor.tests.conftest import MockHass

pytest.importorskip("ruamel.yaml", reason="the write path round-trips through ruamel")
pytest.importorskip("homeassistant", reason="the validators are Home Assistant's own")

import voluptuous as vol  # after Home Assistant, which may alias it


@contextlib.asynccontextmanager
async def _real_hass(tmp_path):
    """A bare Home Assistant, set up just enough to run its config validators."""
    from homeassistant import loader
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import condition, trigger

    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    for helper in (trigger, condition):
        if hasattr(helper, "async_setup"):
            await helper.async_setup(hass)
    try:
        yield hass
    finally:
        await hass.async_stop(force=True)


def _from_file(tmp_path, text: str, shape=list):
    """An entry as HACA holds it after reading a file the user wrote."""
    path = tmp_path / "entries.yaml"
    path.write_text(text, encoding="utf-8")
    target = yw.read_for_edit(str(path), shape)
    return target.yaml, target.document


def _new(entry):
    return yw.roundtrip_yaml(), entry


STATE_TRIGGER = {"trigger": "state", "entity_id": "light.x"}


# ═══════════════════════════════════════════════════════════════════════════
# The validators are Home Assistant's own
# ═══════════════════════════════════════════════════════════════════════════

class TestHomeAssistantsVerdict:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("domain, key, source", [
        ("automation", "a", lambda tmp: _new({
            "id": "a", "alias": "A",
            "triggers": [{**STATE_TRIGGER, "from": "on", "to": "off"}, {"trigger": "time", "at": "22:00:00"}],
            "conditions": [{"condition": "state", "entity_id": "input_boolean.away", "state": "off"}],
            "actions": [{"action": "light.turn_on"}],
        })),
        ("script", "s", lambda tmp: _new({"alias": "S", "sequence": [{"delay": "00:05:00"}]})),
        ("scene", None, lambda tmp: _new({"id": "s", "name": "S", "entities": {"light.a": "off"}})),
    ])
    async def test_a_valid_entry_is_accepted(self, tmp_path, domain, key, source):
        yaml, entry = source(tmp_path)
        async with _real_hass(tmp_path) as hass:
            assert await yw.async_validation_error(hass, domain, yaml, entry, key) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("domain, key, source, expected", [
        # Bare in the file: HA reads False and a base-60 number. The entry is
        # checked as HA reads it, not as HACA holds it (the strings).
        ("automation", "a", lambda tmp: _from_file(
            tmp, "- id: a\n  triggers:\n    - trigger: state\n      entity_id: light.x\n      to: off\n  actions: []\n",
        ), "expected str at 'to'"),
        ("automation", "a", lambda tmp: _from_file(
            tmp, "- id: a\n  triggers:\n    - trigger: time\n      at: 22:00:00\n  actions: []\n",
        ), "at[0]"),
        ("automation", "a", lambda tmp: _new({"id": "a", "triggers": [{"trigger": "state"}], "actions": []}),
         "entity_id"),
        ("script", "s", lambda tmp: _new({"alias": "S", "sequence": [{"delay": "not a delay"}]}), "delay"),
        ("scene", None, lambda tmp: _new({"id": "s", "name": "S", "entities": {"not an entity": "off"}}),
         "invalid entity ID"),
    ])
    async def test_an_entry_home_assistant_would_disable_is_rejected(
        self, tmp_path, domain, key, source, expected
    ):
        yaml, document = source(tmp_path)
        entry = document[0] if isinstance(document, list) else document
        async with _real_hass(tmp_path) as hass:
            error = await yw.async_validation_error(hass, domain, yaml, entry, key)
        assert error is not None and expected in error, error

    @pytest.mark.asyncio
    async def test_a_validator_that_cannot_run_does_not_block_the_write(self):
        """Only a validation error counts; the reload and its rollback cover the rest."""
        hass = MockHass()
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(side_effect=RuntimeError("no integrations loaded")),
        ):
            error = await yw.async_validation_error(
                hass, "automation", yw.roundtrip_yaml(), {"id": "a"}, "a"
            )
        assert error is None


# ═══════════════════════════════════════════════════════════════════════════
# Through the tools: a rejected entry leaves the file and HA untouched
# ═══════════════════════════════════════════════════════════════════════════

AUTOMATIONS = "# mine\n- id: clima\n  alias: Clima\n  triggers: []\n  actions: []\n"


def _hass(tmp_path, files: dict) -> MockHass:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    return hass


def _reloaded(hass) -> bool:
    return any(call.args[1:2] == ("reload",) for call in hass.services.async_call.await_args_list)


def _rejects(message: str):
    return patch(
        "homeassistant.components.automation.config.async_validate_config_item",
        AsyncMock(side_effect=vol.Invalid(message)),
    )


class TestToolsDoNotWriteWhatHomeAssistantRejects:
    @pytest.mark.asyncio
    async def test_update_automation(self, tmp_path):
        from custom_components.config_auditor.mcp_server import tools_automation

        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": AUTOMATIONS,
        })
        with _rejects("expected str at 'to'"):
            result = await tools_automation._tool_ha_update_automation(hass, {
                "entity_id": "automation.clima", "triggers": [STATE_TRIGGER],
            })

        assert "Home Assistant rejects this automation" in result.get("error", ""), result
        assert "expected str at 'to'" in result["error"]
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == AUTOMATIONS
        assert not _reloaded(hass)

    @pytest.mark.asyncio
    async def test_create_automation(self, tmp_path):
        from custom_components.config_auditor.mcp_server import tools_automation

        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": AUTOMATIONS,
        })
        with _rejects("required key not provided at 'entity_id'"):
            result = await tools_automation._tool_ha_create_automation(hass, {
                "alias": "New", "triggers": [{"trigger": "state"}],
                "actions": [{"action": "light.turn_on"}],
            })

        assert "Home Assistant rejects this automation" in result.get("error", ""), result
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == AUTOMATIONS
        assert not _reloaded(hass)

    @pytest.mark.asyncio
    async def test_create_scene_with_the_real_validator(self, tmp_path):
        """The scene validator needs no running Home Assistant: nothing is patched."""
        from custom_components.config_auditor.mcp_server import tools_script_scene

        scenes = "- id: soir\n  name: Evening\n  entities: {}\n"
        hass = _hass(tmp_path, {
            "configuration.yaml": "scene: !include scenes.yaml\n",
            "scenes.yaml": scenes,
        })
        result = await tools_script_scene._tool_ha_create_scene(hass, {
            "name": "Night", "entities": {"not an entity": "off"},
        })

        assert "Home Assistant rejects this scene" in result.get("error", ""), result
        assert (tmp_path / "scenes.yaml").read_text(encoding="utf-8") == scenes
        assert not _reloaded(hass)

    @pytest.mark.asyncio
    async def test_a_valid_entry_is_still_written_and_reloaded(self, tmp_path):
        from custom_components.config_auditor.mcp_server import tools_automation

        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": AUTOMATIONS,
        })
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(return_value=None),
        ) as validator:
            result = await tools_automation._tool_ha_update_automation(hass, {
                "entity_id": "automation.clima", "mode": "restart",
            })

        assert result.get("success") is True, result
        validator.assert_awaited_once()
        assert "mode: restart" in (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert _reloaded(hass)

    @pytest.mark.asyncio
    async def test_a_removal_is_not_validated(self, tmp_path):
        """Removing an entry cannot make it invalid, and must work on a broken one."""
        from custom_components.config_auditor.mcp_server import tools_automation

        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": AUTOMATIONS,
        })
        with _rejects("anything"):
            result = await tools_automation._tool_ha_remove_automation(hass, {"entity_id": "clima"})

        assert result.get("success") is True, result
        assert "Clima" not in (tmp_path / "automations.yaml").read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# The panel's zombie-entity fix goes through the same check and rollback
# ═══════════════════════════════════════════════════════════════════════════

EVIER = (
    "# mine\n"
    "- id: evier\n"
    "  alias: Evier\n"
    "  triggers:\n"
    "    - trigger: state\n"
    "      entity_id: light.evier\n"
    "  actions:\n"
    "    - action: light.turn_on\n"
    "      target:\n"
    "        entity_id: light.cuisine\n"
)
EVIER_FILES = {
    "configuration.yaml": "automation: !include automations.yaml\n",
    "automations.yaml": EVIER,
}


def _assistant(hass):
    from custom_components.config_auditor.refactoring_assistant import RefactoringAssistant

    return RefactoringAssistant(hass)


def _backups(tmp_path) -> list[str]:
    folder = tmp_path / ".haca_backups"
    return sorted(os.listdir(folder)) if folder.is_dir() else []


@contextlib.asynccontextmanager
async def _real_hass_with_reload(tmp_path):
    """HA's real validators, and an `automation.reload` that records its calls."""
    for name, text in EVIER_FILES.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    async with _real_hass(tmp_path) as hass:
        reloads = []

        async def _reload(call):
            reloads.append(call)

        hass.services.async_register("automation", "reload", _reload)
        yield hass, reloads


class TestZombieFix:
    @pytest.mark.asyncio
    async def test_removing_the_only_entity_of_a_trigger_is_refused(self, tmp_path):
        """A state trigger left with no entity is one HA disables on a reload that succeeds."""
        async with _real_hass_with_reload(tmp_path) as (hass, reloads):
            result = await _assistant(hass).apply_zombie_entity_fix("evier", "light.evier", "")

        assert result["success"] is False, result
        assert "Home Assistant rejects this automation" in result["error"]
        assert "entity_id" in result["error"]
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == EVIER
        assert not reloads
        assert _backups(tmp_path) == []

    @pytest.mark.asyncio
    async def test_a_replacement_is_written_and_reloaded(self, tmp_path):
        async with _real_hass_with_reload(tmp_path) as (hass, reloads):
            result = await _assistant(hass).apply_zombie_entity_fix("evier", "light.evier", "light.salon")

        assert result["success"] is True, result
        text = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "entity_id: light.salon" in text and "light.evier" not in text
        assert text.startswith("# mine\n")
        assert len(reloads) == 1
        assert Path(result["backup_path"]).read_text(encoding="utf-8") == EVIER

    @pytest.mark.asyncio
    async def test_a_failed_reload_puts_the_file_back(self, tmp_path):
        from homeassistant.exceptions import HomeAssistantError

        hass = _hass(tmp_path, EVIER_FILES)
        hass.services.async_call = AsyncMock(side_effect=[HomeAssistantError("boom"), None])
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(return_value=None),
        ):
            result = await _assistant(hass).apply_zombie_entity_fix("evier", "light.evier", "light.salon")

        assert result["success"] is False, result
        assert "file restored to original" in result["error"] and "boom" in result["error"]
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == EVIER
        assert hass.services.async_call.await_count == 2, "the restored file is reloaded too"

    @pytest.mark.asyncio
    async def test_nothing_to_replace_writes_nothing(self, tmp_path):
        """No backup either: one used to be taken before looking for the entity."""
        hass = _hass(tmp_path, EVIER_FILES)
        result = await _assistant(hass).apply_zombie_entity_fix("evier", "light.absent", "light.salon")

        assert result["success"] is False
        assert "not found" in result["error"]
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == EVIER
        assert not _reloaded(hass)
        assert _backups(tmp_path) == []


# ═══════════════════════════════════════════════════════════════════════════
# The panel's fixes that leave the reload to the user are checked too
# ═══════════════════════════════════════════════════════════════════════════

# One automation every fix has something to do on: a device action (with a
# real entity_id, so no registry is needed), an is_state() template, no
# description, mode single.
CLIMA = (
    "# mine\n"
    "- id: clima\n"
    "  alias: Clima\n"
    "  triggers:\n"
    "    - trigger: state\n"
    "      entity_id: binary_sensor.door\n"
    "  conditions:\n"
    "    - condition: template\n"
    "      value_template: \"{{ is_state('input_boolean.away', 'on') }}\"\n"
    "  actions:\n"
    "    - device_id: abc123\n"
    "      domain: light\n"
    "      type: turn_on\n"
    "      entity_id: light.kitchen\n"
)
CLIMA_FILES = {
    "configuration.yaml": "automation: !include automations.yaml\n",
    "automations.yaml": CLIMA,
}

FIXES = {
    "device_id": lambda ra: ra.apply_device_id_fix("clima"),
    "mode": lambda ra: ra.apply_mode_fix("clima", "restart"),
    "template": lambda ra: ra.apply_template_fix("clima"),
    "description": lambda ra: ra.apply_description_fix("clima", "Keeps it warm"),
}


class TestFixesWithoutReload:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("fix", list(FIXES))
    async def test_a_rejected_fix_writes_nothing(self, tmp_path, fix):
        hass = _hass(tmp_path, CLIMA_FILES)
        with _rejects("expected str at 'to'"):
            result = await FIXES[fix](_assistant(hass))

        assert result["success"] is False, result
        assert "Home Assistant rejects this automation" in result["error"]
        assert "expected str at 'to'" in result["error"]
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == CLIMA
        assert _backups(tmp_path) == []
        assert not _reloaded(hass)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fix", list(FIXES))
    async def test_an_accepted_fix_is_written_under_its_id(self, tmp_path, fix):
        hass = _hass(tmp_path, CLIMA_FILES)
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(return_value=None),
        ) as validator:
            result = await FIXES[fix](_assistant(hass))

        assert result["success"] is True, result
        validator.assert_awaited_once()
        assert validator.await_args.args[1] == "clima"
        text = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert text != CLIMA and text.startswith("# mine\n")
        assert Path(result["backup_path"]).read_text(encoding="utf-8") == CLIMA

    @pytest.mark.asyncio
    async def test_every_converted_device_block_is_one_home_assistant_loads(self, tmp_path):
        """HA's real validator on the whole conversion, one of each shape it writes.

        `is_open` used to come out as a state condition without `state:` and be
        refused; `to: null`, a `from:` list, a numeric_state on an attribute, a
        zone trigger, a `not` condition and a list of states must all load too.
        No device block is left: one would need the device registry and its
        integration loaded to validate, which a bare Home Assistant has not.
        """
        porte = (
            "- id: porte\n"
            "  triggers:\n"
            "    - trigger: device\n"
            "      device_id: d1\n"
            "      domain: binary_sensor\n"
            "      type: opened\n"
            "      entity_id: binary_sensor.door\n"
            "      id: door_open\n"
            "      for:\n"
            "        minutes: 2\n"
            "    - {trigger: device, device_id: d1, domain: switch, type: changed_states, entity_id: switch.pump}\n"
            "    - {trigger: device, device_id: d1, domain: climate, type: hvac_mode_changed, entity_id: climate.salon, to: heat}\n"
            "    - {trigger: device, device_id: d1, domain: cover, type: position, entity_id: cover.garage, above: 50}\n"
            "    - {trigger: device, device_id: d1, domain: device_tracker, type: enters, entity_id: device_tracker.phone, zone: zone.home}\n"
            "  conditions:\n"
            "    - {condition: device, device_id: d1, domain: binary_sensor, type: is_open, entity_id: binary_sensor.door}\n"
            "    - {condition: device, device_id: d1, domain: vacuum, type: is_cleaning, entity_id: vacuum.robot}\n"
            "    - {condition: device, device_id: d1, domain: device_tracker, type: is_not_home, entity_id: device_tracker.phone}\n"
            "    - {condition: device, device_id: d1, domain: climate, type: is_preset_mode, entity_id: climate.salon, preset_mode: eco}\n"
            "    - {condition: device, device_id: d1, domain: cover, type: is_position, entity_id: cover.garage, below: 30}\n"
            "  actions:\n"
            "    - {device_id: d1, domain: light, type: brightness_increase, entity_id: light.kitchen, metadata: {}}\n"
            "    - {device_id: d1, domain: cover, type: set_tilt_position, entity_id: cover.blind, position: 40}\n"
            "    - {device_id: d1, domain: alarm_control_panel, type: arm_away, entity_id: alarm_control_panel.home, code: '1234'}\n"
        )
        (tmp_path / "configuration.yaml").write_text(
            "automation: !include automations.yaml\n", encoding="utf-8"
        )
        (tmp_path / "automations.yaml").write_text(porte, encoding="utf-8")
        async with _real_hass(tmp_path) as hass:
            from homeassistant.helpers import entity_registry as er

            from custom_components.config_auditor.tests.conftest import MockEntityRegistry

            # Empty: every entity_id here is already one, nothing to resolve.
            hass.data[er.DATA_REGISTRY] = MockEntityRegistry()
            preview = await _assistant(hass).preview_device_id_fix("porte")
            # A validator that crashes is let through on purpose; here it must
            # have run, or this test proves nothing.
            with patch.object(yw._LOGGER, "debug") as debug:
                result = await _assistant(hass).apply_device_id_fix("porte")

        assert result["success"] is True, result
        assert not [c for c in debug.call_args_list if "Could not validate" in str(c)]
        assert preview["changes_count"] == 13 and preview["skipped"] == []
        written = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "device_id" not in written
        assert "id: door_open" in written
        assert "metadata" not in written
        assert "brightness_step_pct: 10" in written

    @pytest.mark.asyncio
    async def test_a_script_description_is_checked_as_a_script(self, tmp_path):
        """HA's real validator: checked as an automation, a script has no triggers."""
        scripts = "morning:\n  alias: Morning\n  sequence:\n    - delay: '00:05:00'\n"
        (tmp_path / "configuration.yaml").write_text(
            "script: !include scripts.yaml\n", encoding="utf-8"
        )
        (tmp_path / "scripts.yaml").write_text(scripts, encoding="utf-8")
        async with _real_hass(tmp_path) as hass:
            result = await _assistant(hass).apply_description_fix("script.morning", "Wake up")

        assert result["success"] is True, result
        assert "description: Wake up" in (tmp_path / "scripts.yaml").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_the_preview_lists_what_stays_and_why(self, tmp_path):
        """With nothing converted, the panel said the device had been re-added -- of a ZHA button."""
        remote = (
            "- id: remote\n"
            "  triggers:\n"
            "    - {trigger: device, device_id: d1, domain: zha, type: remote_button_short_press, subtype: turn_on}\n"
            "    - {trigger: device, device_id: d1, domain: light, type: turned_on, entity_id: light.kitchen}\n"
            "  actions:\n"
            "    - {device_id: d1, domain: light, type: toggle, entity_id: light.kitchen}\n"
        )
        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": remote,
        })
        assistant = _assistant(hass)
        preview = await assistant.preview_device_id_fix("remote")

        assert [c["description"] for c in preview["changes"]] == [
            "Trigger 1: light.turned_on → state trigger on light.kitchen (to: on)",
            "Action 0: light.toggle → light.toggle on light.kitchen",
        ]
        assert [s["reason"] for s in preview["skipped"]] == [
            "Trigger 0: zha.remote_button_short_press: an event of the zha "
            "integration itself, with no entity equivalent"
        ]
        # PyYAML printed the round-trip nodes as python objects.
        assert "!!python" not in preview["current_yaml"] + preview["new_yaml"]
        assert "trigger: state" in preview["new_yaml"]

        scoped = await assistant.preview_device_id_fix("remote", location="action[0]")
        assert [c["section"] for c in scoped["changes"]] == ["action"]
        assert scoped["skipped"] == []


# ═══════════════════════════════════════════════════════════════════════════
# The panel's alias / description fix (websocket) and the AI optimizer
# ═══════════════════════════════════════════════════════════════════════════

CONFIG = {"configuration.yaml": "automation: !include automations.yaml\n"}


def _field_fix():
    """The coroutine under HA's websocket decorators."""
    import inspect

    ws = pytest.importorskip("custom_components.config_auditor.websocket")
    return inspect.unwrap(ws.handle_apply_field_fix)


def _connection(tmp_path):
    from unittest.mock import MagicMock

    connection = MagicMock()
    connection.user.id = f"user-{tmp_path.name}"  # its own rate-limit slot
    return connection


def _alias_msg(value: str) -> dict:
    return {
        "id": 7, "type": "haca/apply_field_fix",
        "entity_id": "automation.clima", "field": "alias", "value": value,
    }


class TestFieldFix:
    @pytest.mark.asyncio
    async def test_a_rejected_entry_writes_nothing(self, tmp_path):
        hass = _hass(tmp_path, {**CONFIG, "automations.yaml": AUTOMATIONS})
        connection = _connection(tmp_path)
        with _rejects("expected str at 'to'"):
            await _field_fix()(hass, connection, _alias_msg("Warm"))

        code, message = connection.send_error.call_args.args[1:]
        assert code == "rejected"
        assert "Home Assistant rejects this automation" in message and "expected str at 'to'" in message
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == AUTOMATIONS
        assert not _reloaded(hass)
        assert _backups(tmp_path) == []

    @pytest.mark.asyncio
    async def test_an_accepted_alias_is_written_and_reloaded_as_the_user(self, tmp_path):
        hass = _hass(tmp_path, {**CONFIG, "automations.yaml": AUTOMATIONS})
        connection = _connection(tmp_path)
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(return_value=None),
        ) as validator:
            await _field_fix()(hass, connection, _alias_msg("Warm"))

        connection.send_result.assert_called_once()
        assert validator.await_args.args[1] == "clima"
        assert "alias: Warm" in (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        reload = hass.services.async_call.await_args
        assert reload.args[:2] == ("automation", "reload")
        assert reload.kwargs["context"] is connection.context.return_value

    @pytest.mark.asyncio
    async def test_a_failed_reload_puts_the_file_back(self, tmp_path):
        from homeassistant.exceptions import HomeAssistantError

        hass = _hass(tmp_path, {**CONFIG, "automations.yaml": AUTOMATIONS})
        hass.services.async_call = AsyncMock(side_effect=[HomeAssistantError("boom"), None])
        connection = _connection(tmp_path)
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(return_value=None),
        ):
            await _field_fix()(hass, connection, _alias_msg("Warm"))

        code, message = connection.send_error.call_args.args[1:]
        assert code == "apply_error" and "file restored to original" in message
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == AUTOMATIONS


class TestOptimizer:
    @pytest.mark.asyncio
    async def test_one_rejected_automation_of_a_split_writes_none(self, tmp_path):
        """A split hands back several automations; HA would disable each bad one alone."""
        from custom_components.config_auditor.automation_optimizer import AutomationOptimizer

        hass = _hass(tmp_path, {**CONFIG, "automations.yaml": AUTOMATIONS})
        split = (
            "alias: Heat\ntriggers: []\nactions: []\n"
            "---\n"
            "alias: Cool\ntriggers: []\nactions: []\n"
        )
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(side_effect=[None, vol.Invalid("expected str at 'to'")]),
        ):
            result = await AutomationOptimizer(hass).apply("automation.clima", split)

        assert result["success"] is False, result
        assert result["error"].startswith("Cool: Home Assistant rejects this automation")
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == AUTOMATIONS
        assert _backups(tmp_path) == []

    @pytest.mark.asyncio
    async def test_a_bare_off_written_by_the_ai_is_refused(self, tmp_path):
        """HA's real validator. The AI's YAML is read as YAML 1.1, so `to: off` is False."""
        from custom_components.config_auditor.automation_optimizer import AutomationOptimizer

        for name, text in {**CONFIG, "automations.yaml": AUTOMATIONS}.items():
            (tmp_path / name).write_text(text, encoding="utf-8")
        rewritten = (
            "id: clima\nalias: Clima\n"
            "triggers:\n  - trigger: state\n    entity_id: light.x\n    to: off\n"
            "actions: []\n"
        )
        async with _real_hass(tmp_path) as hass:
            result = await AutomationOptimizer(hass).apply("automation.clima", rewritten)

        assert result["success"] is False, result
        assert "expected str at 'to'" in result["error"]
        assert (tmp_path / "automations.yaml").read_text(encoding="utf-8") == AUTOMATIONS
