"""The MCP tool declarations, in the order the handshake serves them.

Pure data: the JSON Schema each tool advertises through ``tools/list``, kept in
the release waves it grew in, plus the read / write classification the LLM API
applies on top. :mod:`.catalog` concatenates the waves into ``MCP_TOOLS`` --
the order here is the order on the wire.
"""
from __future__ import annotations

from typing import Any


# ─── Tool definitions (schéma JSON Schema) ────────────────────────────────

HACA_TOOLS: list[dict[str, Any]] = [
    {
        "name": "haca_get_issues",
        "description": "Get all HACA audit issues (automation, entity, security, performance). Filter by severity or category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Filter by severity (optional)",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by issue type (optional), e.g. 'zombie_entity'",
                },
                "category": {
                    "type": "string",
                    "enum": ["automation", "script", "scene", "blueprint", "entity",
                             "helper", "performance", "security", "dashboard", "compliance",
                             "redundancy"],
                    "description": "Filter by category (optional)",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of issues to return",
                },
            },
        },
    },
    {
        "name": "haca_get_score",
        "description": "Get the HACA health score (0-100) with breakdown by category.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "haca_get_automation",
        "description": "Read the full YAML config of a specific automation. Use BEFORE ha_update_automation. Accepts entity_id.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "entity_id or alias of the automation, e.g. 'automation.living_room_lights'",
                },
            },
        },
    },
    {
        "name": "haca_fix_suggestion",
        "description": (
            "Return a proposed fix for a given issue without applying it. "
            "Includes the previewed diff."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["issue_id"],
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Unique issue id (the 'id' field returned by haca_get_issues)",
                },
            },
        },
    },
    {
        "name": "haca_apply_fix",
        "description": (
            "Apply a fix to an issue. Supports dry_run mode to preview the "
            "change without touching any file."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["issue_id"],
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Unique issue id",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), simulate without writing. Set false to apply.",
                },
            },
        },
    },
    {
        "name": "haca_get_batteries",
        "description": (
            "Return the state of every battery detected in HA: level, status "
            "(critical/low/warning/ok) and last update."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_level": {
                    "type": "integer",
                    "description": "Only return batteries below this level (%)",
                },
            },
        },
    },
    {
        "name": "haca_explain_issue",
        "description": "Get an AI-generated explanation of a specific HACA issue. Provide the full issue object from haca_get_issues.",
        "inputSchema": {
            "type": "object",
            "required": ["issue_id"],
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Unique id of the issue to explain",
                },
            },
        },
    },
    {
        "name": "haca_list_issue_catalog",
        "description": (
            "Returns the complete HACA issue catalog: all categories (with short codes), "
            "all issue types per category, severity levels, and whether each type is auto-fixable. "
            "Use this to discover what the user can ask you to fix."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter catalog by category name or code (optional). E.g. 'automation' or 'AUTO'.",
                },
            },
        },
    },
    {
        "name": "haca_fix_batch",
        "description": (
            "Fix one or multiple HACA issues in batch. "
            "Filter by issue_id (single fix), or combine category + type + severity for bulk fixes. "
            "By default dry_run=true: preview changes without applying. "
            "Set dry_run=false to apply. "
            "Examples: "
            "fix_batch(issue_id='HACA-AUTO-NO_ALIAS-a3f2c1') → fix one issue. "
            "fix_batch(category='compliance', type='no_description', severity='low') → fix all matching. "
            "fix_batch(type='device_id_in_trigger') → fix all device_id triggers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_id": {
                    "type": "string",
                    "description": "Single issue ID to fix (HACA-XXX-YYY-zzz format, or legacy entity|type format)",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g. 'automation', 'compliance', 'performance')",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by issue type (e.g. 'no_description', 'device_id_in_trigger')",
                },
                "severity": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Filter by severity level",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), preview without applying. Set false to apply fixes.",
                },
            },
        },
    },
]


# ─── Outils HA Control (nouveaux en v1.4.1) ───────────────────────────────

HA_CONTROL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ha_get_entities",
        "description": "List HA entities by domain. Use domain for efficiency: automation, light, sensor, climate, weather, etc. Use to discover entities before creating cards/automations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string",
                           "description": "Filter by domain, e.g. 'light', 'automation', 'sensor'"},
                "area": {"type": "string",
                         "description": "Filter by area name (partial match), e.g. 'salon', 'chambre'"},
                "search": {"type": "string",
                           "description": "Search in entity_id or friendly_name (partial match)"},
                "limit": {"type": "integer", "default": 50,
                          "description": "Maximum entities to return (default 50)"},
            },
        },
    },
    {
        "name": "ha_call_service",
        "description": (
            "Call any Home Assistant service. This is the universal action tool. "
            "Examples: turn on a light, trigger an automation, set a thermostat. "
            "Use ha_get_entities first to find valid entity_ids. "
            "Common services: light.turn_on, switch.toggle, automation.trigger, "
            "climate.set_temperature, media_player.play_media, script.turn_on. "
            "Response-returning services (weather.get_forecasts, calendar.get_events, "
            "todo.get_items, conversation.process, …) work too: their payload comes "
            "back in a 'response' field."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["domain", "service"],
            "properties": {
                "domain": {"type": "string",
                           "description": "Service domain, e.g. 'light', 'switch', 'automation'"},
                "service": {"type": "string",
                            "description": "Service name, e.g. 'turn_on', 'turn_off', 'toggle'"},
                "data": {"type": "object",
                         "description": "Service call data, e.g. {\"entity_id\": \"light.salon\", \"brightness\": 200}"},
            },
        },
    },
    {
        "name": "ha_create_automation",
        "description": "Create a new HA automation. Config must include: alias, triggers, actions. Call ha_reload_core after. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
        "inputSchema": {
            "type": "object",
            "required": ["alias"],
            "properties": {
                "alias": {"type": "string",
                          "description": "Human-readable name for the automation"},
                "description": {"type": "string",
                                "description": "What the automation does (recommended)"},
                "triggers": {
                    "description": "Trigger(s) — preferred key (HA new format). Array of trigger objects or single trigger.",
                    "oneOf": [{"type": "array"}, {"type": "object"}],
                },
                "trigger": {
                    "description": "Trigger(s) — legacy key (also accepted). Use 'triggers' when possible.",
                    "oneOf": [{"type": "array"}, {"type": "object"}],
                },
                "conditions": {
                    "description": "Optional condition(s) — preferred key (HA new format). Array or single.",
                    "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}],
                },
                "condition": {
                    "description": "Optional condition(s) — legacy key (also accepted).",
                    "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}],
                },
                "actions": {
                    "description": "Action(s) to execute — preferred key (HA new format). Array or single.",
                    "oneOf": [{"type": "array"}, {"type": "object"}],
                },
                "action": {
                    "description": "Action(s) to execute — legacy key (also accepted).",
                    "oneOf": [{"type": "array"}, {"type": "object"}],
                },
                "mode": {"type": "string", "enum": ["single", "parallel", "queued", "restart"],
                         "default": "single"},
            },
        },
    },
    {
        "name": "ha_update_automation",
        "description": "Update an existing automation. ALWAYS call haca_get_automation first to read current config. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {"type": "string",
                              "description": "entity_id or alias of the automation to update"},
                "alias": {"type": "string", "description": "New alias (optional)"},
                "description": {"type": "string", "description": "New description (optional)"},
                "triggers": {"description": "Replace triggers — preferred key (HA new format)",
                             "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "trigger": {"description": "Replace triggers — legacy key (also accepted)",
                            "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "conditions": {"description": "Replace conditions — preferred key (HA new format)",
                               "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "condition": {"description": "Replace conditions — legacy key (also accepted)",
                              "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "actions": {"description": "Replace actions — preferred key (HA new format)",
                            "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "action": {"description": "Replace actions — legacy key (also accepted)",
                           "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "append_action": {"description": "Append action(s) to existing list (optional)",
                                  "oneOf": [{"type": "array"}, {"type": "object"}, {"type": "null"}]},
                "mode": {"type": "string", "enum": ["single", "parallel", "queued", "restart"]},
            },
        },
    },
    {
        "name": "ha_get_automation_traces",
        "description": (
            "Get execution traces for an automation to debug why it's not working. "
            "Returns: last trigger timestamp, trigger type, conditions met/rejected, "
            "actions executed, errors encountered. Essential for debugging."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {"type": "string",
                              "description": "entity_id of the automation, e.g. 'automation.morning_routine'"},
                "limit": {"type": "integer", "default": 5,
                          "description": "Number of recent traces to return"},
            },
        },
    },
    {
        "name": "ha_get_lovelace",
        "description": (
            "Read a Lovelace dashboard structure: views count, card types, titles. "
            "ALWAYS call this BEFORE ha_add_lovelace_card, ha_update_lovelace_card, "
            "or ha_remove_lovelace_card to know the views and card indices. "
            "Use ha_list_dashboards first if you don't know the dashboard_id."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string",
                                 "description": "Dashboard URL path (e.g. 'lovelace', 'cameras'). "
                                                "Omit for the default dashboard."},
            },
        },
    },
    {
        "name": "ha_add_lovelace_card",
        "description": (
            "Add a new card to a Lovelace dashboard view. "
            "IMPORTANT: Always call ha_get_lovelace first to know the view count. "
            "If the dashboard has only 1 view, use view_index=0 without asking the user. "
            "Common card types (always use English type names): "
            "weather-forecast, entities, button, light, thermostat, media-control, "
            "glance, gauge, history-graph, logbook, map, markdown, picture-entity, "
            "sensor, statistics-graph, todo-list, area, tile, mushroom-entity-card. "
            "Example: {\"type\": \"weather-forecast\", \"entity\": \"weather.home\", \"show_forecast\": true}. "
            "The dashboard must be in 'storage' mode."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["card"],
            "properties": {
                "dashboard_id": {"type": "string",
                                 "description": "Dashboard URL path (default: 'lovelace')"},
                "view_index": {"type": "integer", "default": 0,
                               "description": "View index (0 = first view). If dashboard has only 1 view, always use 0."},
                "card": {"type": "object",
                         "description": "Card config object. MUST have a 'type' field (English). Example: {\"type\": \"weather-forecast\", \"entity\": \"weather.home\"}"},
            },
        },
    },
    {
        "name": "ha_create_script",
        "description": "Create or update a script, in whichever file the config `script:` key resolves to. Provide: alias, sequence. Call ha_reload_core after. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
        "inputSchema": {
            "type": "object",
            "required": ["script_id", "alias", "sequence"],
            "properties": {
                "script_id": {"type": "string",
                              "description": "Unique script identifier (no spaces), e.g. 'movie_mode'"},
                "alias": {"type": "string",
                          "description": "Human-readable script name"},
                "description": {"type": "string",
                                "description": "What the script does"},
                "sequence": {"type": "array",
                             "description": "List of actions to execute, same format as automation actions"},
                "mode": {"type": "string", "enum": ["single", "parallel", "queued", "restart"],
                         "default": "single"},
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
#  v1.5.0 — 5 NEW TOOLS: backup_create · check_config · remove_automation
#                         eval_template · rename_entity
# ═══════════════════════════════════════════════════════════════════════════════

# ── Tool definitions ────────────────────────────────────────────────────────

HA_EXTENDED_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ha_backup_create",
        "description": "Start a full Home Assistant backup: configuration and database, plus add-ons and folders on a Supervisor install. Use it when the user asks for one, or before a large change across many files — not before each edit: the automation, script, scene, blueprint and config-file tools already copy the file they change into /config/.haca_backups/ and return that copy's path as 'backup'. Returns as soon as the backup is STARTED (started: true, completed: false) — never report the backup as finished, tell the user to check Settings → System → Backups.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Backup name, e.g. 'pre-haca-refactor-2025-01-15'. "
                                   "Defaults to 'HACA backup <datetime>'.",
                },
            },
        },
    },
    {
        "name": "ha_check_config",
        "description": "Validate HA configuration files. Use before ha_reload_core to check for errors.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ha_remove_automation",
        "description": (
            "Permanently delete an automation from the file that holds it. "
            "The automation is reloaded immediately after deletion. "
            "Use haca_get_automation to inspect the automation before deleting. "
            "The file is copied into /config/.haca_backups/ before it changes; "
            "the copy's path comes back as 'backup'."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "entity_id or alias of the automation to delete, "
                                   "e.g. 'automation.morning_routine' or 'Morning routine'.",
                },
            },
        },
    },
    {
        "name": "ha_eval_template",
        "description": (
            "Evaluate a Jinja2 template against the live Home Assistant state and return its rendered value. "
            "Use this to test templates before writing them into automations or scripts. "
            "Examples: '{{ states(\"sensor.temperature\") }}', "
            "'{{ now().hour >= 22 or now().hour < 7 }}'. "
            "Returns the rendered string and whether it raised an error."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["template"],
            "properties": {
                "template": {
                    "type": "string",
                    "description": "Jinja2 template string to evaluate, e.g. '{{ states(\"light.salon\") }}'",
                },
            },
        },
    },
    {
        "name": "ha_rename_entity",
        "description": "Change an entity_id. WARNING: may break automations/dashboards referencing the old ID.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Current entity_id, e.g. 'light.salon_plafonnier'",
                },
                "new_name": {
                    "type": "string",
                    "description": "New friendly name, e.g. 'Salon — Plafonnier'",
                },
                "new_entity_id": {
                    "type": "string",
                    "description": "New entity_id slug (optional, risky — may break automations)",
                },
                "icon": {
                    "type": "string",
                    "description": "MDI icon, e.g. 'mdi:ceiling-light'",
                },
                "area_id": {
                    "type": "string",
                    "description": "Area ID to assign to this entity. "
                                   "Use ha_get_entities to find valid area_ids.",
                },
            },
        },
    },
    {
        "name": "ha_create_blueprint",
        "description": (
            "Convert an existing Home Assistant automation into a reusable Blueprint YAML file "
            "and save it to /config/blueprints/automation/haca/<slug>.yaml. "
            "Reads the actual automation YAML, extracts entity references as blueprint inputs, "
            "then writes a fully valid blueprint file and reloads blueprints. "
            "IMPORTANT: This tool does NOT modify or delete the original automation. "
            "A blueprint of the same name is overwritten, after a copy into /config/.haca_backups/ "
            "whose path comes back as 'backup'. "
            "Call this tool directly with the automation entity_id."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["automation_entity_id"],
            "properties": {
                "automation_entity_id": {
                    "type": "string",
                    "description": (
                        "entity_id or alias of the automation to convert, "
                        "e.g. 'automation.evening_lights' or 'Evening lights'."
                    ),
                },
                "blueprint_name": {
                    "type": "string",
                    "description": (
                        "Display name for the blueprint. "
                        "Defaults to the automation alias."
                    ),
                },
                "blueprint_description": {
                    "type": "string",
                    "description": (
                        "Description of what this blueprint does and when to use it. "
                        "Will appear in the HA blueprint import UI."
                    ),
                },
                "inputs": {
                    "type": "object",
                    "description": (
                        "Optional: map of blueprint input variables to define. "
                        "Keys are input names (slugs), values are objects with "
                        "{name, description, selector, default?}. "
                        "Example: {\"target_light\": {\"name\": \"Light\", \"selector\": {\"entity\": {\"domain\": \"light\"}}}}. "
                        "If omitted, HACA auto-extracts entity_id inputs from the automation."
                    ),
                },
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
#  v1.5.1 — 7 MEDIUM PRIORITY TOOLS
#  ha_get_history · ha_get_statistics · ha_deep_search · ha_get_logbook
#  ha_config_list_helpers · ha_config_set_helper · ha_config_remove_helper
# ═══════════════════════════════════════════════════════════════════════════════

HA_MEDIUM_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ha_get_history",
        "description": "Retrieve state history of entities over a time period. Defaults to last 24h. Useful for debugging.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_ids"],
            "properties": {
                "entity_ids": {
                    "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
                    "description": "One entity_id or list of entity_ids, e.g. 'sensor.temperature' or ['light.salon', 'switch.tv']",
                },
                "start": {
                    "type": "string",
                    "description": "ISO 8601 start datetime, e.g. '2025-01-15T00:00:00'. Defaults to 24h ago.",
                },
                "end": {
                    "type": "string",
                    "description": "ISO 8601 end datetime. Defaults to now.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max state changes to return per entity (default 50).",
                },
            },
        },
    },
    {
        "name": "ha_get_statistics",
        "description": (
            "Retrieve long-term statistics for sensor entities (min, max, mean, sum per hour/day). "
            "Works for entities with statistics enabled in the recorder. "
            "Ideal for energy consumption analysis, temperature trends, and recorder impact audits. "
            "Returns aggregated data — not raw state changes."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["statistic_ids"],
            "properties": {
                "statistic_ids": {
                    "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
                    "description": "One or more statistic IDs (usually same as entity_id for sensors).",
                },
                "period": {
                    "type": "string",
                    "enum": ["5minute", "hour", "day", "week", "month"],
                    "default": "hour",
                    "description": "Aggregation period.",
                },
                "start": {
                    "type": "string",
                    "description": "ISO 8601 start datetime. Defaults to 7 days ago.",
                },
                "end": {
                    "type": "string",
                    "description": "ISO 8601 end datetime. Defaults to now.",
                },
            },
        },
    },
    {
        "name": "ha_deep_search",
        "description": "Search across all HA entities, automations, scripts, scenes for a keyword. Use when user mentions something by name.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for inside YAML content, e.g. 'light.entree', 'automation.trigger', 'notify.mobile_app'",
                },
                "scope": {
                    "type": "string",
                    "enum": ["automations", "scripts", "all"],
                    "default": "all",
                    "description": "Which files to search.",
                },
            },
        },
    },
    {
        "name": "ha_get_logbook",
        "description": (
            "Retrieve the Home Assistant logbook — chronological log of state changes, "
            "service calls, and automation triggers. "
            "Complements ha_get_automation_traces: use logbook to understand the sequence of events "
            "that led to (or prevented) an automation from firing. "
            "Defaults to the last 24 hours."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Filter by entity_id (optional). Omit to get all logbook entries.",
                },
                "start": {
                    "type": "string",
                    "description": "ISO 8601 start datetime. Defaults to 24h ago.",
                },
                "end": {
                    "type": "string",
                    "description": "ISO 8601 end datetime. Defaults to now.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max entries to return (default 50).",
                },
            },
        },
    },
    {
        "name": "ha_config_list_helpers",
        "description": (
            "List all helper entities in Home Assistant: input_boolean, input_number, input_text, "
            "input_select, input_datetime, counter, timer, schedule. "
            "Returns current state, attributes, and whether each helper is referenced in any automation. "
            "Use this to find orphan helpers (helpers unused by any automation or script)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "helper_type": {
                    "type": "string",
                    "enum": [
                        "input_boolean", "input_number", "input_text",
                        "input_select", "input_datetime", "counter", "timer", "schedule", "all"
                    ],
                    "default": "all",
                    "description": "Filter by helper type. Default: return all helper types.",
                },
                "include_orphans_check": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, check each helper against every automation and script YAML file to flag orphans.",
                },
            },
        },
    },
    {
        "name": "ha_config_set_helper",
        "description": "Create or update a helper (input_boolean, input_number, input_text, input_select, etc.). Provide: helper_type, name, options.",
        "inputSchema": {
            "type": "object",
            "required": ["helper_type", "name"],
            "properties": {
                "helper_type": {
                    "type": "string",
                    "enum": ["input_boolean", "input_number", "input_text", "input_select", "input_datetime", "counter", "timer"],
                    "description": "Type of helper to create/update.",
                },
                "name": {
                    "type": "string",
                    "description": "Friendly name of the helper, e.g. 'Mode nuit actif'",
                },
                "helper_id": {
                    "type": "string",
                    "description": "Optional slug ID, e.g. 'mode_nuit_actif'. Auto-generated from name if omitted.",
                },
                "icon": {
                    "type": "string",
                    "description": "MDI icon, e.g. 'mdi:weather-night'",
                },
                "options": {
                    "description": "Additional type-specific options.",
                    "type": "object",
                    "properties": {
                        "min": {"type": "number", "description": "input_number: minimum value"},
                        "max": {"type": "number", "description": "input_number: maximum value"},
                        "step": {"type": "number", "description": "input_number: step"},
                        "unit_of_measurement": {"type": "string", "description": "input_number: unit"},
                        "options": {"type": "array", "items": {"type": "string"}, "description": "input_select: list of options"},
                        "initial": {"description": "input_boolean/number/text/select: initial value"},
                        "max_length": {"type": "integer", "description": "input_text: max length"},
                        "initial_value": {"type": "integer", "description": "counter: initial value"},
                        "minimum": {"type": "integer", "description": "counter: minimum"},
                        "maximum": {"type": "integer", "description": "counter: maximum"},
                        "step_counter": {"type": "integer", "description": "counter: step"},
                        "duration": {"type": "string", "description": "timer: duration as HH:MM:SS"},
                    },
                },
            },
        },
    },
    {
        "name": "ha_config_remove_helper",
        "description": "Delete a helper. Irreversible and not covered by the file copies in .haca_backups: ask the user to confirm, and offer a full backup (ha_backup_create) before deleting. Check if referenced in automations before deleting.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_id"],
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "entity_id of the helper to delete, e.g. 'input_boolean.mode_nuit'",
                },
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
#  v1.5.0 — 6 LOW PRIORITY TOOLS
#  ha_get_system_health · ha_get_updates · ha_reload_core
#  ha_list_services · ha_config_set_area · ha_manage_entity_labels
# ═══════════════════════════════════════════════════════════════════════════════

HA_LOW_TOOLS: list[dict[str, Any]] = [
    {
        "name": "ha_get_system_health",
        "description": "Get HA system health: version, database size, integrations in error, recorder status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ha_get_updates",
        "description": (
            "List available updates for Home Assistant core, supervisor, add-ons, HACS integrations, "
            "and custom components. Returns version info (current vs available) and release notes URL. "
            "Useful for keeping the system up-to-date and identifying outdated custom components."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ha_reload_core",
        "description": "Reload HA core config. Call after creating/updating automations, scripts, or scenes.",
        "inputSchema": {
            "type": "object",
            "required": ["domain"],
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to reload, e.g. 'automation', 'script', 'scene', 'input_boolean'",
                },
            },
        },
    },
    {
        "name": "ha_list_services",
        "description": "List all available HA services with their parameters. Use before ha_call_service.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Filter by domain, e.g. 'light', 'automation'. Omit to list all.",
                },
            },
        },
    },
    {
        "name": "ha_config_set_area",
        "description": "Create or update an area. Provide: name, optional icon and floor.",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Area name, e.g. 'Salon', 'Chambre principale'",
                },
                "area_id": {
                    "type": "string",
                    "description": "Optional slug ID, e.g. 'salon'. Auto-generated from name if omitted.",
                },
                "icon": {
                    "type": "string",
                    "description": "MDI icon, e.g. 'mdi:sofa'",
                },
                "picture": {
                    "type": "string",
                    "description": "URL or /local/ path to an image for the area.",
                },
            },
        },
    },
    {
        "name": "ha_manage_entity_labels",
        "description": "Add or remove labels from entities. Provide: entity_id, labels list, action (add/remove).",
        "inputSchema": {
            "type": "object",
            "required": ["entity_ids", "action"],
            "properties": {
                "entity_ids": {
                    "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
                    "description": "One entity_id or list of entity_ids to update.",
                },
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "replace"],
                    "description": "'add' appends labels, 'remove' removes them, 'replace' sets exactly these labels.",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label IDs to add/remove/replace, e.g. ['haca_reviewed', 'needs_icon']",
                },
            },
        },
    },
]


# ── Tool definitions for MCP handshake (all 24 new tools) ─────────────────────
NEW_TOOLS_V151: list[dict[str, Any]] = [
    # ── Scripts ────────────────────────────────────────────────────────────
    {"name": "ha_get_script", "description": "Read a script's full YAML config. Use BEFORE ha_update_script. Accepts entity_id or alias.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string", "description": "script entity_id or alias"}}}},
    {"name": "ha_update_script", "description": "Update a script, writing back to the file that holds it. ALWAYS call ha_get_script first. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string"}, "alias": {"type": "string"},
                     "description": {"type": "string"}, "mode": {"type": "string"},
                     "sequence": {"type": "array"}, "variables": {"type": "object"},
                     "icon": {"type": "string"}}}},
    {"name": "ha_remove_script", "description": "Delete a script from the file that holds it. Ask user confirmation. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string"}}}},
    # ── Scenes ─────────────────────────────────────────────────────────────
    {"name": "ha_get_scene", "description": "Read a scene's YAML and entity states. Use BEFORE ha_update_scene.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string", "description": "scene entity_id or name, e.g. 'scene.soiree'"}}}},
    {"name": "ha_create_scene", "description": "Create a new scene. Provide: name, entities dict. Use ha_get_entities to find entity_ids. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["name", "entities"],
      "properties": {"name": {"type": "string"}, "icon": {"type": "string"},
                     "entities": {"type": "object",
                       "description": "e.g. {'light.salon': {'state': 'on', 'brightness': 200}}"}}}},
    {"name": "ha_update_scene", "description": "Update a scene. ALWAYS call ha_get_scene first. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string"}, "name": {"type": "string"},
                     "icon": {"type": "string"}, "entities": {"type": "object"}}}},
    {"name": "ha_remove_scene", "description": "Delete a scene. Ask user confirmation. The file is copied into /config/.haca_backups/ before it changes; the copy's path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string"}}}},
    # ── Blueprints ─────────────────────────────────────────────────────────
    {"name": "ha_list_blueprints",
     "description": "List all automation blueprints (built-in and custom). Use to find paths before ha_get_blueprint.",
     "inputSchema": {"type": "object", "properties": {
       "domain": {"type": "string", "description": "Filter by domain: 'automation' or 'script'. Default: both."}}}},
    {"name": "ha_get_blueprint",
     "description": "Read a blueprint's full YAML. Use ha_list_blueprints first to find the path.",
     "inputSchema": {"type": "object", "required": ["path"],
      "properties": {"path": {"type": "string",
        "description": "Relative path from /config/blueprints/, e.g. 'automation/haca/my_bp.yaml'"}}}},
    {"name": "ha_update_blueprint",
     "description": (
         "Replace an existing blueprint file with new YAML, written verbatim. "
         "Read the current text with ha_get_blueprint(path), edit it, send it back as 'yaml'. "
         "Field-level patching is not available: HA's !input tags do not survive a YAML round-trip. "
         "The file is copied into /config/.haca_backups/ before it changes; "
         "the copy's path comes back as 'backup'."
     ),
     "inputSchema": {"type": "object", "required": ["path", "yaml"],
      "properties": {"path": {"type": "string"},
                     "yaml": {"type": "string",
                              "description": "Full blueprint YAML, including the top-level 'blueprint:' key"}}}},
    {"name": "ha_remove_blueprint",
     "description": "Delete a blueprint YAML file from /config/blueprints/. Ask user confirmation. The file is copied into /config/.haca_backups/ first; the copy's path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["path"],
      "properties": {"path": {"type": "string"}}}},
    {"name": "ha_import_blueprint",
     "description": "Import a blueprint from a URL (GitHub, HA community). Re-importing one of the same name overwrites it, after a copy into /config/.haca_backups/ whose path comes back as 'backup'.",
     "inputSchema": {"type": "object", "required": ["url"],
      "properties": {"url": {"type": "string",
        "description": "Direct raw YAML URL, e.g. 'https://raw.githubusercontent.com/.../blueprint.yaml'"}}}},
    # ── Dashboards ─────────────────────────────────────────────────────────
    {"name": "ha_list_dashboards",
     "description": "List all Lovelace dashboards (default dashboard + all custom dashboards).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ha_update_lovelace_card",
     "description": (
         "Replace an existing Lovelace card. Call ha_get_lovelace first to get view/card indices. "
         "Identify the card by view_index + card_index, or by card_id. "
         "Card type names are always in English (e.g. weather-forecast, entities, tile)."
     ),
     "inputSchema": {"type": "object", "required": ["card_config"],
      "properties": {
        "view_index":   {"type": "integer", "description": "0-based view index (default 0)"},
        "card_index":   {"type": "integer", "description": "0-based card index in the view"},
        "card_id":      {"type": "string",  "description": "Card 'id' field value (alternative to card_index)"},
        "card_config":  {"type": "object",  "description": "Full new card configuration dict"},
        "dashboard_url":{"type": "string",  "description": "Dashboard url_path for non-default dashboards"},
      }}},
    {"name": "ha_remove_lovelace_card",
     "description": "Remove a card from a Lovelace view by index or card id.",
     "inputSchema": {"type": "object", "properties": {
        "view_index":    {"type": "integer"},
        "card_index":    {"type": "integer"},
        "card_id":       {"type": "string"},
        "dashboard_url": {"type": "string"},
      }}},
    # ── Helpers ────────────────────────────────────────────────────────────
    {"name": "ha_get_helper",
     "description": "Read a helper's current state, friendly name, icon, and registry metadata.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string",
        "description": "e.g. 'input_boolean.mode_nuit', 'timer.cuisine'"}}}},
    {"name": "ha_update_helper",
     "description": (
         "Update a helper's configuration: rename, change icon, area, "
         "or domain-specific settings (min/max/step for input_number, "
         "options for input_select, duration for timer)."
     ),
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {
        "entity_id":  {"type": "string"},
        "name":       {"type": "string",  "description": "New friendly name"},
        "icon":       {"type": "string",  "description": "MDI icon, e.g. 'mdi:lightbulb'"},
        "area_id":    {"type": "string"},
        "min":        {"type": "number",  "description": "input_number min"},
        "max":        {"type": "number",  "description": "input_number max"},
        "step":       {"type": "number",  "description": "input_number step"},
        "options":    {"type": "array",   "description": "input_select options list"},
        "duration":   {"type": "string",  "description": "timer duration, e.g. '00:05:00'"},
        "pattern":    {"type": "string",  "description": "input_text regex pattern"},
      }}},
    # ── Entities ───────────────────────────────────────────────────────────
    {"name": "ha_get_entity_detail",
     "description": "Get detailed info about one entity: state, all attributes, device info, area, labels. More complete than ha_get_entities.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {"entity_id": {"type": "string"}}}},
    {"name": "ha_remove_entity",
     "description": (
         "Remove a ghost/zombie/orphaned entity from the registry. "
         "Only safe for unavailable or unknown-state entities. "
         "Set force=true to override the safety check."
     ),
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {
        "entity_id": {"type": "string"},
        "force":     {"type": "boolean", "description": "Set true to remove even if entity state is not unavailable/unknown"},
      }}},
    {"name": "ha_enable_entity",
     "description": "Enable or disable an entity in the entity registry.",
     "inputSchema": {"type": "object", "required": ["entity_id"],
      "properties": {
        "entity_id": {"type": "string"},
        "enable":    {"type": "boolean", "description": "true to enable, false to disable (default: true)"},
      }}},
    # ── Config files ────────────────────────────────────────────────────────
    {"name": "ha_get_config_file",
     "description": (
         "Read any HA config file inside /config/ (configuration.yaml, secrets.yaml, "
         "automations.yaml, scripts.yaml, etc.). Use to inspect hardcoded secrets or misconfigured entries."
     ),
     "inputSchema": {"type": "object", "required": ["filename"],
      "properties": {"filename": {"type": "string",
        "description": "Filename relative to /config/, e.g. 'secrets.yaml', 'configuration.yaml'"}}}},
    {"name": "ha_update_config_file",
     "description": (
         "Write to a HA config file. mode='replace' (full overwrite), "
         "'append' (add to end), or 'patch_line' (replace first occurrence of old_text). "
         "Allowed files: automations.yaml, scripts.yaml, scenes.yaml, secrets.yaml, "
         "groups.yaml, customize.yaml, configuration.yaml, ui-lovelace.yaml. "
         "The file is copied into /config/.haca_backups/ before it changes; "
         "the copy's path comes back as 'backup'."
     ),
     "inputSchema": {"type": "object", "required": ["filename", "content"],
      "properties": {
        "filename": {"type": "string"},
        "content":  {"type": "string", "description": "New content or replacement text"},
        "mode":     {"type": "string", "enum": ["replace", "append", "patch_line"], "default": "replace"},
        "old_text": {"type": "string", "description": "Required for patch_line mode: text to find and replace"},
      }}},
    # ── Labels ─────────────────────────────────────────────────────────────
    {"name": "ha_list_labels",
     "description": "List all labels defined in Home Assistant (id, name, icon, color).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ha_create_label",
     "description": "Create a new label in Home Assistant.",
     "inputSchema": {"type": "object", "required": ["name"],
      "properties": {
        "name":  {"type": "string"},
        "icon":  {"type": "string", "description": "MDI icon, e.g. 'mdi:tag'"},
        "color": {"type": "string", "description": "CSS color, e.g. '#ff5733'"},
      }}},
]


# ─── Read / write classification ──────────────────────────────────────────
# Every tool is either read-only or able to change the instance (files,
# registries, service calls). The LLM API (llm_api.py) uses this to hand a
# conversation agent — a voice satellite, an Assist pipeline, an Alexa or
# Google integration — a read-only tool set unless the owner explicitly
# opted in AND the person speaking is an administrator.
#
# The names live here rather than in each of the 60 tool literals so the
# classification can be read, reviewed and tested in one place; the `access`
# field is then stamped onto every entry below.

MCP_WRITE_TOOLS: frozenset[str] = frozenset({
    # HACA fixes — rewrite automation YAML
    "haca_apply_fix", "haca_fix_batch", "ha_apply_fix", "ha_fix_batch",
    # Arbitrary service calls (lock.unlock, alarm_control_panel.disarm…)
    "ha_call_service",
    # Automations / scripts / scenes / blueprints
    "ha_create_automation", "ha_update_automation", "ha_remove_automation",
    "ha_create_script", "ha_update_script", "ha_remove_script",
    "ha_create_scene", "ha_update_scene", "ha_remove_scene",
    "ha_create_blueprint", "ha_update_blueprint", "ha_remove_blueprint",
    "ha_import_blueprint",
    # Dashboards
    "ha_add_lovelace_card", "ha_update_lovelace_card", "ha_remove_lovelace_card",
    # Registries and helpers
    "ha_rename_entity", "ha_remove_entity", "ha_enable_entity",
    "ha_config_set_helper", "ha_config_remove_helper", "ha_update_helper",
    "ha_config_set_area", "ha_manage_entity_labels", "ha_create_label",
    # Raw configuration files, reloads and backups
    "ha_update_config_file", "ha_reload_core", "ha_backup_create",
})


def tool_access(name: str) -> str:
    """Return "write" if the named tool can change the instance, else "read"."""
    return "write" if name in MCP_WRITE_TOOLS else "read"
