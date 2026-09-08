"""The ``haca_*`` tools -- HACA's own audit surface.

Issues, health score, fix suggestions and their application. These read the
coordinator's last scan rather than Home Assistant directly.
"""
from __future__ import annotations

import hashlib as _hashlib

from homeassistant.core import HomeAssistant

from ..const import DOMAIN
from .common import (
    _async_scan_list_domain,
    _caller_context,
    _get_coordinator_data,
    _LOGGER,
)


# ─── Issue ID system ──────────────────────────────────────────────────────

# Map coordinator list keys → short category codes used in issue IDs
_LIST_KEY_TO_CATEGORY: dict[str, str] = {
    "automation_issue_list": "AUTO",
    "script_issue_list":     "SCRIPT",
    "scene_issue_list":      "SCENE",
    "blueprint_issue_list":  "BP",
    "entity_issue_list":     "ENT",
    "helper_issue_list":     "HELPER",
    "performance_issue_list": "PERF",
    "security_issue_list":   "SEC",
    "dashboard_issue_list":  "DASH",
    "compliance_issue_list": "COMPL",
    "redundancy_issue_list": "REDUND",
}


# Reverse: category code → list key (for filtering)
_CATEGORY_CODE_TO_LIST: dict[str, str] = {v: k for k, v in _LIST_KEY_TO_CATEGORY.items()}


# Also accept full lowercase names from the user / agent
_CATEGORY_NAME_TO_CODE: dict[str, str] = {
    "automation": "AUTO", "script": "SCRIPT", "scene": "SCENE",
    "blueprint": "BP", "entity": "ENT", "helper": "HELPER",
    "performance": "PERF", "security": "SEC", "dashboard": "DASH",
    "compliance": "COMPL", "redundancy": "REDUND",
}


def _issue_stable_id(issue: dict, category_code: str = "") -> str:
    """Generate a human-readable unique ID for an issue.

    Format: HACA-{CATEGORY}-{TYPE}-{HASH6}
    Example: HACA-PERF-MISSING_STATE_CLASS-a3f2c1

    The 6-char hash is derived from the entity_id to guarantee uniqueness
    when multiple entities share the same issue type.
    """
    cat = category_code or issue.get("_category", "UNK")
    itype = (issue.get("type") or "unknown").upper()
    eid = issue.get("entity_id") or issue.get("alias") or "unknown"
    h = _hashlib.md5(eid.encode()).hexdigest()[:6]
    return f"HACA-{cat}-{itype}-{h}"


def _issue_legacy_id(issue: dict) -> str:
    """Legacy format (pre-1.7) for backward compatibility: entity_id|type."""
    eid = issue.get("entity_id", "unknown")
    itype = issue.get("type", "unknown")
    return f"{eid}|{itype}"


def _find_issue_by_id(cdata: dict, issue_id: str) -> dict | None:
    """Find an issue by its stable ID, legacy ID, entity_id, or alias.

    Supports:
    - New format:   HACA-AUTO-NO_ALIAS-a3f2c1
    - Legacy format: automation.xxx|no_alias
    - Raw entity_id: automation.xxx
    - Alias:         'My Automation'
    """
    for lst_key, cat_code in _LIST_KEY_TO_CATEGORY.items():
        for issue in cdata.get(lst_key, []):
            if _issue_stable_id(issue, cat_code) == issue_id:
                return issue
            if _issue_legacy_id(issue) == issue_id:
                return issue
            if issue.get("entity_id") == issue_id:
                return issue
            if issue.get("alias") == issue_id:
                return issue
    return None


def _find_issues_by_filter(
    cdata: dict,
    *,
    category: str | None = None,
    issue_type: str | None = None,
    severity: str | None = None,
) -> list[tuple[dict, str]]:
    """Return all issues matching a combined filter.

    Returns list of (issue_dict, category_code) tuples.
    """
    # Resolve category to list keys
    if category:
        cat_upper = category.upper()
        code = _CATEGORY_NAME_TO_CODE.get(category.lower(), cat_upper)
        lst_key = _CATEGORY_CODE_TO_LIST.get(code)
        if lst_key:
            list_keys = {lst_key: code}
        else:
            return []
    else:
        list_keys = dict(_LIST_KEY_TO_CATEGORY)

    results: list[tuple[dict, str]] = []
    itype_lower = issue_type.lower() if issue_type else None
    sev_lower = severity.lower() if severity else None

    for lst_key, cat_code in list_keys.items():
        for issue in cdata.get(lst_key, []):
            if itype_lower and (issue.get("type", "") or "").lower() != itype_lower:
                continue
            if sev_lower and (issue.get("severity", "") or "").lower() != sev_lower:
                continue
            results.append((issue, cat_code))
    return results


# ─── Tool handlers ────────────────────────────────────────────────────────

async def _tool_get_issues(hass: HomeAssistant, params: dict) -> dict:
    cdata = _get_coordinator_data(hass)
    severity_filter = params.get("severity")
    type_filter = params.get("type")
    category_filter = params.get("category")
    limit = int(params.get("limit", 50))

    # Use the shared filter helper
    matched = _find_issues_by_filter(
        cdata,
        category=category_filter,
        issue_type=type_filter,
        severity=severity_filter,
    )

    # Sort by severity
    sev_order = {"high": 0, "medium": 1, "low": 2}
    matched.sort(key=lambda pair: sev_order.get(pair[0].get("severity", "low"), 2))

    total = len(matched)
    limited = matched[:limit]
    return {
        "total": total,
        "returned": len(limited),
        "issues": [
            {
                "id": _issue_stable_id(issue, cat_code),
                "category": cat_code,
                "severity": issue.get("severity", "low"),
                "type": issue.get("type", ""),
                "entity_id": issue.get("entity_id", issue.get("alias", "")),
                "message": issue.get("message", ""),
                "fixable": issue.get("fix_available", False),
            }
            for issue, cat_code in limited
        ],
    }


async def _tool_get_score(hass: HomeAssistant, params: dict) -> dict:
    cdata = _get_coordinator_data(hass)

    # All issue list keys for severity counting
    _ALL_LISTS = [
        "automation_issue_list", "script_issue_list", "scene_issue_list",
        "blueprint_issue_list", "entity_issue_list", "helper_issue_list",
        "performance_issue_list", "security_issue_list",
        "dashboard_issue_list", "compliance_issue_list",
    ]

    def _count_sev(severity: str) -> int:
        return sum(
            1 for lst_key in _ALL_LISTS
            for i in cdata.get(lst_key, [])
            if i.get("severity") == severity
        )

    return {
        "health_score": cdata.get("health_score", 0),
        "total_issues": cdata.get("total_issues", 0),
        "by_severity": {
            "high": _count_sev("high"),
            "medium": _count_sev("medium"),
            "low": _count_sev("low"),
        },
        "by_category": {
            "automation":  cdata.get("automation_issues", 0),
            "script":      cdata.get("script_issues", 0),
            "scene":       cdata.get("scene_issues", 0),
            "blueprint":   cdata.get("blueprint_issues", 0),
            "entity":      cdata.get("entity_issues", 0),
            "helper":      cdata.get("helper_issues", 0),
            "performance": cdata.get("performance_issues", 0),
            "security":    cdata.get("security_issues", 0),
            "dashboard":   cdata.get("dashboard_issues", 0),
            "compliance":  cdata.get("compliance_issues", 0),
        },
    }


async def _tool_get_automation(hass: HomeAssistant, params: dict) -> dict:
    """Retourne le YAML d'une automation depuis l'état HA."""
    entity_id = params.get("entity_id", "").strip()
    if not entity_id:
        return {"error": "entity_id is required"}

    # Chercher dans les automations HA
    automation_ids = hass.states.async_entity_ids("automation")
    target_id = None

    if entity_id in automation_ids:
        target_id = entity_id
    else:
        # Chercher par alias
        for eid in automation_ids:
            state = hass.states.get(eid)
            if state and state.attributes.get("friendly_name", "").lower() == entity_id.lower():
                target_id = eid
                break

    if not target_id:
        return {"error": f"Automation '{entity_id}' not found"}

    state = hass.states.get(target_id)
    attrs = state.attributes if state else {}

    # Tenter de lire le YAML depuis les fichiers de config
    import yaml

    auto_id = attrs.get("id") or target_id.split(".")[-1]
    yaml_content = None
    source_file = None

    try:
        friendly = attrs.get("friendly_name", "")

        scan = await _async_scan_list_domain(
            hass, "automation", "automations.yaml",
            lambda auto: (
                str(auto.get("id", "")) == str(auto_id)
                or auto.get("alias", "") == friendly
            ),
        )
        if scan.index >= 0:
            yaml_content = yaml.dump(
                scan.documents[scan.index], allow_unicode=True, default_flow_style=False
            )
            source_file = scan.path
    except Exception as exc:
        _LOGGER.debug("[HACA MCP] YAML read error: %s", exc)

    return {
        "entity_id": target_id,
        "alias": attrs.get("friendly_name", target_id),
        "state": state.state if state else "unknown",
        "last_triggered": attrs.get("last_triggered"),
        "source_file": source_file,
        "yaml": yaml_content or (
            f"# YAML not available for {target_id}\n"
            f"# Not found in any file the 'automation:' key resolves to — "
            f"UI-managed or blueprint-based automations have no standalone YAML."
        ),
    }


async def _tool_fix_suggestion(hass: HomeAssistant, params: dict) -> dict:
    issue_id = params.get("issue_id", "")
    if not issue_id:
        return {"error": "issue_id is required"}

    cdata = _get_coordinator_data(hass)
    issue = _find_issue_by_id(cdata, issue_id)
    if not issue:
        return {"error": f"Issue '{issue_id}' not found"}

    if not issue.get("fix_available", False):
        return {
            "issue_id": issue_id,
            "fixable": False,
            "message": "No automatic fix available for this issue.",
            "suggestion": issue.get("recommendation", issue.get("message", "")),
        }

    return {
        "issue_id": issue_id,
        "fixable": True,
        "type": issue.get("type", ""),
        "entity_id": issue.get("entity_id", ""),
        "suggestion": issue.get("recommendation", "Apply the automatic fix"),
        "preview_available": True,
        "note": "Call haca_apply_fix with dry_run=true to see the diff.",
    }


async def _tool_apply_fix(hass: HomeAssistant, params: dict) -> dict:
    issue_id = params.get("issue_id", "")
    dry_run = params.get("dry_run", True)
    if not issue_id:
        return {"error": "issue_id is required"}

    cdata = _get_coordinator_data(hass)
    issue = _find_issue_by_id(cdata, issue_id)
    if not issue:
        return {"error": f"Issue '{issue_id}' not found"}

    if not issue.get("fix_available", False):
        return {"error": "This issue cannot be fixed automatically"}

    if dry_run:
        return {
            "dry_run": True,
            "issue_id": issue_id,
            "entity_id": issue.get("entity_id", ""),
            "fix_type": issue.get("type", ""),
            "message": "Dry run: no files modified. Set dry_run=false to apply.",
            "preview": issue.get("recommendation", ""),
        }

    # Appliquer via le service HA
    try:
        fix_type = issue.get("type", "")
        entity_id = issue.get("entity_id", "")

        if fix_type in ("device_id_in_trigger", "device_id_in_action"):
            service = "fix_device_id"
        elif fix_type == "incorrect_mode_for_pattern":
            service = "fix_mode"
        elif fix_type in ("template_simple_state", "template_numeric_comparison"):
            service = "fix_template"
        else:
            return {"error": f"No fix service for issue type '{fix_type}'"}

        await hass.services.async_call(
            DOMAIN, service, {"entity_id": entity_id}, blocking=True,
            context=_caller_context(),
        )
        return {
            "dry_run": False,
            "issue_id": issue_id,
            "entity_id": entity_id,
            "status": "applied",
            "message": f"Fix applied for {entity_id}",
        }
    except Exception as exc:
        return {"error": f"Error applying fix: {exc}"}


async def _tool_list_issue_catalog(hass: HomeAssistant, params: dict) -> dict:
    """Return the complete HACA issue catalog with live counts."""

    # ── Static catalog: all known issue types ─────────────────────────────
    _CATALOG: dict[str, list[dict]] = {
        "AUTO": [
            {"type": "no_alias",                 "severity": "low",    "fixable": False, "description": "Automation has no alias/friendly name"},
            {"type": "no_description",            "severity": "low",    "fixable": False, "description": "Automation has no description"},
            {"type": "never_triggered",           "severity": "low",    "fixable": False, "description": "Automation was never triggered"},
            {"type": "duplicate_automation",       "severity": "medium", "fixable": False, "description": "Duplicate automation detected"},
            {"type": "probable_duplicate_automation", "severity": "low", "fixable": False, "description": "Probable duplicate automation"},
            {"type": "ghost_automation",           "severity": "medium", "fixable": False, "description": "Automation references non-existent entities"},
            {"type": "incorrect_mode_motion_single", "severity": "medium", "fixable": True, "description": "Motion automation uses mode:single instead of restart"},
            {"type": "high_complexity_actions",    "severity": "low",    "fixable": False, "description": "Automation has high action complexity"},
            {"type": "excessive_delay",            "severity": "low",    "fixable": False, "description": "Automation has excessive delay"},
            {"type": "wait_template_vs_wait_for_trigger", "severity": "low", "fixable": False, "description": "Uses wait_template instead of wait_for_trigger"},
            {"type": "deprecated_service",         "severity": "medium", "fixable": False, "description": "Uses a deprecated service call"},
            {"type": "unknown_service",            "severity": "high",   "fixable": False, "description": "Uses an unknown/invalid service"},
            {"type": "device_id_in_trigger",       "severity": "medium", "fixable": True, "description": "Uses device_id in trigger instead of entity_id"},
            {"type": "device_id_in_action",        "severity": "medium", "fixable": True, "description": "Uses device_id in action instead of entity_id"},
            {"type": "device_id_in_condition",     "severity": "medium", "fixable": False, "description": "Uses device_id in condition"},
            {"type": "device_id_in_target",        "severity": "medium", "fixable": False, "description": "Uses device_id in target"},
            {"type": "device_trigger_platform",    "severity": "low",    "fixable": False, "description": "Uses device trigger platform"},
            {"type": "device_condition_platform",  "severity": "low",    "fixable": False, "description": "Uses device condition platform"},
            {"type": "broken_device_reference",    "severity": "high",   "fixable": False, "description": "References a device that no longer exists"},
        ],
        "SCRIPT": [
            {"type": "empty_script",              "severity": "medium", "fixable": False, "description": "Script has no actions"},
            {"type": "script_orphan",             "severity": "low",    "fixable": False, "description": "Script is not referenced anywhere"},
            {"type": "script_cycle",              "severity": "high",   "fixable": False, "description": "Scripts call each other in a cycle"},
            {"type": "script_call_depth",         "severity": "medium", "fixable": False, "description": "Script call chain is too deep"},
            {"type": "script_single_mode_loop",   "severity": "medium", "fixable": False, "description": "Script in single mode may block itself"},
            {"type": "script_blueprint_candidate", "severity": "low",   "fixable": False, "description": "Similar scripts could be refactored into a blueprint"},
        ],
        "SCENE": [
            {"type": "empty_scene",               "severity": "medium", "fixable": False, "description": "Scene has no entities"},
            {"type": "scene_not_triggered",        "severity": "low",    "fixable": False, "description": "Scene was never activated"},
            {"type": "scene_duplicate",            "severity": "medium", "fixable": False, "description": "Duplicate scene detected"},
            {"type": "scene_entity_unavailable",   "severity": "medium", "fixable": False, "description": "Scene references unavailable entities"},
        ],
        "BP": [
            {"type": "blueprint_missing_path",     "severity": "high",   "fixable": False, "description": "Blueprint path is missing"},
            {"type": "blueprint_file_not_found",   "severity": "high",   "fixable": False, "description": "Blueprint file not found on disk"},
            {"type": "blueprint_no_inputs",        "severity": "medium", "fixable": False, "description": "Blueprint has no inputs defined"},
            {"type": "blueprint_empty_input",      "severity": "medium", "fixable": False, "description": "Blueprint input is empty"},
        ],
        "ENT": [
            {"type": "unavailable_entity",         "severity": "high",   "fixable": False, "description": "Entity is unavailable"},
            {"type": "unknown_state",              "severity": "medium", "fixable": False, "description": "Entity has unknown state and is used by automations/scripts"},
            {"type": "stale_entity",               "severity": "low",    "fixable": False, "description": "Entity has not updated in a long time"},
            {"type": "zombie_entity",              "severity": "medium", "fixable": False, "description": "Entity exists in registry but has no state"},
            {"type": "ghost_registry_entry",       "severity": "medium", "fixable": False, "description": "Registry entry with no matching entity"},
            {"type": "disabled_but_referenced",    "severity": "medium", "fixable": False, "description": "Disabled entity is still referenced"},
        ],
        "HELPER": [
            {"type": "helper_no_friendly_name",    "severity": "low",    "fixable": False, "description": "Helper has no friendly name"},
            {"type": "helper_unused",              "severity": "low",    "fixable": False, "description": "Helper is not used anywhere"},
            {"type": "helper_orphaned_disabled_only", "severity": "low", "fixable": False, "description": "Helper is only used by disabled automations"},
            {"type": "unused_input_boolean",       "severity": "low",    "fixable": False, "description": "Input boolean is not referenced"},
            {"type": "input_number_invalid_range", "severity": "medium", "fixable": False, "description": "Input number has invalid min/max range"},
            {"type": "input_select_duplicate_options", "severity": "low", "fixable": False, "description": "Input select has duplicate options"},
            {"type": "input_select_empty_option",  "severity": "low",    "fixable": False, "description": "Input select has an empty option"},
            {"type": "input_text_invalid_pattern", "severity": "medium", "fixable": False, "description": "Input text has invalid regex pattern"},
            {"type": "timer_orphaned",             "severity": "low",    "fixable": False, "description": "Timer is not referenced"},
            {"type": "timer_never_started",        "severity": "low",    "fixable": False, "description": "Timer was never started"},
            {"type": "timer_zero_duration",        "severity": "medium", "fixable": False, "description": "Timer has zero duration"},
            {"type": "group_empty",                "severity": "medium", "fixable": False, "description": "Group has no members"},
            {"type": "group_missing_entities",     "severity": "medium", "fixable": False, "description": "Group references missing entities"},
            {"type": "group_all_unavailable",      "severity": "high",   "fixable": False, "description": "All entities in group are unavailable"},
            {"type": "group_nested_deep",          "severity": "low",    "fixable": False, "description": "Group nesting is too deep"},
            {"type": "zone_no_entity",             "severity": "low",    "fixable": False, "description": "Zone has no tracked entity"},
        ],
        "PERF": [
            {"type": "potential_self_loop",         "severity": "medium", "fixable": False, "description": "Automation triggers and controls the same entity"},
            {"type": "missing_state_class",         "severity": "low",    "fixable": False, "description": "Template sensor missing state_class for statistics"},
            {"type": "noisy_entity",                "severity": "medium", "fixable": False, "description": "Entity has excessive state changes (>200/day), consider recorder exclusion"},
            {"type": "high_parallel_max",           "severity": "low",    "fixable": False, "description": "Automation has very high parallel max"},
            {"type": "template_sensor_no_metadata", "severity": "low",    "fixable": False, "description": "Template sensor missing device_class/unit_of_measurement"},
            {"type": "template_missing_availability", "severity": "low",  "fixable": False, "description": "Template sensor has no availability check"},
            {"type": "template_no_unavailable_check", "severity": "low",  "fixable": False, "description": "Template uses states() without unavailable guard"},
            {"type": "template_now_without_trigger",  "severity": "low",  "fixable": False, "description": "Template uses now() without time_pattern trigger"},
            {"type": "template_sensor_cycle",       "severity": "high",   "fixable": False, "description": "Template sensors reference each other cyclically"},
            {"type": "template_simple_state",       "severity": "low",    "fixable": True,  "description": "Template can be replaced by a simpler native construct"},
            {"type": "template_numeric_comparison", "severity": "low",    "fixable": True,  "description": "Template numeric comparison can use numeric_state"},
            {"type": "template_time_check",         "severity": "low",    "fixable": False, "description": "Template time check can use time condition"},
            {"type": "expensive_template_selectattr", "severity": "medium", "fixable": False, "description": "Template uses selectattr on all states (expensive)"},
            {"type": "expensive_template_states_all", "severity": "medium", "fixable": False, "description": "Template enumerates all entity states (expensive)"},
        ],
        "SEC": [
            {"type": "hardcoded_secret",           "severity": "high",   "fixable": False, "description": "Hardcoded secret/password in automation config"},
            {"type": "sensitive_data_exposure",     "severity": "high",   "fixable": False, "description": "Sensitive data exposed in automation"},
        ],
        "DASH": [
            {"type": "dashboard_missing_entity",   "severity": "medium", "fixable": False, "description": "Dashboard card references a missing entity"},
        ],
        "COMPL": [
            {"type": "no_description",             "severity": "low",    "fixable": False, "description": "Entity/automation has no description"},
            {"type": "no_alias",                   "severity": "low",    "fixable": False, "description": "Entity has no friendly name"},
            {"type": "unknown_area_reference",     "severity": "medium", "fixable": False, "description": "References an unknown area"},
            {"type": "unknown_floor_reference",    "severity": "medium", "fixable": False, "description": "References an unknown floor"},
            {"type": "unknown_label_reference",    "severity": "medium", "fixable": False, "description": "References an unknown label"},
        ],
        "REDUND": [
            {"type": "redundancy_blueprint_candidate", "severity": "low", "fixable": True, "description": "Automation could be replaced by a standard blueprint (AI can create it)"},
            {"type": "redundancy_native_replacement",  "severity": "low", "fixable": True, "description": "Automation recreates a native HA feature (AI can refactor)"},
            {"type": "redundancy_trigger_overlap",     "severity": "medium", "fixable": False, "description": "Two automations share identical triggers — may conflict"},
        ],
    }

    # ── Live counts from coordinator ──────────────────────────────────────
    cdata = _get_coordinator_data(hass)
    live_counts: dict[str, dict[str, int]] = {}  # cat_code → type → count
    for lst_key, cat_code in _LIST_KEY_TO_CATEGORY.items():
        for issue in cdata.get(lst_key, []):
            itype = issue.get("type", "")
            if itype:
                live_counts.setdefault(cat_code, {})
                live_counts[cat_code][itype] = live_counts[cat_code].get(itype, 0) + 1

    # ── Filter by category if requested ───────────────────────────────────
    cat_filter = params.get("category")
    if cat_filter:
        code = _CATEGORY_NAME_TO_CODE.get(cat_filter.lower(), cat_filter.upper())
        catalog_filtered = {code: _CATALOG.get(code, [])} if code in _CATALOG else {}
    else:
        catalog_filtered = _CATALOG

    # ── Build response ────────────────────────────────────────────────────
    result_categories: list[dict] = []
    for cat_code, type_defs in catalog_filtered.items():
        cat_live = live_counts.get(cat_code, {})
        cat_total = sum(cat_live.values())
        types_out = []
        for td in type_defs:
            count = cat_live.get(td["type"], 0)
            types_out.append({
                "type": td["type"],
                "severity": td["severity"],
                "fixable": td["fixable"],
                "description": td["description"],
                "current_count": count,
            })
        result_categories.append({
            "code": cat_code,
            "name": {v: k for k, v in _CATEGORY_NAME_TO_CODE.items()}.get(cat_code, cat_code.lower()),
            "current_issues": cat_total,
            "issue_types": types_out,
        })

    return {
        "severities": ["high", "medium", "low"],
        "id_format": "HACA-{CATEGORY}-{TYPE}-{HASH6}",
        "id_example": "HACA-AUTO-NO_ALIAS-a3f2c1",
        "categories": result_categories,
    }


async def _tool_fix_batch(hass: HomeAssistant, params: dict) -> dict:
    """Fix one or multiple issues. Supports single ID or filtered batch."""
    issue_id = params.get("issue_id")
    category = params.get("category")
    issue_type = params.get("type")
    severity = params.get("severity")
    dry_run = params.get("dry_run", True)

    cdata = _get_coordinator_data(hass)

    # ── Single issue by ID ────────────────────────────────────────────────
    if issue_id:
        issue = _find_issue_by_id(cdata, issue_id)
        if not issue:
            return {"error": f"Issue '{issue_id}' not found"}
        targets = [(issue, "")]
    # ── Batch by filter ───────────────────────────────────────────────────
    elif category or issue_type or severity:
        targets = _find_issues_by_filter(
            cdata, category=category, issue_type=issue_type, severity=severity,
        )
        if not targets:
            return {"error": "No issues match the given filters", "filters": {
                "category": category, "type": issue_type, "severity": severity,
            }}
    else:
        return {"error": "Provide issue_id for a single fix, or category/type/severity filters for batch fix."}

    # ── Separate fixable from non-fixable ─────────────────────────────────
    fixable = [(i, c) for i, c in targets if i.get("fix_available", False)]
    not_fixable = [(i, c) for i, c in targets if not i.get("fix_available", False)]

    # ── Map fix_type → HA service ─────────────────────────────────────────
    _FIX_SERVICE_MAP = {
        "device_id_in_trigger": "fix_device_id",
        "device_id_in_action": "fix_device_id",
        "incorrect_mode_for_pattern": "fix_mode",
        "incorrect_mode_motion_single": "fix_mode",
        "template_simple_state": "fix_template",
        "template_numeric_comparison": "fix_template",
    }

    if dry_run:
        # ── Preview mode ──────────────────────────────────────────────────
        preview = []
        for issue, cat_code in fixable:
            preview.append({
                "id": _issue_stable_id(issue, cat_code),
                "entity_id": issue.get("entity_id", ""),
                "type": issue.get("type", ""),
                "fix_service": _FIX_SERVICE_MAP.get(issue.get("type", ""), "unknown"),
                "recommendation": issue.get("recommendation", ""),
            })
        return {
            "dry_run": True,
            "total_matched": len(targets),
            "fixable": len(fixable),
            "not_fixable": len(not_fixable),
            "preview": preview,
            "not_fixable_types": list({i.get("type", "") for i, _ in not_fixable}),
            "message": (
                f"{len(fixable)} issue(s) can be auto-fixed. "
                f"{len(not_fixable)} issue(s) require manual intervention. "
                "Set dry_run=false to apply fixes."
            ),
        }

    # ── Apply mode ────────────────────────────────────────────────────────
    applied = []
    errors = []
    for issue, cat_code in fixable:
        fix_type = issue.get("type", "")
        entity_id = issue.get("entity_id", "")
        service = _FIX_SERVICE_MAP.get(fix_type)
        if not service:
            errors.append({"entity_id": entity_id, "type": fix_type, "error": f"No fix service for '{fix_type}'"})
            continue
        try:
            await hass.services.async_call(
                DOMAIN, service, {"entity_id": entity_id}, blocking=True,
                context=_caller_context(),
            )
            applied.append({
                "id": _issue_stable_id(issue, cat_code),
                "entity_id": entity_id,
                "type": fix_type,
                "status": "applied",
            })
        except Exception as exc:
            errors.append({"entity_id": entity_id, "type": fix_type, "error": str(exc)})

    return {
        "dry_run": False,
        "total_matched": len(targets),
        "applied": len(applied),
        "errors": len(errors),
        "not_fixable": len(not_fixable),
        "results": applied,
        "error_details": errors if errors else None,
        "not_fixable_types": list({i.get("type", "") for i, _ in not_fixable}) if not_fixable else None,
    }


async def _tool_get_batteries(hass: HomeAssistant, params: dict) -> dict:
    cdata = _get_coordinator_data(hass)
    min_level = params.get("min_level")
    batteries = cdata.get("battery_list", [])

    if min_level is not None:
        batteries = [b for b in batteries if b.get("level", 100) <= int(min_level)]

    return {
        "total": len(batteries),
        "batteries": [
            {
                "entity_id": b.get("entity_id", ""),
                "friendly_name": b.get("friendly_name", ""),
                "level": b.get("level"),
                "status": b.get("status", "ok"),
                "last_updated": b.get("last_updated"),
            }
            for b in batteries
        ],
    }


async def _tool_explain_issue(hass: HomeAssistant, params: dict) -> dict:
    issue_id = params.get("issue_id", "")
    if not issue_id:
        return {"error": "issue_id is required"}

    cdata = _get_coordinator_data(hass)
    issue = _find_issue_by_id(cdata, issue_id)
    if not issue:
        return {"error": f"Issue '{issue_id}' not found"}

    # Utiliser le cache AI si disponible
    from .conversation import _async_call_ai, _AI_CACHE_KEY
    cache = hass.data.get(DOMAIN, {}).get(_AI_CACHE_KEY, {})
    cache_key = f"explain_{issue_id}"

    if cache_key in cache:
        return {"explanation": cache[cache_key], "cached": True}

    # The prompt is what the model answers in, so it follows the notification
    # language like every other AI prompt (see conversation.explain_issue_ai).
    from .translation_utils import resolve_notification_language
    _lang = resolve_notification_language(hass)
    try:
        from . import _TS_CACHE  # noqa: PLC0415
        _ap = (_TS_CACHE.get(_lang) or _TS_CACHE.get("en") or {}).get("ai_prompts", {})
    except Exception:
        _ap = {}
    prompt = _ap.get(
        "mcp_explain_issue",
        "[H.A.C.A Audit] Issue detected in the Home Assistant configuration.\n"
        "Type: {type}\nSeverity: {severity}\nEntity: {entity}\n"
        "Message: {message}\n\n"
        "Explain this issue in 2-3 clear sentences and propose a concrete fix.",
    ).format(
        type=issue.get("type", ""),
        severity=issue.get("severity", ""),
        entity=issue.get("entity_id", issue.get("alias", "")),
        message=issue.get("message", ""),
    )

    explanation = await _async_call_ai(hass, prompt, "HACA MCP Explain")

    if explanation:
        # Mettre en cache
        if DOMAIN in hass.data:
            entries = hass.config_entries.async_entries(DOMAIN)
            if entries:
                entry_data = hass.data[DOMAIN].get(entries[0].entry_id, {})
                ai_cache = entry_data.get(_AI_CACHE_KEY, {})
                ai_cache[cache_key] = explanation
                entry_data[_AI_CACHE_KEY] = ai_cache

    return {
        "issue_id": issue_id,
        "entity_id": issue.get("entity_id", ""),
        "explanation": explanation or _ap.get(
            "mcp_no_ai_available", "No AI service available."
        ),
        "cached": False,
    }
