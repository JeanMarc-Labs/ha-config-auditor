"""Tests for yaml_writer — the one way HACA rewrites a config file (audit 5-1).

Two halves. The first pins the module's own contract: round-trip reads, refusal
of what must not be rewritten, atomic writes, and the shared backup naming and
pruning. The second is the point of the whole card — every caller that edits an
existing YAML file must come out the other side with the user's comments still
in it. Before 1.8.0 the refactoring assistant, the optimizer and the MCP write
tools all did `yaml.safe_load` + `yaml.dump`, which deleted every comment and
blank line in the file, not just around the entry being edited.

    pytest custom_components/config_auditor/tests/test_yaml_writer.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor import yaml_writer as yw
from custom_components.config_auditor.tests.conftest import MockHass

pytest.importorskip("ruamel.yaml", reason="yaml_writer round-trips through ruamel")


# A file that carries everything a dump would quietly destroy: a header
# comment, an inline comment, a blank line, single quotes and key order.
COMMENTED = """\
# Climate automations — keep this comment!
- id: 'a1'
  alias: Clima
  mode: single          # deliberate
  triggers: []
  actions: []

- id: 'a2'
  alias: General
  triggers: []
  actions: []
"""


def _write(tmp_path, files: dict) -> None:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _assert_untouched_parts_survive(text: str) -> None:
    assert "# Climate automations — keep this comment!" in text
    assert "# deliberate" in text
    assert "id: 'a1'" in text, "preserve_quotes must keep the user's quoting"


# ═══════════════════════════════════════════════════════════════════════════
# read_for_edit — what it accepts, and what it refuses to touch
# ═══════════════════════════════════════════════════════════════════════════

class TestReadForEdit:
    def test_round_trip_keeps_comments_through_a_rewrite(self, tmp_path):
        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")

        target = yw.read_for_edit(str(path), list)
        target.document[0]["description"] = "Added by HACA"
        yw.write_back(target)

        written = path.read_text(encoding="utf-8")
        _assert_untouched_parts_survive(written)
        assert "description: Added by HACA" in written

    def test_ha_tag_anywhere_is_refused(self, tmp_path):
        path = tmp_path / "automations.yaml"
        path.write_text(
            "- id: a9\n  alias: Tagged\n  actions:\n"
            "    - service: notify.notify\n      data:\n"
            "        message: !secret my_message\n",
            encoding="utf-8",
        )
        with pytest.raises(yw.UnsafeToEdit):
            yw.read_for_edit(str(path), list)

    def test_wrong_root_shape_is_refused(self, tmp_path):
        path = tmp_path / "scripts.yaml"
        path.write_text("- not: a mapping\n", encoding="utf-8")
        with pytest.raises(yw.UnsafeToEdit):
            yw.read_for_edit(str(path), dict)

    def test_duplicate_key_is_refused_rather_than_silently_dropped(self, tmp_path):
        """safe_load kept the last one; a rewrite would have deleted the other."""
        path = tmp_path / "scripts.yaml"
        path.write_text(
            "one:\n  alias: First\n  sequence: []\n"
            "one:\n  alias: Second\n  sequence: []\n",
            encoding="utf-8",
        )
        with pytest.raises(yw.UnsafeToEdit):
            yw.read_for_edit(str(path), dict)

    def test_missing_file_is_refused(self, tmp_path):
        with pytest.raises(yw.UnsafeToEdit):
            yw.read_for_edit(str(tmp_path / "nope.yaml"), list)

    def test_empty_file_is_refused(self, tmp_path):
        path = tmp_path / "automations.yaml"
        path.write_text("\n", encoding="utf-8")
        with pytest.raises(yw.UnsafeToEdit):
            yw.read_for_edit(str(path), list)


class TestOpenOrCreate:
    def test_absent_file_starts_a_new_document(self, tmp_path):
        target = yw.open_or_create(str(tmp_path / "scenes.yaml"), list)
        assert target.document == []

    def test_blank_file_starts_a_new_document(self, tmp_path):
        path = tmp_path / "scenes.yaml"
        path.write_text("\n\n", encoding="utf-8")
        assert yw.open_or_create(str(path), list).document == []

    def test_a_file_it_cannot_read_is_still_refused(self, tmp_path):
        """A create must never replace a file it was unable to parse."""
        path = tmp_path / "scenes.yaml"
        path.write_text("- id: s1\n  name: !secret hidden\n", encoding="utf-8")
        with pytest.raises(yw.UnsafeToEdit):
            yw.open_or_create(str(path), list)


# ═══════════════════════════════════════════════════════════════════════════
# write_back — atomic, and it snapshots when asked
# ═══════════════════════════════════════════════════════════════════════════

class TestWriteBack:
    def test_leaves_no_temp_file_behind(self, tmp_path):
        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")
        yw.write_back(yw.read_for_edit(str(path), list))

        assert not (tmp_path / "automations.yaml.haca-tmp").exists()
        siblings = [p.name for p in tmp_path.iterdir()]
        assert siblings == ["automations.yaml"]

    def test_a_failed_dump_leaves_the_original_intact(self, tmp_path):
        """os.replace is the last step, so a dump that raises changes nothing."""
        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")
        target = yw.read_for_edit(str(path), list)
        broken = MagicMock()
        broken.dump.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            yw.write_back(target._replace(yaml=broken))

        assert path.read_text(encoding="utf-8") == COMMENTED
        assert not (tmp_path / "automations.yaml.haca-tmp").exists()

    def test_no_config_dir_means_no_backup(self, tmp_path):
        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")
        assert yw.write_back(yw.read_for_edit(str(path), list)) is None
        assert not (tmp_path / ".haca_backups").exists()

    def test_config_dir_means_a_backup_of_the_previous_content(self, tmp_path):
        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")

        target = yw.read_for_edit(str(path), list)
        target.document[0]["alias"] = "Changed"
        backup = yw.write_back(target, str(tmp_path))

        assert Path(backup).read_text(encoding="utf-8") == COMMENTED, \
            "the snapshot must hold the file as it was before the write"
        assert "alias: Changed" in path.read_text(encoding="utf-8")

    def test_a_file_being_created_has_nothing_to_snapshot(self, tmp_path):
        target = yw.open_or_create(str(tmp_path / "scenes.yaml"), list)
        target.document.append({"id": "s1", "name": "New"})
        assert yw.write_back(target, str(tmp_path)) is None
        assert (tmp_path / "scenes.yaml").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Backups — one naming, one pruning policy, shared by every write path
# ═══════════════════════════════════════════════════════════════════════════

class TestBackups:
    def test_named_after_the_file_it_copies(self, tmp_path):
        source = tmp_path / "automations" / "clima.yaml"
        _write(tmp_path, {"automations/clima.yaml": COMMENTED})

        backup = Path(yw.create_backup(str(tmp_path), str(source)))
        assert backup.parent.name == ".haca_backups"
        assert backup.name.startswith("clima_")
        assert yw.backup_stem(backup.name) == "clima"

    def test_same_second_does_not_overwrite_the_previous_backup(self, tmp_path):
        _write(tmp_path, {"automations.yaml": COMMENTED})
        first = yw.create_backup(str(tmp_path), str(tmp_path / "automations.yaml"))
        second = yw.create_backup(str(tmp_path), str(tmp_path / "automations.yaml"))
        assert first != second
        assert Path(first).exists() and Path(second).exists()

    def test_pruning_is_per_source_file(self, tmp_path):
        """One busy file must not evict another file's restore points."""
        backups = tmp_path / ".haca_backups"
        backups.mkdir()
        for i in range(yw.BACKUP_KEEP + 5):
            (backups / f"clima_2026090{i // 10}_00000{i % 10}.yaml").write_text("x", encoding="utf-8")
        (backups / "bedroom_20260901_000000.yaml").write_text("x", encoding="utf-8")

        yw.prune_backups(str(tmp_path))

        names = sorted(p.name for p in backups.iterdir())
        assert (backups / "bedroom_20260901_000000.yaml").exists(), \
            "another file's only backup must survive a busy file's pruning"
        assert len([n for n in names if n.startswith("clima_")]) == yw.BACKUP_KEEP

    def test_pruning_ignores_files_that_are_not_haca_backups(self, tmp_path):
        backups = tmp_path / ".haca_backups"
        backups.mkdir()
        (backups / "my_own_notes.txt").write_text("x", encoding="utf-8")
        yw.prune_backups(str(tmp_path))
        assert (backups / "my_own_notes.txt").exists()

    def test_missing_source_is_an_error_not_an_empty_backup(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            yw.create_backup(str(tmp_path), str(tmp_path / "gone.yaml"))


# ═══════════════════════════════════════════════════════════════════════════
# Domain scanners — split configs, and what they refuse to open
# ═══════════════════════════════════════════════════════════════════════════

SPLIT = {
    "configuration.yaml": (
        "automation: !include_dir_merge_list automations/\n"
        "script: !include_dir_merge_named ha_scripts/\n"
    ),
    "automations/clima.yaml": COMMENTED,
    "automations/tagged.yaml": "- id: a3\n  alias: Tagged\n  message: !secret m\n",
    "ha_scripts/morning.yaml": "# morning block\nmorning:\n  alias: Morning\n  sequence: []\n",
}


class TestScanners:
    def test_finds_an_entry_in_a_merged_subfolder(self, tmp_path):
        _write(tmp_path, SPLIT)
        scan = yw.scan_list_domain_for_edit(
            str(tmp_path), "automation", "automations.yaml",
            lambda a: a.get("id") == "a2",
        )
        assert scan.found
        assert Path(scan.path).name == "clima.yaml"
        assert scan.index == 1
        assert scan.entry["alias"] == "General"

    def test_reports_the_files_it_would_not_rewrite(self, tmp_path):
        _write(tmp_path, SPLIT)
        scan = yw.scan_list_domain_for_edit(
            str(tmp_path), "automation", "automations.yaml",
            lambda a: a.get("id") == "a3",
        )
        assert not scan.found, "an entry in a tagged file must not be matched"
        assert any("tagged.yaml" in p for p in scan.skipped)

    def test_named_domain(self, tmp_path):
        _write(tmp_path, SPLIT)
        scan = yw.scan_named_domain_for_edit(
            str(tmp_path), "script", "scripts.yaml", lambda k, e: k == "morning",
        )
        assert scan.found and scan.key == "morning"

    def test_passes_run_across_every_file_before_the_next_pass(self, tmp_path):
        """An alias colliding in file B must not beat an exact id in file A."""
        _write(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/one.yaml": "- id: other\n  alias: a1\n  actions: []\n",
            "automations/two.yaml": "- id: a1\n  alias: Something\n  actions: []\n",
        })
        domain = yw.open_domain_for_edit(
            str(tmp_path), "automation", "automations.yaml", list
        )
        scan = yw.scan_in_passes(domain, yw.list_entries, [
            lambda k, e: str(e.get("id", "")) == "a1",
            lambda k, e: str(e.get("alias", "")) == "a1",
        ])
        assert scan.entry["id"] == "a1"


# ═══════════════════════════════════════════════════════════════════════════
# The point of card 5-1: every write path keeps the user's comments
# ═══════════════════════════════════════════════════════════════════════════

def _hass(tmp_path, files: dict) -> MockHass:
    _write(tmp_path, files)
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    return hass


FLAT = {
    "configuration.yaml": "automation: !include automations.yaml\n",
    "automations.yaml": COMMENTED,
}


def _home_assistant_accepts():
    """Validation is test_write_validation.py's subject; here, only the file matters."""
    return patch(
        "homeassistant.components.automation.config.async_validate_config_item",
        AsyncMock(return_value=None),
    )


class TestEveryWritePathPreservesComments:
    @pytest.mark.asyncio
    async def test_refactoring_assistant_mode_fix(self, tmp_path):
        _write(tmp_path, FLAT)
        hass = MockHass(config_dir=str(tmp_path))
        with patch("custom_components.config_auditor.refactoring_assistant.er") as mock_er:
            mock_er.async_get.return_value = MagicMock()
            mock_er.async_get.return_value.async_get.return_value = None
            from custom_components.config_auditor.refactoring_assistant import (
                RefactoringAssistant,
            )
            ra = RefactoringAssistant(hass)
            result = await ra.apply_mode_fix("Clima", "queued")

        assert result["success"] is True
        written = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "mode: queued" in written
        _assert_untouched_parts_survive(written)

    @pytest.mark.asyncio
    async def test_refactoring_assistant_description_fix(self, tmp_path):
        _write(tmp_path, FLAT)
        hass = MockHass(config_dir=str(tmp_path))
        with patch("custom_components.config_auditor.refactoring_assistant.er") as mock_er:
            mock_er.async_get.return_value = MagicMock()
            mock_er.async_get.return_value.async_get.return_value = None
            from custom_components.config_auditor.refactoring_assistant import (
                RefactoringAssistant,
            )
            ra = RefactoringAssistant(hass)
            result = await ra.apply_description_fix("automation.a1", "Hello")

        assert result["success"] is True
        _assert_untouched_parts_survive(
            (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        )

    @pytest.mark.asyncio
    async def test_mcp_update_automation(self, tmp_path):
        tools_automation = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_automation")
        hass = _hass(tmp_path, FLAT)

        result = await tools_automation._tool_ha_update_automation(
            hass, {"entity_id": "automation.clima", "mode": "restart"}
        )

        assert result.get("success") is True, result
        written = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "mode: restart" in written
        _assert_untouched_parts_survive(written)

    @pytest.mark.asyncio
    async def test_mcp_remove_automation(self, tmp_path):
        tools_automation = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_automation")
        hass = _hass(tmp_path, FLAT)

        result = await tools_automation._tool_ha_remove_automation(hass, {"entity_id": "a2"})

        assert result.get("success") is True, result
        written = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "alias: General" not in written
        _assert_untouched_parts_survive(written)

    @pytest.mark.asyncio
    async def test_mcp_create_automation_appends_without_flattening(self, tmp_path):
        tools_automation = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_automation")
        hass = _hass(tmp_path, FLAT)

        result = await tools_automation._tool_ha_create_automation(hass, {
            "alias": "Brand new",
            "triggers": [{"platform": "state", "entity_id": "light.x"}],
            "actions": [{"service": "light.turn_on"}],
        })

        assert result.get("success") is True, result
        written = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "alias: Brand new" in written
        _assert_untouched_parts_survive(written)

    @pytest.mark.asyncio
    async def test_mcp_update_script(self, tmp_path):
        tools_script_scene = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_script_scene")
        hass = _hass(tmp_path, {
            "configuration.yaml": "script: !include scripts.yaml\n",
            "scripts.yaml": "# my scripts\nmorning:\n  alias: Morning\n  sequence: []\n",
        })

        result = await tools_script_scene._tool_ha_update_script(
            hass, {"entity_id": "script.morning", "alias": "Wake up"}
        )

        assert result.get("success") is True, result
        written = (tmp_path / "scripts.yaml").read_text(encoding="utf-8")
        assert "alias: Wake up" in written
        assert "# my scripts" in written

    @pytest.mark.asyncio
    async def test_mcp_create_script_into_a_commented_file(self, tmp_path):
        tools_script_scene = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_script_scene")
        hass = _hass(tmp_path, {
            "configuration.yaml": "script: !include scripts.yaml\n",
            "scripts.yaml": "# my scripts\nmorning:\n  alias: Morning\n  sequence: []\n",
        })

        result = await tools_script_scene._tool_ha_create_script(hass, {
            "script_id": "evening",
            "alias": "Evening",
            "sequence": [{"service": "light.turn_off"}],
        })

        assert result.get("success") is True, result
        written = (tmp_path / "scripts.yaml").read_text(encoding="utf-8")
        assert "alias: Evening" in written
        assert "alias: Morning" in written
        assert "# my scripts" in written

    @pytest.mark.asyncio
    async def test_mcp_remove_scene(self, tmp_path):
        tools_script_scene = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_script_scene")
        hass = _hass(tmp_path, {
            "configuration.yaml": "scene: !include scenes.yaml\n",
            "scenes.yaml": (
                "# evening moods\n"
                "- id: soir\n  name: Evening\n  entities: {}\n"
                "- id: nuit\n  name: Night\n  entities: {}\n"
            ),
        })

        result = await tools_script_scene._tool_ha_remove_scene(hass, {"entity_id": "scene.soir"})

        assert result.get("success") is True, result
        written = (tmp_path / "scenes.yaml").read_text(encoding="utf-8")
        assert "name: Evening" not in written
        assert "name: Night" in written
        assert "# evening moods" in written

    @pytest.mark.asyncio
    async def test_optimizer_replaces_one_entry_and_keeps_the_rest(self, tmp_path):
        from custom_components.config_auditor.automation_optimizer import (
            AutomationOptimizer,
        )

        _write(tmp_path, FLAT)
        optimizer = AutomationOptimizer(MockHass(config_dir=str(tmp_path)))
        with _home_assistant_accepts():
            result = await optimizer.apply(
                "automation.a1", "id: a1\nalias: Clima split\ntriggers: []\nactions: []\n"
            )

        assert result["success"] is True, result
        written = (tmp_path / "automations.yaml").read_text(encoding="utf-8")
        assert "alias: Clima split" in written
        assert "alias: General" in written, "the sibling entry must survive"
        assert "# Climate automations — keep this comment!" in written

    @pytest.mark.asyncio
    async def test_optimizer_backup_is_restorable(self, tmp_path):
        """It used to write `<stem>_optim_<ts>.yaml`, which restore could not resolve."""
        from custom_components.config_auditor.automation_optimizer import (
            AutomationOptimizer,
        )

        _write(tmp_path, FLAT)
        optimizer = AutomationOptimizer(MockHass(config_dir=str(tmp_path)))
        with _home_assistant_accepts():
            result = await optimizer.apply(
                "automation.a1", "id: a1\nalias: Clima split\ntriggers: []\nactions: []\n"
            )

        assert yw.backup_stem(Path(result["backup_path"]).name) == "automations"


# ═══════════════════════════════════════════════════════════════════════════
# Home Assistant reads back what HACA meant to write
# ═══════════════════════════════════════════════════════════════════════════
#
# ruamel writes YAML 1.2 and Home Assistant reads YAML 1.1, so a string ruamel
# left bare could come back as something else: a trigger `to: off` read as
# False got the automation disabled on reload. Every assertion below reads the
# file through HA's own loader, not through PyYAML or ruamel.

def _ha_reads(path):
    loader = pytest.importorskip("homeassistant.util.yaml.loader")
    return loader.load_yaml(str(path))


# Strings ruamel used to write bare and HA read back as a bool or a base-60 int.
MISREAD = ["on", "off", "yes", "no", "On", "OFF", "22:00:00", "12:00", "7:30", "1:20.5"]

# Bare values a user wrote by hand. HA reads `flag` as False and `at` as 37800;
# that is theirs to change, not a side effect of editing the entry below.
HAND_WRITTEN = """\
- id: 'a1'
  alias: Hand-written
  variables:
    flag: off
  triggers:
    - trigger: state
      entity_id: light.x
      to: 'on'
      from: "off"
    - trigger: time
      at: 10:30:00
  actions: []
- id: 'a2'
  alias: Sibling
  triggers: []
  actions: []
"""


class TestHomeAssistantReadsBackAString:
    @pytest.mark.parametrize("value", MISREAD)
    def test_a_new_value_comes_back_a_string(self, tmp_path, value):
        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")

        target = yw.read_for_edit(str(path), list)
        target.document[1]["value"] = value
        yw.write_back(target)

        assert _ha_reads(path)[1]["value"] == value

    def test_a_new_key_comes_back_a_string(self, tmp_path):
        path = tmp_path / "scripts.yaml"
        target = yw.open_or_create(str(path), dict)
        target.document["s"] = {"data": {"on": "heat"}}
        yw.write_back(target)

        assert _ha_reads(path)["s"]["data"] == {"on": "heat"}

    @pytest.mark.parametrize(
        "value", ["light.kitchen", "heat", "y", "n", "07:30", "00:05:00"]
    )
    def test_an_ordinary_string_stays_bare(self, tmp_path, value):
        path = tmp_path / "scripts.yaml"
        target = yw.open_or_create(str(path), dict)
        target.document["s"] = {"value": value}
        yw.write_back(target)

        assert f"value: {value}\n" in path.read_text(encoding="utf-8")

    def test_what_the_file_already_holds_keeps_its_bytes_and_its_meaning(self, tmp_path):
        """Quoting the bare `off` would hand a template the truthy string "off"."""
        path = tmp_path / "automations.yaml"
        path.write_text(HAND_WRITTEN, encoding="utf-8")
        before = _ha_reads(path)[0]

        target = yw.read_for_edit(str(path), list)
        target.document[1]["alias"] = "Edited"
        yw.write_back(target)

        written = path.read_text(encoding="utf-8")
        for line in ("flag: off\n", "at: 10:30:00\n", "to: 'on'\n", 'from: "off"\n'):
            assert line in written
        assert _ha_reads(path)[0] == before

    def test_a_preview_shows_what_will_be_written(self, tmp_path):
        """The panel and the optimizer dump an entry to show it before writing."""
        import io

        path = tmp_path / "automations.yaml"
        path.write_text(COMMENTED, encoding="utf-8")
        target = yw.read_for_edit(str(path), list)
        target.document[0]["triggers"] = [{"trigger": "state", "to": "off"}]

        buffer = io.StringIO()
        target.yaml.dump(target.document[0], buffer)
        assert "to: 'off'" in buffer.getvalue()


class TestMcpWritesReadBackAsSent:
    """The three repros of the report, through the real tools."""

    @pytest.mark.asyncio
    async def test_update_automation(self, tmp_path):
        tools_automation = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_automation")
        hass = _hass(tmp_path, FLAT)
        triggers = [
            {"trigger": "state", "entity_id": "binary_sensor.presence",
             "from": "on", "to": "off", "for": {"minutes": 2}},
            {"trigger": "time", "at": "22:00:00"},
        ]
        actions = [{
            "action": "climate.set_hvac_mode",
            "data": {"hvac_mode": "off"},
            "target": {"entity_id": "climate.living"},
        }]

        result = await tools_automation._tool_ha_update_automation(hass, {
            "entity_id": "automation.clima", "triggers": triggers, "actions": actions,
        })

        assert result.get("success") is True, result
        clima = _ha_reads(tmp_path / "automations.yaml")[0]
        assert clima["triggers"] == triggers
        assert clima["actions"] == actions

    @pytest.mark.asyncio
    async def test_create_automation(self, tmp_path):
        tools_automation = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_automation")
        hass = _hass(tmp_path, FLAT)
        conditions = [{"condition": "state", "entity_id": "input_boolean.away", "state": "off"}]

        result = await tools_automation._tool_ha_create_automation(hass, {
            "alias": "Brand new",
            "triggers": [{"trigger": "state", "entity_id": "light.x", "to": "on"}],
            "conditions": conditions,
            "actions": [{"action": "light.turn_off"}],
        })

        assert result.get("success") is True, result
        new = next(
            a for a in _ha_reads(tmp_path / "automations.yaml") if a["alias"] == "Brand new"
        )
        assert new["conditions"] == conditions
        assert new["triggers"][0]["to"] == "on"

    @pytest.mark.asyncio
    async def test_update_script(self, tmp_path):
        tools_script_scene = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_script_scene")
        hass = _hass(tmp_path, {
            "configuration.yaml": "script: !include scripts.yaml\n",
            "scripts.yaml": "morning:\n  alias: Morning\n  sequence: []\n",
        })
        variables = {"heating": "off", "wake_at": "7:30"}

        result = await tools_script_scene._tool_ha_update_script(
            hass, {"entity_id": "script.morning", "variables": variables}
        )

        assert result.get("success") is True, result
        assert _ha_reads(tmp_path / "scripts.yaml")["morning"]["variables"] == variables

    @pytest.mark.asyncio
    async def test_create_scene(self, tmp_path):
        tools_script_scene = pytest.importorskip("custom_components.config_auditor.mcp_server.tools_script_scene")
        hass = _hass(tmp_path, {
            "configuration.yaml": "scene: !include scenes.yaml\n",
            "scenes.yaml": "- id: soir\n  name: Evening\n  entities: {}\n",
        })
        entities = {"light.kitchen": "off", "switch.fan": {"state": "on"}}

        result = await tools_script_scene._tool_ha_create_scene(
            hass, {"name": "Night", "entities": entities}
        )

        assert result.get("success") is True, result
        night = next(s for s in _ha_reads(tmp_path / "scenes.yaml") if s["name"] == "Night")
        assert night["entities"] == entities


# ═══════════════════════════════════════════════════════════════════════════
# A file is written back in its own layout
# ═══════════════════════════════════════════════════════════════════════════
#
# The indent used to be one setting for every file: a file from Home
# Assistant's editor (lists flush with their key) came back in the docs style,
# a root list came back indented by two, and a long value was re-wrapped -- the
# diff of a one-line edit was the whole file.

def _ha_dump(data) -> str:
    """What Home Assistant's own editor writes."""
    return pytest.importorskip("homeassistant.util.yaml").dump(data)


LONG_TEXT = (
    "Turns the hall light on when the door opens after sunset, unless somebody "
    "already switched it on by hand in the last ten minutes"
)


def _ha_editor_files() -> dict:
    automation = {
        "id": "1700000000000",
        "alias": "Entrée",
        "description": LONG_TEXT,
        "triggers": [{"trigger": "state", "entity_id": ["binary_sensor.door"], "to": "on"}],
        "conditions": [{"condition": "template", "value_template": "{{ " + LONG_TEXT + " }}"}],
        "actions": [
            {"choose": [{
                "conditions": [{"condition": "state", "entity_id": "sun.sun", "state": "below_horizon"}],
                "sequence": [{"action": "notify.phone", "data": {"message": "Line one\nLine two\n"}}],
            }]},
        ],
        "mode": "single",
    }
    return {
        "automations.yaml": _ha_dump([automation, {**automation, "id": "1700000000001", "alias": "Hall"}]),
        "scripts.yaml": _ha_dump({"morning": {"alias": "Morning", "sequence": [
            {"action": "light.turn_on", "target": {"entity_id": ["light.a", "light.b"]}},
        ]}}),
        # No nested list to measure: the default layout, so the root list is
        # shifted while written. A space at column 80 tells whether the wrap
        # width was widened by as much.
        "scenes.yaml": _ha_dump([{"id": "1", "name": LONG_TEXT.replace("somebody", "someone"), "entities": {
            "light.a": {"state": "on", "brightness": 120},
        }}]),
    }


DOCS_STYLE = {
    "automations.yaml": """\
# Hand-written, docs style
- id: kitchen
  alias: Kitchen light   # aligned comment
  # comment inside the entry
  triggers:
    - trigger: state
      entity_id: binary_sensor.motion   # the PIR
      to: 'on'
  actions:
    - action: notify.phone
      data:
        message: |
          Two lines
            and an indented one
    - choose:
        - conditions:
            - condition: state
              entity_id: sun.sun
              state: below_horizon
          sequence: []

# Second one
- id: hall
  alias: Hall
  triggers: []
  actions: []
""",
    "scripts.yaml": """\
morning:
  alias: Morning
  sequence:
    - action: light.turn_on
      target:
        entity_id:
          - light.a
          - light.b
""",
    "configuration.yaml": """\
homeassistant:
  name: Home
recorder:
  purge_keep_days: 5
  exclude:
    entities:
      - sensor.a   # noisy
      - sensor.b
""",
}


def _rewrite(path, edit=None) -> str:
    target = yw.read_for_edit(str(path))
    if edit:
        edit(target.document)
    yw.write_back(target)
    return path.read_text(encoding="utf-8")


def _changed_lines(before: str, after: str) -> list[str]:
    import difflib

    return [
        line for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="")
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


class TestAFileKeepsItsLayout:
    @pytest.mark.parametrize("name", ["automations.yaml", "scripts.yaml", "scenes.yaml"])
    def test_a_file_from_the_ha_editor_comes_back_byte_for_byte(self, tmp_path, name):
        text = _ha_editor_files()[name]
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")

        assert _rewrite(path) == text

    @pytest.mark.parametrize("name", list(DOCS_STYLE))
    def test_a_hand_written_file_comes_back_byte_for_byte(self, tmp_path, name):
        path = tmp_path / name
        path.write_text(DOCS_STYLE[name], encoding="utf-8")

        assert _rewrite(path) == DOCS_STYLE[name]

    @pytest.mark.parametrize("files, nested_list", [
        (_ha_editor_files, "  triggers:\n  - trigger: state\n"),
        (lambda: DOCS_STYLE, "  triggers:\n    - trigger: state\n"),
    ])
    def test_an_added_entry_follows_the_file_and_nothing_else_moves(self, tmp_path, files, nested_list):
        text = files()["automations.yaml"]
        path = tmp_path / "automations.yaml"
        path.write_text(text, encoding="utf-8")

        written = _rewrite(path, lambda doc: doc.append(
            {"id": "new", "alias": "New", "triggers": [{"trigger": "state", "entity_id": "light.x"}]}
        ))

        changed = _changed_lines(text, written)
        assert all(line.startswith("+") for line in changed), changed
        assert "- id: new\n  alias: New\n" + nested_list in written

    def test_long_lines_written_by_hand_are_not_wrapped(self, tmp_path):
        text = f"- id: a\n  description: {LONG_TEXT}\n  triggers:\n    - trigger: state\n"
        path = tmp_path / "automations.yaml"
        path.write_text(text, encoding="utf-8")

        assert _rewrite(path, lambda doc: doc[0].update(alias="A")).endswith(
            f"  description: {LONG_TEXT}\n  triggers:\n    - trigger: state\n  alias: A\n"
        )

    def test_a_new_file_starts_its_list_at_column_zero(self, tmp_path):
        path = tmp_path / "automations.yaml"
        target = yw.open_or_create(str(path), list)
        target.document.append({"id": "a", "triggers": [{"trigger": "state"}]})
        yw.write_back(target)

        assert path.read_text(encoding="utf-8") == "- id: a\n  triggers:\n    - trigger: state\n"
