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
    }
)
@websocket_api.async_response
async def handle_get_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get data request."""
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
        
        connection.send_result(
            msg["id"],
            {
                "health_score": coordinator.data.get("health_score", 0),
                "automation_issues": coordinator.data.get("automation_issues", 0),
                "script_issues": coordinator.data.get("script_issues", 0),
                "scene_issues": coordinator.data.get("scene_issues", 0),
                "entity_issues": coordinator.data.get("entity_issues", 0),
                "performance_issues": coordinator.data.get("performance_issues", 0),
                "security_issues": coordinator.data.get("security_issues", 0),
                "total_issues": coordinator.data.get("total_issues", 0),
                "automation_issue_list": coordinator.data.get("automation_issue_list", []),
                "script_issue_list": coordinator.data.get("script_issue_list", []),
                "scene_issue_list": coordinator.data.get("scene_issue_list", []),
                "entity_issue_list": coordinator.data.get("entity_issue_list", []),
                "performance_issue_list": coordinator.data.get("performance_issue_list", []),
                "security_issue_list": coordinator.data.get("security_issue_list", []),
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
