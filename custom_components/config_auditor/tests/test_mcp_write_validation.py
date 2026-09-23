"""The MCP write tools check an entry the way Home Assistant's editor does.

`_safe_edit_and_reload` rolls a file back when the reload fails, but a reload
does not fail on one invalid automation: Home Assistant disables it, logs, and
succeeds. The tool then reported success on an automation that was offline. An
entry is now validated first -- as Home Assistant will read it back from the
file -- and one it would reject is not written.

    pytest custom_components/config_auditor/tests/test_mcp_write_validation.py -v
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
common = pytest.importorskip("custom_components.config_auditor.mcp_server.common")

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
            assert await common._async_validation_error(hass, domain, yaml, entry, key) is None

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
            error = await common._async_validation_error(hass, domain, yaml, entry, key)
        assert error is not None and expected in error, error

    @pytest.mark.asyncio
    async def test_a_validator_that_cannot_run_does_not_block_the_write(self):
        """Only a validation error counts; the reload and its rollback cover the rest."""
        hass = MockHass()
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(side_effect=RuntimeError("no integrations loaded")),
        ):
            error = await common._async_validation_error(
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
