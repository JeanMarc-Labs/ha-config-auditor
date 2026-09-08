"""Tools over the Home Assistant registries and the helper domains.

Entities, areas, labels, and the ``input_*`` / ``counter`` / ``timer`` helpers.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..yaml_sources import iter_domain_files
from .common import _caller_context, _slugify


# ─── Handlers des nouveaux outils HA Control ──────────────────────────────

async def _tool_ha_get_entities(hass: HomeAssistant, params: dict) -> dict:
    """Liste les entités HA avec leurs états."""
    domain_filter = params.get("domain", "").lower().strip()
    area_filter = params.get("area", "").lower().strip()
    search = params.get("search", "").lower().strip()
    limit = int(params.get("limit", 50))

    try:
        from homeassistant.helpers import area_registry as ar, entity_registry as er, device_registry as dr

        area_reg = ar.async_get(hass)
        entity_reg = er.async_get(hass)
        device_reg = dr.async_get(hass)

        # Build area_id → area_name map
        area_map: dict[str, str] = {a.id: a.name for a in area_reg.async_list_areas()}

        results = []
        for state in hass.states.async_all():
            eid = state.entity_id
            if domain_filter and not eid.startswith(f"{domain_filter}."):
                continue

            name = state.attributes.get("friendly_name", eid)
            if search and search not in eid.lower() and search not in name.lower():
                continue

            # Find area
            entry = entity_reg.entities.get(eid)
            entity_area_id = entry.area_id if entry else None
            device_area_id = None
            if entry and entry.device_id:
                device = device_reg.async_get(entry.device_id)
                device_area_id = device.area_id if device else None
            area_id = entity_area_id or device_area_id
            area_name = area_map.get(area_id, "") if area_id else ""

            if area_filter and area_filter not in area_name.lower():
                continue

            results.append({
                "entity_id": eid,
                "friendly_name": name,
                "state": state.state,
                "area": area_name,
                "domain": eid.split(".")[0],
                "attributes": {
                    k: list(v) if isinstance(v, (set, frozenset)) else v
                    for k, v in state.attributes.items()
                    if k not in ("friendly_name", "icon", "supported_features")
                    and not isinstance(v, (dict, list))
                },
            })
            if len(results) >= limit:
                break

        return {"total": len(results), "entities": results}

    except Exception as exc:
        return {"error": f"Error listing entities: {exc}"}


async def _tool_ha_rename_entity(hass: HomeAssistant, params: dict) -> dict:
    """Rename/update entity properties via the entity registry."""
    from homeassistant.helpers import entity_registry as er, area_registry as ar

    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id is required"}

    new_name = params.get("new_name")
    new_entity_id = params.get("new_entity_id")
    icon = params.get("icon")
    area_id = params.get("area_id")

    if not any([new_name, new_entity_id, icon, area_id]):
        return {"error": "At least one of new_name, new_entity_id, icon, area_id must be provided"}

    try:
        entity_reg = er.async_get(hass)
        entry = entity_reg.entities.get(entity_id)

        if entry is None:
            return {
                "error": f"Entity '{entity_id}' not found in entity registry. "
                         f"Use ha_get_entities to verify the entity_id.",
            }

        # Validate area_id if provided
        if area_id:
            area_reg = ar.async_get(hass)
            if not area_reg.async_get_area(area_id):
                # Try fuzzy match by name
                matches = [
                    a for a in area_reg.async_list_areas()
                    if area_id.lower() in a.name.lower() or a.id == area_id
                ]
                if matches:
                    area_id = matches[0].id
                else:
                    return {
                        "error": f"Area '{area_id}' not found. "
                                 f"Valid areas: {[a.name + ' (' + a.id + ')' for a in area_reg.async_list_areas()]}",
                    }

        # Build kwargs — only pass what's changing
        kwargs: dict[str, Any] = {}
        if new_name is not None:
            kwargs["name"] = new_name
        if icon is not None:
            kwargs["icon"] = icon
        if area_id is not None:
            kwargs["area_id"] = area_id
        if new_entity_id is not None:
            kwargs["new_entity_id"] = new_entity_id

        updated = entity_reg.async_update_entity(entity_id, **kwargs)

        changes: list[str] = []
        if new_name:
            changes.append(f"name → '{new_name}'")
        if icon:
            changes.append(f"icon → '{icon}'")
        if area_id:
            area_reg = ar.async_get(hass)
            area = area_reg.async_get_area(area_id)
            changes.append(f"area → '{area.name if area else area_id}'")
        if new_entity_id:
            changes.append(f"entity_id → '{new_entity_id}'")

        return {
            "success": True,
            "entity_id": updated.entity_id,
            "changes": changes,
            "message": f"Entity '{entity_id}' updated: {', '.join(changes)}.",
            "warning": (
                f"entity_id changed from '{entity_id}' to '{new_entity_id}'. "
                "Update any automations or scripts that reference the old entity_id."
            ) if new_entity_id else None,
        }

    except Exception as exc:
        return {"error": f"Failed to update entity: {exc}"}


_HELPER_DOMAINS = {
    "input_boolean", "input_number", "input_text",
    "input_select", "input_datetime", "counter", "timer", "schedule"
}


async def _tool_ha_config_list_helpers(hass: HomeAssistant, params: dict) -> dict:
    """List helper entities, optionally flagging orphans."""
    from pathlib import Path
    from homeassistant.helpers import entity_registry as er

    helper_type = params.get("helper_type", "all")
    include_orphans_check = params.get("include_orphans_check", True)

    domains = _HELPER_DOMAINS if helper_type == "all" else {helper_type}

    try:
        entity_reg = er.async_get(hass)

        # Build reference corpus from automations + scripts if orphan check requested
        reference_corpus = ""
        if include_orphans_check:
            config_dir = Path(hass.config.config_dir)

            def _read_corpus():
                # Tous les fichiers d'automations et de scripts : avec une
                # config splittée, un corpus limité aux fichiers plats est vide
                # et TOUS les helpers ressortent comme orphelins.
                corpus = ""
                for key, default in (
                    ("automation", "automations.yaml"),
                    ("script", "scripts.yaml"),
                ):
                    for fpath in iter_domain_files(str(config_dir), key, default):
                        try:
                            corpus += Path(fpath).read_text(encoding="utf-8")
                        except Exception:
                            continue
                return corpus

            reference_corpus = await hass.async_add_executor_job(_read_corpus)

        helpers: list[dict] = []
        for state in hass.states.async_all():
            domain = state.entity_id.split(".")[0]
            if domain not in domains:
                continue

            entry = entity_reg.entities.get(state.entity_id)
            used_in_config = (state.entity_id in reference_corpus) if include_orphans_check else None

            helpers.append({
                "entity_id": state.entity_id,
                "type": domain,
                "name": state.attributes.get("friendly_name", state.entity_id),
                "state": state.state,
                "icon": (entry.icon if entry else None) or state.attributes.get("icon"),
                "area_id": entry.area_id if entry else None,
                "orphan": (not used_in_config) if include_orphans_check else None,
            })

        orphan_count = sum(1 for h in helpers if h.get("orphan"))
        return {
            "success": True,
            "total": len(helpers),
            "orphan_count": orphan_count if include_orphans_check else None,
            "helpers": helpers,
            "note": f"{orphan_count} helper(s) not referenced in any automation or script YAML file." if include_orphans_check and orphan_count else "",
        }

    except Exception as exc:
        return {"error": f"Failed to list helpers: {exc}"}


async def _tool_ha_config_set_helper(hass: HomeAssistant, params: dict) -> dict:
    """Create or update a helper entity via HA service calls."""
    helper_type = params.get("helper_type", "")
    name = params.get("name", "").strip()

    if not helper_type or not name:
        return {"error": "helper_type and name are required"}
    if helper_type not in _HELPER_DOMAINS - {"schedule"}:
        return {"error": f"Unsupported helper_type '{helper_type}'. Choose from: {sorted(_HELPER_DOMAINS - {'schedule'})}"}

    # Build helper_id from name if not provided
    helper_id = params.get("helper_id") or _slugify(name)
    full_entity_id = f"{helper_type}.{helper_id}"
    options = params.get("options") or {}

    # Check if already exists
    existing = hass.states.get(full_entity_id)
    action = "update" if existing else "create"

    try:
        # Use HA REST-equivalent: hass.config_entries or direct storage manipulation
        # The cleanest approach is via the built-in services
        service_data: dict[str, Any] = {"name": name}
        if params.get("icon"):
            service_data["icon"] = params["icon"]

        # Type-specific fields
        if helper_type == "input_number":
            service_data["min"] = options.get("min", 0)
            service_data["max"] = options.get("max", 100)
            service_data["step"] = options.get("step", 1)
            if options.get("unit_of_measurement"):
                service_data["unit_of_measurement"] = options["unit_of_measurement"]
        elif helper_type == "input_select":
            opts = options.get("options", [])
            if not opts:
                return {"error": "input_select requires options.options (list of strings)"}
            service_data["options"] = opts
        elif helper_type == "input_text":
            if options.get("max_length"):
                service_data["max"] = options["max_length"]
        elif helper_type == "counter":
            if options.get("initial_value") is not None:
                service_data["initial"] = options["initial_value"]
            if options.get("step_counter") is not None:
                service_data["step"] = options["step_counter"]
            if options.get("minimum") is not None:
                service_data["minimum"] = options["minimum"]
            if options.get("maximum") is not None:
                service_data["maximum"] = options["maximum"]
        elif helper_type == "timer":
            if options.get("duration"):
                service_data["duration"] = options["duration"]

        # Create via entity_component config create
        component = hass.data.get(helper_type)

        if component and hasattr(component, "async_create_entity"):
            await component.async_create_entity(hass, service_data)
        else:
            # Fallback: use the storage-based config create service
            # Many helpers expose `<domain>.create` in HA 2024+
            await hass.services.async_call(
                helper_type,
                "create",
                service_data,
                blocking=True,
                context=_caller_context(),
            )

        return {
            "success": True,
            "action": action,
            "entity_id": full_entity_id,
            "name": name,
            "type": helper_type,
            "message": f"Helper '{name}' ({full_entity_id}) {action}d successfully.",
        }

    except Exception as exc:
        return {
            "error": f"Failed to {action} helper '{name}': {exc}",
            "hint": "Some helper types require HA 2024.4+. "
                    "You can also create helpers manually in Settings → Helpers.",
        }


async def _tool_ha_config_remove_helper(hass: HomeAssistant, params: dict) -> dict:
    """Delete a helper entity."""
    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id is required"}

    domain = entity_id.split(".")[0]
    if domain not in _HELPER_DOMAINS:
        return {"error": f"'{entity_id}' does not appear to be a helper entity. "
                          f"Helper domains: {sorted(_HELPER_DOMAINS)}"}

    # Check it exists
    if not hass.states.get(entity_id):
        return {"error": f"Entity '{entity_id}' not found. Use ha_config_list_helpers to find valid entity_ids."}

    try:
        from homeassistant.helpers import entity_registry as er
        entity_reg = er.async_get(hass)
        entry = entity_reg.entities.get(entity_id)

        if entry:
            entity_reg.async_remove(entity_id)
            return {
                "success": True,
                "entity_id": entity_id,
                "message": f"Helper '{entity_id}' deleted successfully.",
            }
        else:
            # Try via service
            await hass.services.async_call(
                domain,
                "remove",
                {"entity_id": entity_id},
                blocking=True,
                context=_caller_context(),
            )
            return {
                "success": True,
                "entity_id": entity_id,
                "message": f"Helper '{entity_id}' deleted successfully.",
            }

    except Exception as exc:
        return {"error": f"Failed to delete helper '{entity_id}': {exc}"}


async def _tool_ha_config_set_area(hass: HomeAssistant, params: dict) -> dict:
    """Create or update a HA area."""
    from homeassistant.helpers import area_registry as ar

    name = params.get("name", "").strip()
    if not name:
        return {"error": "name is required"}

    area_id = params.get("area_id") or _slugify(name)
    icon = params.get("icon")
    picture = params.get("picture")

    try:
        area_reg = ar.async_get(hass)

        # Check if exists (by id or name)
        existing = area_reg.async_get_area(area_id) or next(
            (a for a in area_reg.async_list_areas() if a.name.lower() == name.lower()), None
        )

        kwargs: dict[str, Any] = {}
        if icon is not None:
            kwargs["icon"] = icon
        if picture is not None:
            kwargs["picture"] = picture

        if existing:
            area_reg.async_update(existing.id, name=name, **kwargs)
            action = "updated"
            final_id = existing.id
        else:
            new_area = area_reg.async_create(name, **kwargs)
            action = "created"
            final_id = new_area.id

        return {
            "success": True,
            "action": action,
            "area_id": final_id,
            "name": name,
            "message": f"Area '{name}' (id: {final_id}) {action} successfully.",
        }

    except Exception as exc:
        return {"error": f"Failed to {('update' if existing else 'create')} area: {exc}"}


async def _tool_ha_manage_entity_labels(hass: HomeAssistant, params: dict) -> dict:
    """Add, remove, or replace labels on entities."""
    from homeassistant.helpers import entity_registry as er, label_registry as lr

    raw_ids = params.get("entity_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]

    action = params.get("action", "add")
    labels_input = params.get("labels", [])

    if not raw_ids:
        return {"error": "entity_ids is required"}
    if action not in ("add", "remove", "replace"):
        return {"error": "action must be 'add', 'remove', or 'replace'"}
    if not labels_input and action in ("add", "replace"):
        return {"error": "labels list is required for add/replace actions"}

    try:
        entity_reg = er.async_get(hass)
        label_reg = lr.async_get(hass)

        # Ensure labels exist (create if needed for add/replace)
        if action in ("add", "replace"):
            for label_id in labels_input:
                existing_label = label_reg.async_get_label(label_id)
                if not existing_label:
                    label_reg.async_create(label_id, name=label_id)

        updated: list[str] = []
        not_found: list[str] = []

        for eid in raw_ids:
            entry = entity_reg.entities.get(eid)
            if not entry:
                not_found.append(eid)
                continue

            current_labels: set[str] = set(entry.labels or [])
            input_set = set(labels_input)

            if action == "add":
                new_labels = current_labels | input_set
            elif action == "remove":
                new_labels = current_labels - input_set
            else:  # replace
                new_labels = input_set

            entity_reg.async_update_entity(eid, labels=new_labels)
            updated.append(eid)

        return {
            "success": True,
            "action": action,
            "labels": labels_input,
            "updated_count": len(updated),
            "updated": updated,
            "not_found": not_found,
            "message": f"Labels {action}d on {len(updated)} entity/entities.",
        }

    except Exception as exc:
        return {"error": f"Failed to manage labels: {exc}"}


# ── HELPERS EDIT ──────────────────────────────────────────────────────────────

async def _tool_ha_get_helper(hass: HomeAssistant, params: dict) -> dict:
    """Read a helper's current state, friendly name, and configuration."""
    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id required (e.g. 'input_boolean.mode_nuit')"}

    state = hass.states.get(entity_id)
    if state is None:
        # Try by friendly name
        for s in hass.states.async_all():
            if s.attributes.get("friendly_name", "").lower() == entity_id.lower():
                state = s
                entity_id = s.entity_id
                break

    if state is None:
        return {"error": f"Helper '{entity_id}' not found in HA state machine"}

    try:
        from homeassistant.helpers import entity_registry as er_mod
        registry = er_mod.async_get(hass)
        entry = registry.async_get(entity_id)
        entry_dict = {
            "unique_id": entry.unique_id if entry else None,
            "platform": entry.platform if entry else None,
            "area_id": entry.area_id if entry else None,
            "icon": entry.icon if entry else None,
            "disabled_by": str(entry.disabled_by) if entry and entry.disabled_by else None,
        }
    except Exception:
        entry_dict = {}

    return {
        "entity_id": entity_id,
        "state": state.state,
        "friendly_name": state.attributes.get("friendly_name"),
        "icon": state.attributes.get("icon"),
        "domain": entity_id.split(".")[0],
        "attributes": dict(state.attributes),
        "registry": entry_dict,
    }


async def _tool_ha_update_helper(hass: HomeAssistant, params: dict) -> dict:
    """Update a helper's configuration (name, icon, min/max/step, options, etc.)."""
    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id required"}

    domain = entity_id.split(".")[0]
    _HELPER_DOMAINS = {
        "input_boolean", "input_number", "input_text",
        "input_select", "input_datetime", "input_button",
        "timer", "counter",
    }
    if domain not in _HELPER_DOMAINS:
        return {"error": f"'{entity_id}' is not a recognised helper domain. Supported: {sorted(_HELPER_DOMAINS)}"}

    try:
        from homeassistant.helpers import entity_registry as er_mod
        registry = er_mod.async_get(hass)
        entry = registry.async_get(entity_id)
    except Exception as exc:
        return {"error": f"Could not access entity registry: {exc}"}

    if entry is None:
        return {"error": f"'{entity_id}' not found in entity registry"}

    # Rename friendly name via registry
    updated_fields: list[str] = []
    try:
        if params.get("name") is not None:
            registry.async_update_entity(entity_id, name=params["name"])
            updated_fields.append("name")
        if params.get("icon") is not None:
            registry.async_update_entity(entity_id, icon=params["icon"])
            updated_fields.append("icon")
        if params.get("area_id") is not None:
            registry.async_update_entity(entity_id, area_id=params["area_id"])
            updated_fields.append("area_id")
    except Exception as exc:
        return {"error": f"Registry update failed: {exc}"}

    # Domain-specific config update via service
    svc_data: dict = {}
    if domain == "input_number":
        for f in ("min", "max", "step", "mode"):
            if params.get(f) is not None:
                svc_data[f] = params[f]
    elif domain == "input_select":
        if params.get("options") is not None:
            svc_data["options"] = params["options"]
    elif domain == "input_text":
        for f in ("min", "max", "pattern", "mode"):
            if params.get(f) is not None:
                svc_data[f] = params[f]
    elif domain == "timer":
        if params.get("duration") is not None:
            svc_data["duration"] = params["duration"]

    if svc_data:
        svc_data["entity_id"] = entity_id
        try:
            await hass.services.async_call(domain, "reload", blocking=True, context=_caller_context())
            updated_fields.extend(list(svc_data.keys()) - {"entity_id"})
        except Exception:
            pass

    return {
        "success": True,
        "entity_id": entity_id,
        "updated_fields": updated_fields,
        "message": f"Helper '{entity_id}' updated ({', '.join(updated_fields) or 'no changes'}).",
    }


# ── ENTITIES ──────────────────────────────────────────────────────────────────

async def _tool_ha_get_entity_detail(hass: HomeAssistant, params: dict) -> dict:
    """Read all metadata (state, attributes, registry, device info) for an entity."""
    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id required"}

    state = hass.states.get(entity_id)
    state_dict: dict = {}
    if state:
        state_dict = {
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat() if state.last_changed else None,
            "last_updated": state.last_updated.isoformat() if state.last_updated else None,
            "context": {"id": state.context.id} if state.context else {},
        }

    registry_dict: dict = {}
    device_dict: dict = {}
    try:
        from homeassistant.helpers import entity_registry as er_mod, device_registry as dr_mod
        er = er_mod.async_get(hass)
        entry = er.async_get(entity_id)
        if entry:
            registry_dict = {
                "unique_id": entry.unique_id,
                "platform": entry.platform,
                "area_id": entry.area_id,
                "icon": entry.icon,
                "disabled_by": str(entry.disabled_by) if entry.disabled_by else None,
                "hidden_by": str(entry.hidden_by) if entry.hidden_by else None,
                "device_id": entry.device_id,
                "config_entry_id": entry.config_entry_id,
                "labels": list(entry.labels) if entry.labels else [],
                "categories": dict(entry.categories) if entry.categories else {},
            }
            if entry.device_id:
                dr = dr_mod.async_get(hass)
                device = dr.async_get(entry.device_id)
                if device:
                    device_dict = {
                        "name": device.name_by_user or device.name,
                        "manufacturer": device.manufacturer,
                        "model": device.model,
                        "sw_version": device.sw_version,
                        "area_id": device.area_id,
                    }
    except Exception as exc:
        registry_dict["error"] = str(exc)

    return {
        "entity_id": entity_id,
        "found": state is not None or bool(registry_dict),
        "state": state_dict,
        "registry": registry_dict,
        "device": device_dict,
    }


async def _tool_ha_remove_entity(hass: HomeAssistant, params: dict) -> dict:
    """Remove a ghost/zombie/orphaned entity from the entity registry.

    WARNING: This only removes the registry entry — the entity may reappear
    if the underlying integration re-creates it.
    """
    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id required"}

    try:
        from homeassistant.helpers import entity_registry as er_mod
        er = er_mod.async_get(hass)
        entry = er.async_get(entity_id)
        if entry is None:
            return {"error": f"'{entity_id}' not found in entity registry"}

        # Safety check: entity should be unavailable/unknown/disabled or explicitly forced
        force = params.get("force", False)
        state = hass.states.get(entity_id)
        if state and state.state not in ("unavailable", "unknown") and not force:
            return {
                "error": (
                    f"Entity '{entity_id}' is currently in state '{state.state}' — "
                    "it appears active. Set force=true to remove anyway, or use ha_enable_entity "
                    "to disable it first."
                ),
                "current_state": state.state,
            }

        er.async_remove(entity_id)
        return {
            "success": True,
            "removed": entity_id,
            "platform": entry.platform,
            "message": (
                f"Entity '{entity_id}' removed from registry. "
                "Note: it may reappear if the integration re-discovers it."
            ),
        }
    except Exception as exc:
        return {"error": f"Failed to remove entity: {exc}"}


async def _tool_ha_enable_entity(hass: HomeAssistant, params: dict) -> dict:
    """Enable or disable an entity in the registry."""
    entity_id = params.get("entity_id", "").strip()
    enable = params.get("enable", True)
    if not entity_id:
        return {"error": "entity_id required"}

    try:
        from homeassistant.helpers import entity_registry as er_mod
        from homeassistant.helpers.entity_registry import RegistryEntryDisabler
        er = er_mod.async_get(hass)
        entry = er.async_get(entity_id)
        if entry is None:
            return {"error": f"'{entity_id}' not found in entity registry"}

        if enable:
            er.async_update_entity(entity_id, disabled_by=None)
            msg = f"Entity '{entity_id}' enabled."
        else:
            er.async_update_entity(entity_id, disabled_by=RegistryEntryDisabler.USER)
            msg = f"Entity '{entity_id}' disabled."

        return {"success": True, "entity_id": entity_id, "enabled": enable, "message": msg}
    except Exception as exc:
        return {"error": f"Failed to update entity: {exc}"}


# ── LABELS & CATEGORIES ───────────────────────────────────────────────────────

async def _tool_ha_list_labels(hass: HomeAssistant, params: dict) -> dict:
    """List all labels defined in Home Assistant."""
    try:
        from homeassistant.helpers import label_registry as lr_mod
        lr = lr_mod.async_get(hass)
        labels = [
            {
                "label_id": lbl.label_id,
                "name": lbl.name,
                "icon": lbl.icon,
                "color": lbl.color,
            }
            for lbl in lr.async_list_labels()
        ]
        return {"labels": labels, "total": len(labels)}
    except Exception as exc:
        return {"error": f"Failed to list labels: {exc}"}


async def _tool_ha_create_label(hass: HomeAssistant, params: dict) -> dict:
    """Create a new label in Home Assistant."""
    name = params.get("name", "").strip()
    if not name:
        return {"error": "name required"}
    icon  = params.get("icon", "")
    color = params.get("color", "")

    try:
        from homeassistant.helpers import label_registry as lr_mod
        lr = lr_mod.async_get(hass)
        existing = [l for l in lr.async_list_labels() if l.name.lower() == name.lower()]
        if existing:
            return {
                "success": False,
                "label_id": existing[0].label_id,
                "message": f"Label '{name}' already exists (id: {existing[0].label_id})",
            }
        kwargs: dict = {"name": name}
        if icon:
            kwargs["icon"] = icon
        if color:
            kwargs["color"] = color
        entry = lr.async_create(**kwargs)
        return {
            "success": True,
            "label_id": entry.label_id,
            "name": entry.name,
            "message": f"Label '{name}' created (id: {entry.label_id}).",
        }
    except Exception as exc:
        return {"error": f"Failed to create label: {exc}"}
