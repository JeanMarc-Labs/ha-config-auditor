"""Shared pytest fixtures for H.A.C.A tests.

Run with:
    pip install pytest pytest-asyncio pytest-homeassistant-custom-component
    pytest tests/ -v
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Make the custom component importable without a real HA installation
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Minimal HA stubs (used when pytest-homeassistant-custom-component not available) ──

class MockState:
    def __init__(self, entity_id, state="on", attributes=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}


class _MockStatesProxy:
    """Proxy that lets tests call hass.states.get(), hass.states.async_all(), etc."""

    def __init__(self, store: dict):
        self._store = store

    def get(self, entity_id: str):
        return self._store.get(entity_id)

    def async_entity_ids(self, domain: str):
        return [eid for eid in self._store if eid.startswith(domain + ".")]

    def async_all(self):
        return list(self._store.values())


class MockHass:
    """Minimal HomeAssistant mock sufficient for unit-testing analysers."""

    def __init__(self, config_dir="/tmp/haca_test"):
        self.config = MagicMock()
        self.config.config_dir = config_dir
        self.config.language = "en"
        self._states: dict[str, MockState] = {}
        self.states = _MockStatesProxy(self._states)
        self.loop = MagicMock()
        self.bus = MagicMock()
        self.data: dict = {}
        self.config_entries = MagicMock()
        self.config_entries.async_entries = MagicMock(return_value=[])
        self.services = MagicMock()
        self.services.async_call = MagicMock(return_value=None)
        self.services = MagicMock()

    def add_state(self, entity_id: str, state: str = "on", attributes: dict = None):
        self._states[entity_id] = MockState(entity_id, state, attributes or {})

    async def async_add_executor_job(self, func, *args):
        return func(*args)


@pytest.fixture
def mock_hass(tmp_path):
    """Provide a MockHass instance with a temporary config directory."""
    hass = MockHass(config_dir=str(tmp_path))
    # Create minimal automations.yaml and scripts.yaml
    (tmp_path / "automations.yaml").write_text("[]", encoding="utf-8")
    (tmp_path / "scripts.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "scenes.yaml").write_text("[]", encoding="utf-8")
    return hass


@pytest.fixture
def sample_automation():
    """Return a well-formed automation config dict."""
    return {
        "id": "test_auto_001",
        "alias": "Test Automation",
        "description": "A test automation",
        "mode": "single",
        "triggers": [{"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
        "conditions": [],
        "actions": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
    }


@pytest.fixture
def god_automation():
    """Return a complex 'God automation' config for complexity testing."""
    actions = [
        {"service": f"light.turn_on", "target": {"entity_id": f"light.room_{i}"}}
        for i in range(20)
    ]
    actions += [
        {"condition": "state", "entity_id": f"sensor.temp_{i}", "state": "high"}
        for i in range(5)
    ]
    return {
        "id": "god_auto_001",
        "alias": "God Automation",
        "triggers": [
            {"platform": "state", "entity_id": f"sensor.motion_{i}"}
            for i in range(6)
        ],
        "conditions": [
            {"condition": "state", "entity_id": "input_boolean.enabled", "state": "on"},
        ] * 4,
        "actions": actions,
    }
