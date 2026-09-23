"""The MCP fix tools reach the fix services the way those services take a call.

`haca_apply_fix` and `haca_fix_batch` sent every fix service `entity_id`, which
none of their schemas accepts -- they take `automation_id` -- so no fix from an
AI agent ever ran; `fix_mode` was not given its mode either. The service's
answer was never read, so a fix that wrote nothing would have been reported as
applied. And an issue's ID was hashed on its entity alone: two device blocks
of one automation shared it, and the second could not be named.

These tests go through the services' own schemas and handlers, down to the
file on disk.

    pytest custom_components/config_auditor/tests/test_mcp_fix_tools.py -v
"""
from __future__ import annotations

import os
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

pytest.importorskip("homeassistant", reason="the services are Home Assistant's")
pytest.importorskip("ruamel.yaml", reason="the fixes round-trip through ruamel")

import voluptuous as vol  # after Home Assistant, which may alias it
from homeassistant.core import Context

from custom_components.config_auditor import services
from custom_components.config_auditor.const import DOMAIN
from custom_components.config_auditor.mcp_server import tools_audit
from custom_components.config_auditor.refactoring_assistant import RefactoringAssistant
from custom_components.config_auditor.tests.conftest import MockHass

AUTOMATIONS = (
    "- id: nested\n"
    "  alias: Nested\n"
    "  mode: single\n"
    "  triggers:\n"
    "    - {trigger: device, device_id: d1, domain: light, type: turned_on, entity_id: light.kitchen}\n"
    "  actions:\n"
    "    - choose:\n"
    "        - conditions:\n"
    "            - {condition: device, device_id: d1, domain: light, type: is_on, entity_id: light.kitchen}\n"
    "          sequence:\n"
    "            - {condition: device, device_id: d1, domain: switch, type: is_off, entity_id: switch.pump}\n"
)


def _issue(issue_type: str, location: str, fix_available: bool = True) -> dict:
    return {
        "entity_id": "automation.nested", "alias": "Nested", "automation_id": "nested",
        "type": issue_type, "location": location, "fix_available": fix_available,
        # What the scan tags an issue with: hashed on entity, type and location.
        "haca_id": f"HACA-AUTO-{issue_type.upper()}-{zlib.crc32(location.encode()):08x}",
    }


TRIGGER = _issue("device_id_in_trigger", "trigger[0]")
TRIGGER_PLATFORM = _issue("device_trigger_platform", "trigger[0]")
CHOOSE_CONDITION = _issue("device_id_in_condition", "action[0].choose[0].conditions[0]")
CHOOSE_STEP = _issue("device_id_in_condition", "action[0].choose[0].sequence[0]")


class _Setup(SimpleNamespace):
    def text(self) -> str:
        return (self.path / "automations.yaml").read_text(encoding="utf-8")

    def fix_calls(self) -> list[tuple[str, dict]]:
        return [(service, data) for domain, service, data in self.calls if domain == DOMAIN]


async def _setup(tmp_path, issues: list[dict]) -> _Setup:
    """HACA's services registered on a test hass, and a coordinator holding *issues*."""
    (tmp_path / "configuration.yaml").write_text("automation: !include automations.yaml\n", encoding="utf-8")
    (tmp_path / "automations.yaml").write_text(AUTOMATIONS, encoding="utf-8")
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    entry = MagicMock(entry_id="e1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data[DOMAIN] = {"e1": {
        "refactoring_assistant": RefactoringAssistant(hass),
        "coordinator": MagicMock(data={"automation_issue_list": issues}),
    }}
    await services.async_setup_services(hass, entry)
    registered = {c.args[1]: c for c in hass.services.async_register.call_args_list}
    calls: list[tuple] = []

    async def _call(domain, service, data=None, blocking=False, context=None, return_response=False):
        calls.append((domain, service, data))
        if domain != DOMAIN:  # the persistent notification
            return None
        registration = registered[service]
        # The service's own schema: it refused `entity_id` outright.
        validated = registration.kwargs["schema"](dict(data or {}))
        call = SimpleNamespace(domain=domain, service=service, data=validated, context=context or Context())
        response = await registration.args[2](call)
        return response if return_response else None

    hass.services.async_call = AsyncMock(side_effect=_call)
    return _Setup(hass=hass, calls=calls, path=tmp_path)


def _accepted():
    return patch(
        "homeassistant.components.automation.config.async_validate_config_item",
        AsyncMock(return_value=None),
    )


class TestApplyFix:
    @pytest.mark.asyncio
    async def test_the_issue_named_is_the_block_converted(self, tmp_path):
        """The second nested condition: its own ID, its own location, nothing else."""
        setup = await _setup(tmp_path, [TRIGGER, CHOOSE_CONDITION, CHOOSE_STEP])
        with _accepted():
            result = await tools_audit._tool_apply_fix(
                setup.hass, {"issue_id": CHOOSE_STEP["haca_id"], "dry_run": False}
            )

        assert result["status"] == "applied", result
        assert setup.fix_calls() == [("fix_device_id", {
            "automation_id": "automation.nested", "location": "action[0].choose[0].sequence[0]",
        })]
        text = setup.text()
        assert text.count("device_id") == AUTOMATIONS.count("device_id") - 1
        assert "entity_id: switch.pump\n              state: 'off'" in text

    @pytest.mark.asyncio
    async def test_a_fix_home_assistant_would_refuse_is_reported_as_not_applied(self, tmp_path):
        setup = await _setup(tmp_path, [TRIGGER])
        with patch(
            "homeassistant.components.automation.config.async_validate_config_item",
            AsyncMock(side_effect=vol.Invalid("expected str at 'to'")),
        ):
            result = await tools_audit._tool_apply_fix(
                setup.hass, {"issue_id": TRIGGER["haca_id"], "dry_run": False}
            )

        assert "status" not in result
        assert "expected str at 'to'" in result["error"]
        assert setup.text() == AUTOMATIONS

    @pytest.mark.asyncio
    async def test_the_mode_fix_is_given_its_mode(self, tmp_path):
        motion = _issue("incorrect_mode_motion_single", "mode")
        setup = await _setup(tmp_path, [motion])
        with _accepted():
            result = await tools_audit._tool_apply_fix(
                setup.hass, {"issue_id": motion["haca_id"], "dry_run": False}
            )

        assert result["status"] == "applied", result
        assert setup.fix_calls() == [("fix_mode", {"automation_id": "automation.nested", "mode": "restart"})]
        assert "mode: restart" in setup.text()

    @pytest.mark.asyncio
    async def test_a_type_no_tool_can_fix_is_refused_before_the_dry_run(self, tmp_path):
        """The dry run used to say yes, and the real run: no fix service."""
        setup = await _setup(tmp_path, [_issue("no_description", "root")])
        result = await tools_audit._tool_apply_fix(
            setup.hass, {"issue_id": _issue("no_description", "root")["haca_id"]}
        )
        assert result == {"error": "This issue cannot be fixed automatically"}


class TestFixBatch:
    @pytest.mark.asyncio
    async def test_every_block_is_converted_once(self, tmp_path):
        """A device trigger is two issues; converting it twice failed the second time."""
        no_description = _issue("no_description", "root")
        setup = await _setup(
            tmp_path, [TRIGGER, TRIGGER_PLATFORM, CHOOSE_CONDITION, CHOOSE_STEP, no_description]
        )
        with _accepted():
            result = await tools_audit._tool_fix_batch(
                setup.hass, {"category": "automation", "dry_run": False}
            )

        assert (result["applied"], result["errors"], result["not_fixable"]) == (4, 0, 1), result
        assert result["not_fixable_types"] == ["no_description"]
        assert [data["location"] for _, data in setup.fix_calls()] == [
            "trigger[0]", "action[0].choose[0].conditions[0]", "action[0].choose[0].sequence[0]",
        ]
        assert "device_id" not in setup.text()

    @pytest.mark.asyncio
    async def test_the_dry_run_names_the_service_and_the_block(self, tmp_path):
        setup = await _setup(tmp_path, [CHOOSE_STEP])
        result = await tools_audit._tool_fix_batch(setup.hass, {"type": "device_id_in_condition"})

        assert result["preview"][0]["fix_service"] == "fix_device_id"
        assert result["preview"][0]["location"] == "action[0].choose[0].sequence[0]"
        assert not setup.calls
        assert setup.text() == AUTOMATIONS


class TestIssueIds:
    @pytest.mark.asyncio
    async def test_two_blocks_of_one_automation_are_two_ids(self, tmp_path):
        setup = await _setup(tmp_path, [CHOOSE_CONDITION, CHOOSE_STEP])
        listed = await tools_audit._tool_get_issues(setup.hass, {})

        assert [(i["id"], i["location"]) for i in listed["issues"]] == [
            (CHOOSE_CONDITION["haca_id"], "action[0].choose[0].conditions[0]"),
            (CHOOSE_STEP["haca_id"], "action[0].choose[0].sequence[0]"),
        ]

    def test_the_id_from_before_still_names_the_first_issue(self):
        cdata = {"automation_issue_list": [CHOOSE_CONDITION, CHOOSE_STEP]}
        old_id = tools_audit._issue_entity_id(CHOOSE_STEP, "AUTO")
        assert tools_audit._find_issue_by_id(cdata, old_id) is CHOOSE_CONDITION
        assert tools_audit._find_issue_by_id(cdata, CHOOSE_STEP["haca_id"]) is CHOOSE_STEP
