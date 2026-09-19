# 🛡️ H.A.C.A — Home Assistant Config Auditor

<div align="center">

![Version](https://img.shields.io/badge/version-1.8.1-orange)
![HA](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![Tests](https://img.shields.io/badge/tests-70%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![HACS](https://img.shields.io/badge/HACS-Custom-blue)

**Audit, detect and automatically fix issues in your Home Assistant configuration.**

[Full Documentation](https://jeanmarc-labs.github.io/docs-haca/documentation.html) · [README Français](README.fr.md) · [Report a bug](https://github.com/JeanMarc-Labs/ha-config-auditor/issues)

</div>

---

## Why H.A.C.A?

Over time, a Home Assistant setup accumulates stale automations, ghost entities, broken references, silently draining batteries and hard-to-spot performance issues. H.A.C.A does this work for you — automatically, continuously, from a dedicated sidebar panel.

---

## Features

| Feature | Description |
|---|---|
| 🔍 **Continuous audit** | Auto-scan every 60 min (configurable). Real-time 0-100 health score exposed as HA sensor. |
| ⚡ **1-click fixes** | Before/after preview. Direct application with automatic YAML backup. |
| 🤖 **Built-in AI** | Explanations, description suggestions, complex automation optimization and conversational assistant via your HA-configured LLM. Native LLM API — no prompt hacks. |
| 📊 **History & Trends** | Health score tracking over time. Diff comparison between scans. PDF, Markdown and JSON reports. Configurable frequency (daily / weekly / monthly). |
| 🔋 **Batteries + Predictions** | Monitor all devices. Linear regression lifetime predictions. 7-day advance alerts. CSV export. |
| 🗄️ **Recorder DB + Impact** | Detect and purge orphan entities. Per-entity impact analysis (writes/day, MB/year). Copy-paste YAML exclude block. |
| 🔒 **Security** | Detection of hardcoded secrets, sensitive data and vulnerable configurations. Admin-only destructive operations. |
| ✅ **Compliance** | Audit naming conventions, missing icons, missing areas, unused labels — configurable per check type. |
| 🗺️ **Area Complexity** | Interactive complexity heatmap per area. Merge and split suggestions. |
| 🔄 **Redundancies** | Detect logically overlapping automations, blueprint candidates, and automations replaceable by native HA features. |
| 🧩 **Helpers** | Dedicated tab for all `input_*` and timers with unused-helper detection. |
| 🔗 **MCP Server (60 tools)** | Built-in Model Context Protocol server for 12 AI agents: Claude Desktop, Cursor, VS Code, Windsurf, Cline, n8n and more. |
| 🗂️ **Dependency graph** | D3.js force-directed graph with relationship sidebar (Used by / Uses), CSV and Markdown export per node or full graph. |

---

## Installation

### Via HACS (recommended)

> HACS handles updates automatically.

1. In HACS → **Integrations** → **⋮** → **Custom repositories**
2. URL: `https://github.com/JeanMarc-Labs/ha-config-auditor` · Category: **Integration**
3. Search **H.A.C.A** → **Download**
4. **Restart Home Assistant** (full restart required)
5. **Settings → Devices & Services → + Add Integration** → search **H.A.C.A**

> ✅ The H.A.C.A panel appears in your sidebar. All configuration is done from this panel.

### Manual installation

```bash
git clone https://github.com/JeanMarc-Labs/ha-config-auditor.git
cp -r ha-config-auditor/custom_components/config_auditor /config/custom_components/
# Restart HA, then add the integration via Settings → Devices & Services
```

### Requirements

- Home Assistant **2024.1** or newer
- Python 3.12+ (bundled with HA)
- Read/write access to `/config/`

---

## Navigation

The H.A.C.A panel is organized into **10 main tabs**:

| Tab | Content |
|---|---|
| **Issues** | All detected issues — 12 sub-tabs: All · Security · Automations · Scripts · Scenes · Entities · Helpers · Performance · Blueprints · Dashboards · **Area Map** · **Redundancies** |
| **Recorder** | SQLite orphans · **Impact** (writes/day, MB/year) |
| **History** | Scan history, score chart, diff between versions |
| **Backups** | YAML backups created before each fix |
| **Reports** | PDF/Markdown/JSON reports |
| **Carte** | D3.js dependency graph with relationship exports |
| **Batteries** | Monitor · **Predictions** (linear regression) |
| **Chat** | AI conversational assistant (native LLM API, 60 MCP tools) |
| **Compliance** | Metadata quality audit |
| **Config** | Options, thresholds, MCP token, report frequency, enabled issue types |

---

## Configuration

> ⚠️ **All configuration is done from the H.A.C.A panel** (⚙️ Config tab), not from Settings → Devices & Services.

| Option | Default | Description |
|---|---|---|
| `scan_interval` | 60 min | Auto-scan interval (5–1440 min) |
| `battery_alert_threshold` | 20% | Battery alert threshold (applied without HA restart) |
| `notifications_enabled` | true | HA notifications for new HIGH issues |
| `report_frequency` | weekly | Automatic report frequency: `daily` / `weekly` / `monthly` / `never` |
| `mcp_server_enabled` | **off** | MCP server over HTTP — see [Security & privacy](#security--privacy) |
| `llm_api_enabled` | **off** | Offers the H.A.C.A tools to HA conversation agents |
| `llm_write_enabled` | false | Lets those agents use the write tools (administrators only) |
| `proactive_agent_enabled` | **off** | Autonomous analysis and periodic AI report |

### Ignoring entities

Two ways, and they add up:

- **The `haca_ignore` label** — add it to any entity, device or area to exclude it from all scans.
- **Glob patterns** — *Configuration → Ignore entities with a pattern*, one [glob](https://docs.python.org/3/library/fnmatch.html) per line (`sensor.bbq_*`, `climate.garage?`). Any entity whose `entity_id` matches is skipped by every scan, exactly as if it carried the label.

The label can only be put on something Home Assistant knows about. A card pointing at an entity you deleted, or a device you power down on purpose whose integration therefore never starts, has no registry entry at all — there is nothing to label. A pattern is tested on the `entity_id` itself, so it covers those too. On a *missing*, *unavailable* or *zombie entity* issue, the **Ignore entity** button adds that entity_id to the list for you.

---

## Artificial Intelligence

### Native HA LLM API

HACA registers itself as a **native LLM API** in Home Assistant. Configure it once:

> Settings → Voice Assistants → [your agent] → LLM API → **HACA**

After that, Mistral, Gemini, Llama or any HA conversation agent can use the HACA tools natively. If the preferred agent fails (quota, timeout), the next available agent is tried automatically.

**Read-only by default.** Attaching the HACA API to an agent gives it to everything that talks to that agent — an Assist satellite, a smart speaker, an Alexa or Google integration. So the agent only gets the read tools (diagnose, explain, suggest). The tools that write — configuration files, service calls such as `lock.unlock` — are added only when **both** of these hold:

- **Configuration → AI agents → Allow write tools** is enabled (off by default), and
- the person the conversation belongs to is a Home Assistant administrator.

A voice satellite with no authenticated user is never an administrator. When write tools are withheld, the agent simply does not have them and says so, rather than failing mid-operation.

### AI Chat

The **Chat** tab is a conversational AI assistant with access to **60 MCP tools** enabling reading, creating, modifying and reloading any HA configuration.

Example requests:
```
"Create a blueprint from the kitchen_lights automation and apply it to the 3 similar rooms"
"Analyze the 5 automations with the highest Recorder impact and generate an exclusion YAML block"
"Rename all entities in the Living Room area to follow snake_case convention"
```

### AI buttons on issues

Each issue has an **AI** button that opens Chat with a pre-filled prompt tailored to the issue type:
- **66 types → Imperative Chat**: the AI directly executes the fix via MCP tools
- **8 informational types → Explanation**: the AI explains the problem with best practices

Simple field issues (`no_description`, `no_alias`) show an editable suggestion modal — no full Chat needed.

### MCP Server (60 tools)

The built-in MCP server exposes all H.A.C.A and HA tools to external AI agents:

```
# Server URL
http://homeassistant.local:8123/api/haca_mcp

# Authentication header
Authorization: Bearer <your-haca-token>
```

**Tool categories:** Audit HACA · Discovery · Control · Automations & Scripts · Blueprints · Scenes · Dashboards · Monitoring · Helpers & Areas · Config files · Security & Validation

**The MCP endpoint requires an administrator token.** The tools write configuration files and can call any service, which Home Assistant reserves for admins; a long-lived token issued by a non-admin account gets `403`. Every service call made through MCP is attributed to the token's owner in the Home Assistant logbook. `/api/haca_mcp/info` is admin-only too.

Supported agents: Claude Code · Claude Desktop · Cursor · VS Code/Copilot · Windsurf · Cline · Antigravity · Continue.dev · Open WebUI · n8n · HTTP/REST · Gemini CLI

---

## Security & privacy

H.A.C.A reads your entire configuration, can rewrite it, and can hand parts of it to an AI. This section states exactly what that opens, what leaves your machine, and how to close each of it.

### What H.A.C.A exposes

| Surface | Who can reach it | New install |
|---|---|---|
| H.A.C.A sidebar panel | Administrators only | on |
| 32 `haca/*` WebSocket commands (everything the panel calls) | Administrators only | on |
| 16 `config_auditor.*` HA services | Administrators only | on |
| `/api/config_auditor/report/<file>` — generated reports | Authenticated administrators | on |
| `/api/haca_mcp` — MCP server, 60 tools over HTTP | Administrator token; anything else gets `403` | **off** |
| `/api/haca_mcp/info` — MCP discovery document | Administrator token | **off** |
| H.A.C.A LLM API — the same 60 tools offered to HA conversation agents | Read tools: anyone who talks to that agent. Write tools: administrators, and only with `llm_write_enabled` on | **off** |
| Proactive agent — periodic report, AI-enriched | Runs on its own; calls the AI provider configured in HA | **off** |

Two things are worth knowing about that table:

- **The last three are off on a new installation.** They are the only features that reach outside the panel, so you turn them on knowing what they open — from Configuration → **Exposed features**. An entry created *before* v1.8.0 was migrated with all three **on**, so nothing broke on upgrade; if you never used them, turn them off.
- **Reports are not static files.** They used to be served from a plain static path, which Home Assistant serves without authentication, under predictable names. They now go through an authenticated admin-only view.

### What is sent to an LLM, and when

H.A.C.A never contacts an AI provider itself. It calls whatever you have configured in Home Assistant — an `ai_task` entity, or a conversation agent — so the provider, the account and the billing are the ones you already set up there.

| When | What leaves your instance |
|---|---|
| You press the **AI** button on an issue | The issue's type, severity, message, recommendation, and the entity ID or alias |
| You type in the **Chat** tab | Your message, plus whatever the tools you let it call return |
| You open a **fix suggestion** modal | The field being fixed and the surrounding automation |
| You run the **automation optimizer** or ask for a description | The automation's YAML |
| **Proactive agent**, on its own | Health score, issue counts by severity, and the top 5 issues — entity ID plus the first 100 characters of each message |

Only the last row happens without you asking. It is off on a new install, and `report_frequency: never` stops it on an existing one.

**The fallback chain is worth understanding.** A single AI call tries *every* `ai_task` entity, then *every* conversation agent — your preferred Assist pipeline first, the rest in discovery order — until one answers. So if your local agent is down or out of quota, the same prompt goes to the next provider you have configured, which may be a cloud one. There is no per-call provider pin. If that matters to you, keep a single AI provider configured in Home Assistant, or leave the proactive agent off.

### Turning it all off

Everything above is a toggle in the panel's **Configuration** tab:

| Option | Effect when off |
|---|---|
| `mcp_server_enabled` | The `/api/haca_mcp` endpoints are not registered at all |
| `llm_api_enabled` | The HACA LLM API disappears from Settings → Voice assistants |
| `llm_write_enabled` | Conversation agents keep the read tools and lose the 31 write ones |
| `proactive_agent_enabled` | No autonomous analysis, no AI report |
| `report_frequency: never` | Keeps the agent's event monitoring, drops the periodic report |

Changing one of the first three reloads the integration, so the change takes effect immediately. Removing the integration removes every endpoint and service with it; `.haca_backups/` and `.haca_reports/` stay on disk for you to delete.

### Do not expose Home Assistant directly on the internet

Every H.A.C.A endpoint requires an administrator, but an administrator is proven by a bearer token — and a long-lived token that leaks gives its holder your configuration files, `lock.unlock`, and `alarm_control_panel.disarm` through a single HTTP endpoint. That is true of Home Assistant with or without H.A.C.A; H.A.C.A raises what is reachable through one URL.

Reach your instance through Home Assistant Cloud, a VPN, or a reverse proxy with MFA in front of it. Do not port-forward 8123. Issue MCP tokens from an account you can revoke, and revoke them in Settings → Security when an agent no longer needs one.

---

## Detected Issue Types

### 🤖 Automations & Scripts

| Type | Severity | Fix |
|---|---|---|
| `device_id_in_trigger` / `device_id_in_action` / `device_id_in_target` | 🔴 HIGH | ✅ Auto |
| `incorrect_mode_motion_single` | 🔴 HIGH | ✅ Auto |
| `template_simple_state` | 🟡 MEDIUM | ✅ Auto |
| `no_alias` / `no_description` | 🔵 LOW | ✅ AI modal |
| `duplicate_automation` / `probable_duplicate_automation` | 🟡 MEDIUM | ✅ AI Chat |
| `potential_self_loop` | 🔴 HIGH | Manual |
| `high_complexity_actions` | 🟡 MEDIUM | ✅ AI Chat |
| `deprecated_service` | 🔴 HIGH | Manual |
| `script_blueprint_candidate` | 🟡 MEDIUM | ✅ AI Chat |

### 📦 Entities

| Type | Severity | Fix |
|---|---|---|
| `unavailable_entity` / `stale_entity` | 🔴/🟡 | Manual |
| `zombie_entity` | 🟡 MEDIUM | ✅ Auto |
| `broken_device_reference` | 🔴 HIGH | ✅ Auto |
| `disabled_but_referenced` | 🟡 MEDIUM | Manual |

### ⚡ Performance & Recorder

| Type | Severity |
|---|---|
| `expensive_template_states_all` | 🔴 HIGH |
| `high_parallel_max` | 🟡 MEDIUM |
| `recorder_high_impact` | 🟡 MEDIUM |

### 🛡️ Security

| Type | Severity |
|---|---|
| `hardcoded_secret` | 🔴 HIGH |
| `sensitive_data_exposure` | 🔴 HIGH |

### ✅ Compliance

| Type | Severity |
|---|---|
| `compliance_no_friendly_name` / `compliance_raw_entity_name` | 🔵 LOW |
| `compliance_area_no_icon` / `compliance_unused_label` | 🔵 LOW |
| `compliance_automation_no_description` / `compliance_automation_no_unique_id` | 🔵 LOW |
| `compliance_entity_no_area` / `compliance_helper_no_icon` / `compliance_helper_no_area` | 🔵 LOW |

### 🗺️ Areas & Redundancies *(v1.5.0)*

| Type | Severity |
|---|---|
| `area_high_complexity` | 🟡 MEDIUM |
| `area_split_suggested` | 🟡 MEDIUM |
| `area_merge_suggested` | 🔵 LOW |
| `redundancy_overlap` | 🟡 MEDIUM |
| `redundancy_blueprint_candidate` | 🟡 MEDIUM |
| `redundancy_native_ha` | 🔵 LOW |

---

## HA Services

```yaml
# Full audit
service: config_auditor.scan_all

# Selective scans
service: config_auditor.scan_automations
service: config_auditor.scan_entities
service: config_auditor.scan_compliance

# Preview a fix
service: config_auditor.preview_device_id
data:
  automation_id: "abc123"

# Apply a fix (with automatic backup)
service: config_auditor.fix_device_id
data:
  automation_id: "abc123"
  dry_run: false  # true = simulate without writing

# Generate a report
service: config_auditor.generate_report
data:
  format: pdf  # pdf | md | json
```

---

## Dashboard Integration

```yaml
automation:
  - alias: "HACA: Low health score alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.haca_health_score
        below: 70
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ HA config degraded"
          message: "Score: {{ states('sensor.haca_health_score') }}/100"
```

**Available sensors:**

| Sensor | Description |
|---|---|
| `sensor.haca_health_score` | Global health score (0–100) |
| `sensor.haca_total_issues` | Total number of issues |
| `sensor.haca_automation_issues` | Automation issues |
| `sensor.haca_entity_issues` | Entity issues |
| `sensor.haca_battery_low_count` | Devices below battery threshold |
| `sensor.haca_battery_critical_count` | Devices below 10% |
| `sensor.haca_battery_threshold` | Current battery threshold |

---

## Files Created by H.A.C.A

```
/config/
├── custom_components/config_auditor/   # Integration code
├── .haca_backups/                      # YAML backups before fixes
│   ├── automations_20260314_143022.yaml
│   └── scripts_20260314_091500.yaml
└── .haca_reports/                      # Generated reports
    ├── haca_report_20260314.pdf
    ├── haca_report_20260314.md
    └── haca_report_20260314.json
```

---

## License

MIT © JeanMarc-Labs

---

<div align="center">
<sub>H.A.C.A collects no data. All processing is local. AI uses only the LLMs configured in your Home Assistant.</sub>
</div>
