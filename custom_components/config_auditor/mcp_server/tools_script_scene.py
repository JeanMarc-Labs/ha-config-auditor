"""Script and scene CRUD.

Both live in YAML domains Home Assistant merges from several files, are edited
through the same round-trip reader, and roll back together when the reload
that follows a write fails.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..yaml_writer import open_or_create
from .common import (
    _async_scan_list_domain,
    _async_scan_list_for_edit,
    _async_scan_named_domain,
    _async_scan_named_for_edit,
    _async_write_target,
    _read_plain_yaml,
    _safe_edit_and_reload,
    _skipped_note,
    _slugify,
)
from .tools_system import _auto_backup


async def _tool_ha_create_script(hass: HomeAssistant, params: dict) -> dict:
    """Crée ou met à jour un script dans scripts.yaml."""
    from pathlib import Path

    script_id = _slugify(params.get("script_id", "").strip())
    alias = params.get("alias", "").strip()
    sequence = params.get("sequence")

    if not script_id or not alias or not sequence:
        return {"error": "script_id, alias and sequence are required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_create_script")
    if not isinstance(sequence, list):
        sequence = [sequence]

    script_def: dict[str, Any] = {
        "alias": alias,
        "description": params.get("description", ""),
        "mode": params.get("mode", "single"),
        "sequence": sequence,
    }

    try:
        # Un script existant est réécrit dans SON fichier ; un nouveau va dans
        # la cible d'écriture (scripts.yaml à plat, fichier dédié si splitté).
        owner = await _async_scan_named_for_edit(
            hass, "script", "scripts.yaml",
            lambda key, _entry: key == script_id,
        )
        if owner.found:
            scripts_file = Path(owner.path)
        else:
            scripts_file = Path(
                await _async_write_target(hass, "script", "scripts.yaml", "haca_mcp.yaml")
            )

        await hass.async_add_executor_job(
            lambda: scripts_file.parent.mkdir(parents=True, exist_ok=True)
        )
        # Reuse the document the owner scan already parsed, so the file is read
        # once and the other scripts in it keep their comments.
        target = owner.target if owner.found else await hass.async_add_executor_job(
            open_or_create, str(scripts_file), dict
        )
        action = "updated" if script_id in target.document else "created"
        target.document[script_id] = script_def
        await _safe_edit_and_reload(
            hass, target, "script", entry=script_def, key=script_id
        )

        return {
            "success": True,
            "script_id": script_id,
            "entity_id": f"script.{script_id}",
            "alias": alias,
            "action": action,
            "file": str(scripts_file),
            "message": f"Script '{alias}' {action} in {scripts_file} and reloaded. Call it with ha_call_service(domain='script', service='{script_id}').",
        }
    except Exception as exc:
        return {"error": f"Failed to create script: {exc}"}


# ═══════════════════════════════════════════════════════════════════════════════
# v1.5.1 — 24 NEW TOOLS: scripts, scenes, blueprints, dashboard, helpers,
#           entities, config files, labels/categories
# ═══════════════════════════════════════════════════════════════════════════════

# ── SCRIPTS ─────────────────────────────────────────────────────────────────

async def _tool_ha_get_script(hass: HomeAssistant, params: dict) -> dict:
    """Read a script's full YAML and metadata."""
    import yaml as _yaml
    script_ref = params.get("entity_id", "").strip()
    if not script_ref:
        return {"error": "entity_id required (e.g. 'script.morning_routine' or alias)"}

    # Normalise ref → slug
    slug = script_ref.replace("script.", "").strip()

    def _matches(key: str, val: dict) -> bool:
        if key == slug:
            return True
        alias = val.get("alias", "")
        return bool(alias) and str(alias).lower() == script_ref.lower()

    # Cherche dans TOUS les fichiers que la clé `script:` résout — un
    # `!include_dir_merge_named` répartit les scripts sur plusieurs fichiers.
    scan = await _async_scan_named_domain(hass, "script", "scripts.yaml", _matches)

    if scan.key is None:
        # The slug hint re-reads only the files the scan could parse; the scan
        # itself already told us which ones it had to pass over.
        available: list[str] = []
        for path in scan.files:
            if path in scan.skipped:
                continue
            try:
                data = await hass.async_add_executor_job(_read_plain_yaml, path)
            except Exception:
                continue
            if isinstance(data, dict):
                available.extend(data.keys())
        return {
            "error": f"Script '{script_ref}' not found in any script YAML file "
                     f"({len(scan.files)} scanned)" + _skipped_note(scan.skipped),
            "files_scanned": scan.files,
            "skipped_files": scan.skipped,
            "available_slugs": available[:20],
        }
    found_path, all_scripts, found_key = scan.path, scan.mapping, scan.key

    found_data = all_scripts[found_key]
    return {
        "slug": found_key,
        "entity_id": f"script.{found_key}",
        "alias": found_data.get("alias", found_key) if isinstance(found_data, dict) else found_key,
        "description": found_data.get("description", "") if isinstance(found_data, dict) else "",
        "mode": found_data.get("mode", "single") if isinstance(found_data, dict) else "single",
        "source_file": found_path,
        "yaml": _yaml.dump({found_key: found_data}, allow_unicode=True, default_flow_style=False),
        "data": found_data,
    }


async def _tool_ha_update_script(hass: HomeAssistant, params: dict) -> dict:
    """Update an existing script in scripts.yaml."""
    script_ref = params.get("entity_id", "").strip()
    if not script_ref:
        return {"error": "entity_id required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_update_script")

    slug = script_ref.replace("script.", "").strip()
    scan = await _async_scan_named_for_edit(
        hass, "script", "scripts.yaml", lambda key, _entry: key == slug,
    )
    if not scan.found:
        return {
            "error": f"Script '{slug}' not found in any script YAML file "
                     f"({len(scan.files)} scanned)" + _skipped_note(scan.skipped),
            "files_scanned": scan.files,
            "skipped_files": scan.skipped,
        }
    scripts_path = scan.path

    current = scan.entry
    # Apply updates
    for field in ("alias", "description", "mode", "icon"):
        if params.get(field) is not None:
            current[field] = params[field]
    if params.get("sequence") is not None:
        current["sequence"] = params["sequence"]
    if params.get("variables") is not None:
        current["variables"] = params["variables"]

    try:
        await _safe_edit_and_reload(
            hass, scan.target, "script", entry=current, key=scan.key
        )
    except Exception as exc:
        return {"error": f"Failed to write {scripts_path}: {exc}"}

    return {
        "success": True,
        "entity_id": f"script.{slug}",
        "file": scripts_path,
        "message": f"Script '{slug}' updated in {scripts_path} and reloaded.",
    }


async def _tool_ha_remove_script(hass: HomeAssistant, params: dict) -> dict:
    """Delete a script from scripts.yaml."""
    script_ref = params.get("entity_id", "").strip()
    if not script_ref:
        return {"error": "entity_id required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_remove_script")

    slug = script_ref.replace("script.", "").strip()
    scan = await _async_scan_named_for_edit(
        hass, "script", "scripts.yaml", lambda key, _entry: key == slug,
    )
    if not scan.found:
        return {
            "error": f"Script '{slug}' not found in any script YAML file "
                     f"({len(scan.files)} scanned)" + _skipped_note(scan.skipped),
            "files_scanned": scan.files,
            "skipped_files": scan.skipped,
        }
    scripts_path = scan.path

    removed = scan.document.pop(slug)
    try:
        await _safe_edit_and_reload(hass, scan.target, "script")
    except Exception as exc:
        return {"error": f"Failed to write {scripts_path}: {exc}"}

    alias = removed.get("alias", slug) if isinstance(removed, dict) else slug
    return {
        "success": True,
        "deleted": slug,
        "alias": alias,
        "file": scripts_path,
        "message": f"Script '{alias}' deleted from {scripts_path}.",
    }


# ── SCENES ───────────────────────────────────────────────────────────────────

async def _tool_ha_get_scene(hass: HomeAssistant, params: dict) -> dict:
    """Read a scene's full YAML and entity states."""
    import yaml as _yaml
    scene_ref = params.get("entity_id", "").strip()
    if not scene_ref:
        return {"error": "entity_id required (e.g. 'scene.movie_night' or alias 'Movie night')"}

    slug = scene_ref.replace("scene.", "").strip().lower()

    def _matches(scene: dict) -> bool:
        sid = str(scene.get("id", "")).lower()
        sname = str(scene.get("name", "")).lower()
        return sid == slug or sname == slug or sname == scene_ref.lower()

    scan = await _async_scan_list_domain(hass, "scene", "scenes.yaml", _matches)
    if scan.index >= 0:
        scene = scan.documents[scan.index]
        return {
            "id": scene.get("id"),
            "name": scene.get("name"),
            "entity_id": f"scene.{scene.get('id', slug)}",
            "entities": scene.get("entities", {}),
            "source_file": scan.path,
            "yaml": _yaml.dump(scene, allow_unicode=True, default_flow_style=False),
        }

    # The name hint re-reads only the files the scan could parse; the scan
    # itself already told us which ones it had to pass over.
    available: list = []
    for path in scan.files:
        if path in scan.skipped:
            continue
        try:
            data = await hass.async_add_executor_job(_read_plain_yaml, path)
        except Exception:
            continue
        if isinstance(data, list):
            available.extend(
                s.get("name") or s.get("id") for s in data if isinstance(s, dict)
            )
    return {
        "error": f"Scene '{scene_ref}' not found in any scene YAML file "
                 f"({len(scan.files)} scanned)" + _skipped_note(scan.skipped),
        "files_scanned": scan.files,
        "skipped_files": scan.skipped,
        "available": available[:20],
    }


async def _tool_ha_create_scene(hass: HomeAssistant, params: dict) -> dict:
    """Create a new scene in scenes.yaml."""
    name = params.get("name", "").strip()
    entities = params.get("entities")
    if not name:
        return {"error": "name required"}
    if not entities or not isinstance(entities, dict):
        return {"error": "entities dict required, e.g. {'light.salon': {'state': 'on', 'brightness': 200}}"}

    slug = _slugify(name)

    # Doublon cherché dans toute la config, pas seulement dans scenes.yaml
    # Plain reader on purpose, as in ha_create_automation: a duplicate check
    # should see as many existing entries as it can, and the edit reader is
    # stricter — it also passes over a file with a duplicate key. A false "no
    # duplicate" is the costly answer here.
    duplicate = await _async_scan_list_domain(
        hass, "scene", "scenes.yaml", lambda s: s.get("id") == slug
    )
    if duplicate.index >= 0:
        return {"error": f"Scene with id '{slug}' already exists in {duplicate.path}. "
                         "Use ha_update_scene to modify."}

    scenes_path = await _async_write_target(
        hass, "scene", "scenes.yaml", "haca_mcp.yaml"
    )

    new_scene: dict = {"id": slug, "name": name, "entities": entities}
    if params.get("icon"):
        new_scene["icon"] = params["icon"]

    try:
        import os as _os

        await hass.async_add_executor_job(
            _os.makedirs, _os.path.dirname(scenes_path), 0o755, True
        )
        target = await hass.async_add_executor_job(
            open_or_create, scenes_path, list
        )
        target.document.append(new_scene)
        await _safe_edit_and_reload(hass, target, "scene", entry=new_scene)
    except Exception as exc:
        return {"error": f"Failed to write {scenes_path}: {exc}"}

    return {
        "success": True,
        "id": slug,
        "entity_id": f"scene.{slug}",
        "file": scenes_path,
        "message": f"Scene '{name}' created in {scenes_path} (scene.{slug}).",
    }


async def _tool_ha_update_scene(hass: HomeAssistant, params: dict) -> dict:
    """Update an existing scene in scenes.yaml."""
    scene_ref = params.get("entity_id", "").strip()
    if not scene_ref:
        return {"error": "entity_id required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_update_scene")

    slug = scene_ref.replace("scene.", "").strip().lower()
    scan = await _async_scan_list_for_edit(
        hass, "scene", "scenes.yaml",
        lambda s: (
            str(s.get("id", "")).lower() == slug
            or str(s.get("name", "")).lower() == scene_ref.lower()
        ),
    )
    if not scan.found:
        return {"error": f"Scene '{scene_ref}' not found in any scene YAML file "
                         f"({len(scan.files)} scanned)" + _skipped_note(scan.skipped),
                "files_scanned": scan.files,
                "skipped_files": scan.skipped}
    scenes_path = scan.path

    scene = scan.entry
    for field in ("name", "icon"):
        if params.get(field) is not None:
            scene[field] = params[field]
    if params.get("entities") is not None:
        scene["entities"] = params["entities"]

    try:
        await _safe_edit_and_reload(hass, scan.target, "scene", entry=scene)
    except Exception as exc:
        return {"error": f"Failed to write {scenes_path}: {exc}"}

    return {
        "success": True,
        "entity_id": f"scene.{scene.get('id', slug)}",
        "file": scenes_path,
        "message": f"Scene '{scene.get('name', slug)}' updated in {scenes_path} and reloaded.",
    }


async def _tool_ha_remove_scene(hass: HomeAssistant, params: dict) -> dict:
    """Delete a scene from scenes.yaml."""
    scene_ref = params.get("entity_id", "").strip()
    if not scene_ref:
        return {"error": "entity_id required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_remove_scene")

    slug = scene_ref.replace("scene.", "").strip().lower()
    scan = await _async_scan_list_for_edit(
        hass, "scene", "scenes.yaml",
        lambda s: (
            str(s.get("id", "")).lower() == slug
            or str(s.get("name", "")).lower() == scene_ref.lower()
        ),
    )
    if not scan.found:
        return {"error": f"Scene '{scene_ref}' not found in any scene YAML file "
                         f"({len(scan.files)} scanned)" + _skipped_note(scan.skipped),
                "files_scanned": scan.files,
                "skipped_files": scan.skipped}
    scenes_path = scan.path

    removed = scan.document.pop(scan.index)
    removed_name = removed.get("name") or removed.get("id")

    try:
        await _safe_edit_and_reload(hass, scan.target, "scene")
    except Exception as exc:
        return {"error": f"Failed to write {scenes_path}: {exc}"}

    return {
        "success": True,
        "deleted": removed_name or scene_ref,
        "file": scenes_path,
        "message": f"Scene '{removed_name or scene_ref}' deleted from {scenes_path}.",
    }
