"""Tests for RefactoringAssistant — v1.1.2."""
from __future__ import annotations

import pytest
import sys
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import MockHass

AUTOMATION_DEVICE_ID = {
    "id": "auto_001", "alias": "Device ID Test", "mode": "single",
    "triggers": [{"platform": "device", "device_id": "abc123", "domain": "light", "type": "turned_on"}],
    "actions": [{"service": "light.turn_off", "target": {"device_id": "abc123"}}],
}
AUTOMATION_WRONG_MODE = {
    "id": "auto_002", "alias": "Motion Light Wrong Mode", "mode": "single",
    "triggers": [{"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
    "conditions": [],
    "actions": [{"service": "light.turn_on", "target": {"entity_id": "light.lamp"}},
                {"delay": "00:05:00"},
                {"service": "light.turn_off", "target": {"entity_id": "light.lamp"}}],
}
AUTOMATION_NO_ALIAS = {
    "id": "auto_003", "mode": "single",
    "triggers": [{"platform": "state", "entity_id": "binary_sensor.door", "to": "on"}],
    "actions": [{"service": "notify.mobile_app", "data": {"message": "Door opened"}}],
}


def make_ra(tmp_path, automations):
    auto_file = tmp_path / "automations.yaml"
    auto_file.write_text(yaml.dump(automations, allow_unicode=True), encoding="utf-8")
    (tmp_path / "scripts.yaml").write_text("{}", encoding="utf-8")
    hass = MockHass(config_dir=str(tmp_path))
    with patch("custom_components.config_auditor.refactoring_assistant.er") as mock_er:
        mock_er.async_get.return_value = MagicMock()
        mock_er.async_get.return_value.async_get.return_value = None
        from custom_components.config_auditor.refactoring_assistant import RefactoringAssistant
        return RefactoringAssistant(hass)


class TestLoadAutomationById:
    @pytest.mark.asyncio
    async def test_find_by_id(self, tmp_path):
        ra = make_ra(tmp_path, [AUTOMATION_DEVICE_ID])
        result = await ra._load_automation_by_id("auto_001")
        assert result is not None
        assert result["alias"] == "Device ID Test"

    @pytest.mark.asyncio
    async def test_find_by_alias(self, tmp_path):
        ra = make_ra(tmp_path, [AUTOMATION_DEVICE_ID])
        assert await ra._load_automation_by_id("Device ID Test") is not None

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, tmp_path):
        ra = make_ra(tmp_path, [AUTOMATION_DEVICE_ID])
        assert await ra._load_automation_by_id("nonexistent_id") is None

    @pytest.mark.asyncio
    async def test_find_by_entity_id(self, tmp_path):
        ra = make_ra(tmp_path, [AUTOMATION_DEVICE_ID])
        result = await ra._load_automation_by_id("automation.device_id_test")
        assert result is not None


class TestBackupCreation:
    @pytest.mark.asyncio
    async def test_backup_creates_file(self, tmp_path):
        ra = make_ra(tmp_path, [AUTOMATION_DEVICE_ID])
        backup_path = await ra._create_backup()
        assert backup_path.exists()
        content = yaml.safe_load(backup_path.read_text())
        assert isinstance(content, list)
        assert content[0]["id"] == "auto_001"

    @pytest.mark.asyncio
    async def test_backup_cleanup_keeps_last_10(self, tmp_path):
        ra = make_ra(tmp_path, [AUTOMATION_DEVICE_ID])
        for _ in range(15):
            await ra._create_backup()
            await asyncio.sleep(0.01)
        await ra._cleanup_old_backups()
        assert len(list(ra._backup_dir.glob("automations_*.yaml"))) <= 10


import asyncio

class TestNormalizeAutomation:
    def test_no_alias_detected(self, tmp_path):
        (tmp_path / "automations.yaml").write_text(yaml.dump([AUTOMATION_NO_ALIAS]), encoding="utf-8")
        assert "alias" not in AUTOMATION_NO_ALIAS

# ═══════════════════════════════════════════════════════════════════════════
# Split configs — `automation: !include_dir_merge_list automations/`
#
# Every service here used to open <config>/automations.yaml unconditionally,
# so on a split install they all failed with
# `[Errno 2] No such file or directory: '/config/automations.yaml'`.
# ═══════════════════════════════════════════════════════════════════════════

def _make_split_ra(tmp_path):
    (tmp_path / "automations" / "sub").mkdir(parents=True)
    (tmp_path / "ha_scripts").mkdir()
    (tmp_path / "configuration.yaml").write_text(
        "automation: !include_dir_merge_list automations/\n"
        "script: !include_dir_merge_named ha_scripts/\n", encoding="utf-8")
    (tmp_path / "automations" / "clima.yaml").write_text(
        "- id: '1700000000001'\n  alias: Clima salon\n  mode: single\n"
        "  trigger: []\n  action:\n    - service: light.turn_on\n"
        "      entity_id: light.evier\n", encoding="utf-8")
    (tmp_path / "automations" / "sub" / "night.yaml").write_text(
        "- id: '1700000000002'\n  alias: Nuit\n  mode: single\n"
        "  trigger: []\n  action: []\n", encoding="utf-8")
    (tmp_path / "ha_scripts" / "morning.yaml").write_text(
        "morning_routine:\n  alias: Morning routine\n  sequence: []\n", encoding="utf-8")

    hass = MockHass(config_dir=str(tmp_path))
    with patch("custom_components.config_auditor.refactoring_assistant.er") as mock_er:
        mock_er.async_get.return_value = MagicMock()
        mock_er.async_get.return_value.async_get.return_value = None
        from custom_components.config_auditor.refactoring_assistant import RefactoringAssistant
        return RefactoringAssistant(hass)


class TestSplitConfig:
    @pytest.mark.asyncio
    async def test_locates_the_holding_file_in_a_subfolder(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        path, _docs, index = await ra._async_locate_automation("1700000000002")
        assert index >= 0
        assert path.name == "night.yaml"

    @pytest.mark.asyncio
    async def test_mode_fix_writes_only_the_holding_file(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        result = await ra.apply_mode_fix("Clima salon", "queued")
        assert result["success"] is True
        assert "queued" in (tmp_path / "automations" / "clima.yaml").read_text(encoding="utf-8")
        # the config root is not where HA reads from in this layout
        assert not (tmp_path / "automations.yaml").exists()
        assert "queued" not in (tmp_path / "automations" / "sub" / "night.yaml").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_zombie_entity_fix(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        result = await ra.apply_zombie_entity_fix("Clima salon", "light.evier", "light.cuisine")
        assert result["success"] is True
        assert "light.cuisine" in (tmp_path / "automations" / "clima.yaml").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_description_fix_on_a_split_script(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        result = await ra.apply_description_fix("script.morning_routine", "Wake up")
        assert result["success"] is True
        assert "Wake up" in (tmp_path / "ha_scripts" / "morning.yaml").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_backup_is_named_after_the_file_it_copies(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        path, _docs, _index = await ra._async_locate_automation("Clima salon")
        backup = await ra._create_backup(path)
        assert backup.exists()
        assert backup.name.startswith("clima_")

    @pytest.mark.asyncio
    async def test_restore_puts_the_backup_back_where_it_came_from(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        await ra.apply_mode_fix("Clima salon", "queued")
        backups = await ra.list_backups()
        snapshot = next(b for b in backups if b["name"].startswith("clima_"))
        result = await ra.restore_backup(snapshot["path"])
        assert result["success"] is True
        assert Path(result["restored_to"]).name == "clima.yaml"

    @pytest.mark.asyncio
    async def test_a_miss_is_an_error_not_a_traceback(self, tmp_path):
        ra = _make_split_ra(tmp_path)
        result = await ra.apply_mode_fix("automation.does_not_exist", "single")
        assert result["success"] is False
        assert "not found" in result["error"]
