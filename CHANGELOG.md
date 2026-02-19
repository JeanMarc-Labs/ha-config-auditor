# Changelog

All notable changes to this project will be documented in this file.

## [1.1.1] - 2026-02-19

### Added
- **Frontend Panel**: Added "Edit" button to each issue that opens the Home Assistant native editor directly (automations, scripts, scenes). This allows users to manually edit items without going through AI proposals.
- **Translations (EN/FR)**: Added `edit_ha` key for the new Edit button.

## [1.1.0] - 2026-02-19

### Fixed
- **Automation Analyzer**: Fixed false positives on `template_simple_state` detection — now correctly checks for `has_complex_logic`, `has_other_functions`, and `has_jinja_filter` before reporting.
- **Performance Analyzer**: Added detection of expensive Jinja2 templates (`states | selectattr` without domain filter, `states | list` / `states | count` iterating all states). Added `import asyncio` and `import re` missing imports.
- **Entity Analyzer**: Fixed zombie entity detection — scripts are now scanned in addition to automations. Added optional `script_configs` parameter to `analyze_all()` and `_build_entity_references()`.
- **`__init__.py`**: Fixed wiring — `script_configs` from `automation_analyzer` is now correctly passed to `entity_analyzer` in all scan paths (`async_update_data`, `handle_scan_entities`, `_run_scan`).

### Added
- **Translations (EN/FR)**: Added 4 new keys for expensive template issues: `expensive_template_no_domain`, `add_domain_filter`, `expensive_template_states_all`, `filter_by_domain`.
- **Frontend Panel**: Added version display `V1.1.0` in the panel header.
- **Frontend Panel**: Added XSS protection via `escapeHtml()` on all user data injected into the DOM (`alias`, `entity_id`, `message`, `recommendation`, backup names).
- **Frontend Panel**: Added debounce pattern on scan buttons (`scanAll`, `scanAutomations`, `scanEntities`) to prevent double-click race conditions. Buttons re-enable 3 seconds after the service call resolves (not in `finally` block).

## [1.0.0] - 2026-02-15

### Added
- **Initial Release**
- **Core Analyzers**: Automation, Entity, Performance, and Security.
- **AI Assist**: Integrated explanations using HA Conversation Agent.
- **Refactoring Assistant**: Native UI to fix `device_id` and template issues.
- **Bilingual Interface**: Supporting English and French.
- **Cooperative Multitasking**: Optimized scan logic to prevent WebSocket timeouts.




