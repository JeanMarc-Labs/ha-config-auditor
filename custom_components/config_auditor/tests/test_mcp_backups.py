"""The MCP write tools' safety net: a copy of the file, taken before it changes.

Up to 1.8.0 every write tool fired a full Home Assistant backup in the
background before touching anything. On a Core install the backup manager
refused each one ("Addons and folders are not supported by core backup"), the
refusal only reached the log, and the tool had written long before the backup
would have read the file anyway. Each write tool now copies the file it
replaces into .haca_backups first -- the raw config file and blueprint tools
had no copy at all -- and returns the copy's path. ha_backup_create is left as
a deliberate full backup, which reports a refusal instead of "started".

    pytest custom_components/config_auditor/tests/test_mcp_backups.py -v
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor import yaml_writer  # noqa: E402
from custom_components.config_auditor.tests.conftest import (  # noqa: E402
    MockHass,
    mcp_package_files,
    mcp_package_source,
)

common = pytest.importorskip(
    "custom_components.config_auditor.mcp_server.common",
    reason="the MCP tools need aiohttp + homeassistant",
)
tools_automation = pytest.importorskip(
    "custom_components.config_auditor.mcp_server.tools_automation",
    reason="the MCP tools need aiohttp + homeassistant",
)
tools_blueprint = pytest.importorskip(
    "custom_components.config_auditor.mcp_server.tools_blueprint",
    reason="the MCP tools need aiohttp + homeassistant",
)
tools_system = pytest.importorskip(
    "custom_components.config_auditor.mcp_server.tools_system",
    reason="the MCP tools need aiohttp + homeassistant",
)

BLUEPRINT = (
    "blueprint:\n"
    "  name: Motion light\n"
    "  domain: automation\n"
    "  input:\n"
    "    light:\n"
    "      selector:\n"
    "        entity: {}\n"
    "triggers: []\n"
    "actions:\n"
    "  - action: light.turn_on\n"
    "    target:\n"
    "      entity_id: !input light\n"
)
BP_REL = "automation/someone/motion.yaml"


def _hass(tmp_path, files: dict) -> MockHass:
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.path = lambda *parts: os.path.join(str(tmp_path), *parts)
    return hass


def _under(path: str, base: Path) -> Path:
    """*path* relative to *base*, both resolved; fails the test if it is outside."""
    return Path(path).resolve().relative_to(base.resolve())


# ═══════════════════════════════════════════════════════════════════════════
# yaml_writer.snapshot_file
# ═══════════════════════════════════════════════════════════════════════════

class TestSnapshotFile:
    def test_kept_under_the_path_of_the_file(self, tmp_path):
        src = tmp_path / "blueprints" / "automation" / "someone" / "motion.yaml"
        src.parent.mkdir(parents=True)
        src.write_text(BLUEPRINT, encoding="utf-8")

        backup = yaml_writer.snapshot_file(str(tmp_path), str(src))

        rel = _under(backup, tmp_path / ".haca_backups" / "files")
        assert rel.parent == Path("blueprints/automation/someone/motion.yaml")
        assert Path(backup).read_text(encoding="utf-8") == BLUEPRINT

    def test_lands_in_the_panel_restore_list_with_its_path(self, tmp_path):
        (tmp_path / "configuration.yaml").write_text("default_config:\n", encoding="utf-8")

        backup = yaml_writer.snapshot_file(str(tmp_path), str(tmp_path / "configuration.yaml"))

        [listed] = yaml_writer.list_backup_files(str(tmp_path))
        assert (listed.path, listed.source) == (backup, "configuration.yaml")

    def test_a_new_file_has_nothing_to_snapshot(self, tmp_path):
        assert yaml_writer.snapshot_file(str(tmp_path), str(tmp_path / "new.yaml")) is None
        assert not (tmp_path / ".haca_backups").exists()

    def test_a_file_outside_the_config_dir_is_refused(self, tmp_path):
        config = tmp_path / "config"
        config.mkdir()
        outside = tmp_path / "elsewhere.yaml"
        outside.write_text("x: 1\n", encoding="utf-8")

        with pytest.raises(ValueError):
            yaml_writer.snapshot_file(str(config), str(outside))

    def test_same_name_in_two_folders_keeps_two_quotas(self, tmp_path, monkeypatch):
        """Pruning goes by name: flat, the two blueprints would evict each other."""
        monkeypatch.setattr(yaml_writer, "BACKUP_KEEP", 2)
        for folder in ("a", "b"):
            path = tmp_path / "blueprints" / folder / "motion.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(folder, encoding="utf-8")

        for _ in range(3):
            yaml_writer.snapshot_file(str(tmp_path), str(tmp_path / "blueprints/a/motion.yaml"))
        yaml_writer.snapshot_file(str(tmp_path), str(tmp_path / "blueprints/b/motion.yaml"))

        root = tmp_path / ".haca_backups" / "files" / "blueprints"
        assert len(list((root / "a" / "motion.yaml").iterdir())) == 2
        assert len(list((root / "b" / "motion.yaml").iterdir())) == 1


# ═══════════════════════════════════════════════════════════════════════════
# The write tools
# ═══════════════════════════════════════════════════════════════════════════

class TestWriteToolsCopyFirst:
    @pytest.mark.asyncio
    async def test_config_file_is_copied_before_it_is_replaced(self, tmp_path):
        """A broken configuration.yaml keeps HA from starting: the copy is the way back."""
        hass = _hass(tmp_path, {"configuration.yaml": "default_config:\n"})

        res = await tools_system._tool_ha_update_config_file(hass, {
            "filename": "configuration.yaml", "content": "broken: [\n"})

        assert res.get("success") is True, res
        assert (tmp_path / "configuration.yaml").read_text(encoding="utf-8") == "broken: [\n"
        _under(res["backup"], tmp_path / ".haca_backups" / "files")
        assert Path(res["backup"]).read_text(encoding="utf-8") == "default_config:\n"

    @pytest.mark.asyncio
    async def test_a_patch_that_does_not_apply_takes_no_copy(self, tmp_path):
        hass = _hass(tmp_path, {"configuration.yaml": "default_config:\n"})

        res = await tools_system._tool_ha_update_config_file(hass, {
            "filename": "configuration.yaml", "content": "x", "mode": "patch_line",
            "old_text": "not in the file"})

        assert "error" in res
        assert not (tmp_path / ".haca_backups").exists()

    @pytest.mark.asyncio
    async def test_a_new_package_file_reports_no_copy(self, tmp_path):
        hass = _hass(tmp_path, {"configuration.yaml": "default_config:\n"})
        (tmp_path / "packages").mkdir()

        res = await tools_system._tool_ha_update_config_file(hass, {
            "filename": "packages/lights.yaml", "content": "light: []", "mode": "append"})

        assert res.get("success") is True, res
        assert res["backup"] is None

    @pytest.mark.asyncio
    async def test_blueprint_update_keeps_the_old_text(self, tmp_path):
        hass = _hass(tmp_path, {"blueprints/" + BP_REL: BLUEPRINT})
        new_text = BLUEPRINT.replace("Motion light", "Motion light v2")

        res = await tools_blueprint._tool_ha_update_blueprint(hass, {"path": BP_REL, "yaml": new_text})

        assert res.get("success") is True, res
        assert Path(res["backup"]).read_text(encoding="utf-8") == BLUEPRINT
        assert yaml_writer.backup_source(str(tmp_path), res["backup"]) == \
            str(tmp_path / "blueprints" / BP_REL)

    @pytest.mark.asyncio
    async def test_a_removed_blueprint_can_be_restored(self, tmp_path):
        hass = _hass(tmp_path, {"blueprints/" + BP_REL: BLUEPRINT})

        res = await tools_blueprint._tool_ha_remove_blueprint(hass, {"path": BP_REL})

        assert res.get("success") is True, res
        target = tmp_path / "blueprints" / BP_REL
        assert not target.exists()
        destination = yaml_writer.backup_source(str(tmp_path), res["backup"])
        assert yaml_writer.restore_snapshot(str(tmp_path), res["backup"], destination) is None
        assert target.read_text(encoding="utf-8") == BLUEPRINT

    @pytest.mark.asyncio
    async def test_no_copy_no_write(self, tmp_path, monkeypatch):
        hass = _hass(tmp_path, {"blueprints/" + BP_REL: BLUEPRINT})

        def _disk_full(config_dir, source):
            raise OSError("No space left on device")

        monkeypatch.setattr(common, "snapshot_file", _disk_full)
        res = await tools_blueprint._tool_ha_update_blueprint(hass, {
            "path": BP_REL, "yaml": BLUEPRINT.replace("Motion light", "changed")})

        assert "error" in res and "No space left" in res["error"]
        assert (tmp_path / "blueprints" / BP_REL).read_text(encoding="utf-8") == BLUEPRINT

    @pytest.mark.asyncio
    async def test_automation_update_returns_a_restorable_copy(self, tmp_path):
        original = "- id: f1\n  alias: Flat\n  triggers: []\n  actions: []\n"
        hass = _hass(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": original,
        })

        res = await tools_automation._tool_ha_update_automation(hass, {
            "entity_id": "automation.flat", "description": "changed"})

        assert res.get("success") is True, res
        assert yaml_writer.backup_source(str(tmp_path), res["backup"]) == \
            str(tmp_path / "automations.yaml")
        assert Path(res["backup"]).read_text(encoding="utf-8") == original


# ═══════════════════════════════════════════════════════════════════════════
# ha_backup_create
# ═══════════════════════════════════════════════════════════════════════════

backup_manager = pytest.importorskip("homeassistant.components.backup.manager")
from homeassistant.components.backup import Folder  # noqa: E402
from homeassistant.components.backup.const import DATA_MANAGER  # noqa: E402

_REAL_SIGNATURE = inspect.signature(backup_manager.BackupManager.async_initiate_backup)


class _Manager:
    """HA's BackupManager as far as the tool can tell: its real signature, and
    on Core the real Core backend's check of what a backup may include."""

    def __init__(self, tmp_path, *, core: bool, refuse: str | None = None):
        self.backup_agents = {"backup.local": object()}
        self.calls: list[dict] = []
        self._refuse = refuse
        self._core = None
        if core:
            rw_hass = MagicMock()
            rw_hass.config.path.return_value = str(tmp_path / "tmp_backups")
            rw_hass.async_create_task.side_effect = lambda coro, **_kw: coro.close()
            self._core = backup_manager.CoreBackupReaderWriter(rw_hass)

    async def async_initiate_backup(self, **kwargs):
        # A keyword-only argument left out raises TypeError, as it does on HA.
        _REAL_SIGNATURE.bind(self, **kwargs)
        self.calls.append(kwargs)
        if self._refuse:
            raise backup_manager.BackupManagerError(self._refuse)
        if self._core is not None:
            try:
                await self._core.async_create_backup(
                    agent_ids=kwargs["agent_ids"],
                    backup_name=kwargs["name"],
                    extra_metadata={},
                    include_addons=kwargs["include_addons"],
                    include_all_addons=kwargs["include_all_addons"],
                    include_database=kwargs["include_database"],
                    include_folders=kwargs["include_folders"],
                    include_homeassistant=kwargs["include_homeassistant"],
                    on_progress=lambda _event: None,
                    password=kwargs["password"],
                )
            except backup_manager.BackupReaderWriterError as err:
                raise backup_manager.BackupManagerError(str(err)) from err
        return backup_manager.NewBackup(backup_job_id="job-1")


_Manager.async_initiate_backup.__signature__ = _REAL_SIGNATURE


def _backup_hass(tmp_path, manager: _Manager, *, supervisor: bool) -> MockHass:
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.components = {"hassio"} if supervisor else set()
    hass.data[DATA_MANAGER] = manager
    return hass


class TestBackupCreate:
    @pytest.mark.asyncio
    async def test_core_backup_passes_the_core_backend(self, tmp_path):
        """Up to 1.8.0 this asked for every add-on and folder, and Core refused."""
        manager = _Manager(tmp_path, core=True)
        hass = _backup_hass(tmp_path, manager, supervisor=False)

        res = await tools_system._tool_ha_backup_create(hass, {"name": "before refactor"})

        assert res.get("started") is True, res
        assert res["backup_job_id"] == "job-1"
        sent = manager.calls[0]
        assert sent["include_all_addons"] is False
        assert sent["include_addons"] is None
        assert sent["include_folders"] is None
        hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_supervisor_backup_keeps_addons_and_folders(self, tmp_path):
        manager = _Manager(tmp_path, core=False)
        hass = _backup_hass(tmp_path, manager, supervisor=True)

        res = await tools_system._tool_ha_backup_create(hass, {})

        assert res.get("started") is True, res
        sent = manager.calls[0]
        assert sent["include_all_addons"] is True
        assert sent["include_folders"] == list(Folder)

    @pytest.mark.asyncio
    async def test_a_refusal_reaches_the_caller(self, tmp_path):
        """It used to die in a background task while the tool said "started"."""
        manager = _Manager(tmp_path, core=True, refuse="Backup manager busy: create_backup")
        hass = _backup_hass(tmp_path, manager, supervisor=False)

        res = await tools_system._tool_ha_backup_create(hass, {})

        assert "busy" in res.get("error", ""), res
        assert "started" not in res
        # backup.create would reach the same manager without waiting, and say "started".
        hass.services.async_call.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Source guards
# ═══════════════════════════════════════════════════════════════════════════

class TestNoBackgroundBackup:
    def test_only_the_tool_itself_starts_a_full_backup(self):
        users = sorted(
            p.name for p in mcp_package_files()
            if "_tool_ha_backup_create" in p.read_text(encoding="utf-8")
        )
        assert users == ["catalog.py", "tools_system.py"]
        assert "_auto_backup" not in mcp_package_source()

    def test_no_prompt_asks_for_a_full_backup_before_every_edit(self):
        src = mcp_package_source()
        assert "ALWAYS call ha_backup_create" not in src
        assert "ha_backup_create first" not in src
