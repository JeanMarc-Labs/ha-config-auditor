"""The MCP recorder tools call what Home Assistant actually provides.

ha_get_logbook called logbook.async_get_logbook_entries, which no Home
Assistant version has ever had, so it only ever returned an error. It now runs
the query /api/logbook runs. And ha_get_history takes entity_id as well as
entity_ids. The patches below are autospecced on Home
Assistant's own functions: if one disappears or changes its signature, these
tests fail instead of the tool.

    pytest custom_components/config_auditor/tests/test_mcp_history.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

pytest.importorskip("homeassistant", reason="the tools query Home Assistant's recorder")

from custom_components.config_auditor.mcp_server import tools_history

PROCESSOR = "homeassistant.components.logbook.processor.EventProcessor"
EVENT_TYPES = "homeassistant.components.logbook.helpers.async_determine_event_types"
RECORDER = "homeassistant.components.recorder.get_instance"
HISTORY = "homeassistant.components.recorder.history.get_significant_states"


def _hass(*components):
    return SimpleNamespace(config=SimpleNamespace(components=set(components)))


def _recorder():
    return SimpleNamespace(async_add_executor_job=AsyncMock(side_effect=lambda f, *a: f(*a)))


class TestLogbook:
    @pytest.mark.asyncio
    async def test_runs_the_logbook_query_and_keeps_the_latest(self):
        hass = _hass("logbook")
        events = [{"when": f"2026-10-17T10:0{i}:00+00:00", "entity_id": "switch.x"} for i in range(5)]
        with patch(EVENT_TYPES, autospec=True, return_value={"logbook_entry"}) as types, \
             patch(PROCESSOR, autospec=True) as processor, \
             patch(RECORDER, autospec=True, return_value=_recorder()):
            processor.return_value.get_events.return_value = events
            result = await tools_history._tool_ha_get_logbook(hass, {"entity_id": "switch.x", "limit": 2})

        assert result["success"] is True
        assert result["entries"] == events[-2:]
        assert (result["total_entries"], result["truncated"]) == (5, True)
        types.assert_called_once_with(hass, ["switch.x"], None)
        assert processor.call_args.args[2] == ["switch.x"]

    @pytest.mark.asyncio
    async def test_without_the_logbook_it_says_so(self):
        result = await tools_history._tool_ha_get_logbook(_hass(), {})

        assert result["success"] is False
        assert "not loaded" in result["error"]


class TestHistory:
    """ha_get_history read entity_ids only; an agent sending entity_id got the
    recorder's 'entity_ids must be provided'."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("params", [{"entity_id": "switch.x"}, {"entity_ids": "switch.x"}, {"entity_ids": ["switch.x"]}])
    async def test_one_entity_reaches_the_recorder_as_a_list(self, params):
        with patch(HISTORY, autospec=True, return_value={}) as history, \
             patch(RECORDER, autospec=True, return_value=_recorder()):
            result = await tools_history._tool_ha_get_history(_hass(), params)

        assert result["success"] is True
        assert history.call_args.args[3] == ["switch.x"]

    @pytest.mark.asyncio
    async def test_no_entity_is_a_clear_error(self):
        with patch(HISTORY, autospec=True) as history:
            result = await tools_history._tool_ha_get_history(_hass(), {"entity_ids": []})

        assert result == {"error": "entity_ids (or entity_id) is required"}
        history.assert_not_called()
