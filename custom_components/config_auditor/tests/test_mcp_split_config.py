"""Runtime tests for the MCP write tools on split configs, plus the blueprint guards.

These exercise the tools that used to write to <config>/automations.yaml (or
scripts.yaml / scenes.yaml) whatever the layout — appending to a file HA no
longer reads, then reporting {"success": true} — and the blueprint tools, which
crashed on !input and accepted any path.

    pytest custom_components/config_auditor/tests/test_mcp_split_config.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import MockHass

mcp = pytest.importorskip(
    "custom_components.config_auditor.mcp_server",
    reason="mcp_server needs aiohttp + homeassistant",
)


SPLIT_CONFIG = {
    "configuration.yaml": (
        "automation: !include_dir_merge_list automations/\n"
        "script: !include_dir_merge_named ha_scripts/\n"
        "scene: !include_dir_merge_list scenes/\n"
    ),
    "automations/clima.yaml": "- id: a1\n  alias: Clima\n  triggers: []\n  actions: []\n",
    "automations/general.yaml": "- id: a2\n  alias: General\n  triggers: []\n  actions: []\n",
    "automations.yaml": "- id: stale\n  alias: Phantom\n  triggers: []\n  actions: []\n",
    "ha_scripts/general.yaml": "notificar_todo:\n  alias: Notificar\n  sequence: []\n",
    "scenes/soir.yaml": "- id: soir\n  name: Evening\n  entities: {}\n",
}

TRIGGERS = [{"platform": "state", "entity_id": "light.salon"}]
ACTIONS = [{"service": "light.turn_on"}]


def _write(tmp_path, files: dict) -> None:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _hass(tmp_path, files: dict) -> MockHass:
    _write(tmp_path, files)
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    return hass


def _read(tmp_path, rel: str) -> str:
    return (tmp_path / rel).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_backup(monkeypatch):
    """The tools snapshot the config before destructive ops; not under test here."""
    async def _noop(hass, reason):
        return None

    monkeypatch.setattr(mcp, "_auto_backup", _noop)


# ═══════════════════════════════════════════════════════════════════════════
# Automations
# ═══════════════════════════════════════════════════════════════════════════

class TestAutomationTools:
    @pytest.mark.asyncio
    async def test_create_writes_into_the_merged_folder(self, tmp_path):
        """Never the stale config-root file: HA does not read it in this layout."""
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_create_automation(hass, {
            "alias": "Nouvelle", "triggers": TRIGGERS, "actions": ACTIONS})

        assert res.get("success") is True, res
        assert "Nouvelle" in _read(tmp_path, "automations/haca_mcp.yaml")
        assert "Nouvelle" not in _read(tmp_path, "automations.yaml")

    @pytest.mark.asyncio
    async def test_create_detects_a_duplicate_in_any_file(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_create_automation(hass, {
            "alias": "Clima", "triggers": TRIGGERS, "actions": ACTIONS})

        assert "already exists" in res.get("error", "")

    @pytest.mark.asyncio
    async def test_update_writes_the_owning_file(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_update_automation(hass, {
            "entity_id": "automation.clima", "description": "modifiee"})

        assert res.get("success") is True, res
        assert "modifiee" in _read(tmp_path, "automations/clima.yaml")
        assert "modifiee" not in _read(tmp_path, "automations.yaml")

    @pytest.mark.asyncio
    async def test_update_reports_a_miss_instead_of_a_false_success(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_update_automation(hass, {
            "entity_id": "automation.inexistante", "description": "x"})

        assert "error" in res and "not found" in res["error"]
        assert res.get("success") is not True

    @pytest.mark.asyncio
    async def test_remove_deletes_from_the_owning_file(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_remove_automation(hass, {"entity_id": "a2"})

        assert res.get("success") is True, res
        assert "General" not in _read(tmp_path, "automations/general.yaml")
        assert "Phantom" in _read(tmp_path, "automations.yaml")

    @pytest.mark.asyncio
    async def test_flat_install_still_uses_the_flat_file(self, tmp_path):
        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": "- id: f1\n  alias: Flat\n  triggers: []\n  actions: []\n",
        })
        res = await mcp._tool_ha_create_automation(hass, {
            "alias": "Autre", "triggers": TRIGGERS, "actions": ACTIONS})

        assert res.get("success") is True, res
        assert "Autre" in _read(tmp_path, "automations.yaml")
        assert not (tmp_path / "automations" / "haca_mcp.yaml").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Scripts and scenes
# ═══════════════════════════════════════════════════════════════════════════

class TestScriptAndSceneTools:
    @pytest.mark.asyncio
    async def test_get_script_finds_a_split_script(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_get_script(hass, {"entity_id": "script.notificar_todo"})

        assert res.get("slug") == "notificar_todo", res
        assert res.get("source_file", "").endswith("general.yaml")

    @pytest.mark.asyncio
    async def test_update_and_remove_script_touch_the_owning_file(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_update_script(hass, {
            "entity_id": "script.notificar_todo", "description": "maj"})
        assert res.get("success") is True, res
        assert "maj" in _read(tmp_path, "ha_scripts/general.yaml")

        res = await mcp._tool_ha_remove_script(hass, {"entity_id": "script.notificar_todo"})
        assert res.get("success") is True, res
        assert "notificar_todo" not in _read(tmp_path, "ha_scripts/general.yaml")

    @pytest.mark.asyncio
    async def test_scene_read_update_create(self, tmp_path):
        hass = _hass(tmp_path, SPLIT_CONFIG)
        res = await mcp._tool_ha_get_scene(hass, {"entity_id": "scene.soir"})
        assert res.get("name") == "Evening", res

        res = await mcp._tool_ha_update_scene(hass, {
            "entity_id": "scene.soir", "name": "Late Evening"})
        assert res.get("success") is True, res
        assert "Late Evening" in _read(tmp_path, "scenes/soir.yaml")

        res = await mcp._tool_ha_create_scene(hass, {
            "name": "Morning", "entities": {"light.a": "on"}})
        assert res.get("success") is True, res
        assert "Morning" in _read(tmp_path, "scenes/haca_mcp.yaml")


# ═══════════════════════════════════════════════════════════════════════════
# Blueprints
# ═══════════════════════════════════════════════════════════════════════════

BLUEPRINT = (
    "blueprint:\n"
    "  name: Apagar switch\n"
    "  domain: automation\n"
    "  input:\n"
    "    switch_entity:\n"
    "      name: Switch\n"
    "      selector:\n"
    "        entity: {}\n"
    "triggers:\n"
    "  - trigger: state\n"
    "    entity_id: !input switch_entity\n"
    "actions:\n"
    "  - action: switch.turn_off\n"
    "    target:\n"
    "      entity_id: !input switch_entity\n"
)

BP_REL = "automation/rootmin/apagar.yaml"
BP_FILES = {
    "configuration.yaml": "default_config:\n",
    "secrets.yaml": "api_key: TOPSECRET\n",
    "blueprints/" + BP_REL: BLUEPRINT,
}


class TestBlueprintTools:
    @pytest.mark.asyncio
    async def test_get_blueprint_handles_input_tags(self, tmp_path):
        """!input is a standard HA tag; PyYAML safe_load raised on every real
        blueprint, so the tool returned an error for all of them."""
        hass = _hass(tmp_path, BP_FILES)
        res = await mcp._tool_ha_get_blueprint(hass, {"path": BP_REL})

        assert res.get("name") == "Apagar switch", res
        assert list(res.get("inputs", {})) == ["switch_entity"]
        assert "!input switch_entity" in res["yaml"]
        assert "parsed" not in res          # Input objects are not JSON-safe
        json.dumps(res)                     # the MCP response must serialise

    @pytest.mark.asyncio
    async def test_list_blueprints_returns_metadata_not_errors(self, tmp_path):
        hass = _hass(tmp_path, BP_FILES)
        res = await mcp._tool_ha_list_blueprints(hass, {})

        assert res["total"] == 1, res
        assert res["blueprints"][0]["name"] == "Apagar switch"
        assert "error" not in res["blueprints"][0]

    @pytest.mark.asyncio
    async def test_update_writes_verbatim_and_keeps_input_tags(self, tmp_path):
        hass = _hass(tmp_path, BP_FILES)
        new_text = BLUEPRINT.replace("Apagar switch", "Apagar switch v2")
        res = await mcp._tool_ha_update_blueprint(hass, {"path": BP_REL, "yaml": new_text})

        assert res.get("success") is True, res
        on_disk = _read(tmp_path, "blueprints/" + BP_REL)
        assert "!input switch_entity" in on_disk
        assert "v2" in on_disk

    @pytest.mark.asyncio
    async def test_update_refuses_field_only_calls(self, tmp_path):
        """Patching fields meant a yaml.dump() round-trip, which cannot
        represent !input — it silently mangled any real blueprint."""
        hass = _hass(tmp_path, BP_FILES)
        res = await mcp._tool_ha_update_blueprint(hass, {"path": BP_REL, "name": "X"})

        assert "yaml=" in res.get("error", "")
        assert "!input switch_entity" in _read(tmp_path, "blueprints/" + BP_REL)

    @pytest.mark.asyncio
    async def test_update_rejects_yaml_without_a_blueprint_key(self, tmp_path):
        hass = _hass(tmp_path, BP_FILES)
        res = await mcp._tool_ha_update_blueprint(hass, {
            "path": BP_REL, "yaml": "alias: not a blueprint\n"})

        assert "blueprint" in res.get("error", "")
        assert "Apagar switch" in _read(tmp_path, "blueprints/" + BP_REL)

    @pytest.mark.parametrize("bad_path", [
        "../secrets.yaml",
        "../../secrets.yaml",
        "automation/../../secrets.yaml",
    ])
    @pytest.mark.asyncio
    async def test_path_traversal_is_refused(self, tmp_path, bad_path):
        """A joined path starting with /config/blueprints/ is not proof that the
        resolved path stays there — these tools are LLM-driven."""
        hass = _hass(tmp_path, BP_FILES)

        assert "error" in await mcp._tool_ha_get_blueprint(hass, {"path": bad_path})
        assert "error" in await mcp._tool_ha_remove_blueprint(hass, {"path": bad_path})
        assert "error" in await mcp._tool_ha_update_blueprint(
            hass, {"path": bad_path, "yaml": "blueprint:\n  name: x\n"})
        assert (tmp_path / "secrets.yaml").exists()
        assert "TOPSECRET" in _read(tmp_path, "secrets.yaml")

    @pytest.mark.asyncio
    async def test_absolute_path_outside_blueprints_is_refused(self, tmp_path):
        hass = _hass(tmp_path, BP_FILES)
        outside = str(tmp_path / "secrets.yaml")

        assert "error" in await mcp._tool_ha_get_blueprint(hass, {"path": outside})
        assert "error" in await mcp._tool_ha_remove_blueprint(hass, {"path": outside})
        assert (tmp_path / "secrets.yaml").exists()
