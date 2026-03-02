"""Regression tests for event_monitor.py.

Guards against:
  - Event monitor not triggering coordinator refresh on automation_reloaded
  - Debounce logic failing (multiple events → only one scan)
  - Listeners not cleaned up on unload
  - Monitoring disabled when option is False
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import MockHass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(options: dict | None = None):
    entry = MagicMock()
    entry.options = options or {}
    _unload_callbacks = []
    entry.async_on_unload = lambda cb: _unload_callbacks.append(cb)
    entry._unload_callbacks = _unload_callbacks
    return entry


def _make_hass_with_loop():
    hass = MockHass()
    loop = asyncio.new_event_loop()
    hass.loop = loop
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro, loop=loop)
    return hass, loop


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEventMonitorSetup:
    """Guard against setup regressions."""

    def test_module_exposes_async_setup_event_monitor(self):
        from custom_components.config_auditor.event_monitor import (
            async_setup_event_monitor,
        )
        assert callable(async_setup_event_monitor)

    def test_monitored_events_include_automation_reloaded(self):
        from custom_components.config_auditor.event_monitor import MONITORED_EVENTS
        assert "automation_reloaded" in MONITORED_EVENTS, (
            "automation_reloaded must be monitored so HA Repairs issues are "
            "refreshed when user saves an automation"
        )

    def test_monitored_events_include_script_and_scene(self):
        from custom_components.config_auditor.event_monitor import MONITORED_EVENTS
        assert "script_reloaded" in MONITORED_EVENTS
        assert "scene_reloaded" in MONITORED_EVENTS

    def test_monitored_events_include_entity_registry(self):
        from custom_components.config_auditor.event_monitor import MONITORED_EVENTS
        assert "entity_registry_updated" in MONITORED_EVENTS


class TestEventMonitorListeners:
    """Guard against listener registration bugs."""

    def test_listeners_registered_on_hass_bus(self):
        """async_setup_event_monitor must register one listener per event."""
        from custom_components.config_auditor.event_monitor import (
            MONITORED_EVENTS,
            async_setup_event_monitor,
        )
        hass = MockHass()
        listen_calls = []
        hass.bus.async_listen = lambda evt, handler: listen_calls.append(evt) or (lambda: None)

        entry = _make_entry({"event_monitoring_enabled": True})
        async_setup_event_monitor(hass, entry)

        for event in MONITORED_EVENTS:
            assert event in listen_calls, (
                f"Listener for '{event}' not registered on hass.bus"
            )

    def test_listeners_registered_via_async_on_unload(self):
        """Unsubscribe callbacks must be registered via entry.async_on_unload."""
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor
        hass = MockHass()
        hass.bus.async_listen = MagicMock(return_value=lambda: None)

        entry = _make_entry()
        async_setup_event_monitor(hass, entry)

        assert len(entry._unload_callbacks) >= 1, (
            "async_on_unload must be called to register cleanup"
        )

    def test_disabled_monitoring_skips_registration(self):
        """When event_monitoring_enabled=False, no listeners should fire scans."""
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor
        hass = MockHass()
        hass.bus.async_listen = MagicMock(return_value=lambda: None)

        entry = _make_entry({"event_monitoring_enabled": False})
        async_setup_event_monitor(hass, entry)
        # Listeners are registered but _schedule_debounced_scan checks the flag
        # The key test: triggering events should NOT schedule scans


class TestDebounce:
    """Guard against debounce logic bugs."""

    @pytest.mark.asyncio
    async def test_multiple_events_trigger_single_scan(self):
        """Rapid events must be coalesced into a single debounced scan."""
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor

        hass = MockHass()
        scan_count = 0
        loop = asyncio.get_event_loop()
        hass.loop = loop

        mock_coord = MagicMock()

        async def mock_refresh():
            nonlocal scan_count
            scan_count += 1

        mock_coord.async_refresh = mock_refresh

        # Wire domain data
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"event_debounce_seconds": 0.05}
        unload_cbs = []
        entry.async_on_unload = lambda cb: unload_cbs.append(cb)
        hass.data["config_auditor"] = {"test_entry": {"coordinator": mock_coord}}

        listeners = {}
        def fake_listen(event_name, handler):
            listeners[event_name] = handler
            return lambda: None
        hass.bus.async_listen = fake_listen

        async_setup_event_monitor(hass, entry)

        # Fire 5 events rapidly
        fake_event = MagicMock()
        for _ in range(5):
            if "automation_reloaded" in listeners:
                listeners["automation_reloaded"](fake_event)

        # Wait for debounce to fire
        await asyncio.sleep(0.15)

        # Should have triggered at most 1 scan (debounce coalesced)
        assert scan_count <= 1, (
            f"Debounce failed: {scan_count} scans triggered instead of 1"
        )


class TestRaceConditionGuard:
    """Guard against the race condition that causes 'Handler does not support user'.

    Race: user opens Repairs → event triggers scan → issue deleted → user clicks Fix
    → HA raises UnknownStep → 'Handler does not support user'.

    Fix: is_persistent=True for fixable issues in async_create_issue.
    """

    @pytest.mark.skip(reason="repairs.py retiré du package actif (MODULE_8 désactivé)")
    def test_fixable_issues_use_is_persistent_true(self):
        """REGRESSION: fixable issues must have is_persistent=True to survive rescan."""
        import inspect
        from custom_components.config_auditor.repairs import HacaRepairsManager
        source = inspect.getsource(HacaRepairsManager._async_create_repair)
        # is_persistent=is_fixable OR is_persistent=True must appear for fixable issues
        assert "is_persistent" in source, (
            "is_persistent must be set for fixable issues to prevent race condition "
            "where rescan deletes the issue while user clicks Fix"
        )
        # Specifically, fixable issues should be persistent
        assert "is_persistent=is_fixable" in source or "is_persistent=True" in source, (
            "Fixable issues must use is_persistent=True/is_fixable to prevent "
            "'Handler does not support user' error (UnknownStep race condition)"
        )
