"""WebSocket API pour H.A.C.A."""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register WebSocket handlers."""
    websocket_api.async_register_command(hass, handle_get_data)
    websocket_api.async_register_command(hass, handle_scan_all)
    websocket_api.async_register_command(hass, handle_preview_fix)
    websocket_api.async_register_command(hass, handle_apply_fix)
    websocket_api.async_register_command(hass, handle_list_backups)
    websocket_api.async_register_command(hass, handle_restore_backup)
    websocket_api.async_register_command(hass, handle_get_translations)
    _LOGGER.info("✅ WebSocket handlers registered")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_data",
        vol.Optional("limit", default=200): int,
        vol.Optional("offset", default=0): int,
        vol.Optional("category"): vol.In([
            "automation", "script", "scene", "blueprint",
            "entity", "performance", "security"
        ]),
    }
)
@websocket_api.async_response
async def handle_get_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get data request with optional pagination."""
    try:
        # Get coordinator data
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        entry = entries[0]
        data = hass.data[DOMAIN].get(entry.entry_id)
        
        if not data:
            connection.send_error(msg["id"], "no_data", "No data available")
            return

        coordinator = data["coordinator"]
        cdata = coordinator.data or {}

        limit  = msg.get("limit", 200)
        offset = msg.get("offset", 0)
        category = msg.get("category")

        def _paginate(lst: list) -> list:
            return lst[offset: offset + limit]

        # If a category filter is requested, only return that list
        category_map = {
            "automation":  "automation_issue_list",
            "script":      "script_issue_list",
            "scene":       "scene_issue_list",
            "blueprint":   "blueprint_issue_list",
            "entity":      "entity_issue_list",
            "performance": "performance_issue_list",
            "security":    "security_issue_list",
        }

        def _get_list(key: str) -> list:
            lst = cdata.get(key, [])
            if category and category_map.get(category) == key:
                return _paginate(lst)
            if not category:
                return _paginate(lst)
            return lst if category_map.get(category) != key else []

        auto_list  = cdata.get("automation_issue_list", [])
        script_list = cdata.get("script_issue_list", [])
        scene_list  = cdata.get("scene_issue_list", [])
        bp_list     = cdata.get("blueprint_issue_list", [])
        ent_list    = cdata.get("entity_issue_list", [])
        perf_list   = cdata.get("performance_issue_list", [])
        sec_list    = cdata.get("security_issue_list", [])

        connection.send_result(
            msg["id"],
            {
                "health_score":         cdata.get("health_score", 0),
                "automation_issues":    cdata.get("automation_issues", 0),
                "script_issues":        cdata.get("script_issues", 0),
                "scene_issues":         cdata.get("scene_issues", 0),
                "blueprint_issues":     cdata.get("blueprint_issues", 0),
                "entity_issues":        cdata.get("entity_issues", 0),
                "performance_issues":   cdata.get("performance_issues", 0),
                "security_issues":      cdata.get("security_issues", 0),
                "total_issues":         cdata.get("total_issues", 0),
                # Paginated lists
                "automation_issue_list":    _paginate(auto_list)   if not category or category == "automation"  else auto_list,
                "script_issue_list":        _paginate(script_list) if not category or category == "script"      else script_list,
                "scene_issue_list":         _paginate(scene_list)  if not category or category == "scene"       else scene_list,
                "blueprint_issue_list":     _paginate(bp_list)     if not category or category == "blueprint"   else bp_list,
                "entity_issue_list":        _paginate(ent_list)    if not category or category == "entity"      else ent_list,
                "performance_issue_list":   _paginate(perf_list)   if not category or category == "performance" else perf_list,
                "security_issue_list":      _paginate(sec_list)    if not category or category == "security"    else sec_list,
                # Pagination metadata
                "pagination": {
                    "limit":  limit,
                    "offset": offset,
                    "category": category,
                    "total_automation":  len(auto_list),
                    "total_script":      len(script_list),
                    "total_scene":       len(scene_list),
                    "total_blueprint":   len(bp_list),
                    "total_entity":      len(ent_list),
                    "total_performance": len(perf_list),
                    "total_security":    len(sec_list),
                },
            },
        )
    except Exception as e:
        _LOGGER.error("Error getting data: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/scan_all",
    }
)
@websocket_api.async_response
async def handle_scan_all(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle scan all request."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        entry = entries[0]
        data = hass.data[DOMAIN].get(entry.entry_id)
        coordinator = data["coordinator"]
        
        # Trigger refresh
        await coordinator.async_refresh()
        
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "message": "Scan completed",
            },
        )
    except Exception as e:
        _LOGGER.error("Error scanning: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/preview_fix",
        vol.Required("automation_id"): str,
        vol.Required("fix_type"): str,
        vol.Optional("mode"): str,
    }
)
@websocket_api.async_response
async def handle_preview_fix(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle preview fix request."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        entry = entries[0]
        data = hass.data[DOMAIN].get(entry.entry_id)
        refactoring = data.get("refactoring_assistant")
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        automation_id = msg["automation_id"]
        fix_type = msg["fix_type"]
        
        if fix_type == "device_id":
            result = await refactoring.preview_device_id_fix(automation_id)
        elif fix_type == "mode":
            mode = msg.get("mode", "restart")
            result = await refactoring.preview_mode_fix(automation_id, mode)
        else:
            connection.send_error(msg["id"], "invalid_type", f"Unknown fix type: {fix_type}")
            return
        
        connection.send_result(msg["id"], result)
        
    except Exception as e:
        _LOGGER.error("Error previewing fix: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/apply_fix",
        vol.Required("automation_id"): str,
        vol.Required("fix_type"): str,
        vol.Optional("mode"): str,
    }
)
@websocket_api.async_response
async def handle_apply_fix(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle apply fix request."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        entry = entries[0]
        data = hass.data[DOMAIN].get(entry.entry_id)
        refactoring = data.get("refactoring_assistant")
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        automation_id = msg["automation_id"]
        fix_type = msg["fix_type"]
        
        if fix_type == "device_id":
            result = await refactoring.apply_device_id_fix(automation_id)
        elif fix_type == "mode":
            mode = msg.get("mode", "restart")
            result = await refactoring.apply_mode_fix(automation_id, mode)
        else:
            connection.send_error(msg["id"], "invalid_type", f"Unknown fix type: {fix_type}")
            return
        
        connection.send_result(msg["id"], result)
        
    except Exception as e:
        _LOGGER.error("Error applying fix: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/list_backups",
    }
)
@websocket_api.async_response
async def handle_list_backups(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle list backups request."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        entry = entries[0]
        data = hass.data[DOMAIN].get(entry.entry_id)
        refactoring = data.get("refactoring_assistant")
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        backups = await refactoring.list_backups()
        
        connection.send_result(
            msg["id"],
            {
                "backups": backups,
                "count": len(backups),
            },
        )
        
    except Exception as e:
        _LOGGER.error("Error listing backups: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/restore_backup",
        vol.Required("backup_path"): str,
    }
)
@websocket_api.async_response
async def handle_restore_backup(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle restore backup request."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        entry = entries[0]
        data = hass.data[DOMAIN].get(entry.entry_id)
        refactoring = data.get("refactoring_assistant")
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        backup_path = msg["backup_path"]
        result = await refactoring.restore_backup(backup_path)
        
        connection.send_result(msg["id"], result)
        
    except Exception as e:
        _LOGGER.error("Error restoring backup: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_translations",
    }
)
@websocket_api.async_response
async def handle_get_translations(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get translations request for the panel."""
    try:
        # Get the current language from Home Assistant
        language = hass.config.language
        
        # Build path to translations file
        integration_path = Path(__file__).parent
        translations_file = integration_path / "translations" / f"{language}.json"
        
        # Fallback to English if the language file doesn't exist
        if not translations_file.exists():
            translations_file = integration_path / "translations" / "en.json"
            _LOGGER.debug("Translation file for %s not found, falling back to English", language)
        
        # Load translations (in executor to avoid blocking the event loop)
        translations = {}
        if translations_file.exists():
            try:
                def _read_translations():
                    with open(translations_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                translations = await hass.async_add_executor_job(_read_translations)
            except Exception as e:
                _LOGGER.error("Error loading translations: %s", e)
        
        # Extract panel translations
        panel_translations = translations.get("panel", {})
        
        connection.send_result(
            msg["id"],
            {
                "language": language,
                "translations": panel_translations,
            },
        )
        
    except Exception as e:
        _LOGGER.error("Error getting translations: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))
