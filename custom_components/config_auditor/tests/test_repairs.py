"""Tests for repairs.py — the one-way push of HIGH issues into HA Repairs.

Rewritten in 1.8.0. The previous file tested the pre-1.7 ``HacaFixFlow``
design — init/confirm steps, ``async_create_fix_flow``, ``_sanitize_ph`` — none
of which survives in ``repairs.py``, so all 30 of its tests failed on import and
had been skipped ever since. The module they were meant to protect kept running
for every user on every scan.

What is covered here is what the module actually does now:

  - a HIGH issue becomes exactly one Repairs entry, MEDIUM and LOW never do;
  - all nine coordinator issue lists are read;
  - previous HACA entries are cleared first, entries of other domains are not;
  - the flood cap holds;
  - user text reaches HA as a *placeholder value*, never as part of the
    template — the ``{ }``-in-a-message crash the old file was written for;
  - the placeholder names the code sends are the ones the translation files
    declare, in all 13 languages.

``homeassistant.helpers.issue_registry`` is replaced by a recorder: the real one
needs a live hass with loaded storage, and what matters here is the call, not
HA's own bookkeeping.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

TRANSLATIONS = Path(__file__).parent.parent / "translations"

# The nine lists repairs.py walks. Pinned here on purpose: a tenth category
# added to the coordinator and forgotten in repairs.py fails this file rather
# than silently never reaching the Repairs panel.
ISSUE_LISTS = (
    "automation_issue_list", "script_issue_list", "scene_issue_list",
    "blueprint_issue_list", "entity_issue_list", "helper_issue_list",
    "performance_issue_list", "security_issue_list", "dashboard_issue_list",
)


# ── Test doubles ─────────────────────────────────────────────────────────────

class _FakeRegistry:
    """Only the ``issues`` mapping is read by repairs.py."""

    def __init__(self):
        self.issues: dict[tuple[str, str], dict] = {}


class FakeIssueRegistry:
    """Stand-in for ``homeassistant.helpers.issue_registry``."""

    class IssueSeverity:
        WARNING = "warning"
        ERROR = "error"
        CRITICAL = "critical"

    def __init__(self):
        self.registry = _FakeRegistry()
        self.created: list[dict] = []
        self.deleted: list[tuple[str, str]] = []

    def async_get(self, hass):
        return self.registry

    def async_delete_issue(self, hass, domain, issue_id):
        self.deleted.append((domain, issue_id))
        self.registry.issues.pop((domain, issue_id), None)

    def async_create_issue(self, hass, **kwargs):
        self.created.append(kwargs)
        self.registry.issues[(kwargs["domain"], kwargs["issue_id"])] = kwargs

    # convenience for the assertions below
    def created_ids(self) -> list[str]:
        return [c["issue_id"] for c in self.created]


@pytest.fixture
def fake_ir(monkeypatch):
    """Swap the issue registry module the function imports at call time."""
    from homeassistant import helpers

    fake = FakeIssueRegistry()
    monkeypatch.setattr(helpers, "issue_registry", fake, raising=False)
    return fake


def issue(entity_id="automation.test", type_="device_id_in_trigger",
          severity="high", **extra) -> dict:
    base = {"entity_id": entity_id, "type": type_, "severity": severity}
    base.update(extra)
    return base


def coordinator_data(**lists) -> dict:
    """Coordinator payload with every issue list present, empty by default."""
    data = {name: [] for name in ISSUE_LISTS}
    data.update(lists)
    return data


async def run(hass, data):
    from custom_components.config_auditor.repairs import async_update_repairs
    await async_update_repairs(hass, data)


# ── What gets pushed ─────────────────────────────────────────────────────────

class TestWhatIsPushed:

    @pytest.mark.asyncio
    async def test_a_high_issue_becomes_one_repair_entry(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(message="Uses device_id", recommendation="Use entity_id"),
        ]))

        assert len(fake_ir.created) == 1
        entry = fake_ir.created[0]
        assert entry["domain"] == "config_auditor"
        assert entry["issue_id"] == "haca_automation.test_device_id_in_trigger"
        assert entry["translation_key"] == "generic_high_issue"
        assert entry["severity"] == FakeIssueRegistry.IssueSeverity.WARNING

    @pytest.mark.asyncio
    async def test_only_high_severity_is_pushed(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(entity_id="automation.a", severity="high"),
            issue(entity_id="automation.b", severity="medium"),
            issue(entity_id="automation.c", severity="low"),
            issue(entity_id="automation.d", severity=None),
        ]))

        assert fake_ir.created_ids() == ["haca_automation.a_device_id_in_trigger"]

    @pytest.mark.asyncio
    async def test_every_coordinator_issue_list_is_read(self, mock_hass, fake_ir):
        data = coordinator_data(**{
            name: [issue(entity_id=f"automation.{name}")] for name in ISSUE_LISTS
        })

        await run(mock_hass, data)

        assert len(fake_ir.created) == len(ISSUE_LISTS)

    @pytest.mark.asyncio
    async def test_the_same_issue_in_two_lists_is_pushed_once(self, mock_hass, fake_ir):
        same = issue(entity_id="automation.dup", type_="zombie_entity")
        await run(mock_hass, coordinator_data(
            automation_issue_list=[dict(same)],
            entity_issue_list=[dict(same)],
        ))

        assert fake_ir.created_ids() == ["haca_automation.dup_zombie_entity"]

    @pytest.mark.asyncio
    async def test_the_number_of_entries_is_capped(self, mock_hass, fake_ir):
        from custom_components.config_auditor.repairs import MAX_REPAIR_ISSUES

        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(entity_id=f"automation.n{i}") for i in range(MAX_REPAIR_ISSUES * 2)
        ]))

        assert len(fake_ir.created) == MAX_REPAIR_ISSUES

    @pytest.mark.asyncio
    async def test_entries_are_never_fixable(self, mock_hass, fake_ir):
        """No fix flow exists, so a Fix button would open nothing.

        The source-level guard lives in test_repairs_diagnostics.py; this is the
        same contract seen from the call HA actually receives.
        """
        await run(mock_hass, coordinator_data(automation_issue_list=[issue()]))

        assert fake_ir.created[0]["is_fixable"] is False
        assert fake_ir.created[0]["is_persistent"] is False

    @pytest.mark.asyncio
    async def test_empty_coordinator_data_touches_nothing(self, mock_hass, fake_ir):
        fake_ir.registry.issues[("config_auditor", "haca_stale")] = {}

        await run(mock_hass, {})

        assert fake_ir.created == []
        assert fake_ir.deleted == [], (
            "An empty payload means the scan produced nothing, not that the "
            "panel should be emptied"
        )


# ── Clean slate ──────────────────────────────────────────────────────────────

class TestCleanSlate:

    @pytest.mark.asyncio
    async def test_previous_haca_entries_are_cleared_first(self, mock_hass, fake_ir):
        fake_ir.registry.issues[("config_auditor", "haca_old_one")] = {}
        fake_ir.registry.issues[("config_auditor", "haca_old_two")] = {}

        await run(mock_hass, coordinator_data(automation_issue_list=[issue()]))

        assert fake_ir.deleted == [
            ("config_auditor", "haca_old_one"),
            ("config_auditor", "haca_old_two"),
        ]

    @pytest.mark.asyncio
    async def test_other_domains_are_left_alone(self, mock_hass, fake_ir):
        fake_ir.registry.issues[("homeassistant", "deprecated_yaml")] = {}
        fake_ir.registry.issues[("hacs", "restart_required")] = {}

        await run(mock_hass, coordinator_data())

        assert fake_ir.deleted == []
        assert ("homeassistant", "deprecated_yaml") in fake_ir.registry.issues
        assert ("hacs", "restart_required") in fake_ir.registry.issues

    @pytest.mark.asyncio
    async def test_a_resolved_issue_disappears_on_the_next_scan(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(entity_id="automation.gone"),
        ]))
        assert ("config_auditor", "haca_automation.gone_device_id_in_trigger") \
            in fake_ir.registry.issues

        await run(mock_hass, coordinator_data(automation_issue_list=[]))

        assert fake_ir.registry.issues == {}


# ── The text handed to Home Assistant ────────────────────────────────────────

class TestPlaceholders:

    @pytest.mark.asyncio
    async def test_alias_is_preferred_over_entity_id(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(alias="Evening lights"),
        ]))

        assert fake_ir.created[0]["translation_placeholders"]["entity"] == "Evening lights"

    @pytest.mark.asyncio
    async def test_the_type_is_made_readable(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(type_="device_id_in_trigger"),
        ]))

        assert fake_ir.created[0]["translation_placeholders"]["type"] == "Device id in trigger"

    @pytest.mark.asyncio
    async def test_the_recommendation_is_appended_under_a_label(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(message="Trigger uses a device_id.", recommendation="Target the entity."),
        ]))

        message = fake_ir.created[0]["translation_placeholders"]["message"]
        assert message.startswith("Trigger uses a device_id.")
        assert message.endswith("Recommendation: Target the entity.")

    @pytest.mark.asyncio
    async def test_long_text_is_truncated(self, mock_hass, fake_ir):
        await run(mock_hass, coordinator_data(automation_issue_list=[
            issue(message="m" * 500, recommendation="r" * 500),
        ]))

        message = fake_ir.created[0]["translation_placeholders"]["message"]
        assert "m" * 200 in message
        assert "m" * 201 not in message
        assert "r" * 200 in message
        assert "r" * 201 not in message

    @pytest.mark.asyncio
    async def test_braces_in_a_message_reach_ha_untouched(self, mock_hass, fake_ir):
        """The regression the previous file was written for.

        A user's message can contain ``{`` and ``}`` — a Jinja template quoted
        back at them, for instance. That text is only safe as a placeholder
        *value*: built into the template instead, ``str.format`` reads it as a
        field name and raises KeyError on the user's own config.
        """
        raw = "Template {{ states('sensor.x') }} and a bare { } pair"
        await run(mock_hass, coordinator_data(automation_issue_list=[issue(message=raw)]))

        entry = fake_ir.created[0]
        assert entry["translation_placeholders"]["message"] == raw
        assert entry["translation_key"] == "generic_high_issue"

        template = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))
        description = template["issues"]["generic_high_issue"]["description"]
        rendered = description.format(**entry["translation_placeholders"])
        assert raw in rendered

    @pytest.mark.asyncio
    async def test_the_placeholders_sent_are_the_ones_every_language_declares(
        self, mock_hass, fake_ir
    ):
        import re

        await run(mock_hass, coordinator_data(automation_issue_list=[issue()]))
        sent = set(fake_ir.created[0]["translation_placeholders"])

        pattern = re.compile(r"\{([a-z_]+)\}")
        for path in sorted(TRANSLATIONS.glob("*.json")):
            strings = json.loads(path.read_text(encoding="utf-8"))
            entry = strings["issues"]["generic_high_issue"]
            wanted = set(pattern.findall(entry["title"] + entry["description"]))
            assert wanted <= sent, (
                f"{path.stem}.json asks for {sorted(wanted - sent)}, which "
                f"repairs.py never sends — the placeholder renders empty"
            )


# ── Degraded environments ────────────────────────────────────────────────────

class TestOldHomeAssistant:

    @pytest.mark.asyncio
    async def test_a_missing_issue_registry_is_not_fatal(
        self, mock_hass, monkeypatch, caplog
    ):
        """Pre-2023.1 has no issue_registry; the scan must still finish.

        The log assertion is what makes this a test: without it, the import
        could keep succeeding and the case would never be exercised.
        """
        import logging

        from homeassistant import helpers

        monkeypatch.delattr(helpers, "issue_registry", raising=False)
        monkeypatch.setitem(sys.modules, "homeassistant.helpers.issue_registry", None)

        with caplog.at_level(logging.DEBUG, logger="custom_components.config_auditor.repairs"):
            await run(mock_hass, coordinator_data(automation_issue_list=[issue()]))

        assert "issue_registry not available" in caplog.text

    @pytest.mark.asyncio
    async def test_a_registry_that_raises_does_not_stop_the_scan(self, mock_hass, fake_ir):
        def boom(hass):
            raise RuntimeError("registry not loaded")

        fake_ir.async_get = boom

        await run(mock_hass, coordinator_data(automation_issue_list=[issue()]))

        # Clearing failed, but the push still happened.
        assert len(fake_ir.created) == 1


# ── Readable type ────────────────────────────────────────────────────────────

class TestReadableType:

    def test_snake_case_becomes_a_sentence(self):
        from custom_components.config_auditor.repairs import _readable_type
        assert _readable_type("incorrect_mode_for_pattern") == "Incorrect mode for pattern"

    def test_a_single_word_is_only_capitalised(self):
        from custom_components.config_auditor.repairs import _readable_type
        assert _readable_type("zombie") == "Zombie"

    def test_an_empty_type_stays_empty(self):
        from custom_components.config_auditor.repairs import _readable_type
        assert _readable_type("") == ""


# ── The option that gates the whole thing ────────────────────────────────────

class TestOptionGate:
    """``repairs_enabled`` is read in __init__.py, not in repairs.py.

    Reaching the listener needs a full ``async_setup_entry``, so this checks the
    wiring at the source level: the option name and, above all, that its default
    is True — flipping that default would empty every user's Repairs panel on
    the next scan without anything else in the suite noticing.
    """

    def test_the_push_is_gated_by_repairs_enabled_defaulting_to_true(self):
        from custom_components.config_auditor import repairs

        init_py = Path(repairs.__file__).parent / "__init__.py"
        source = init_py.read_text(encoding="utf-8")

        assert 'entry.options.get("repairs_enabled", True)' in source
        assert "async_update_repairs(hass, cdata)" in source
