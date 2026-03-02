# Changelog — H.A.C.A

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.2/)  
Versioning: [Semantic Versioning](https://semver.org/)

---
## [1.0.2] — 2026-03-02 — Hard text internationalization and bug fixing

## [1.0.1] — 2026-03-01 — Internationalization of hard texts

## [1.0.0] — 2026-02-27 — First public release

### Added

- **Automation Analyzer** (Module 1) — `device_id` detection, incorrect modes, unknown services, broken references, exact and functional duplicates
- **Entity Health Monitor** (Module 2) — ghost entities, unavailable, disabled-but-referenced, registry duplicates
- **Performance Analyzer** (Module 3) — high-frequency automations, high-refresh templates, loop patterns
- **Report Generator** (Module 4) — timestamped MD, JSON and PDF reports in `/config/haca_reports/`
- **Refactoring Assistant** (Module 5) — automatic `device_id → entity_id`, mode, and simple template fixes; YAML backup before each correction
- **AI Assistant** (Module 6) — issue explanation and suggestions via HA AI Task (OpenAI, Google Generative AI, Ollama…)
- **Security Analyzer** (Module 7) — unwanted exposures and bad practice detection
- **Dashboard Analyzer** (Module 9) — missing entities in Lovelace views
- **Event Monitoring** (Module 10) — debounced auto-scan on HA config changes
- **Recorder Analyzer** (Module 11) — orphaned entities in SQLite, wasted space estimation, one-click purge
- **Audit History** (Module 12) — timestamped snapshots, health score trend chart, individual/bulk deletion
- **Dependency Graph** — D3.js force-directed visualization, filters by type/issues, SVG and PNG export
- **Battery Monitor** — full battery table with severity-based alerts
- **Global Health Score** — 0–100 score computed across all issues, displayed with trend indicator
- **Automation Complexity** — ranked by complexity score with detailed metrics
- Custom HA panel with 10 main tabs and per-category sub-tabs
- Severity filters (HIGH / MEDIUM / LOW) and CSV export on all issue lists
- Full-text search in the dependency graph
- Persistent HA notifications for newly detected HIGH issues
- French / English multilingual support
- HA config flow with configurable options (scan interval, startup delay, event monitoring)
- **Debug mode** — persistent toggle in Configuration tab, applied at startup and on save
- 86 unit and regression tests


