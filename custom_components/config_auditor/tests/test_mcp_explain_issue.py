"""haca_explain_issue runs, and its cache answers the question it was asked.

The 1.8.0 split left three of its imports one package too shallow, so every
call failed with "No module named ...mcp_server.conversation". Its cache was
read from hass.data[DOMAIN] but written under the config entry, so no answer
was ever reused; and it was keyed on the issue ID alone, which can name
several issues of one entity.

    pytest custom_components/config_auditor/tests/test_mcp_explain_issue.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

pytest.importorskip("homeassistant", reason="the handler imports the integration")

from custom_components.config_auditor.const import DOMAIN
from custom_components.config_auditor.mcp_server import tools_audit

ENTRY_ID = "entry1"
AI = "custom_components.config_auditor.conversation._async_call_ai"


def _hass(issue):
    entry = SimpleNamespace(entry_id=ENTRY_ID, options={})
    coordinator = SimpleNamespace(data={"automation_issue_list": [issue]})
    return SimpleNamespace(
        data={DOMAIN: {ENTRY_ID: {"coordinator": coordinator}}},
        config_entries=SimpleNamespace(async_entries=lambda domain: [entry]),
        config=SimpleNamespace(language="en"),
    )


def _issue():
    return {"entity_id": "automation.kitchen", "type": "no_alias", "severity": "low", "message": "No alias"}


@pytest.mark.asyncio
async def test_second_call_is_served_from_cache():
    hass = _hass(_issue())
    with patch(AI, AsyncMock(return_value="Because.")) as ai:
        first = await tools_audit._tool_explain_issue(hass, {"issue_id": "automation.kitchen"})
        second = await tools_audit._tool_explain_issue(hass, {"issue_id": "automation.kitchen"})

    assert (first["explanation"], first["cached"]) == ("Because.", False)
    assert (second["explanation"], second["cached"]) == ("Because.", True)
    assert ai.await_count == 1


@pytest.mark.asyncio
async def test_changed_message_gets_a_fresh_answer():
    issue = _issue()
    hass = _hass(issue)
    with patch(AI, AsyncMock(side_effect=["Old.", "New."])) as ai:
        await tools_audit._tool_explain_issue(hass, {"issue_id": "automation.kitchen"})
        issue["message"] = "No alias, and no description"
        result = await tools_audit._tool_explain_issue(hass, {"issue_id": "automation.kitchen"})

    assert (result["explanation"], result["cached"]) == ("New.", False)
    assert ai.await_count == 2


@pytest.mark.asyncio
async def test_no_answer_is_not_cached():
    hass = _hass(_issue())
    with patch(AI, AsyncMock(return_value="")) as ai:
        first = await tools_audit._tool_explain_issue(hass, {"issue_id": "automation.kitchen"})
        await tools_audit._tool_explain_issue(hass, {"issue_id": "automation.kitchen"})

    assert first["explanation"] == "No AI service available."
    assert ai.await_count == 2
