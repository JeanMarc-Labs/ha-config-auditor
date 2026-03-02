# 🛡️ H.A.C.A — Home Assistant Config Auditor

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.3-orange)
![HA](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![HACS](https://img.shields.io/badge/HACS-Custom-blue)

**Audit, detect and automatically fix issues in your Home Assistant configuration.**

[Full Documentation](https://jeanmarc-labs.github.io/docs-haca/documentation.html) · [README Français](README.fr.md) · [Report a bug](https://github.com/JeanMarc-Labs/ha-config-auditor/issues)

</div>

---

## Why H.A.C.A?

Over time, a Home Assistant setup accumulates stale automations, ghost entities, broken references and hard-to-spot performance issues. H.A.C.A does this work for you — automatically, continuously, from a dedicated sidebar panel.

---

## Features

| Feature | Description |
|---|---|
| 🔍 **Continuous audit** | Auto scan every 60 min (configurable). Real-time health score exposed as an HA sensor. |
| ⚡ **1-click fixes** | Before/after preview. Direct application with automatic YAML backup. |
| 🤖 **Built-in AI** | Explanations, description suggestions and complex automation optimization via your HA-configured LLM. |
| 📊 **History** | Health score tracking over time. Reports exportable as PDF, Markdown and JSON. |
| 🔋 **Batteries** | Monitor all devices. Configurable alerts. Exposed HA sensors. |
| 🗄️ **Recorder DB** | Detect and purge orphan entities from the database. |
| 🔒 **Security** | Detection of hardcoded secrets, sensitive data and vulnerable configurations. |

---

## Installation

### Via HACS (recommended)

> HACS handles updates automatically.

1. In HACS → **Integrations** → **⋮** → **Custom repositories**
2. URL: `https://github.com/JeanMarc-Labs/ha-config-auditor` · Category: **Integration**
3. Search **H.A.C.A** → **Download**
4. Restart Home Assistant (full restart required)
5. **Settings → Devices & Services → + Add Integration** → search **H.A.C.A**

> ✅ The H.A.C.A panel appears in your sidebar. All configuration is done from this panel.

### Manual

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

## Configuration

> ⚠️ **All configuration is done from the H.A.C.A panel** (sidebar → H.A.C.A → ⚙️ Configuration tab), not from Settings → Devices & Services.

| Option | Default | Description |
|---|---|---|
| `scan_interval` | 60 min | Auto scan interval (5–1440 min) |
| `battery_alert_threshold` | 20% | Battery alert threshold |
| `notifications_enabled` | true | HA notifications for new issues |

---

## Detected Issue Types

### 🤖 Automations & Scripts

| Type | Severity | Auto-fix |
|---|---|---|
| `device_id_in_trigger` | 🔴 HIGH | ✅ |
| `device_id_in_action` | 🔴 HIGH | ✅ |
| `device_id_in_target` | 🔴 HIGH | ✅ |
| `incorrect_mode_motion_single` | 🔴 HIGH | ✅ |
| `template_simple_state` | 🟡 MEDIUM | ✅ |
| `no_alias` / `no_description` | 🔵 LOW | ✅ (AI) |
| `duplicate_automation` | 🟡 MEDIUM | Manual |
| `potential_self_loop` | 🔴 HIGH | Manual |
| `high_complexity_actions` | 🟡 MEDIUM | ✅ (AI) |
| `deprecated_service` | 🔴 HIGH | Manual |

### 📦 Entities

| Type | Severity | Auto-fix |
|---|---|---|
| `unavailable_entity` | 🔴 HIGH | Manual |
| `zombie_entity` | 🟡 MEDIUM | ✅ |
| `broken_device_reference` | 🔴 HIGH | ✅ |
| `stale_entity` | 🟡 MEDIUM | Manual |
| `disabled_but_referenced` | 🟡 MEDIUM | Manual |

### ⚡ Performance

| Type | Severity |
|---|---|
| `expensive_template_states_all` | 🔴 HIGH |
| `template_time_check` | 🟡 MEDIUM |
| `excessive_delay` | 🔵 LOW |
| `high_parallel_max` | 🟡 MEDIUM |

### 🛡️ Security

| Type | Severity |
|---|---|
| `hardcoded_secret` | 🔴 HIGH |
| `sensitive_data_exposure` | 🔴 HIGH |

---

## HA Services

```yaml
# Full audit
service: config_auditor.scan_all

# Selective scans
service: config_auditor.scan_automations
service: config_auditor.scan_entities
service: config_auditor.scan_performance

# Preview a fix
service: config_auditor.preview_device_id
data:
  automation_id: "abc123"

# Apply a fix
service: config_auditor.fix_device_id
data:
  automation_id: "abc123"
  dry_run: false  # true = simulate without writing

# Generate a report
service: config_auditor.generate_report
data:
  format: pdf  # pdf | markdown | json | all
```

---

## Dashboard Integration

The health score is exposed as an HA sensor:

```yaml
# Alert automation
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

Available sensors:

| Sensor | Description |
|---|---|
| `sensor.haca_health_score` | Global health score (0–100) |
| `sensor.haca_total_issues` | Total number of issues |
| `sensor.haca_automation_issues` | Automation issues |
| `sensor.haca_entity_issues` | Entity issues |
| `sensor.haca_battery_low_count` | Devices below battery threshold |

---

## Files Created by H.A.C.A

```
/config/
├── custom_components/config_auditor/   # Integration code
├── .haca_backups/                      # YAML backups before fixes
│   └── automations_20240315_143022.yaml
└── .haca_reports/                      # Generated reports
    ├── haca_report_20240315.pdf
    ├── haca_report_20240315.md
    └── haca_report_20240315.json
```
---

## License

MIT © JeanMarc-Labs

---

<div align="center">
<sub>H.A.C.A collects no data. All processing is local. AI uses only the LLMs configured in your Home Assistant.</sub>
</div>
