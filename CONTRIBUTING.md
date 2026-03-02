# Contributing to H.A.C.A

> 🇫🇷 [Version française](CONTRIBUTING.fr.md)

Thank you for your interest in H.A.C.A! This document explains how to contribute to the project.

---

## Table of contents

- [Code of conduct](#code-of-conduct)
- [How to contribute](#how-to-contribute)
- [Reporting a bug](#reporting-a-bug)
- [Suggesting an enhancement](#suggesting-an-enhancement)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Project structure](#project-structure)
- [Development environment](#development-environment)
- [Code conventions](#code-conventions)
- [Tests](#tests)

---

## Code of conduct

This project follows a simple code of conduct: **be respectful to other contributors**. All interactions should be constructive, kind, and focused on the project.

---

## How to contribute

There are several ways to contribute:

- **Report a bug** via [GitHub Issues](https://github.com/JeanMarc-Labs/ha-config-auditor/issues)
- **Suggest a new feature** via Issues (label `enhancement`)
- **Improve documentation** (README, code comments)
- **Submit a Pull Request** with a fix or a new feature
- **Test** the development version and share feedback

---

## Reporting a bug

Before opening an issue, check that it doesn't already exist.

**Required information:**

1. H.A.C.A version (visible in the panel → Configuration tab)
2. Home Assistant version
3. Precise description of observed vs. expected behavior
4. Steps to reproduce the bug
5. Relevant HA logs (enable debug mode in Configuration → Diagnostics & Logs)
6. Screenshot if relevant

```yaml
# To enable debug logs in configuration.yaml:
logger:
  logs:
    custom_components.config_auditor: debug
```

---

## Suggesting an enhancement

Open an issue with the `enhancement` label, describing:

- The problem the feature solves
- The expected behavior
- Concrete usage examples
- If possible, an implementation sketch

---

## Submitting a Pull Request

### Workflow

1. **Fork** the repository on GitHub
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/feature-name
   # or
   git checkout -b fix/bug-description
   ```
3. **Develop** following the conventions below
4. **Test**: all existing tests must pass
5. **Commit** with clear messages (see convention below)
6. **Push** and open a Pull Request targeting `main`

### Commit convention

```
type(scope): short description

feat(analyzer): add detection of restart-mode automations
fix(panel): fix scroll in AI proposal modal
docs(readme): update installation section
test(health_score): add edge cases for score=0 and score=100
refactor(websocket): extract scan logic into a dedicated function
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `style`, `chore`

### PR acceptance criteria

- All tests pass (`python3 -m pytest tests/ -v`)
- Code follows the conventions below
- PR includes a clear description of the change
- New features are documented

---

## Project structure

```
ha-config-auditor/
├── README.md                    # Main documentation (EN)
├── README.fr.md                 # Documentation (FR)
├── CONTRIBUTING.md              # Contribution guide (EN)
├── CONTRIBUTING.fr.md           # Contribution guide (FR)
├── CHANGELOG.md                 # Changelog
├── LICENSE                      # MIT License
├── hacs.json                    # HACS metadata
└── custom_components/
    └── config_auditor/
        ├── __init__.py          # Integration setup & teardown
        ├── manifest.json        # HA metadata
        ├── const.py             # Global constants
        ├── config_flow.py       # HA config flow
        ├── websocket.py         # WebSocket handlers (panel API)
        ├── services.py          # HA services
        ├── services.yaml        # Service schemas
        ├── sensor.py            # HA sensor entities
        ├── custom_panel.py      # Frontend panel registration
        ├── automation_analyzer.py
        ├── entity_analyzer.py
        ├── performance_analyzer.py
        ├── security_analyzer.py
        ├── dashboard_analyzer.py
        ├── recorder_analyzer.py
        ├── battery_monitor.py
        ├── dependency_mapper.py
        ├── refactoring_assistant.py
        ├── automation_optimizer.py
        ├── report_generator.py
        ├── history_manager.py
        ├── health_score.py
        ├── conversation.py      # AI Chat
        ├── event_monitor.py     # Event monitoring
        ├── translation_utils.py
        ├── models.py
        ├── translations/
        │   ├── fr.json
        │   └── en.json
        ├── www/
        │   └── haca-panel.js    # Frontend (compiled bundle)
        └── tests/
            ├── conftest.py
            └── test_*.py
```

The frontend source is in `www/src/` (not included in the HACS repository).  
To modify the frontend, clone the separate development repository.

---

## Development environment

### Requirements

- Python 3.12+
- Home Assistant in development mode or via Docker

### Setup

```bash
git clone https://github.com/JeanMarc-Labs/ha-config-auditor
cd ha-config-auditor/custom_components/config_auditor

# Install test dependencies
pip install pytest pytest-asyncio homeassistant PyYAML fpdf2 --break-system-packages
```

### Running tests

```bash
python3 -m pytest tests/ -v
# With short traceback
python3 -m pytest tests/ -v --tb=short
```

### Local deployment for testing

```bash
# Copy to your development HA instance
cp -r custom_components/config_auditor /config/custom_components/
# Restart HA
```

---

## Code conventions

### Python

- **Style**: strict PEP 8, lines ≤ 100 characters
- **Type hints**: required on all public functions
- **Docstrings**: Google format for all non-trivial functions
- **Logging**: use `_LOGGER = logging.getLogger(__name__)` in each module
- **Async**: all HA code must be async-safe
- **No `time.sleep()`** in HA code — use `asyncio.sleep()`

```python
# Good example
async def analyze_automation(
    hass: HomeAssistant,
    automation: dict[str, Any],
) -> list[Issue]:
    """Analyze an automation and return detected issues.

    Args:
        hass: Home Assistant instance.
        automation: Raw automation data.

    Returns:
        List of detected issues, empty if none.
    """
    ...
```

### JavaScript (frontend)

- **ES2020+**, no framework (Vanilla JS + Web Components)
- Public panel methods are documented with a `//` comment
- WebSocket calls go through `this._hass.callWS()`
- Service calls go through `this._hass.callService()`
- Always check `this._hass` before use

---

## Tests

### Organization

```
tests/
├── conftest.py                    # Shared fixtures (HA mocks)
├── test_automation_analyzer.py    # Automation analyzer tests
├── test_health_score.py           # Health score tests
├── test_infrastructure.py         # Integration setup/teardown tests
├── test_models.py                 # Data model tests
├── test_refactoring_assistant.py  # Auto-fix tests
├── test_event_monitor.py          # Event monitoring tests
└── test_repairs.py                # Repairs module tests (skipped)
```

### Writing a test

```python
import pytest
from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer

async def test_detects_device_id_in_trigger(mock_hass):
    """Verifies that device_id usage in triggers is detected."""
    automation = {
        "id": "test_auto",
        "alias": "Test",
        "trigger": [{"platform": "device", "device_id": "abc123"}],
        "action": [],
    }
    analyzer = AutomationAnalyzer(mock_hass)
    issues = await analyzer.analyze_automation(automation)
    assert any(i.type == "device_id_in_trigger" for i in issues)
```

---

## Questions?

Open a [GitHub Discussion](https://github.com/JeanMarc-Labs/ha-config-auditor/discussions) for any question that is not a bug report or feature request.
