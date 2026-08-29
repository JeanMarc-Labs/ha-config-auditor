"""Tests for split-config support in the audit loaders.

A common mid-sized layout splits domains across folders:

    automation: !include_dir_merge_list automations/
    script:     !include_dir_merge_named ha_scripts/

Before this was supported, HACA audited zero scripts and zero scenes on such an
install — silently, which reads as a clean bill of health — and only recognised
the one `!include_dir_merge_list` spelling for automations.

    pytest custom_components/config_auditor/tests/test_split_config.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import (
    MockEntityRegistry,
    MockHass,
    MockRegistryEntry,
)


def _make_analyzer(hass):
    with patch("custom_components.config_auditor.automation_analyzer.TranslationHelper") as TH:
        TH.return_value.async_load_language = AsyncMock()
        TH.return_value.t = lambda k, **kw: k
        from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer
        return AutomationAnalyzer(hass)


def _write(tmp_path, files: dict) -> None:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Automations
# ═══════════════════════════════════════════════════════════════════════════

class TestSplitAutomations:
    @pytest.mark.parametrize("tag", [
        "!include_dir_merge_list",
        "!include_dir_list",
        "!include_dir_merge_named",
        "!include_dir_named",
    ])
    @pytest.mark.asyncio
    async def test_every_directory_form_is_read(self, tmp_path, tag):
        _write(tmp_path, {
            "configuration.yaml": f"automation: {tag} automations/\n",
            "automations/clima.yaml": "- id: a1\n  alias: Clima\n  trigger: []\n  action: []\n",
            "automations/sub/deep.yml": "- id: a2\n  alias: Deep\n  trigger: []\n  action: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_automation_configs()

        ids = sorted(c.get("id") for c in aa._automation_configs.values())
        assert ids == ["a1", "a2"]

    @pytest.mark.asyncio
    async def test_labelled_sections_are_both_read(self, tmp_path):
        """`automation ui:` + `automation manual:` — the layout that keeps the
        UI editor working alongside a split folder."""
        _write(tmp_path, {
            "configuration.yaml": (
                "automation ui: !include automations.yaml\n"
                "automation manual: !include_dir_merge_list automations/\n"
            ),
            "automations.yaml": "- id: ui1\n  alias: UI\n  trigger: []\n  action: []\n",
            "automations/m.yaml": "- id: m1\n  alias: Manual\n  trigger: []\n  action: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_automation_configs()

        ids = sorted(c.get("id") for c in aa._automation_configs.values())
        assert ids == ["m1", "ui1"]

    @pytest.mark.asyncio
    async def test_stale_root_file_is_not_audited(self, tmp_path):
        """automations.yaml left over from before the split is not read by HA,
        so auditing it produced findings on automations that do not exist."""
        _write(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/clima.yaml": "- id: a1\n  alias: Clima\n  trigger: []\n  action: []\n",
            "automations.yaml": "- id: stale\n  alias: Phantom\n  trigger: []\n  action: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_automation_configs()

        ids = [c.get("id") for c in aa._automation_configs.values()]
        assert ids == ["a1"]

    @pytest.mark.asyncio
    async def test_flat_install_is_unchanged(self, tmp_path):
        _write(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": "- id: f1\n  alias: Flat\n  trigger: []\n  action: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_automation_configs()

        assert [c.get("id") for c in aa._automation_configs.values()] == ["f1"]

    @pytest.mark.asyncio
    async def test_one_unreadable_file_does_not_sink_the_scan(self, tmp_path):
        _write(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/ok.yaml": "- id: ok1\n  alias: Ok\n  trigger: []\n  action: []\n",
            "automations/broken.yaml": "- id: bad\n  alias: [unclosed\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_automation_configs()

        assert [c.get("id") for c in aa._automation_configs.values()] == ["ok1"]


# ═══════════════════════════════════════════════════════════════════════════
# Scripts
# ═══════════════════════════════════════════════════════════════════════════

class TestSplitScripts:
    @pytest.mark.asyncio
    async def test_merge_named_folder_is_read(self, tmp_path):
        """The regression that mattered most: ~50 real scripts audited as zero."""
        _write(tmp_path, {
            "configuration.yaml": "script: !include_dir_merge_named ha_scripts/\n",
            "ha_scripts/clima.yaml": "notificar_todo:\n  alias: Notificar\n  sequence: []\n",
            "ha_scripts/general.yaml": "otro:\n  alias: Otro\n  sequence: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_script_configs()

        assert sorted(aa._script_configs) == ["script.notificar_todo", "script.otro"]

    @pytest.mark.asyncio
    async def test_renamed_script_still_maps_to_its_entity_id(self, tmp_path):
        _write(tmp_path, {
            "configuration.yaml": "script: !include_dir_merge_named ha_scripts/\n",
            "ha_scripts/general.yaml": "notificar_todo:\n  alias: Notificar\n  sequence: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        registry = MockEntityRegistry([
            MockRegistryEntry("script.renamed", platform="script", unique_id="notificar_todo")
        ])
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = registry
            await aa._load_script_configs()

        assert list(aa._script_configs) == ["script.renamed"]

    @pytest.mark.asyncio
    async def test_flat_scripts_yaml_is_unchanged(self, tmp_path):
        _write(tmp_path, {
            "configuration.yaml": "script: !include scripts.yaml\n",
            "scripts.yaml": "s1:\n  alias: S\n  sequence: []\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_script_configs()

        assert list(aa._script_configs) == ["script.s1"]

    @pytest.mark.asyncio
    async def test_no_scripts_anywhere_is_empty_not_an_error(self, tmp_path):
        _write(tmp_path, {"configuration.yaml": "default_config:\n"})
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_script_configs()

        assert aa._script_configs == {}


# ═══════════════════════════════════════════════════════════════════════════
# Scenes
# ═══════════════════════════════════════════════════════════════════════════

class TestSplitScenes:
    @pytest.mark.asyncio
    async def test_merge_list_folder_is_read(self, tmp_path):
        _write(tmp_path, {
            "configuration.yaml": "scene: !include_dir_merge_list scenes/\n",
            "scenes/soir.yaml": "- id: soir\n  name: Evening\n  entities: {}\n",
            "scenes/matin.yaml": "- id: matin\n  name: Morning\n  entities: {}\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_scene_configs()

        assert sorted(aa._scene_configs) == ["scene.evening", "scene.morning"]

    @pytest.mark.asyncio
    async def test_flat_scenes_yaml_is_unchanged(self, tmp_path):
        _write(tmp_path, {
            "configuration.yaml": "scene: !include scenes.yaml\n",
            "scenes.yaml": "- id: s1\n  name: Movie\n  entities: {}\n",
        })
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_scene_configs()

        assert list(aa._scene_configs) == ["scene.movie"]

    @pytest.mark.asyncio
    async def test_no_scenes_anywhere_is_empty_not_an_error(self, tmp_path):
        _write(tmp_path, {"configuration.yaml": "default_config:\n"})
        hass = MockHass(config_dir=str(tmp_path))
        aa = _make_analyzer(hass)
        with patch("custom_components.config_auditor.automation_analyzer.er") as er_m:
            er_m.async_get.return_value = MockEntityRegistry()
            await aa._load_scene_configs()

        assert aa._scene_configs == {}
