"""Runtime tests for the phase-2 bug fixes of the 1.7.7 audit.

Each class maps to one card of AUDIT_PLAN.md:

  2-1  entity references are collected recursively (choose:, templates, targets)
  2-2  get_data no longer truncates a category silently
  2-3  ai_suggest_fix / apply_field_fix find the entry on a split config
  2-4  apply_field_fix keeps comments and takes a backup
  2-5  asking for one category narrows the answer instead of widening it
  2-6  history retention counts days, not scans
  2-8  the battery library reads a user file outside the integration folder

    pytest custom_components/config_auditor/tests/test_audit_phase2.py -v
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import (
    MockDeviceEntry,
    MockHass,
    MockRegistryEntry,
)


def _write(tmp_path, files: dict) -> None:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _hass(tmp_path, files: dict | None = None) -> MockHass:
    if files:
        _write(tmp_path, files)
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    return hass


def _entity_analyzer(hass):
    with patch(
        "custom_components.config_auditor.entity_analyzer.TranslationHelper"
    ) as TH:
        TH.return_value.t = lambda key, **kw: key
        TH.return_value.async_load_language = AsyncMock()
        from custom_components.config_auditor.entity_analyzer import EntityAnalyzer

        analyzer = EntityAnalyzer(hass)
    analyzer._ignored_entity_ids = set()
    return analyzer


# ══════════════════════════════════════════════════════════════════════════════
# 2-1 — recursive entity references
# ══════════════════════════════════════════════════════════════════════════════

class TestRecursiveEntityReferences:
    """_build_entity_references must walk the whole config, not just level one."""

    @pytest.mark.asyncio
    async def test_reference_inside_choose_branch_counts(self, tmp_path):
        """The regression that made this a 🔴: choose: hid every reference."""
        hass = _hass(tmp_path)
        hass.add_state("input_boolean.test", "off", {"friendly_name": "Test"})
        configs = {
            "automation.deep": {
                "alias": "Deep",
                "triggers": [{"platform": "time", "at": "07:00"}],
                "actions": [
                    {
                        "choose": [
                            {
                                "conditions": [],
                                "sequence": [
                                    {
                                        "service": "input_boolean.turn_on",
                                        "target": {"entity_id": "input_boolean.test"},
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        assert analyzer._entity_references.get("input_boolean.test") == ["automation.deep"]

        await analyzer._analyze_input_helpers(configs, {})
        unused = [i for i in analyzer.issues if i["type"] == "helper_unused"]
        assert not unused, "a helper used inside a choose: branch is not unused"

    @pytest.mark.asyncio
    async def test_nested_if_repeat_parallel_and_data(self, tmp_path):
        hass = _hass(tmp_path)
        for eid in (
            "light.if_branch", "light.else_branch", "light.repeated",
            "light.parallel", "light.in_data", "light.defaulted",
        ):
            hass.add_state(eid, "on")
        configs = {
            "automation.every_shape": {
                "actions": [
                    {
                        "if": [{"condition": "state", "entity_id": "light.if_branch"}],
                        "then": [{"service": "light.turn_on",
                                  "target": {"entity_id": "light.repeated"}}],
                        "else": [{"service": "light.turn_off",
                                  "entity_id": "light.else_branch"}],
                    },
                    {"repeat": {"count": 3, "sequence": [
                        {"service": "light.toggle",
                         "target": {"entity_id": "light.repeated"}}]}},
                    {"parallel": [{"service": "light.turn_on",
                                   "target": {"entity_id": "light.parallel"}}]},
                    {"service": "notify.notify",
                     "data": {"entity_id": "light.in_data"}},
                    {"choose": [], "default": [
                        {"service": "light.turn_on",
                         "target": {"entity_id": "light.defaulted"}}]},
                ],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        for eid in (
            "light.if_branch", "light.else_branch", "light.repeated",
            "light.parallel", "light.in_data", "light.defaulted",
        ):
            assert eid in analyzer._entity_references, f"{eid} was not collected"

    @pytest.mark.asyncio
    async def test_template_reference_counts_only_for_existing_entities(self, tmp_path):
        """A regex hit proves usage, never a zombie — and never for a service name."""
        hass = _hass(tmp_path)
        hass.add_state("sensor.outside", "12")
        configs = {
            "automation.templated": {
                "conditions": [
                    {"condition": "template",
                     "value_template": "{{ states('sensor.outside') | float > 10 }}"}
                ],
                "actions": [{"service": "light.turn_on"}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        assert "sensor.outside" in analyzer._entity_references
        assert "light.turn_on" not in analyzer._entity_references, \
            "a service name must not be mistaken for an entity reference"
        assert "sensor.outside" not in analyzer._strong_entity_references, \
            "a template hit is a weak reference and must not feed zombie detection"

    @pytest.mark.asyncio
    async def test_template_reference_never_produces_a_zombie(self, tmp_path):
        hass = _hass(tmp_path)
        configs = {
            "automation.ghosty": {
                "actions": [{"service": "notify.notify", "data": {
                    "message": "{{ states('sensor.does_not_exist') }}"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_zombie_entities()

        assert not analyzer.issues, "an unresolved template hit is not a zombie entity"

    @pytest.mark.asyncio
    async def test_explicit_entity_id_still_produces_a_zombie(self, tmp_path):
        hass = _hass(tmp_path)
        configs = {
            "automation.broken": {
                "alias": "Broken",
                "actions": [{"service": "light.turn_on",
                             "target": {"entity_id": "light.removed"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_zombie_entities()

        assert [i["type"] for i in analyzer.issues] == ["zombie_entity"]
        assert analyzer.issues[0]["entity_id"] == "light.removed"

    @pytest.mark.asyncio
    async def test_half_templated_entity_id_is_not_a_zombie(self, tmp_path):
        hass = _hass(tmp_path)
        configs = {
            "automation.dynamic": {
                "actions": [{"service": "light.turn_on",
                             "target": {"entity_id": "light.{{ room }}_ceiling"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})
        await analyzer._analyze_zombie_entities()

        assert not analyzer.issues, \
            "'light.{{ room }}_ceiling' is a template, not a missing entity"

    @pytest.mark.asyncio
    async def test_area_and_device_targets_resolve_to_entities(self, tmp_path):
        hass = _hass(tmp_path)
        hass.add_device(MockDeviceEntry("dev1", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("light.lamp", device_id="dev1"))
        hass.add_registry_entry(MockRegistryEntry("switch.plug", area_id="salon"))
        hass.add_registry_entry(MockRegistryEntry("fan.tagged", labels={"night"}))

        configs = {
            "automation.by_area":   {"actions": [{"target": {"area_id": "salon"}}]},
            "automation.by_device": {"actions": [{"target": {"device_id": "dev1"}}]},
            "automation.by_label":  {"actions": [{"target": {"label_id": "night"}}]},
        }

        analyzer = _entity_analyzer(hass)
        await analyzer._build_entity_references(configs, {})

        refs = analyzer._entity_references
        assert "automation.by_area" in refs["light.lamp"], "device inherits its area"
        assert "automation.by_area" in refs["switch.plug"]
        assert "automation.by_device" in refs["light.lamp"]
        assert "automation.by_label" in refs["fan.tagged"]
        assert not analyzer._strong_entity_references, \
            "a target: selector is a weak reference"

    @pytest.mark.asyncio
    async def test_unused_input_boolean_has_the_same_safety_net(self, tmp_path):
        """Card 2-1 item 4: align the two 'unused helper' detectors."""
        hass = _hass(tmp_path)
        hass.add_state("input_boolean.only_in_text", "off")
        configs = {
            "automation.obscure": {
                "actions": [{"service": "python_script.x",
                             "data": {"which": "input_boolean.only_in_text"}}],
            }
        }

        analyzer = _entity_analyzer(hass)
        # Strip the reference map so only the raw-text net can save the helper.
        await analyzer._build_entity_references(configs, {})
        analyzer._entity_references = {}
        await analyzer._analyze_unused_input_booleans()

        assert not analyzer.issues, \
            "a helper named anywhere in the configs must not be reported unused"


# ══════════════════════════════════════════════════════════════════════════════
# 2-3 / 2-4 — apply_field_fix on split configs, without destroying the file
# ══════════════════════════════════════════════════════════════════════════════

SPLIT_CONFIG = {
    "configuration.yaml": (
        "automation: !include_dir_merge_list automations/\n"
        "script: !include_dir_merge_named ha_scripts/\n"
    ),
    "automations/clima.yaml": (
        "# Climate automations — keep this comment!\n"
        "- id: a1\n"
        "  alias: Clima\n"
        "  triggers: []\n"
        "  actions: []\n"
    ),
    "ha_scripts/general.yaml": "notificar_todo:\n  alias: Notificar\n  sequence: []\n",
}


def _ws():
    return pytest.importorskip(
        "custom_components.config_auditor.websocket",
        reason="websocket needs homeassistant",
    )


class TestFieldFixOnSplitConfig:
    """The hardcoded <config>/automations.yaml missed every split install."""

    def test_finds_automation_in_split_folder(self, tmp_path):
        ws = _ws()
        _write(tmp_path, SPLIT_CONFIG)
        match = ws._find_entry_sync(str(tmp_path), "automation.a1", "Clima")

        assert match.entry is not None, "the entry lives in automations/clima.yaml"
        assert Path(match.path).name == "clima.yaml"
        assert match.entry["alias"] == "Clima"

    def test_finds_script_in_split_folder(self, tmp_path):
        ws = _ws()
        _write(tmp_path, SPLIT_CONFIG)
        match = ws._find_entry_sync(str(tmp_path), "script.notificar_todo", "Notificar")

        assert match.entry is not None
        assert Path(match.path).name == "general.yaml"

    def test_miss_says_how_many_files_were_searched(self, tmp_path):
        ws = _ws()
        _write(tmp_path, SPLIT_CONFIG)
        match = ws._find_entry_sync(str(tmp_path), "automation.nope", "Nope")

        assert match.entry is None
        message = ws._entry_not_found_message("automation.nope", "Nope", match)
        assert f"{len(match.files)} scanned" in message
        assert match.files, "the resolver must report the files it looked at"

    def test_entry_can_be_dumped_as_a_yaml_snippet(self, tmp_path):
        """ai_suggest_fix feeds the entry to the LLM as YAML text."""
        ws = _ws()
        import io as _io

        _write(tmp_path, SPLIT_CONFIG)
        match = ws._find_entry_sync(str(tmp_path), "automation.a1", "Clima")
        buffer = _io.StringIO()
        match.yaml.dump(match.entry, buffer)

        assert "alias: Clima" in buffer.getvalue()

    def test_numeric_id_beats_a_colliding_alias(self, tmp_path):
        ws = _ws()
        _write(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/one.yaml": "- id: other\n  alias: Clima\n  actions: []\n",
            "automations/two.yaml": "- id: a1\n  alias: Something else\n  actions: []\n",
        })
        match = ws._find_entry_sync(str(tmp_path), "automation.a1", "Clima")

        assert match.entry["id"] == "a1", "the id pass must run before the alias pass"

    def test_file_with_ha_tags_is_skipped_not_rewritten(self, tmp_path):
        ws = _ws()
        _write(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/secrets.yaml": (
                "- id: a9\n  alias: Tagged\n  actions:\n"
                "    - service: notify.notify\n      data:\n"
                "        message: !secret my_message\n"
            ),
        })
        match = ws._find_entry_sync(str(tmp_path), "automation.a9", "Tagged")

        assert match.entry is None, "a file we cannot safely rewrite must not match"
        assert match.skipped, "and it must be reported as skipped"
        assert "!secret" in ws.skipped_note(match.skipped)


class TestFieldFixPreservesTheFile:
    """Card 2-4: safe_load + dump flattened comments and took no backup."""

    def test_comment_survives_the_edit(self, tmp_path):
        ws = _ws()
        from custom_components.config_auditor.yaml_sources import write_roundtrip_yaml

        _write(tmp_path, SPLIT_CONFIG)
        match = ws._find_entry_sync(str(tmp_path), "automation.a1", "Clima")
        match.entry["description"] = "Generated by HACA"
        write_roundtrip_yaml(match.path, match.yaml, match.document)

        written = Path(match.path).read_text(encoding="utf-8")
        assert "# Climate automations — keep this comment!" in written
        assert "description: Generated by HACA" in written
        assert "alias: Clima" in written

    def test_write_is_atomic_and_leaves_no_temp_file(self, tmp_path):
        ws = _ws()
        from custom_components.config_auditor.yaml_sources import write_roundtrip_yaml

        _write(tmp_path, SPLIT_CONFIG)
        match = ws._find_entry_sync(str(tmp_path), "automation.a1", "Clima")
        write_roundtrip_yaml(match.path, match.yaml, match.document)

        assert not (tmp_path / "automations" / "clima.yaml.tmp").exists()


# ══════════════════════════════════════════════════════════════════════════════
# 2-2 / 2-5 — get_data pagination and category filter
# ══════════════════════════════════════════════════════════════════════════════

class TestGetDataContract:
    def test_helper_list_is_part_of_the_response(self):
        ws = _ws()
        assert ws.ISSUE_CATEGORY_MAP["helper"] == "helper_issue_list", (
            "the coordinator produces helper_issue_list and the panel renders it; "
            "get_data used to drop it, leaving the Helpers tab permanently empty"
        )

    def test_default_limit_is_not_200(self):
        ws = _ws()
        assert ws.DEFAULT_ISSUE_LIMIT >= 1000, \
            "200 truncated real installations without telling anyone"

    def test_every_category_maps_to_a_list(self):
        ws = _ws()
        for name, key in ws.ISSUE_CATEGORY_MAP.items():
            assert key.endswith("_issue_list"), f"{name} maps to {key}"


# ══════════════════════════════════════════════════════════════════════════════
# 2-6 — history retention in days
# ══════════════════════════════════════════════════════════════════════════════

class TestHistoryRetention:
    @staticmethod
    def _snapshot(days_ago: int) -> dict:
        ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return {"ts": ts.isoformat(), "score": 80, "total": 3}

    def test_old_snapshots_are_dropped_by_date(self):
        from custom_components.config_auditor.history_manager import prune_snapshots

        entries = [self._snapshot(400), self._snapshot(31), self._snapshot(1)]
        kept = prune_snapshots(entries, retention_days=30)

        assert len(kept) == 1, "only the snapshot inside the 30-day window survives"

    def test_a_day_of_scans_is_not_a_day_of_history(self):
        """The old code compared len(history) to retention_days."""
        from custom_components.config_auditor.history_manager import prune_snapshots

        # 24 scans/day for 10 days, retention 30 days: everything must be kept.
        entries = [
            {"ts": (datetime.now(timezone.utc)
                    - timedelta(hours=hours)).isoformat(), "score": 90}
            for hours in range(10 * 24)
        ]
        kept = prune_snapshots(entries, retention_days=30)

        assert len(kept) == len(entries)

    def test_hard_cap_protects_storage(self):
        from custom_components.config_auditor import history_manager as hm

        entries = [{"ts": datetime.now(timezone.utc).isoformat()}] * (
            hm.MAX_HISTORY_SNAPSHOTS + 10
        )
        kept = hm.prune_snapshots(entries, retention_days=365)

        assert len(kept) == hm.MAX_HISTORY_SNAPSHOTS

    def test_undatable_snapshot_is_kept(self):
        from custom_components.config_auditor.history_manager import prune_snapshots

        kept = prune_snapshots([{"score": 50}], retention_days=1)
        assert len(kept) == 1, "a snapshot with no usable ts is not evidence of age"


# ══════════════════════════════════════════════════════════════════════════════
# 2-8 — battery library user file
# ══════════════════════════════════════════════════════════════════════════════

class TestBatteryLibraryUserFile:
    @staticmethod
    def _library(hass):
        from custom_components.config_auditor.battery_library import BatteryLibrary

        return BatteryLibrary(hass)

    def test_user_file_lives_outside_the_integration_folder(self, tmp_path):
        hass = _hass(tmp_path)
        library = self._library(hass)

        assert Path(library.user_path).parent == tmp_path, \
            "HACS replaces the integration folder — the user file must not be in it"
        assert "custom_components" not in library.user_path

    @pytest.mark.asyncio
    async def test_user_entry_is_found(self, tmp_path):
        hass = _hass(tmp_path, {
            "haca_battery_library_user.json": json.dumps({"devices": [
                {"manufacturer": "Acme", "model": "Widget",
                 "battery_type": "CR2032", "battery_quantity": 2}
            ]})
        })
        library = self._library(hass)
        await library.async_load()

        assert library.lookup("Acme", "Widget") == {
            "battery_type": "CR2032", "battery_quantity": 2,
        }
        assert library.user_count == 1

    @pytest.mark.asyncio
    async def test_user_entry_overrides_the_bundled_seed(self, tmp_path):
        hass = _hass(tmp_path)
        library = self._library(hass)
        await library.async_load()
        seeded = library.size
        assert seeded > 1000, "the bundled seed should have loaded"

        # Take a real seed entry and contradict it from the user file.
        sample = next(
            e for e in library._entries
            if e.get("battery_type") not in ("MANUAL", "")
            and e.get("model_match_method", "exact") == "exact"
            and not e.get("hw_version")
        )
        _write(tmp_path, {"haca_battery_library_user.json": json.dumps({"devices": [
            {"manufacturer": sample["manufacturer"], "model": sample["model"],
             "battery_type": "9V", "battery_quantity": 1}
        ]})})

        library = self._library(hass)
        await library.async_load()

        assert library.lookup(sample["manufacturer"], sample["model"])["battery_type"] == "9V"
        assert library.size == seeded, "the shadowed seed entry must be dropped, not doubled"

    @pytest.mark.asyncio
    async def test_missing_user_file_is_not_an_error(self, tmp_path):
        hass = _hass(tmp_path)
        library = self._library(hass)
        await library.async_load()

        assert library.user_count == 0
        assert library.size > 0
