"""H.A.C.A — Refactoring Assistant — Module 5."""
from __future__ import annotations

from datetime import datetime
import difflib
import io
import logging
import re
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import device_conversion
from .const import BACKUP_DIR
from .yaml_sources import iter_domain_files
from .yaml_writer import (
    EditScan,
    RejectedByHomeAssistant,
    async_write_and_reload,
    async_write_checked,
    create_backup,
    list_entries,
    open_domain_for_edit,
    parse_backup_name,
    prune_backups,
    roundtrip_yaml,
    scan_in_passes,
    scan_named_domain_for_edit,
)

_LOGGER = logging.getLogger(__name__)


def _backup_stem(path: Path) -> str | None:
    """The source file's stem behind a `<stem>_<YYYYmmdd_HHMMSS>.yaml` backup.

    Backups are named after the file they copy, so a split config's backups no
    longer all claim to be `automations_*`.
    """
    parsed = parse_backup_name(path.name)
    return parsed[0] if parsed else None


def _as_yaml(node: Any) -> str:
    """An entry, or part of one, in YAML -- dumped by ruamel, as HACA writes it.

    The entries come off the round-trip reader as ruamel nodes, which PyYAML's
    `yaml.dump` cannot represent: the preview's before/after panes, and the
    prompt of the AI description, showed
    `!!python/object/apply:ruamel.yaml.comments.CommentedMap` instead.
    """
    buffer = io.StringIO()
    roundtrip_yaml().dump(node, buffer)
    return buffer.getvalue()


def _match_automation(
    domain, automation_id: str, unique_id: str | None
) -> EditScan:
    """Locate an automation across every file the `automation:` key resolves to.

    Priority, most precise first: the YAML `id`, the registry `unique_id` (which
    HA sets to that same `id`, so an `entity_id` resolves exactly), then the
    alias in its several spellings, then the positional fallback the
    `automation.unknown_<n>` form relies on. The match comes back still attached
    to its round-trip document, so the caller edits it and writes back the one
    file that holds it, comments and all.
    """
    def _slug(value: str) -> str:
        return value.lower().replace(" ", "_").replace("-", "_").replace(".", "_")

    passes = []

    # 1. exact YAML id, then the registry's unique_id for an entity_id
    for wanted in (automation_id, unique_id):
        if wanted:
            passes.append(lambda k, a, w=wanted: str(a.get("id", "")) == w)

    # 2. alias, exact then slugified
    passes += [
        lambda k, a: a.get("alias") == automation_id,
        lambda k, a: bool(a.get("alias")) and _slug(str(a["alias"])) == automation_id,
    ]

    # 3. `automation.<something>` — alias slug or plain alias behind the prefix
    if automation_id.startswith("automation."):
        name = automation_id[len("automation."):]
        passes += [
            lambda k, a: bool(a.get("alias")) and _slug(str(a["alias"])) == name,
            lambda k, a: bool(a.get("alias")) and str(a["alias"]).lower() == name.lower(),
            lambda k, a: str(a.get("id", "")) == name,
        ]

    # 4. `automation.unknown_<id|alias|position>` — the entity had no name
    rest = ""
    if automation_id.startswith("automation.unknown_"):
        rest = automation_id[len("automation.unknown_"):]
        passes += [
            lambda k, a: str(a.get("id", "")) == rest,
            lambda k, a: bool(a.get("alias")) and _slug(str(a["alias"])) == rest,
        ]

    scan = scan_in_passes(domain, list_entries, passes)
    if scan.found or not rest:
        return scan

    try:  # positional, counted across the files in merge order
        wanted_pos = int(rest)
    except ValueError:
        return scan
    position = 0
    for target in domain.targets:
        for index in range(len(target.document)):
            if position == wanted_pos:
                return EditScan(
                    target, target.document[index], index, None,
                    domain.files, domain.skipped,
                )
            position += 1
    return scan


class RefactoringAssistant:
    """Assistant for automated refactoring with preview and backup."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize refactoring assistant."""
        self.hass = hass
        self._config_dir = str(hass.config.config_dir)
        self._backup_dir = Path(hass.config.config_dir) / BACKUP_DIR
        # Created lazily, in the executor, the first time a backup is written:
        # this constructor runs on the event loop during setup, where a mkdir()
        # is a blocking call Home Assistant logs a warning for.
        # No `_automations_file` / `_scripts_file`: which file holds an entry is
        # a per-target question, not an install-wide constant. With a split
        # config (`automation: !include_dir_merge_list automations/`) the flat
        # paths do not exist, and every service here failed on
        # `[Errno 2] .../automations.yaml`. Each read-modify-write now locates
        # the holding file first and writes back only there.

    # ── Locating the file that holds an entry ─────────────────────────────
    #   Everything below writes back to the one file a target actually lives
    #   in, resolved through the shared yaml_sources helpers, so a split
    #   config behaves exactly like a flat one.

    async def _async_locate_automation(self, automation_id: str) -> EditScan:
        """The automation, in the file that holds it, open for editing.

        ``automation_id`` may be the YAML ``id``, an alias, or an ``entity_id``.
        The entity registry is consulted first for the ``entity_id`` form: HA
        stores a YAML automation's ``id`` as its ``unique_id``, which is exact,
        where re-slugifying the alias is a guess that two aliases can share.
        """
        unique_id: str | None = None
        if automation_id.startswith("automation."):
            try:
                entry = er.async_get(self.hass).async_get(automation_id)
                unique_id = entry.unique_id if entry and entry.unique_id else None
            except Exception:  # noqa: BLE001 — registry unavailable: fall through
                unique_id = None

        domain = await self.hass.async_add_executor_job(
            open_domain_for_edit, self._config_dir, "automation", "automations.yaml", list
        )
        if domain.skipped:
            # A file carrying !secret or !include is passed over rather than
            # rewritten with the tag lost.
            _LOGGER.debug(
                "Automation lookup skipped %d file(s) that must not be rewritten: %s",
                len(domain.skipped), ", ".join(domain.skipped),
            )
        return _match_automation(domain, automation_id, unique_id)

    async def _async_locate_script(self, entity_id: str) -> EditScan:
        """The script, in the file that holds it, open for editing."""
        script_key = entity_id.replace("script.", "").strip()

        def _matches(key: str, cfg: dict) -> bool:
            if key == script_key:
                return True
            alias = cfg.get("alias") or ""
            return bool(alias) and (
                str(alias).lower() == script_key.lower()
                or str(alias).lower().replace(" ", "_") == script_key
            )

        scan = await self.hass.async_add_executor_job(
            scan_named_domain_for_edit,
            self._config_dir, "script", "scripts.yaml", _matches,
        )
        if not scan.found and scan.skipped:
            _LOGGER.debug(
                "Script lookup skipped %d file(s) that must not be rewritten: %s",
                len(scan.skipped), ", ".join(scan.skipped),
            )
        return scan

    async def preview_device_id_fix(self, automation_id: str, location: str | None = None) -> dict[str, Any]:
        """Preview device_id to entity_id conversion without applying.

        When *location* is provided (e.g. ``"action[0]"`` or ``"trigger[2]"``),
        only the matching section/index is inspected so the preview stays
        scoped to the single reported issue instead of fixing the whole automation.

        Only what :mod:`device_conversion` can rewrite the way Home Assistant
        runs it is changed. The rest -- an integration's own trigger, an unknown
        type, an entity gone from the registry -- is listed in ``skipped`` with
        the reason, rather than guessed.
        """
        import re as _re

        # Parse optional location filter → (section, index)
        _loc_section: str | None = None
        _loc_index: int | None = None
        if location:
            m = _re.match(r'^(trigger|condition|action)\[(\d+)\]', location)
            if m:
                _loc_section = m.group(1)
                _loc_index = int(m.group(2))
        
        # Load automation config
        automation_config = await self._load_automation_by_id(automation_id)
        
        if not automation_config:
            return {
                "success": False,
                "error": f"Automation {automation_id} not found"
            }
        
        # `action:` names the service since HA 2024.8; `service:` loads everywhere.
        actions = automation_config.get("actions", automation_config.get("action")) or []
        uses_action = "actions" in automation_config or any(
            isinstance(a, dict) and "action" in a for a in (actions if isinstance(actions, list) else [actions])
        )
        service_key = "action" if uses_action else "service"

        # Each device block is rewritten the way HA runs it (device_conversion);
        # one that cannot be rewritten faithfully stays, with the reason.
        changes: list[dict] = []
        skipped: list[dict] = []
        keys: dict[str, str] = {}
        for section in ("trigger", "condition", "action"):
            key = keys[section] = f"{section}s" if f"{section}s" in automation_config else section
            if _loc_section and _loc_section != section:
                continue
            items = automation_config.get(key, [])
            if not isinstance(items, list):
                items = [items] if items else []
            for idx, item in enumerate(items):
                if _loc_index is not None and idx != _loc_index:
                    continue
                conversion = device_conversion.convert(
                    self.hass, section, item, service_key=service_key
                )
                if conversion is None:
                    continue
                note = f"{section.capitalize()} {idx}: {conversion.note}"
                if conversion.new is None:
                    skipped.append({"section": section, "index": idx, "reason": note})
                else:
                    changes.append({
                        "section": section, "index": idx,
                        "to": conversion.new, "description": note,
                    })

        # --- Generate YAML previews ---
        import copy
        current_yaml = _as_yaml(automation_config)

        new_config = copy.deepcopy(automation_config)

        # Apply all changes to the deep copy
        for change in changes:
            key = keys[change["section"]]
            items = new_config.get(key, [])
            if not isinstance(items, list):
                items = [items] if items else []
            if change["index"] < len(items):
                items[change["index"]] = change["to"]
            new_config[key] = items

        new_yaml = _as_yaml(new_config)

        return {
            "success": True,
            "automation_id": automation_id,
            "alias": automation_config.get("alias", ""),
            "changes": changes,
            "changes_count": len(changes),
            "skipped": skipped,
            "current_yaml": current_yaml,
            "new_yaml": new_yaml
        }

    async def apply_device_id_fix(self, automation_id: str, preview: dict = None, dry_run: bool = False, location: str | None = None) -> dict[str, Any]:
        """Apply device_id to entity_id conversion with backup.

        When *location* is provided (e.g. ``"action[0]"``), only the matching
        section/index is fixed — consistent with the location-scoped preview
        shown to the user when they click "Corriger" on a single issue card.
        Without it, every device_id reference in the automation is rewritten.
        """

        # Get preview if not provided — scoped to the same location the caller
        # asked for, otherwise the apply would fix more actions than the user
        # was shown in the preview modal.
        if not preview:
            preview = await self.preview_device_id_fix(automation_id, location=location)
        
        if not preview.get("success"):
            return preview
        
        if not preview.get("changes"):
            return {
                "success": False,
                "error": "No changes to apply"
            }
            
        if dry_run:
            return {
                "success": True,
                "automation_id": automation_id,
                "changes_applied": 0,
                "dry_run": True,
                "preview": preview,
                "message": "Dry run complete. No changes applied."
            }
        
        scan = await self._async_locate_automation(automation_id)
        if not scan.found:
            return {"success": False, "error": f"Automation not found: {automation_id}"}

        try:
            automation = scan.entry

            # Apply changes per section
            for change in preview["changes"]:
                section = change["section"]
                idx = change["index"]

                # Detect correct key for each section
                if section == "trigger":
                    key = "triggers" if "triggers" in automation else "trigger"
                elif section == "condition":
                    key = "conditions" if "conditions" in automation else "condition"
                elif section == "action":
                    key = "actions" if "actions" in automation else "action"
                else:
                    continue

                items = automation.get(key, [])
                if not isinstance(items, list):
                    items = [items] if items else []
                if idx < len(items):
                    items[idx] = change["to"]
                automation[key] = items

            # No reload here, so HA would only disable a broken conversion at
            # the user's next one — a device condition with no state mapping
            # becomes a state condition without `state:`.
            backup_path = await async_write_checked(
                self.hass, scan.target, "automation", entry=automation, key=automation.get("id")
            )

            return {
                "success": True,
                "automation_id": automation_id,
                "changes_applied": len(preview["changes"]),
                "backup_path": str(backup_path),
                "message": "Changes applied successfully. Restart Home Assistant to apply."
            }

        except RejectedByHomeAssistant as e:
            _LOGGER.info("device_id fix on %s not applied: %s", automation_id, e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            _LOGGER.error("Error applying fixes: %s", e)
            return {"success": False, "error": str(e)}

    async def preview_mode_fix(self, automation_id: str, new_mode: str) -> dict[str, Any]:
        """Preview automation mode change."""
        
        valid_modes = ["single", "restart", "queued", "parallel"]
        if new_mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid mode. Must be one of: {valid_modes}"
            }
        
        automation_config = await self._load_automation_by_id(automation_id)
        
        if not automation_config:
            return {
                "success": False,
                "error": f"Automation {automation_id} not found"
            }
        
        current_mode = automation_config.get("mode", "single")
        
        changes = [{
            "field": "mode",
            "from": current_mode,
            "to": new_mode,
            "description": f"Change mode from '{current_mode}' to '{new_mode}'"
        }]
        
        # Add max parameter for queued/parallel
        if new_mode in ["queued", "parallel"]:
            if "max" not in automation_config:
                changes.append({
                    "field": "max",
                    "from": None,
                    "to": 10,
                    "description": "Add max parameter (default: 10)"
                })
        
        # Generate YAML previews
        import copy
        current_yaml = _as_yaml(automation_config)
        
        # Create a deep copy to apply changes for preview
        new_config = copy.deepcopy(automation_config)
        new_config["mode"] = new_mode
        
        if new_mode in ["queued", "parallel"]:
            if "max" not in new_config:
                new_config["max"] = 10
                
        new_yaml = _as_yaml(new_config)
        
        return {
            "success": True,
            "automation_id": automation_id,
            "alias": automation_config.get("alias", ""),
            "changes": changes,
            "changes_count": len(changes),
            "current_yaml": current_yaml,
            "new_yaml": new_yaml
        }

    async def apply_mode_fix(self, automation_id: str, new_mode: str, dry_run: bool = False) -> dict[str, Any]:
        """Apply automation mode change with backup."""
        
        preview = await self.preview_mode_fix(automation_id, new_mode)
        
        if not preview.get("success"):
            return preview

        if dry_run:
            return {
                "success": True,
                "automation_id": automation_id,
                "new_mode": new_mode,
                "dry_run": True,
                "preview": preview,
                "message": "Dry run complete. No changes applied."
            }
        
        scan = await self._async_locate_automation(automation_id)
        if not scan.found:
            return {"success": False, "error": f"Automation not found: {automation_id}"}

        try:
            automation = scan.entry
            automation["mode"] = new_mode
            if new_mode in ["queued", "parallel"] and "max" not in automation:
                automation["max"] = 10

            backup_path = await async_write_checked(
                self.hass, scan.target, "automation", entry=automation, key=automation.get("id")
            )

            return {
                "success": True,
                "automation_id": automation_id,
                "new_mode": new_mode,
                "backup_path": str(backup_path),
                "message": "Mode changed successfully. Restart Home Assistant to apply."
            }

        except RejectedByHomeAssistant as e:
            _LOGGER.info("Mode fix on %s not applied: %s", automation_id, e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            _LOGGER.error("Error changing mode: %s", e)
            return {"success": False, "error": str(e)}

    async def preview_template_fix(self, automation_id: str) -> dict[str, Any]:
        """Preview template to native condition conversion."""
        automation_config = await self._load_automation_by_id(automation_id)
        
        if not automation_config:
            return {"success": False, "error": f"Automation {automation_id} not found"}
            
        changes = []
        
        # Check conditions
        condition_key = "conditions" if "conditions" in automation_config else "condition"
        conditions = automation_config.get(condition_key, [])
        if not isinstance(conditions, list):
            conditions = [conditions] if conditions else []
            
        for idx, condition in enumerate(conditions):
            if not isinstance(condition, dict) or condition.get("condition") != "template":
                continue
                
            template = condition.get("value_template", "")
            parsed = self._parse_is_state_template(template)
            
            if parsed:
                new_condition = {
                    "condition": "state",
                    "entity_id": parsed["entity_id"],
                    "state": parsed["state"]
                }
                
                changes.append({
                    "section": "condition",
                    "index": idx,
                    "to": new_condition,
                    "description": f"Condition {idx}: Template → state condition ({parsed['entity_id']} is {parsed['state']})"
                })

        if not changes:
            return {"success": False, "error": "No simple template conditions found to fix"}

        # Generate YAML previews
        import copy
        current_yaml = _as_yaml(automation_config)
        new_config = copy.deepcopy(automation_config)
        
        for change in changes:
            idx = change["index"]
            items = new_config.get(condition_key, [])
            if idx < len(items):
                items[idx] = change["to"]
                
        new_yaml = _as_yaml(new_config)
        
        return {
            "success": True,
            "automation_id": automation_id,
            "alias": automation_config.get("alias", ""),
            "changes": changes,
            "changes_count": len(changes),
            "current_yaml": current_yaml,
            "new_yaml": new_yaml
        }

    async def apply_template_fix(self, automation_id: str, dry_run: bool = False) -> dict[str, Any]:
        """Apply template fix with backup."""
        preview = await self.preview_template_fix(automation_id)
        if not preview.get("success"):
            return preview

        if dry_run:
            return {
                "success": True,
                "automation_id": automation_id,
                "dry_run": True,
                "preview": preview,
                "message": "Dry run complete."
            }
            
        scan = await self._async_locate_automation(automation_id)
        if not scan.found:
            return {"success": False, "error": f"Automation not found: {automation_id}"}

        try:
            automation = scan.entry
            cond_key = "conditions" if "conditions" in automation else "condition"
            items = automation.get(cond_key, [])
            if not isinstance(items, list):
                items = [items] if items else []

            for change in preview["changes"]:
                idx = change["index"]
                if idx < len(items):
                    items[idx] = change["to"]
            automation[cond_key] = items

            backup_path = await async_write_checked(
                self.hass, scan.target, "automation", entry=automation, key=automation.get("id")
            )

            return {
                "success": True,
                "automation_id": automation_id,
                "changes_applied": len(preview["changes"]),
                "backup_path": str(backup_path),
                "message": "Template fix applied successfully."
            }
        except RejectedByHomeAssistant as e:
            _LOGGER.info("Template fix on %s not applied: %s", automation_id, e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            _LOGGER.error("Error applying template fix: %s", e)
            return {"success": False, "error": str(e)}

    def _parse_is_state_template(self, template: str) -> dict[str, str] | None:
        """Parse is_state('entity', 'state') from template string."""
        # Regex to match is_state('...', '...') or is_state("...", "...")
        # Supports optional spaces and different quote types
        pattern = r"is_state\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
        match = re.search(pattern, template)
        
        if match:
            return {
                "entity_id": match.group(1),
                "state": match.group(2)
            }
        return None

    async def list_backups(self) -> list[dict]:
        """List available backups."""

        def _scan_backups():
            results = []
            # The directory probe belongs in here with the walk: on the event
            # loop it is one more blocking stat() for Home Assistant to warn
            # about.
            if not self._backup_dir.is_dir():
                _LOGGER.debug("Backup directory does not exist: %s", self._backup_dir)
                return results
            try:
                _LOGGER.debug("Scanning backups in: %s", self._backup_dir)
                for entry in self._backup_dir.iterdir():
                    # Any `<source stem>_<timestamp>.yaml`, not just
                    # `automations_*`: a split config backs up the file that
                    # holds the entry, which is rarely named automations.yaml.
                    if entry.is_file() and _backup_stem(entry):
                        try:
                            stat = entry.stat()
                            # Parser la date depuis le nom de fichier (automations_YYYYMMDD_HHMMSS.yaml)
                            # Plus fiable que st_mtime qui reflète l'heure de copie/restauration
                            created_iso = datetime.fromtimestamp(stat.st_mtime).isoformat()
                            try:
                                ts_str = parse_backup_name(entry.name)[1]
                                parsed = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                                created_iso = parsed.isoformat()
                            except Exception:
                                pass  # garder st_mtime si parsing impossible
                            results.append({
                                "path": str(entry.absolute()),
                                "name": entry.name,
                                "size": stat.st_size,
                                "created": created_iso,
                                "source": _backup_stem(entry) + ".yaml",
                            })
                        except Exception as err:
                            _LOGGER.warning("Error reading backup file %s: %s", entry.name, err)
                            
                # Sort by reverse chronological order (newest first) based on created timestamp
                results.sort(key=lambda x: (x["created"], x["name"]), reverse=True)
                return results[:10]
                
            except Exception as err:
                _LOGGER.error("Error scanning backup directory: %s", err)
                return []

        try:
            return await self.hass.async_add_executor_job(_scan_backups)
        except Exception as e:
            _LOGGER.error("Error listing backups: %s", e)
            return []

    def _check_backup_path_sync(self, backup_file: Path) -> str:
        """Validate one backup path. Returns "ok", "outside" or "missing".

        Both halves touch the filesystem — ``resolve()`` follows symlinks and
        ``is_file()`` stats — so they run together in the executor rather than
        four blocking calls deep in an async handler.
        """
        try:
            backup_file.resolve().relative_to(self._backup_dir.resolve())
        except ValueError:
            return "outside"
        except OSError:
            return "outside"
        return "ok" if backup_file.is_file() else "missing"

    async def restore_backup(self, backup_path: str) -> dict[str, Any]:
        """Restore automations from backup.

        Security: backup_path is validated to be inside the designated backup
        directory before any file operation, preventing path-traversal attacks.
        """
        backup_file = Path(backup_path)

        # ── Path-traversal guard ──────────────────────────────────────────────
        # Resolve both paths to their canonical (symlink-free) absolute forms,
        # then assert the backup file is inside _backup_dir.
        verdict = await self.hass.async_add_executor_job(
            self._check_backup_path_sync, backup_file
        )
        if verdict == "outside":
            _LOGGER.warning(
                "restore_backup: rejected path outside backup dir: %s", backup_path
            )
            return {
                "success": False,
                "error": "Invalid backup path — file must be inside the HACA backup directory.",
            }
        if verdict == "missing":
            return {
                "success": False,
                "error": "Backup file not found"
            }
        
        # ── Which file does this backup belong to? ────────────────────────
        # The backup is named after its source (`<stem>_<timestamp>.yaml`), so
        # the destination is the automation file with that stem. Restoring
        # blindly to `<config>/automations.yaml` — what this did before — wrote
        # a file HA does not read on a split config, silently restoring nothing.
        destination = await self.hass.async_add_executor_job(
            self._resolve_restore_target, backup_file
        )
        if destination is None:
            stem = _backup_stem(backup_file) or "?"
            return {
                "success": False,
                "error": (
                    f"Cannot tell which file '{backup_file.name}' belongs to: no "
                    f"automation file named '{stem}.yaml' is loaded by 'automation:' "
                    f"any more. Restore it by hand."
                ),
            }

        try:
            # Create backup of current state before restore
            pre_restore_backup = await self._create_backup(destination)

            def restore():
                import shutil
                shutil.copy2(backup_file, destination)

            await self.hass.async_add_executor_job(restore)

            return {
                "success": True,
                "restored_from": str(backup_file),
                "restored_to": str(destination),
                "backup_before_restore": str(pre_restore_backup),
                "message": "Backup restored. Restart Home Assistant to apply."
            }
            
        except Exception as e:
            _LOGGER.error("Error restoring backup: %s", e)
            return {
                "success": False,
                "error": str(e)
            }

    def _resolve_restore_target(self, backup_file: Path) -> Path | None:
        """The automation file a backup came from, or None when it is gone.

        Matches on the stem the backup name carries. Refuses an ambiguous match
        — two files of that name in different sub-folders of a merged directory
        — rather than picking one and overwriting the wrong config.
        """
        stem = _backup_stem(backup_file)
        if not stem:
            return None
        candidates = [
            Path(p)
            for p in iter_domain_files(self._config_dir, "automation", "automations.yaml")
            if Path(p).stem == stem
        ]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            # A flat install whose automations.yaml does not exist yet still has
            # a well-defined destination.
            flat = Path(self._config_dir) / f"{stem}.yaml"
            return flat if stem == "automations" else None
        _LOGGER.warning(
            "restore_backup: '%s' matches %d files, refusing to guess: %s",
            backup_file.name, len(candidates), [str(c) for c in candidates],
        )
        return None

    async def create_backup(self) -> dict[str, Any]:
        """Create a manual backup."""
        try:
            backup_path = await self._create_backup()
            return {
                "success": True,
                "backup_path": str(backup_path),
                "message": f"Backup created: {backup_path.name}"
            }
        except Exception as e:
            _LOGGER.error("Error creating backup: %s", e)
            return {
                "success": False,
                "error": str(e)
            }

    async def delete_backup(self, backup_path: str) -> dict[str, Any]:
        """Delete a specific backup file."""
        backup_file = Path(backup_path)

        # Security check: ensure file is in backup directory
        verdict = await self.hass.async_add_executor_job(
            self._check_backup_path_sync, backup_file
        )
        if verdict == "outside":
            return {
                "success": False,
                "error": "Invalid backup path - file must be in backup directory"
            }
        if verdict == "missing":
            return {
                "success": False,
                "error": "Backup file not found"
            }
        
        try:
            def delete_file():
                backup_file.unlink()
            
            await self.hass.async_add_executor_job(delete_file)
            
            _LOGGER.info("Deleted backup: %s", backup_file)
            return {
                "success": True,
                "deleted_file": backup_file.name,
                "message": f"Backup deleted: {backup_file.name}"
            }
        except Exception as e:
            _LOGGER.error("Error deleting backup: %s", e)
            return {
                "success": False,
                "error": str(e)
            }

    async def _create_backup(self, target: Path | str | None = None) -> Path:
        """Back up the file about to be written, before any write.

        Delegates to :func:`yaml_writer.create_backup`, which every write path
        in HACA shares — the naming and the pruning are the same whether the
        edit came from this module, the panel or an MCP tool, so
        :meth:`restore_backup` can put any of them back. Falls back to the first
        file the `automation:` key resolves to when no target is given (a manual
        backup).
        """
        def _do() -> Path:
            source = Path(target) if target else None
            if source is None:
                files = iter_domain_files(
                    self._config_dir, "automation", "automations.yaml"
                )
                source = Path(files[0]) if files else None
            if source is None or not source.is_file():
                raise FileNotFoundError(
                    "no automation YAML file to back up — `automation:` resolves "
                    "to nothing that exists on disk"
                )
            return Path(create_backup(self._config_dir, str(source)))

        backup_file = await self.hass.async_add_executor_job(_do)
        _LOGGER.info("Created backup: %s", backup_file)
        return backup_file

    async def _cleanup_old_backups(self):
        """Prune every source file's backups down to the shared ceiling."""
        await self.hass.async_add_executor_job(prune_backups, self._config_dir)

    async def _load_automation_by_id(self, automation_id: str) -> dict | None:
        """Load an automation configuration by ID, alias, or entity_id."""
        try:
            scan = await self._async_locate_automation(automation_id)
            return scan.entry if scan.found else None
        except Exception as e:
            _LOGGER.error("Error loading automation: %s", e)
            return None

    async def _load_script_by_entity_id(self, entity_id: str) -> dict | None:
        """Load a script configuration by entity_id (e.g. 'script.my_script')."""
        try:
            scan = await self._async_locate_script(entity_id)
            if not scan.found:
                return None
            config = scan.entry
            config["_script_key"] = scan.key
            return config
        except Exception:
            return None

    async def get_fuzzy_suggestions(self, broken_entity_id: str) -> list[str]:
        """Get similar entity IDs for a broken reference."""
        all_entities = [e.entity_id for e in self.hass.states.async_all()]
        
        # Also check registry for potentially disabled ones
        entity_reg = er.async_get(self.hass)
        all_entities.extend([e.entity_id for e in entity_reg.entities.values() if e.entity_id not in all_entities])
        
        return difflib.get_close_matches(broken_entity_id, all_entities, n=3, cutoff=0.6)

    async def apply_zombie_entity_fix(
        self,
        automation_id: str,
        old_entity_id: str,
        new_entity_id: str = "",
    ) -> dict[str, Any]:
        """Replace or remove a zombie entity reference inside an automation.

        Parameters
        ----------
        automation_id:
            The automation 'id' field or entity_id (e.g. "automation.my_auto").
        old_entity_id:
            The non-existent entity to remove/replace (e.g. "light.evier").
        new_entity_id:
            Replacement entity. Empty string = remove the reference.

        The edited automation is checked the way Home Assistant's editor checks
        it before anything is written: removing the only entity of a state
        trigger leaves a trigger HA disables on reload, and the reload itself
        succeeds. A reload that fails puts the file back.
        """
        try:
            scan = await self._async_locate_automation(automation_id)
            if not scan.found:
                return {"success": False, "error": f"Automation not found: {automation_id}"}
            config = scan.entry

            changed = self._replace_entity_in_config(config, old_entity_id, new_entity_id)
            if not changed:
                return {"success": False, "error": f"{old_entity_id} not found in automation config"}

            # The entry was mutated in place inside the document of the file
            # that holds it — no second lookup, no risk of matching a namesake.
            backup_path = await async_write_and_reload(
                self.hass, scan.target, "automation", entry=config, key=config.get("id")
            )
            _LOGGER.info("Backup created before zombie fix: %s", backup_path)

            action = f"replaced with {new_entity_id}" if new_entity_id else "removed"
            return {
                "success": True,
                "message": f"Reference to {old_entity_id} {action} in {config.get('alias') or automation_id}",
                "backup_path": str(backup_path),
            }

        except RejectedByHomeAssistant as exc:
            # Nothing was written: Home Assistant's own verdict, not a fault here.
            _LOGGER.info("Zombie fix on %s not applied: %s", automation_id, exc)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            _LOGGER.error("apply_zombie_entity_fix error: %s", exc)
            return {"success": False, "error": str(exc)}

    def _replace_entity_in_config(
        self, config: dict, old_entity_id: str, new_entity_id: str
    ) -> bool:
        """Walk the automation config dict/list tree and replace entity references.

        Returns True if at least one substitution was made.
        """
        changed = False

        def walk(obj):
            nonlocal changed
            if isinstance(obj, dict):
                for key in list(obj.keys()):
                    if key in ("entity_id",):
                        val = obj[key]
                        if isinstance(val, list):
                            if old_entity_id in val:
                                changed = True
                                if new_entity_id:
                                    obj[key] = [new_entity_id if e == old_entity_id else e for e in val]
                                else:
                                    obj[key] = [e for e in val if e != old_entity_id]
                                    if not obj[key]:
                                        del obj[key]
                        elif val == old_entity_id:
                            changed = True
                            if new_entity_id:
                                obj[key] = new_entity_id
                            else:
                                del obj[key]
                    else:
                        walk(obj[key])
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(config)
        return changed

    async def purge_orphaned_entities(self, dry_run: bool = True) -> dict[str, Any]:
        """Purge entities from registry that have no backing integration."""
        entity_reg = er.async_get(self.hass)
        orphaned = []
        
        for entry in list(entity_reg.entities.values()):
            if entry.config_entry_id:
                config_entry = self.hass.config_entries.async_get_entry(entry.config_entry_id)
                if config_entry is None or config_entry.state.recoverable is False:
                    orphaned.append(entry.entity_id)
                    if not dry_run:
                        entity_reg.async_remove(entry.entity_id)
                        _LOGGER.info("Removed orphaned entity: %s", entry.entity_id)
                        
        return {
            "success": True,
            "purged_count": len(orphaned),
            "entities": orphaned,
            "dry_run": dry_run
        }

    async def suggest_description_ai(self, entity_id: str) -> dict[str, Any]:
        """Get an AI-suggested description for an automation or script."""
        is_script = entity_id.startswith("script.")
        
        if is_script:
            config = await self._load_script_by_entity_id(entity_id)
        else:
            # For automations, we need to resolve the entity_id to the YAML 'id'
            registry = er.async_get(self.hass)
            entry = registry.async_get(entity_id)
            automation_id = None
            
            if entry and entry.unique_id:
                automation_id = entry.unique_id
            else:
                automation_id = entity_id.replace("automation.", "")

            config = await self._load_automation_by_id(automation_id)
            
            # Second attempt: if not found, try by alias mapping (as slug)
            if not config:
                config = await self._load_automation_by_id(entity_id.replace("automation.", ""))
            
        if not config:
            return {"success": False, "error": f"Configuration not found for {entity_id}"}
            
        alias = config.get("alias", entity_id)
        
        # Prepare content for prompt
        if is_script:
            triggers_yaml = _as_yaml(config.get("sequence", []))
            actions_yaml = ""
        else:
            triggers_yaml = _as_yaml(config.get("trigger", []) or config.get("triggers", []))
            actions_yaml = _as_yaml(config.get("action", []) or config.get("actions", []))

        # Build the full YAML block from triggers + actions parts
        yaml_block = (triggers_yaml + "\n" + actions_yaml).strip()[:4000] or "(YAML unavailable)"

        # Read the AI-prompt section from the in-memory translation cache —
        # never block the event loop with file I/O.
        from .translation_utils import resolve_notification_language
        _lang = resolve_notification_language(self.hass)
        try:
            from . import _TS_CACHE  # noqa: PLC0415
            _cache = _TS_CACHE.get(_lang) or _TS_CACHE.get("en") or {}
            _ap = _cache.get("ai_prompts", {})
        except Exception:
            _ap = {}
        prompt = _ap.get("description_suggest_system", "Suggest a short description for: {yaml}").format(yaml=yaml_block)

        # ── Call AI ────────────────────────────────────────────────────────────
        suggestion = ""
        try:
            from .conversation import _async_call_ai
            raw = await _async_call_ai(self.hass, prompt, "HACA Description Suggest")
            if raw:
                # Extract content from ```suggestion ... ``` block if present, else use raw
                import re as _re
                m = _re.search(r"```suggestion\s*(.*?)\s*```", raw, _re.DOTALL)
                suggestion = m.group(1).strip() if m else raw.strip()
        except Exception as ai_err:
            _LOGGER.debug("suggest_description_ai AI call failed: %s", ai_err)

        if not suggestion:
            # Fallback: use alias as base suggestion
            suggestion = alias

        return {
            "success": True,
            "entity_id": entity_id,
            "alias": alias,
            "suggestion": suggestion,
        }

    async def apply_description_fix(self, entity_id: str, description: str) -> dict[str, Any]:
        """Write a description field into an automation or script YAML config."""
        if not entity_id or not description:
            return {"success": False, "error": "entity_id and description are required"}

        is_script = entity_id.startswith("script.")

        if is_script:
            scan = await self._async_locate_script(entity_id)
            if not scan.found:
                return {
                    "success": False,
                    "error": f"Script '{entity_id}' not found in any script YAML file",
                }
        else:
            scan = await self._async_locate_automation(entity_id)
            if not scan.found:
                return {
                    "success": False,
                    "error": f"Automation '{entity_id}' not found in any automation YAML file",
                }

        try:
            scan.entry["description"] = description
            # A script is validated under its key, an automation under its `id`.
            backup_path = await async_write_checked(
                self.hass, scan.target,
                "script" if is_script else "automation",
                entry=scan.entry,
                key=scan.key if is_script else scan.entry.get("id"),
            )

            return {
                "success": True,
                "entity_id": entity_id,
                "description": description,
                "backup_path": str(backup_path),
                "message": "Description saved. Reload automations/scripts to apply.",
            }

        except RejectedByHomeAssistant as exc:
            _LOGGER.info("Description fix on %s not applied: %s", entity_id, exc)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            _LOGGER.error("apply_description_fix error: %s", exc)
            return {"success": False, "error": str(exc)}
