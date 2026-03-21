# Changelog — H.A.C.A

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [1.6.1] — 2026-03-20 — Bug fixes, new features, UX improvements

### Added

- **LOW checks disabled by default** (#10) — New installations exclude 14 low-severity issue types (no_description, no_alias, helper_unused, etc.) to avoid overwhelming new users with 1400+ notifications. Users can enable them in Configuration when ready
- **Manual-only scan mode** (#19) — Setting scan_interval to 0 disables automatic scanning. HACA only scans when the user clicks "Full Scan"
- **Battery notifications toggle** (#11) — New toggle in Configuration to disable battery persistent notifications while keeping the battery list in the dashboard
- **Admin-only panel** (#6.2) — The HACA sidebar panel is now hidden for non-admin users via `require_admin=True`
- **Mobile menu button** (#6.3) — Menu hamburger icon in the header on mobile/tablet that opens the HA sidebar (dispatches `hass-toggle-menu`), matching native HA behavior
- **Issue type hints** (#13) — 33 short explanations displayed below each issue card explaining what was detected and why it matters. Translated in English and French
- **Last scan timestamp** — Displayed in the HACA panel header next to the Scan button with label "Last scan" (translated in 13 languages), date and time including year
- **Config panel: scripts, scenes, helpers, groups categories** — Issue type toggles now cover all 74 analyzer types across 11 categories including new Scripts, Scenes, Helpers & Templates, and Groups sections

### Fixed

- **`excluded_issue_types` not working** (#12, #18, #6) — Root cause: 29 analyzer types were missing from the config panel toggle list. `god_automation` and `complex_automation` (the real type names) were absent while orphan `high_complexity_actions` was listed. Full resync of all 74 types across 11 categories
- **`haca_ignore` label ignored by performance and security analyzers** (#3) — Both `performance_analyzer.py` and `security_analyzer.py` now load and filter by `haca_ignore` labels
- **Repairs not cleared after fixing issues** (#16) — Rewrote `repairs.py` with clean-slate approach: deletes ALL previous HACA repairs before creating current ones. No more stale entries after HA restart
- **Repairs messages too vague** (#9) — Type displayed as readable text ("Device ID in trigger" instead of "device_id_in_trigger"). Recommendation included in description. Only simple fixes (no_description, no_alias) marked as auto-fixable — complex automations never
- **Deleted scripts still reported** (#17) — `_load_script_configs()` and `_load_scene_configs()` now call `.clear()` before reloading YAML, preventing stale data from previous scans
- **"IA" hardcoded instead of "AI"** (#4) — Replaced with translation key `actions.ai_explain` in `issues.js`, `optimizer.js`, and `config_tab.js`
- **Unused label check too narrow** (#7) — Now checks entities, devices, areas, and automations/scripts — not just entities
- **Copy buttons not working in MCP config panel** — Replaced `navigator.clipboard` (requires HTTPS) with `_hacaCopy()` fallback using textarea + execCommand. Replaced fragile inline onclick with proper event listeners
- **Blueprint creation blocked by backup** (#5 forum) — AI was calling `ha_backup_create` first, then waiting forever. Tool description now explicitly says "do NOT call ha_backup_create". Internal `_auto_backup` runs synchronously inside `_tool_ha_create_blueprint`
- **Blueprint `inputs` format rejection** — Robust parsing: accepts dict, JSON string, or simple string values. Default values preserved in `input` section (HA requires them)
- **Score card showing "0/100"** — Changed to "%" for the gauge label
- **Score card battery showing "0%" for no alerts** — Shows ✓ with green battery-check icon when battery_alerts = 0
- **Dashboard card battery "0"** — Shows ✓ instead of "0" for battery_alerts with 0 alerts

### Changed

- **MCP Antigravity config** — Uses `mcp-proxy` bridge instead of direct URL (HACA does not support OAuth2 dynamic client registration). Hint explains the limitation clearly
- **MCP server `/api/haca_mcp/sse` alias** — Kept as optional route but all config examples use the base URL `/api/haca_mcp`

---

## [1.6.1] — 2026-03-20 — Issue tracker bugfixes, new config options, mobile UX and MCP improvements

### Added

- **LOW checks disabled by default** (#10) — new installations exclude 14 low-severity issue types (no_description, helper_unused, etc.) to avoid overwhelming new users with 1400+ notifications
- **Manual-only scan mode** (#19) — set scan interval to 0 in Configuration to disable automatic scans; only the "Full Scan" button triggers analysis
- **Battery notifications toggle** (#11) — new toggle in Configuration to disable persistent battery notifications while keeping the battery list in the dashboard
- **Issue type hints** (#13) — 33 short explanations displayed below each issue card (e.g. "Uses device_id which breaks if the device is re-paired"). Translated in 13 languages
- **Admin-only panel** (#6.2) — `require_admin=True` on panel registration; non-admin users no longer see HACA in the sidebar
- **Mobile menu button** (#6.3) — hamburger icon in panel header dispatches `hass-toggle-menu` to open HA sidebar on mobile/tablet, matching the standard HA behavior
- **Last scan timestamp** — "Last scan: DD/MM/YYYY HH:MM" displayed in the panel header next to the Scan button, with label translated in 13 languages
- **MCP `/sse` alias route** — `/api/haca_mcp/sse` accepted as an alternative URL for SSE-based MCP clients

### Fixed

- **`excluded_issue_types` mismatch** (#12/#18/#6) — config panel listed 55 types but analyzers produce 74. Added 4 new categories (Scripts, Scenes, Helpers, Groups) with 31 missing types including `god_automation`, `complex_automation`, all script/scene/helper/template/timer/group types. Removed orphan `high_complexity_actions` (real type is in automations category)
- **`haca_ignore` not respected** (#3) — `performance_analyzer.py` and `security_analyzer.py` had no `haca_ignore` filtering; entities with the label were still scanned and flagged
- **Repairs not cleaned** (#9/#16) — rewrote `repairs.py`: clean slate on every scan (deletes ALL existing HACA repairs then recreates only current HIGH issues). Fixes stale repairs surviving HA restarts. Human-readable type names in descriptions. `FIXABLE_ISSUE_TYPES` reduced to safe-only fixes
- **Deleted scripts still flagged** (#17) — `_load_script_configs()` and `_load_scene_configs()` did not clear their dicts before reloading from YAML; deleted items persisted across scans
- **"IA" hardcoded instead of "AI"** (#4) — replaced with `this.t('actions.ai_explain')` translation key in issues.js, optimizer.js, and config_tab.js
- **Unused label false positives** (#7) — compliance check now scans entity registry + device registry + area registry + automation/script labels, not just entities
- **Blueprint creation regression** (#5 user report) — AI called `ha_backup_create` before `ha_create_blueprint` and got stuck waiting. Fixed: backup is now internal to the function, tool description explicitly says "do NOT call ha_backup_create". Input parsing accepts string JSON, dict, and simple values. Default values preserved in blueprint input section
- **Copy buttons not working** — `navigator.clipboard` fails on HTTP (non-HTTPS). Added `_hacaCopy()` helper with `textarea + execCommand` fallback. Replaced inline `onclick` with `addEventListener` (works in Shadow DOM)
- **Score card battery 0/100** — pill now shows `✓` with green `mdi:battery-check-outline` icon when no battery alerts
- **Dashboard card /100** — gauge shows `%` instead of `/100`
- **Lovelace card timestamp removed** — timestamp belongs in the panel header, not the Lovelace card

### Changed

- **MCP agent configs** — all examples use base URL `/api/haca_mcp` (no `/sse` suffix). Antigravity config uses `mcp-proxy` bridge with explicit note that OAuth2 is not supported
- **Config flow defaults** — `excluded_issue_types`, `repairs_enabled`, `battery_notifications_enabled` set at installation time

---

## [1.6.0] — 2026-03-16 — Lovelace cards, deep audit fixes, Unicode slugs and HA 2026.x compatibility

### Added

- **Lovelace Dashboard Card** (`haca-dashboard-card`) — custom card with health score gauge, issue counter grid, scan button, and panel link. Visual configuration via `getConfigForm()` with native HA selectors (title, toggles, column count, entity picker filtered by integration). Click opens standard HA more-info dialog (history, settings gear, 3-dot menu)
- **Lovelace Score Card** (`haca-score-card`) — compact health score gauge with optional issue count pills. Auto-discovers score entity via `haca_type` attribute. Visual editor with entity picker and detail toggle
- **Automatic Lovelace resource registration** — cards are auto-registered as dashboard resources at integration setup via `async_setup` following the official HA embedded card pattern (manifest dependencies, `lovelace.resources.async_create_item`, retry on `resources.loaded`). Stale resources from previous paths automatically cleaned up
- **`haca_type` state attribute** — all 14 HACA sensors expose `haca_type` (e.g. `"health_score"`, `"automation_issues"`) in `extra_state_attributes` for language-independent entity discovery by frontend cards
- **`suggested_object_id`** — sensors suggest English-only object IDs regardless of HA backend language, producing stable entity IDs like `sensor.h_a_c_a_health_score` instead of localized variants
- **`_slugify()` helper** — centralized Unicode-aware slug generator using `unicodedata.normalize('NFKD')`. Handles all diacritics (é→e, ç→c, ñ→n, ü→u). Applied to 9 locations: blueprints (3), area_id, script_id, helper_id, entity_id in create_automation, entity_id in deep_search, scene creation
- **`_issue_stable_id()`** — generates deterministic issue identifiers (`entity_id|type`) for MCP tools since analyzers don't produce `id` fields
- **`_TS_CACHE` merged strategy** — translation cache now stores root + panel JSON merged, making `ai_prompts` (30 keys), `services_notif`, and root-level `notifications` accessible alongside panel sections

### Fixed

- **MCP tools `fixable` field** — tools read `fix_available` and `recommendation` (the actual field names from analyzers) instead of non-existent `fixable` and `fix_description`. Fixes `haca_fix_suggestion`, `haca_apply_fix`, and `haca_get_issues`
- **`_find_issue_by_id` broken** — searched for `issue.get("id")` but no analyzer produces an `id` field. Now matches on stable ID, entity_id, or alias
- **`_tool_get_score` incomplete** — counted only 5 of 10 categories in `by_severity`. Now counts all 10 (automation, script, scene, blueprint, entity, helper, performance, security, dashboard, compliance). Removed phantom `last_scan` field
- **13 blocking I/O in `mcp_server.py`** — all `.read_text()`, `.exists()`, `open()`, `os.remove()`, `os.makedirs()` in async functions wrapped in `async_add_executor_job`. Affects: `_tool_get_automation`, `_tool_ha_create_automation`, `_tool_ha_update_automation`, `_tool_ha_create_script`, `_tool_ha_remove_automation`, `_tool_ha_deep_search`, `_tool_ha_config_list_helpers`, `_tool_ha_remove_blueprint`, `_tool_ha_update_config_file`, `_tool_ha_create_blueprint`, `_tool_ha_import_blueprint`
- **`_TS_CACHE` only stored `panel` subtree** — `services.py` notifications, `conversation.py` AI prompts (30 keys), `automation_optimizer.py` system prompt, and `__init__.py` uninstall message all returned raw keys instead of translated text
- **`extra_state_attributes` override without `super()`** — `HACAHealthScoreSensor`, `HACABatteryAlertsSensor`, and `HACARecorderOrphansSensor` overwrote the base class `haca_type` attribute. All three now call `super().extra_state_attributes`
- **Blueprint slug `allumer_une_lumi_re`** — `re.sub(r"[^a-z0-9_]", "_", ...)` stripped accented characters as underscores. Fixed by `_slugify()` with NFKD normalization: `"Allumer une lumière avec un capteur de présence"` → `"allumer_une_lumiere_avec_un_capteur_de_presence"`
- **Manual accent replacement** — area_id generation used a chain of 8 `.replace("é","e")` calls. Replaced by `_slugify()` for full Unicode coverage
- **`Path.mkdir(True)` crash** — `exist_ok` is keyword-only in `Path.mkdir()`. Passing `True` as positional set `mode=1`. Fixed with lambda
- **`LovelaceData.mode` removed in HA 2026.x** — replaced by `resource_mode`. Code now uses `getattr` with fallback for backward compatibility
- **Card resource cache busting** — resource URLs used static version `?v=1.5.2` which never changed between JS rebuilds. Now uses build hash (`?v=70c62e88`) ensuring browser reloads on every code change
- **`customElements.define` crash** — HA 2026.x scoped registry throws on duplicate registration. Both cards guarded with `if (!customElements.get(...))`
- **Card `ha-card` destroyed on every render** — `this.innerHTML = '<ha-card>...'` in `set hass()` replaced the `ha-card` element HA attached its edit overlay to. Now follows official HA pattern: `ha-card` created once in `if (!this.content)`, only inner `div` content updated
- **Card `setConfig` destroyed DOM** — reset `_cardBuilt = false` causing `ha-card` recreation. `setConfig` now stores config only, never touches DOM

### Changed

- **`manifest.json`** — `dependencies` now includes `["frontend", "http"]` (required for Lovelace resource registration)
- **Card registration in `async_setup`** — moved from `async_setup_entry` to `async_setup` per official HA developer guide (runs once per domain, not per config entry). Uses `CoreState.running` check with `homeassistant_started` event listener fallback

### Removed

- **Custom card editor elements** — `HacaDashboardCardEditor` and `HacaScoreCardEditor` custom elements removed in favor of `getConfigForm()` with native HA selectors

---

## [1.5.2] — 2026-03-14 — Native LLM API, security hardening, graph relationships and code quality

### Added

- **Native HA LLM API** — HACA registers itself as an LLM API in Home Assistant. Configure it once in Settings → Voice Assistants → [your agent] → LLM API → HACA. Mistral, Gemini, Llama and any HA conversation agent can then use all 58 HACA tools natively, without any prompt hacks or intermediate parsing
- **Chat fallback chain** — if the preferred agent fails (quota exceeded, timeout), the next available agent is tried automatically. Works with all agents configured in HA, preferred agent always first
- **Simple fix modal** — issues with a simple field fix (`no_description`, `no_alias`) now show an AI-powered modal with an editable suggestion field and three actions: Close, Edit manually (opens HA editor), Apply with AI (writes YAML directly, no backup needed)
- **Dependency graph — relationship sidebar** — clicking a node now shows "Used by" and "Uses" sections listing all connections with clickable navigation between nodes
- **Dependency graph — relationship exports** — new CSV and Markdown export buttons in the sidebar (per-node) and toolbar (full graph). Markdown report groups nodes by type (automations → scripts → scenes…) with "orphan" detection
- **Configurable report frequency** — in the Agent IA Proactif section of Config tab, a selector now allows choosing: Daily, Weekly (default), Monthly, or Never (disabled). The automatic check runs once a day instead of every hour
- **`_safe_write_and_reload`** — new helper in `mcp_server.py`: writes YAML atomically, runs reload, and automatically restores the original file if the reload fails. Used in `update_automation`, `remove_automation`, `update_script`
- **`_auto_backup` unified** — `_auto_backup` now delegates entirely to `_tool_ha_backup_create` (single source of truth for backup logic). All 11 destructive MCP tools trigger an automatic background backup before writing
- **70 tests** in updated/new test files covering: admin protection, chat fallback, atomic writes, auto-backup, path traversal, LLM API structure, rate limiting, deep_search timeout

### Fixed

- **MCP tools panel count** — panel was showing "33 tools" instead of the actual 65. All 65 tools now displayed across 11 categories (added: Blueprints, Scenes, Config files)
- **`_async_find_all_ai_task_entities`** — preferred agent was never placed first because `conversation_engine` (e.g. `conversation.google_xxx`) and `ai_task` entity IDs have different formats. Fixed by matching via `config_entry_id` through the entity registry
- **`handle_apply_field_fix` ambiguous match** — the fallback `msg.get("alias", item_alias)` always matched the first automation. Replaced with a two-pass priority system: HA numeric id first, then exact alias (case-sensitive then insensitive)
- **`_tool_ha_remove_automation` slug heuristic** — `alias.lower().replace(" ", "_")` could confuse similar automation names. Replaced with the same two-pass priority system
- **Dependency graph sidebar blank** — D3.js mutates edge `source`/`target` from strings to objects during simulation. The comparison `e.source === node.id` never matched. Fixed with `_edgeSrc(e)` / `_edgeTgt(e)` normalizers
- **Dependency graph sidebar data lost on refresh** — node data (`usedBy`, `uses`, `allNodes`) is now saved in `sb._hacaNodeData` so CSV/MD exports and node navigation work even after `_graphStopAll()` sets `_graphRawData = null`
- **Translation keys in wrong JSON section** — new keys were placed at root level (`graph.*`, `misc.*`) instead of under `panel.*` where `this.t()` looks. All 13 language files corrected; root-level orphan sections removed
- **`manifest.json` version** — was `1.5.0`, now `1.5.2`
- **Translation files** — 12 languages had 66–108 missing `panel.diag_prompts.*` keys; filled with EN fallback values (AI prompts — LLMs respond in the user's configured language regardless)
- **Automatic report check interval** — reduced from every hour to once per day (the check is cheap but unnecessary 24× per day)

### Security

- **`@require_admin`** on all destructive WebSocket handlers (18 handlers): `apply_fix`, `restore_backup`, `purge_recorder_orphans`, `apply_field_fix`, `chat`, `save_options`, `delete_history`, `ai_suggest_fix`, `set_log_level`, `agent_force_report`, `record_fix_outcome`, `get_battery_predictions`, `export_battery_csv`, `get_redundancy`, `get_recorder_impact`, `get_history_diff`, `scan_all`, `preview_fix`
- **Atomic YAML writes** — new `_atomic_write(path, content)` helper: writes to `.tmp` then `os.replace()`. No more risk of corrupted YAML if HA crashes mid-write
- **Path traversal protection** — `_tool_ha_get_config_file` and `_tool_ha_update_config_file` now use `os.path.realpath()` to resolve symlinks and `../` sequences before checking the config root boundary

### Removed

- **Compliance AI fix button** — the "Correctif IA" button in the Compliance tab has been removed. Compliance issues (missing names, icons, areas) do not require AI — use the HA editor directly
- **Dead code cleanup**:
  - `_agent_has_native_tools` + `_HA_BUILTIN_AGENTS` — obsolete since native LLM API handles tool routing
  - `_sanitize_tools_for_converse` — no longer needed; tools are injected natively
  - `_truncate_for_converse` — no longer needed; prompt is not sent via `async_converse`
  - `_async_find_llm_agent` — deprecated alias, no callers
  - `_HacaJsonEncoder` — was used by the removed `[HACA_ACTION:]` loop
  - 7 dead translation keys (`compliance.btn_ai_fix`, `compliance.ai_fix_*`) from all 13 language files
  - `conversation.py` reduced from 705 → 526 lines (−25%)

---

## [1.5.1] — 2026-03-12 — AI loop fixes, button routing and code quality

### Fixed

- **Agentic loop — break-on-success** — the loop was incorrectly stopping after the first successful tool call (e.g. `ha_backup_create`), preventing subsequent steps from executing. The loop now continues until the AI itself decides the task is complete
- **MAX_STEPS exhaustion** — when 12 steps are reached without a final text reply, the last useful tool result (`last_tool_summary`) is now returned to the user instead of the generic `ai_error` message
- **AI button routing — 74 issue types** — AI buttons were sending `explainWithAI()` for all types, hitting the generic API without MCP tools. `_buildActionPrompt()` now routes 66 types to Chat (imperative prompt + explicit tools) and 8 purely informational types to `explainWithAI()` as fallback
- **Intermediate modal — Redundancy** — `_showRedundancyAI()` no longer goes through a 3-step modal (suggestion → apply). Clicking "AI" now opens Chat directly with an imperative prompt
- **Intermediate modal — Area Map** — `_showAreaSuggestionAI()` same fix: direct to Chat without intermediate modal
- **Hardcoded FR/EN messages in `mcp_server.py`** — 6 messages returned to AI agents normalized to English

### Added

- **49 new tests** (386 → 435) covering critical modules that had no test file:
  - `test_mcp_server.py` (16 tests) — handler name consistency, 58/58 tool registry, NameError prevention, English-only messages
  - `test_websocket.py` (12 tests) — agentic loop, MAX_STEPS, break-on-success, result injection, system_prompt integrity
  - `test_js_integrity.py` (21 tests) — bundle freshness, zero suggestion patterns, translation key coverage, `_buildActionPrompt` coverage across 30 actionable issue types

---

## [1.5.0] — 2026-03-12 — Battery Predictor, Area Complexity, Redundancy Analyzer, Recorder Impact

### Added

- **Battery Predictor** (Module 18) — linear regression on HA history; predicts replacement dates; 7-day advance alerts; CSV export. **Predictions** sub-tab in Batteries
- **Area Complexity Analyzer** (Module 19) — composite complexity score per area; interactive heatmap; merge/split suggestions. **Area Map** sub-tab in Issues
- **Redundancy Analyzer** (Module 20) — logical overlaps, blueprint candidates (≥3 identical automations), native HA replacements. **Redundancies** sub-tab in Issues
- **Recorder Impact Analyzer** (Module 21) — writes/day, MB/year, copy-paste `recorder: exclude:` YAML block. **Impact** sub-tab in Recorder
- **Agentic loop raised to 12 steps**
- **12 MCP agents documented** in the configuration panel

### Changed

- Issues sub-tabs raised to 12; Recorder to 2; Batteries to 2

---

## [1.4.3] — 2026-03-11 — UI/UX fixes, compliance label unification, mobile improvements

### Fixed

- Compliance type labels unified across 13 languages
- Config buttons height on mobile
- Compliance list disappearing on auto-refresh
- Helpers tab icon (`cog-box` → `cog-outline`)
- Subtabs scroll on mobile
- Battery note contrast

### Added

- Compliance AI modal improvements (Details + Open settings buttons)
- Helpers compliance checks (`compliance_helper_no_icon`, `compliance_helper_no_area`)
- Entity no-area individual listing (up to 150, then bulk summary)
- Compliance section in Configuration (10 configurable check types)
- Pagination improvements (Page X/N, first/last page buttons)

---

## [1.4.2] — 2026-03-09 — Compliance analysis, Helpers tab, AI Chat and MCP server

### Added

- **Compliance tab** — metadata quality audit
- **Helpers tab** — all `input_*` and timers, unused-helper detection
- **AI Chat assistant** — conversational assistant with health context
- **MCP Server** — built-in Model Context Protocol server, 58 tools
- **`haca_ignore` label support**
- **13-language translation system** — complete rewrite

---

## [1.4.1] — 2026-03-09 — Responsive tabs, AI compliance modal and scan improvements

### Fixed

- AI compliance modal "Unknown command" error
- `analyze_all()` error handling
- `excluded_compliance_types` added to ALLOWED_KEYS

---

## [1.4.0] — 2026-03-09 — Script graph, scene analysis, group analyzer and blueprint candidates

### Added

- Script Graph Analyzer (Module 13)
- Advanced Scene Analyzer
- Blueprint Candidate Detection
- Group Analyzer (Module 14)
- 110 new unit tests

---

## [1.2.0] — 2026-03-08 — Multi-source automation scan, helper analysis and UX improvements

### Added

- Open Entity button
- Multi-source automation scan
- Input helpers analysis
- Template sensor analysis
- Timer helper analysis

---

## [1.1.1] — 2026-03-06 — Internationalization system rewrite

### Added

- 13-language internationalization system
- `haca_ignore` label support

---

## [1.0.0] — 2026-02-27 — First public release

### Added

- Automation Analyzer (Module 1)
- Entity Health Monitor (Module 2)
- Performance Analyzer (Module 3)
- Report Generator (Module 4)
- Refactoring Assistant (Module 5)
- AI Assistant (Module 6)
- Security Analyzer (Module 7)
- Dashboard Analyzer (Module 8)
- Event Monitoring (Module 9)
- Recorder Analyzer (Module 10)
- Audit History (Module 11)
- Dependency Graph (D3.js)
- Battery Monitor
- Global Health Score (HA sensor)
- 119 unit and regression tests
