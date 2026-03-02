"""Tests for event_monitor and health_score integration."""
import asyncio
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── health_score integration (already tested standalone, test integration here) ──

class TestHealthScoreIntegration:
    """Verify health_score.py is correctly imported and called in services.py."""

    def test_health_score_importable_from_services(self):
        from custom_components.config_auditor.services import calculate_health_score
        assert callable(calculate_health_score)

    def test_health_score_importable_standalone(self):
        from custom_components.config_auditor.health_score import calculate_health_score
        assert callable(calculate_health_score)

    def test_same_function_both_paths(self):
        from custom_components.config_auditor.health_score import calculate_health_score as hs1
        from custom_components.config_auditor.services import calculate_health_score as hs2
        assert hs1 is hs2


# ── event_monitor unit tests ───────────────────────────────────────────────────

class TestEventMonitorSetup:
    """Unit tests for async_setup_event_monitor."""

    def _make_hass_and_entry(self, monitoring_enabled=True, debounce=0):
        hass = MagicMock()
        hass.data = {}
        hass.loop = MagicMock()
        hass.bus = MagicMock()
        hass.bus.async_listen.return_value = MagicMock()  # unsub callable

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {
            "event_monitoring_enabled": monitoring_enabled,
            "event_debounce_seconds": debounce,
        }
        entry._unload_callbacks = []

        def capture_unload(cb):
            entry._unload_callbacks.append(cb)

        entry.async_on_unload.side_effect = capture_unload
        return hass, entry

    def test_registers_all_monitored_events(self):
        from custom_components.config_auditor.event_monitor import (
            async_setup_event_monitor, MONITORED_EVENTS
        )
        hass, entry = self._make_hass_and_entry()
        async_setup_event_monitor(hass, entry)

        # Each event + 1 cancel callback = len(MONITORED_EVENTS) + 1
        listen_calls = hass.bus.async_listen.call_args_list
        registered_events = [c[0][0] for c in listen_calls]
        for event in MONITORED_EVENTS:
            assert event in registered_events, f"Missing listener for {event}"

    def test_registers_cancel_callback_on_unload(self):
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor, MONITORED_EVENTS
        hass, entry = self._make_hass_and_entry()
        async_setup_event_monitor(hass, entry)
        # We should have len(MONITORED_EVENTS) listener unsubs + 1 cancel callback
        assert len(entry._unload_callbacks) == len(MONITORED_EVENTS) + 1

    def test_disabled_monitoring_still_registers_but_noop(self):
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor
        hass, entry = self._make_hass_and_entry(monitoring_enabled=False)
        # Should not raise
        async_setup_event_monitor(hass, entry)
        # Still registers listeners (they're no-ops when disabled)
        assert hass.bus.async_listen.called

    def test_debounced_scan_fires_coordinator_refresh(self):
        """When an event fires and debounce expires, coordinator is refreshed."""
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor, MONITORED_EVENTS
        hass, entry = self._make_hass_and_entry(debounce=0)

        coord = MagicMock()
        coord.async_refresh = MagicMock(return_value=MagicMock())  # sync mock, not a coroutine
        hass.data = {"config_auditor": {"test_entry": {"coordinator": coord}}}

        # Capture the call_later callback
        fired_fn = []
        def capture_call_later(delay, fn):
            fired_fn.append(fn)
            return MagicMock()
        hass.loop.call_later.side_effect = capture_call_later

        async_setup_event_monitor(hass, entry)

        # Find and trigger the handler for "automation_reloaded"
        listen_calls = hass.bus.async_listen.call_args_list
        automation_handler = None
        for c in listen_calls:
            if c[0][0] == "automation_reloaded":
                automation_handler = c[0][1]
                break
        assert automation_handler is not None

        automation_handler(MagicMock())  # fire the event
        assert len(fired_fn) == 1, "call_later should have been called once"

        # Simulate timer firing
        fired_fn[0]()
        hass.async_create_task.assert_called_once()


# ── models integration ─────────────────────────────────────────────────────────

class TestModelsImportIntegration:
    def test_all_models_importable(self):
        from custom_components.config_auditor.models import (
            AuditIssue, ComplexityScore, BatteryEntry,
            IssueDict, GraphNodeDict, GraphEdgeDict, CoordinatorData,
        )
        assert AuditIssue is not None

    def test_audit_issue_severity_literals(self):
        from custom_components.config_auditor.models import AuditIssue
        for sev in ("high", "medium", "low"):
            issue = AuditIssue("x", "t", sev, "m", "r")
            assert issue.severity == sev

    def test_coordinator_data_typed_dict_keys(self):
        """CoordinatorData should list all expected coordinator keys."""
        from custom_components.config_auditor.models import CoordinatorData
        annotations = CoordinatorData.__annotations__
        required_keys = [
            "health_score", "total_issues", "automation_issue_list",
            "battery_list", "dependency_graph", "complexity_scores",
        ]
        for key in required_keys:
            assert key in annotations, f"Missing key in CoordinatorData: {key}"
