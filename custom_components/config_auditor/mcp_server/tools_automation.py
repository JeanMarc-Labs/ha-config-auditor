"""Automation CRUD, plus the trace reader."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..yaml_writer import open_or_create
from .common import (
    _async_open_domain_for_edit,
    _async_scan_list_domain,
    _async_scan_list_for_edit,
    _async_write_target,
    _LOGGER,
    _safe_edit_and_reload,
    _skipped_note,
    _slugify,
)
from .tools_system import _auto_backup


async def _tool_ha_create_automation(hass: HomeAssistant, params: dict) -> dict:
    """Crée une nouvelle automation dans automations.yaml."""
    from pathlib import Path
    import uuid

    alias = params.get("alias", "").strip()
    if not alias:
        return {"error": "alias is required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_create_automation")

    # Accept both new HA format (triggers/actions/conditions) and legacy (trigger/action/condition)
    trigger = params.get("triggers") or params.get("trigger")
    action = params.get("actions") or params.get("action")
    if trigger is None or action is None:
        return {"error": "triggers (or trigger) and actions (or action) are required"}

    # Normalise to lists
    if isinstance(trigger, dict):
        trigger = [trigger]
    if isinstance(action, dict):
        action = [action]

    condition = params.get("conditions") or params.get("condition")
    if isinstance(condition, dict):
        condition = [condition]

    new_auto: dict[str, Any] = {
        "id": str(params.get("id") or uuid.uuid4())[:32],
        "alias": alias,
        "description": params.get("description", ""),
        "triggers": trigger,
        "conditions": condition or [],
        "actions": action,
        "mode": params.get("mode", "single"),
    }

    try:
        # Refuser un doublon d'alias dans N'IMPORTE quel fichier de la config,
        # pas seulement dans automations.yaml.
        existing = await _async_scan_list_domain(
            hass, "automation", "automations.yaml",
            lambda item: item.get("alias") == alias,
        )
        if existing.path is not None:
            return {"error": f"Automation '{alias}' already exists in {existing.path}. "
                             "Use ha_update_automation to modify it."}

        # Cible d'écriture : le fichier plat sur une install classique, un
        # fichier dédié dans le dossier mergé sur une config splittée — jamais
        # la racine de config, que HA ne lit plus dans ce cas.
        auto_file = Path(
            await _async_write_target(
                hass, "automation", "automations.yaml", "haca_mcp.yaml"
            )
        )

        await hass.async_add_executor_job(
            lambda: auto_file.parent.mkdir(parents=True, exist_ok=True)
        )
        # Round-trip: appending an automation must not flatten the comments
        # around the ones already in the file.
        target = await hass.async_add_executor_job(
            open_or_create, str(auto_file), list
        )
        target.document.append(new_auto)
        await _safe_edit_and_reload(hass, target, "automation")

        return {
            "success": True,
            "id": new_auto["id"],
            "alias": alias,
            "entity_id": f"automation.{_slugify(alias)}",
            "message": f"Automation '{alias}' created and reloaded.",
        }
    except Exception as exc:
        return {"error": f"Failed to create automation: {exc}"}


async def _tool_ha_update_automation(hass: HomeAssistant, params: dict) -> dict:
    """Met à jour une automation existante dans automations.yaml."""
    from pathlib import Path

    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id is required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_update_automation")

    try:
        # Chercher l'automation dans TOUS les fichiers que la clé `automation:`
        # résout, et n'écrire que dans celui qui la contient.
        search_name = entity_id.replace("automation.", "").replace("_", " ")
        state = hass.states.get(entity_id)
        friendly = state.attributes.get("friendly_name", "") if state else ""

        def _matches(auto: dict) -> bool:
            alias = (auto.get("alias") or "").lower()
            return (
                (bool(friendly) and alias == friendly.lower())
                or alias == search_name.lower()
                or (bool(auto.get("id")) and str(auto["id"]) in entity_id)
            )

        scan = await _async_scan_list_for_edit(
            hass, "automation", "automations.yaml", _matches
        )
        if not scan.found:
            return {"error": f"Automation '{entity_id}' not found in any automation YAML file "
                             f"({len(scan.files)} scanned). "
                             f"Note: only YAML automations can be updated this way."
                             + _skipped_note(scan.skipped),
                    "skipped_files": scan.skipped}

        auto_file = Path(scan.path)
        auto = scan.entry

        # Apply updates — accept both new format (triggers/actions/conditions) and legacy
        if params.get("alias"):
            auto["alias"] = params["alias"]
        if "description" in params:
            auto["description"] = params["description"]

        # triggers / trigger
        new_triggers = params.get("triggers") if params.get("triggers") is not None else params.get("trigger")
        if new_triggers is not None:
            auto["triggers"] = [new_triggers] if isinstance(new_triggers, dict) else new_triggers
            auto.pop("trigger", None)  # remove legacy key if present

        # conditions / condition
        new_conditions = params.get("conditions") if params.get("conditions") is not None else params.get("condition")
        if new_conditions is not None:
            auto["conditions"] = [new_conditions] if isinstance(new_conditions, dict) else new_conditions
            auto.pop("condition", None)

        # actions / action
        new_actions = params.get("actions") if params.get("actions") is not None else params.get("action")
        if new_actions is not None:
            auto["actions"] = [new_actions] if isinstance(new_actions, dict) else new_actions
            auto.pop("action", None)

        # append_action (always appends to actions key, regardless of format)
        if params.get("append_action") is not None:
            ap = params["append_action"]
            new_ap = [ap] if isinstance(ap, dict) else ap
            existing = auto.get("actions") or auto.get("action", [])
            if isinstance(existing, dict):
                existing = [existing]
            auto["actions"] = existing + new_ap
            auto.pop("action", None)

        if params.get("mode"):
            auto["mode"] = params["mode"]

        # `auto` is the node inside the round-trip document, mutated in place.
        await _safe_edit_and_reload(hass, scan.target, "automation")

        return {
            "success": True,
            "alias": auto.get("alias"),
            "file": str(auto_file),
            "message": f"Automation '{auto.get('alias')}' updated in {auto_file} and reloaded.",
        }
    except Exception as exc:
        return {"error": f"Failed to update automation: {exc}"}


async def _tool_ha_get_automation_traces(hass: HomeAssistant, params: dict) -> dict:
    """Récupère les traces d'exécution d'une automation pour le débogage."""
    entity_id = params.get("entity_id", "").strip()
    limit = int(params.get("limit", 5))

    if not entity_id:
        return {"error": "entity_id is required"}

    state = hass.states.get(entity_id)
    if not state:
        return {"error": f"Automation '{entity_id}' not found"}

    attrs = state.attributes
    result: dict[str, Any] = {
        "entity_id": entity_id,
        "alias": attrs.get("friendly_name", entity_id),
        "current_state": state.state,
        "last_triggered": attrs.get("last_triggered"),
        "mode": attrs.get("mode", "single"),
        "current_task_count": attrs.get("current", 0),
        "max_tasks": attrs.get("max", 10),
    }

    # Tenter d'accéder aux traces depuis hass.data
    traces = []
    try:
        automation_domain_data = hass.data.get("automation", {})
        # HA stores automation entities in different ways by version
        # Try common keys
        for key in [entity_id, entity_id.replace("automation.", "")]:
            entity_obj = automation_domain_data.get(key)
            if entity_obj and hasattr(entity_obj, "traces"):
                raw_traces = entity_obj.traces
                for trace in list(raw_traces)[-limit:]:
                    trace_info: dict[str, Any] = {}
                    if hasattr(trace, "as_dict"):
                        trace_info = trace.as_dict()
                    elif hasattr(trace, "__dict__"):
                        trace_info = {
                            "run_id": getattr(trace, "run_id", "?"),
                            "timestamp": str(getattr(trace, "timestamp", "")),
                            "trigger": getattr(trace, "trigger", {}),
                            "result": getattr(trace, "result", {}),
                        }
                    traces.append(trace_info)
                break
    except Exception as exc:
        _LOGGER.debug("[HACA MCP] Trace access error: %s", exc)
        result["trace_note"] = (
            "Full traces require HA Automation Traces API. "
            "Check Developer Tools → Events → automation_triggered for debug info."
        )

    if traces:
        result["traces"] = traces[-limit:]
    else:
        # Provide actionable debug info from attributes
        result["debug_hints"] = [
            f"Last triggered: {attrs.get('last_triggered', 'never')}",
            f"Mode: {attrs.get('mode', 'single')} — {'could block if already running' if attrs.get('mode') == 'single' else 'ok'}",
            "Check Developer Tools → Automations → [select automation] → Traces for full execution log",
            "Common issues: trigger conditions not met, entity unavailable, condition blocking execution",
        ]

    return result


async def _tool_ha_remove_automation(hass: HomeAssistant, params: dict) -> dict:
    """Delete an automation from automations.yaml."""
    from pathlib import Path

    identifier = params.get("entity_id", "").strip()
    if not identifier:
        return {"error": "entity_id (or alias) is required"}

    # Backup automatique avant opération destructive
    await _auto_backup(hass, "_tool_ha_remove_automation")

    try:
        # Toutes les sources de la clé `automation:` — la passe de recherche
        # doit rester globale (id exact d'abord, tous fichiers confondus).
        load = await _async_open_domain_for_edit(
            hass, "automation", "automations.yaml", list
        )
        if not load.targets:
            return {"error": "no automation YAML file found"}

        # Find the automation — priority order (most precise first):
        # 1. Exact match on HA numeric id (most reliable — never ambiguous)
        # 2. The entity registry's unique_id for an `automation.<slug>` ref
        # 3. Exact case-sensitive alias match
        # 4. Case-insensitive alias match (last resort — may be ambiguous)
        #
        # The old slugify heuristic (alias.lower().replace(" ","_")) is removed
        # because "Lumière salon" and "Lumiere salon" would both match the same slug.
        # The registry replaces it without the ambiguity: a YAML automation's
        # entity slug comes from slugify(alias) and is written nowhere in the
        # file, but HA stores its `id:` as the entity's unique_id. Without this
        # pass the full entity_id — the form every other tool reports back —
        # resolved only when the slug happened to equal the id.
        slug = identifier.removeprefix("automation.") if identifier.startswith("automation.") else None

        unique_id: str | None = None
        if identifier.startswith("automation."):
            try:
                from homeassistant.helpers import entity_registry as er

                entry = er.async_get(hass).async_get(identifier)
                if entry and entry.unique_id:
                    unique_id = str(entry.unique_id).strip()
            except Exception:  # noqa: BLE001 — registry unavailable, fall through
                unique_id = None
        wanted_ids = {v for v in (slug or identifier, unique_id) if v}

        found_target = None
        found_idx = None
        found_alias = None

        # Pass 1 — exact id or exact entity_id slug
        for candidate in load.targets:
            for i, a in enumerate(candidate.document):
                if not isinstance(a, dict):
                    continue
                ha_id = str(a.get("id", "")).strip()
                if ha_id and ha_id in wanted_ids:
                    found_target, found_idx = candidate, i
                    found_alias = str(a.get("alias", "")).strip()
                    break
            if found_idx is not None:
                break

        # Pass 2 — exact alias (case-sensitive, then case-insensitive)
        if found_idx is None:
            for sensitive in (True, False):
                for candidate in load.targets:
                    for i, a in enumerate(candidate.document):
                        if not isinstance(a, dict):
                            continue
                        alias_val = str(a.get("alias", "")).strip()
                        cmp_id  = alias_val if sensitive else alias_val.lower()
                        # `slug` too: the alias never carries the domain prefix.
                        refs = {identifier, slug} - {None}
                        if not sensitive:
                            refs = {r.lower() for r in refs}
                        if cmp_id in refs:
                            found_target, found_idx = candidate, i
                            found_alias = alias_val
                            break
                    if found_idx is not None:
                        break
                if found_idx is not None:
                    break

        if found_idx is None:
            return {
                "error": f"Automation '{identifier}' not found in any automation YAML file "
                         f"({len(load.files)} scanned). "
                         f"Use ha_get_entities(domain='automation') to list available automations."
                         + _skipped_note(load.skipped),
                "skipped_files": load.skipped,
            }

        # Remove it — rewriting only the file that actually holds it
        auto_file = Path(found_target.path)
        removed = found_target.document.pop(found_idx)
        await _safe_edit_and_reload(hass, found_target, "automation")

        return {
            "success": True,
            "removed_alias": found_alias,
            "removed_id": removed.get("id", ""),
            "file": str(auto_file),
            "message": f"Automation '{found_alias}' deleted from {auto_file} and reloaded.",
        }

    except Exception as exc:
        return {"error": f"Failed to remove automation: {exc}"}
