"""The assembled tool registry.

``MCP_TOOLS`` is what ``tools/list`` serves, ``TOOL_HANDLERS`` is what
``tools/call`` dispatches through, and every declaration is stamped with its
read / write class here so the two can never disagree. Both names are
re-exported from the package root, which is where ``llm_api`` reads them.

Splitting the server across modules made this file necessary: it is the only
one that knows about every handler, which keeps ``views`` from having to.
"""
from __future__ import annotations

from typing import Any

from .schemas import (
    HA_CONTROL_TOOLS,
    HA_EXTENDED_TOOLS,
    HA_LOW_TOOLS,
    HA_MEDIUM_TOOLS,
    HACA_TOOLS,
    NEW_TOOLS_V151,
    tool_access,
)
from .tools_audit import (
    _tool_apply_fix,
    _tool_explain_issue,
    _tool_fix_batch,
    _tool_fix_suggestion,
    _tool_get_automation,
    _tool_get_batteries,
    _tool_get_issues,
    _tool_get_score,
    _tool_list_issue_catalog,
)
from .tools_automation import (
    _tool_ha_create_automation,
    _tool_ha_get_automation_traces,
    _tool_ha_remove_automation,
    _tool_ha_update_automation,
)
from .tools_blueprint import (
    _tool_ha_create_blueprint,
    _tool_ha_get_blueprint,
    _tool_ha_import_blueprint,
    _tool_ha_list_blueprints,
    _tool_ha_remove_blueprint,
    _tool_ha_update_blueprint,
)
from .tools_history import _tool_ha_get_history, _tool_ha_get_logbook, _tool_ha_get_statistics
from .tools_lovelace import (
    _tool_ha_add_lovelace_card,
    _tool_ha_get_lovelace,
    _tool_ha_list_dashboards,
    _tool_ha_remove_lovelace_card,
    _tool_ha_update_lovelace_card,
)
from .tools_registry import (
    _tool_ha_config_list_helpers,
    _tool_ha_config_remove_helper,
    _tool_ha_config_set_area,
    _tool_ha_config_set_helper,
    _tool_ha_create_label,
    _tool_ha_enable_entity,
    _tool_ha_get_entities,
    _tool_ha_get_entity_detail,
    _tool_ha_get_helper,
    _tool_ha_list_labels,
    _tool_ha_manage_entity_labels,
    _tool_ha_remove_entity,
    _tool_ha_rename_entity,
    _tool_ha_update_helper,
)
from .tools_script_scene import (
    _tool_ha_create_scene,
    _tool_ha_create_script,
    _tool_ha_get_scene,
    _tool_ha_get_script,
    _tool_ha_remove_scene,
    _tool_ha_remove_script,
    _tool_ha_update_scene,
    _tool_ha_update_script,
)
from .tools_system import (
    _tool_ha_backup_create,
    _tool_ha_call_service,
    _tool_ha_check_config,
    _tool_ha_deep_search,
    _tool_ha_eval_template,
    _tool_ha_get_config_file,
    _tool_ha_get_system_health,
    _tool_ha_get_updates,
    _tool_ha_list_services,
    _tool_ha_reload_core,
    _tool_ha_update_config_file,
)

# The waves are concatenated in declaration order — that is the order a client
# sees in the handshake, and reordering it would change what every agent reads.
MCP_TOOLS: list[dict[str, Any]] = [
    *HACA_TOOLS,
    *HA_CONTROL_TOOLS,
    *HA_EXTENDED_TOOLS,
    *HA_MEDIUM_TOOLS,
    *HA_LOW_TOOLS,
    *NEW_TOOLS_V151,
]

TOOL_HANDLERS = {
    # ── HACA audit tools ─────────────────────────────────────────────────
    "haca_get_issues":        _tool_get_issues,
    "haca_get_score":         _tool_get_score,
    "haca_get_automation":    _tool_get_automation,
    "haca_fix_suggestion":    _tool_fix_suggestion,
    "haca_apply_fix":         _tool_apply_fix,
    "haca_get_batteries":     _tool_get_batteries,
    "haca_explain_issue":     _tool_explain_issue,
    "haca_list_issue_catalog": _tool_list_issue_catalog,
    "haca_fix_batch":         _tool_fix_batch,
    # ── HA control tools — v1.4 ──────────────────────────────────────────
    "ha_get_entities":          _tool_ha_get_entities,
    "ha_call_service":          _tool_ha_call_service,
    "ha_create_automation":     _tool_ha_create_automation,
    "ha_update_automation":     _tool_ha_update_automation,
    "ha_get_automation_traces": _tool_ha_get_automation_traces,
    "ha_get_lovelace":          _tool_ha_get_lovelace,
    "ha_add_lovelace_card":     _tool_ha_add_lovelace_card,
    "ha_create_script":         _tool_ha_create_script,

    # ── v1.5.0 ───────────────────────────────────────────────────────────
    "ha_backup_create": _tool_ha_backup_create,
    "ha_check_config": _tool_ha_check_config,
    "ha_remove_automation": _tool_ha_remove_automation,
    "ha_eval_template": _tool_ha_eval_template,
    "ha_rename_entity": _tool_ha_rename_entity,

    # ── v1.5.1 — medium priority ─────────────────────────────────────────
    "ha_get_history": _tool_ha_get_history,
    "ha_get_statistics": _tool_ha_get_statistics,
    "ha_deep_search": _tool_ha_deep_search,
    "ha_get_logbook": _tool_ha_get_logbook,
    "ha_config_list_helpers": _tool_ha_config_list_helpers,
    "ha_config_set_helper": _tool_ha_config_set_helper,
    "ha_config_remove_helper": _tool_ha_config_remove_helper,

    # ── v1.5.0 — low priority ────────────────────────────────────────────
    "ha_get_system_health": _tool_ha_get_system_health,
    "ha_get_updates": _tool_ha_get_updates,
    "ha_reload_core": _tool_ha_reload_core,
    "ha_list_services": _tool_ha_list_services,
    "ha_config_set_area": _tool_ha_config_set_area,
    "ha_manage_entity_labels": _tool_ha_manage_entity_labels,
    "ha_create_blueprint": _tool_ha_create_blueprint,

    # ── v1.5.1 — scripts, scenes, blueprints, dashboards, helpers ────────
    # Scripts
    "ha_get_script":             _tool_ha_get_script,
    "ha_update_script":          _tool_ha_update_script,
    "ha_remove_script":          _tool_ha_remove_script,
    # Scenes
    "ha_get_scene":              _tool_ha_get_scene,
    "ha_create_scene":           _tool_ha_create_scene,
    "ha_update_scene":           _tool_ha_update_scene,
    "ha_remove_scene":           _tool_ha_remove_scene,
    # Blueprints
    "ha_list_blueprints":        _tool_ha_list_blueprints,
    "ha_get_blueprint":          _tool_ha_get_blueprint,
    "ha_update_blueprint":       _tool_ha_update_blueprint,
    "ha_remove_blueprint":       _tool_ha_remove_blueprint,
    "ha_import_blueprint":       _tool_ha_import_blueprint,
    # Dashboards
    "ha_list_dashboards":        _tool_ha_list_dashboards,
    "ha_update_lovelace_card":   _tool_ha_update_lovelace_card,
    "ha_remove_lovelace_card":   _tool_ha_remove_lovelace_card,
    # Helpers
    "ha_get_helper":             _tool_ha_get_helper,
    "ha_update_helper":          _tool_ha_update_helper,
    # Entities
    "ha_get_entity_detail":      _tool_ha_get_entity_detail,
    "ha_remove_entity":          _tool_ha_remove_entity,
    "ha_enable_entity":          _tool_ha_enable_entity,
    # Config files
    "ha_get_config_file":        _tool_ha_get_config_file,
    "ha_update_config_file":     _tool_ha_update_config_file,
    # Labels
    "ha_list_labels":            _tool_ha_list_labels,
    "ha_create_label":           _tool_ha_create_label,

    # ── ha_* aliases for the haca_* audit tools ──────────────────────────
    "ha_get_automation":  _tool_get_automation,
    "ha_get_issues":      _tool_get_issues,
    "ha_get_score":       _tool_get_score,
    "ha_fix_suggestion":  _tool_fix_suggestion,
    "ha_apply_fix":       _tool_apply_fix,
    "ha_get_batteries":   _tool_get_batteries,
    "ha_explain_issue":   _tool_explain_issue,
    "ha_list_issue_catalog": _tool_list_issue_catalog,
    "ha_fix_batch":       _tool_fix_batch,
}

for _tool_def in MCP_TOOLS:
    _tool_def["access"] = tool_access(_tool_def["name"])
del _tool_def
