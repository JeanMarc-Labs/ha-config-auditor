"""Infrastructure & integration tests — v1.1.2.

Covers:
  - health_score importable from both services.py and health_score.py
  - event_monitor: listeners registered, debounce, cleanup
  - models: AuditIssue, ComplexityScore, BatteryEntry importable + CoordinatorData keys
  - VERSION = 1.1.2
"""
from __future__ import annotations

import asyncio
import re
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ══════════════════════════════════════════════════════════════════════════════
# VERSION
# ══════════════════════════════════════════════════════════════════════════════

class TestVersion:
    """The version string lives in six places and they must not drift.

    A bump touches manifest.json, const.py, core.js's HACA_VERSION and
    panel.version in the 13 translation files. Missing one is silent: the
    panel then reports a version that is not the one running. These checks
    read the files directly so they hold without a Home Assistant install,
    and they assert consistency rather than a literal, so they never need
    updating on a bump.
    """

    BASE = Path(__file__).parent.parent

    def _const_version(self) -> str:
        src = (self.BASE / "const.py").read_text(encoding="utf-8")
        match = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.MULTILINE)
        assert match, "const.py no longer defines VERSION"
        return match.group(1)

    def test_version_string_format(self):
        version = self._const_version()
        parts = version.split(".")
        assert len(parts) == 3, f"VERSION must be semantic (X.Y.Z), got {version!r}"
        assert all(p.isdigit() for p in parts)

    def test_manifest_matches_const(self):
        import json
        manifest = json.loads((self.BASE / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["version"] == self._const_version(), (
            f"manifest.json {manifest['version']!r} != const.py "
            f"{self._const_version()!r}"
        )

    def test_panel_build_marker_matches_const(self):
        src = (self.BASE / "www" / "src" / "core.js").read_text(encoding="utf-8")
        match = re.search(r"HACA_VERSION\s*=\s*'([^']+)'", src)
        assert match, "core.js no longer defines HACA_VERSION"
        assert match.group(1) == self._const_version(), (
            f"core.js HACA_VERSION {match.group(1)!r} != const.py "
            f"{self._const_version()!r} — rebuild after fixing (www/build.sh)"
        )

    def test_translations_report_the_running_version(self):
        import json
        expected = "v" + self._const_version()
        wrong = {
            f.stem: json.loads(f.read_text(encoding="utf-8"))["panel"]["version"]
            for f in sorted((self.BASE / "translations").glob("*.json"))
            if json.loads(f.read_text(encoding="utf-8"))["panel"]["version"] != expected
        }
        assert not wrong, f"panel.version should be {expected!r}, got: {wrong}"


# ══════════════════════════════════════════════════════════════════════════════
# health_score integration
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthScoreIntegration:
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


# ══════════════════════════════════════════════════════════════════════════════
# event_monitor
# ══════════════════════════════════════════════════════════════════════════════

class TestEventMonitorSetup:
    def _make_hass_entry(self, monitoring_enabled=True, debounce=0):
        from custom_components.config_auditor.tests.conftest import MockHass
        hass = MockHass()
        hass.bus.async_listen = MagicMock(return_value=lambda: None)
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"event_monitoring_enabled": monitoring_enabled,
                         "event_debounce_seconds": debounce}
        cbs = []
        entry.async_on_unload = lambda cb: cbs.append(cb)
        entry._unload_callbacks = cbs
        return hass, entry

    def test_registers_all_monitored_events(self):
        from custom_components.config_auditor.event_monitor import (
            async_setup_event_monitor, MONITORED_EVENTS,
        )
        hass, entry = self._make_hass_entry()
        async_setup_event_monitor(hass, entry)
        registered = [c[0][0] for c in hass.bus.async_listen.call_args_list]
        for event in MONITORED_EVENTS:
            assert event in registered, f"Missing listener for {event}"

    def test_automation_reloaded_in_monitored_events(self):
        from custom_components.config_auditor.event_monitor import MONITORED_EVENTS
        assert "automation_reloaded" in MONITORED_EVENTS

    def test_script_and_scene_in_monitored_events(self):
        from custom_components.config_auditor.event_monitor import MONITORED_EVENTS
        assert "script_reloaded" in MONITORED_EVENTS
        assert "scene_reloaded" in MONITORED_EVENTS

    def test_entity_registry_updated_in_monitored_events(self):
        from custom_components.config_auditor.event_monitor import MONITORED_EVENTS
        assert "entity_registry_updated" in MONITORED_EVENTS

    def test_unload_callbacks_registered(self):
        from custom_components.config_auditor.event_monitor import (
            async_setup_event_monitor, MONITORED_EVENTS,
        )
        hass, entry = self._make_hass_entry()
        async_setup_event_monitor(hass, entry)
        assert len(entry._unload_callbacks) >= len(MONITORED_EVENTS)

    def test_disabled_monitoring_does_not_crash(self):
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor
        hass, entry = self._make_hass_entry(monitoring_enabled=False)
        async_setup_event_monitor(hass, entry)

    @pytest.mark.asyncio
    async def test_debounce_coalesces_rapid_events(self):
        from custom_components.config_auditor.event_monitor import async_setup_event_monitor
        from custom_components.config_auditor.tests.conftest import MockHass
        hass = MockHass()
        loop = asyncio.get_event_loop()
        hass.loop = loop
        scan_count = 0

        coord = MagicMock()
        async def mock_refresh():
            nonlocal scan_count
            scan_count += 1
        coord.async_refresh = mock_refresh

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"event_debounce_seconds": 0.05}
        entry.async_on_unload = lambda cb: None
        hass.data["config_auditor"] = {"test_entry": {"coordinator": coord}}

        listeners = {}
        hass.bus.async_listen = lambda evt, handler: listeners.update({evt: handler}) or (lambda: None)

        async_setup_event_monitor(hass, entry)

        fake_event = MagicMock()
        for _ in range(5):
            if "automation_reloaded" in listeners:
                listeners["automation_reloaded"](fake_event)

        await asyncio.sleep(0.2)
        assert scan_count <= 1, f"Debounce failed: {scan_count} scans triggered"


# ══════════════════════════════════════════════════════════════════════════════
# models
# ══════════════════════════════════════════════════════════════════════════════

class TestModelsImportIntegration:
    def test_all_models_importable(self):
        from custom_components.config_auditor.models import (
            AuditIssue, ComplexityScore, BatteryEntry,
            IssueDict, GraphNodeDict, GraphEdgeDict, CoordinatorData,
        )
        assert all(m is not None for m in (
            AuditIssue, ComplexityScore, BatteryEntry,
            IssueDict, GraphNodeDict, GraphEdgeDict, CoordinatorData,
        ))

    def test_coordinator_data_has_required_keys(self):
        from custom_components.config_auditor.models import CoordinatorData
        required = [
            "health_score", "total_issues", "automation_issue_list",
            "battery_list", "dependency_graph", "complexity_scores",
        ]
        ann = CoordinatorData.__annotations__
        for key in required:
            assert key in ann, f"Missing key in CoordinatorData: {key}"


# ══════════════════════════════════════════════════════════════════════════════
# manifest.json consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestManifestConsistency:
    def _load_manifest(self):
        import json
        p = Path(__file__).parent.parent / "manifest.json"
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_manifest_version_matches_const(self):
        from custom_components.config_auditor.const import VERSION
        manifest = self._load_manifest()
        assert manifest["version"] == VERSION, (
            f"manifest.json version {manifest['version']!r} != const.py VERSION {VERSION!r}. "
            "Both must be updated together."
        )

    def test_manifest_has_required_keys(self):
        manifest = self._load_manifest()
        for key in ("domain", "name", "version", "config_flow", "requirements"):
            assert key in manifest, f"Missing key in manifest.json: {key}"

    def test_manifest_domain_is_config_auditor(self):
        manifest = self._load_manifest()
        assert manifest["domain"] == "config_auditor"


# ══════════════════════════════════════════════════════════════════════════════
# Service registration is admin-only
# ══════════════════════════════════════════════════════════════════════════════

class TestServicesAreAdminOnly:
    """Plain hass.services.async_register accepts any logged-in user.

    HACA's services rewrite configuration files (restore_backup, fix_device_id,
    purge_ghosts…), which Home Assistant reserves for admins. Every one of them
    must go through _register_admin(), which wraps the handler in _admin_only().
    """

    @staticmethod
    def _source() -> str:
        return (Path(__file__).parent.parent / "services.py").read_text(encoding="utf-8")

    def test_admin_wrapper_exists(self):
        src = self._source()
        assert "def _admin_only(" in src, "services.py must define _admin_only()"
        assert "raise Unauthorized(context=call.context)" in src, \
            "_admin_only must refuse non-admins with Unauthorized"
        assert "if user_id is not None:" in src, (
            "calls with no user_id (automations, HACA's own internal calls) "
            "must keep working — that is what HA's own admin handler does"
        )

    def test_no_service_registered_without_the_guard(self):
        src = self._source()
        raw = [
            line.strip()
            for line in src.split("\n")
            if "hass.services.async_register(" in line
        ]
        # The only surviving call is the one inside _register_admin itself.
        assert len(raw) == 1, (
            "service(s) registered outside _register_admin(), so callable by any "
            "logged-in user:\n" + "\n".join(raw)
        )
        helper = src[src.index("def _register_admin("):]
        helper = helper[:helper.index("\n\n")]
        assert "_admin_only(hass, handler)" in helper, \
            "_register_admin no longer wraps the handler"

    def test_every_service_goes_through_register_admin(self):
        src = self._source()
        registrations = src.count("_register_admin(")
        # 1 definition + 1 call inside it + one per registered service.
        assert registrations >= 20, (
            f"only {registrations} _register_admin references — services were "
            "probably registered some other way"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Exposed features: MCP server / proactive agent / LLM API
# ══════════════════════════════════════════════════════════════════════════════

class TestExposedFeatureOptions:
    """The three surfaces that reach outside the panel are options now (1.8.0).

    They are off on a new install, and an entry created before 1.8.0 — when all
    three ran unconditionally — is migrated to on, so upgrading H.A.C.A never
    silently switches off a server somebody is talking to.
    """

    BASE = Path(__file__).parent.parent

    def _entry(self, *, version=1, minor_version=1, options=None):
        entry = MagicMock()
        entry.version = version
        entry.minor_version = minor_version
        entry.options = options if options is not None else {}
        entry.entry_id = "haca_entry"
        return entry

    @pytest.mark.asyncio
    async def test_pre_1_8_0_entry_keeps_all_three_enabled(self):
        from custom_components.config_auditor import async_migrate_entry
        from custom_components.config_auditor.const import (
            OPT_MCP_SERVER_ENABLED,
            OPT_PROACTIVE_AGENT_ENABLED,
            OPT_LLM_API_ENABLED,
        )

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._entry(options={"scan_interval": 60})

        assert await async_migrate_entry(hass, entry) is True

        _, kwargs = hass.config_entries.async_update_entry.call_args
        assert kwargs["minor_version"] == 2
        assert kwargs["options"][OPT_MCP_SERVER_ENABLED] is True
        assert kwargs["options"][OPT_PROACTIVE_AGENT_ENABLED] is True
        assert kwargs["options"][OPT_LLM_API_ENABLED] is True
        # Untouched options survive the migration.
        assert kwargs["options"]["scan_interval"] == 60

    @pytest.mark.asyncio
    async def test_migration_does_not_override_an_explicit_choice(self):
        from custom_components.config_auditor import async_migrate_entry
        from custom_components.config_auditor.const import OPT_MCP_SERVER_ENABLED

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._entry(options={OPT_MCP_SERVER_ENABLED: False})

        await async_migrate_entry(hass, entry)

        _, kwargs = hass.config_entries.async_update_entry.call_args
        assert kwargs["options"][OPT_MCP_SERVER_ENABLED] is False

    @pytest.mark.asyncio
    async def test_already_migrated_entry_is_left_alone(self):
        from custom_components.config_auditor import async_migrate_entry

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        assert await async_migrate_entry(hass, self._entry(minor_version=2)) is True
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_from_a_newer_haca_is_refused(self):
        from custom_components.config_auditor import async_migrate_entry

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()

        assert await async_migrate_entry(hass, self._entry(version=2)) is False
        hass.config_entries.async_update_entry.assert_not_called()

    def test_config_flow_declares_the_migration_target(self):
        from custom_components.config_auditor.config_flow import ConfigAuditorConfigFlow

        assert ConfigAuditorConfigFlow.VERSION == 1
        assert ConfigAuditorConfigFlow.MINOR_VERSION == 2, (
            "async_migrate_entry migrates to minor_version 2 — HA only calls it "
            "while the flow declares a higher version than the stored entry"
        )

    def test_defaults_are_off(self):
        from custom_components.config_auditor.const import (
            DEFAULT_MCP_SERVER_ENABLED,
            DEFAULT_PROACTIVE_AGENT_ENABLED,
            DEFAULT_LLM_API_ENABLED,
        )

        assert DEFAULT_MCP_SERVER_ENABLED is False
        assert DEFAULT_PROACTIVE_AGENT_ENABLED is False
        assert DEFAULT_LLM_API_ENABLED is False

    def test_setup_reads_the_options(self):
        """Each of the three setups must be gated on its option, not just its
        MODULE_* compile flag."""
        src = (self.BASE / "__init__.py").read_text(encoding="utf-8")
        for opt in ("OPT_MCP_SERVER_ENABLED", "OPT_PROACTIVE_AGENT_ENABLED",
                    "OPT_LLM_API_ENABLED"):
            assert f"entry.options.get(\n        {opt}" in src or f"get({opt}," in src, (
                f"{opt} is never read in async_setup_entry — the toggle would do nothing"
            )

    def test_panel_can_save_the_options(self):
        """A toggle the panel cannot write is a toggle that does nothing."""
        src = (self.BASE / "websocket.py").read_text(encoding="utf-8")
        # Slice on the closing line, not the next "}": several entries carry a
        # comment that contains one ("# dict {entity_id: ISO datetime}").
        lines = src.split("\n")
        start = next(i for i, l in enumerate(lines) if "ALLOWED_KEYS = {" in l)
        end = next(i for i, l in enumerate(lines[start:], start) if l.strip() == "}")
        allowed = "\n".join(lines[start:end])
        for opt in ("OPT_MCP_SERVER_ENABLED", "OPT_PROACTIVE_AGENT_ENABLED",
                    "OPT_LLM_API_ENABLED"):
            assert opt in allowed, f"{opt} missing from handle_save_options ALLOWED_KEYS"
        assert "async_reload(entry.entry_id)" in src, (
            "the three options are read only at setup, so save_options must "
            "reload the entry when one of them changes"
        )
