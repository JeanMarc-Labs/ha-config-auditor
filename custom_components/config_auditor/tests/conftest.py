"""Shared fixtures and helpers for the H.A.C.A tests.

Run with:
    pip install -r requirements_test.txt
    pytest custom_components/config_auditor/tests -q

Home Assistant itself is required: MockHass below pre-populates hass.data with
the real entity/device registry singleton keys, so the analyzers reach our mocks
instead of building empty registries. Everything else about HA is stubbed here.
"""
from __future__ import annotations

import re
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

# ── Make custom_components importable ────────────────────────────────────────
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

_WWW = Path(__file__).parent.parent / "www"
_BUNDLE_NAME_RE = re.compile(r"haca-panel\.[0-9a-f]{8}\.js")


def panel_bundle_path() -> Path:
    """The one bundle www/build.sh emits, named after the hash of its contents.

    Resolved the way custom_panel.py resolves it: through haca-panel.hash, then
    by scanning for a hashed bundle if that file is missing or stale. When there
    is none, the name that should have been there is returned so the caller's
    assertion fails with something readable rather than on a bare FileNotFound.
    """
    try:
        cache_bust = (_WWW / "haca-panel.hash").read_text(encoding="utf-8").strip()
    except OSError:
        cache_bust = ""
    if cache_bust and (_WWW / f"haca-panel.{cache_bust}.js").is_file():
        return _WWW / f"haca-panel.{cache_bust}.js"
    found = sorted(p for p in _WWW.glob("haca-panel.*.js") if _BUNDLE_NAME_RE.fullmatch(p.name))
    return found[0] if found else _WWW / f"haca-panel.{cache_bust or '<no hash file>'}.js"


_MCP_PKG = Path(__file__).parent.parent / "mcp_server"

# The reading order of the package: plumbing, then data, then the tool modules,
# then the assembly and the HTTP surface. Several tests slice the source between
# two landmarks, so this order is part of what they assert.
_MCP_MODULES = (
    "common", "schemas",
    "tools_system", "tools_audit", "tools_history", "tools_registry",
    "tools_automation", "tools_script_scene", "tools_blueprint", "tools_lovelace",
    "catalog", "views", "__init__",
)


def mcp_package_files() -> list[Path]:
    """Every module of the mcp_server package, in reading order.

    Used by the tests that must parse or compile each file on its own — a
    concatenation is not valid Python, every module opens with __future__.
    """
    files = [_MCP_PKG / f"{name}.py" for name in _MCP_MODULES]
    missing = [p.name for p in files if not p.is_file()]
    extra = sorted(p.name for p in _MCP_PKG.glob("*.py") if p not in files)
    assert not missing, f"mcp_server package is missing {missing}"
    assert not extra, f"mcp_server gained {extra} — add it to conftest._MCP_MODULES"
    return files


def mcp_package_source() -> str:
    """The whole MCP server as one string, for the source-level guards.

    mcp_server was a single 6 000-line file until the 1.8.0 split; the checks
    that used to grep it now grep the package, so a handler cannot escape them
    by moving to another module.
    """
    return "\n".join(p.read_text(encoding="utf-8") for p in mcp_package_files())


# ═══════════════════════════════════════════════════════════════════════════
# Minimal HA object stubs
# ═══════════════════════════════════════════════════════════════════════════

class MockState:
    def __init__(self, entity_id: str, state: str = "on", attributes: dict | None = None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        # Provide a recent last_updated so stale-entity checks don't fire
        self.last_updated = datetime.now(tz=timezone.utc)


class _MockStatesProxy:
    def __init__(self, store: dict):
        self._store = store

    def get(self, entity_id: str):
        return self._store.get(entity_id)

    def async_entity_ids(self, domain: str):
        return [eid for eid in self._store if eid.startswith(domain + ".")]

    def async_all(self):
        return list(self._store.values())


class MockRegistryEntry:
    """Minimal entity registry entry with label support."""

    def __init__(
        self,
        entity_id: str,
        *,
        labels: set | None = None,
        disabled_by=None,
        device_id: str | None = None,
        platform: str = "test",
        unique_id: str | None = None,
        config_entry_id: str | None = None,
        area_id: str | None = None,
    ):
        self.entity_id = entity_id
        self.labels: set = labels or set()
        self.disabled_by = disabled_by
        self.device_id = device_id
        self.platform = platform
        self.unique_id = unique_id or entity_id
        self.config_entry_id = config_entry_id
        self.area_id = area_id
        self.domain = entity_id.split(".")[0] if "." in entity_id else "unknown"


class _MockEntityItems(dict):
    """Dict subclass that also implements get_entries_for_device_id."""

    def get_entries_for_device_id(self, device_id: str) -> list:
        return [e for e in self.values() if getattr(e, "device_id", None) == device_id]


class MockEntityRegistry:
    """Minimal entity registry mock."""

    def __init__(self, entries: list | None = None):
        self._entries: _MockEntityItems = _MockEntityItems()
        for e in (entries or []):
            self._entries[e.entity_id] = e

    @property
    def entities(self) -> _MockEntityItems:
        return self._entries

    def async_get(self, entity_id: str):
        return self._entries.get(entity_id)

    def add(self, entry) -> None:
        self._entries[entry.entity_id] = entry


class MockDeviceEntry:
    def __init__(self, device_id: str, *, labels: set | None = None, area_id: str | None = None):
        self.id = device_id
        self.labels: set = labels or set()
        self.area_id = area_id


class MockDeviceRegistry:
    """Minimal device registry mock."""

    def __init__(self, devices: list | None = None):
        self._devices: dict = {}
        for d in (devices or []):
            self._devices[d.id] = d

    @property
    def devices(self) -> dict:
        return self._devices

    def async_get(self, device_id: str):
        return self._devices.get(device_id)


class MockHass:
    """Minimal HomeAssistant mock sufficient for all HACA unit tests.

    Crucially, pre-populates hass.data with the entity/device registry keys
    so that er.async_get(hass) / dr.async_get(hass) via @singleton return
    our mocks instead of creating empty unloaded EntityRegistry instances.
    """

    def __init__(self, config_dir: str = "/tmp/haca_test"):
        from homeassistant.helpers import entity_registry as er, device_registry as dr

        self.config = MagicMock()
        self.config.config_dir = config_dir
        self.config.language = "en"
        self._states: dict = {}
        self.states = _MockStatesProxy(self._states)
        self.loop = MagicMock()
        self.bus = MagicMock()
        self.config_entries = MagicMock()
        self.config_entries.async_entries = MagicMock(return_value=[])
        self.services = MagicMock()
        self.services.async_call = AsyncMock(return_value=None)
        self._entity_registry = MockEntityRegistry()
        self._device_registry = MockDeviceRegistry()

        # Pre-populate hass.data so er/dr @singleton returns our mocks
        self.data: dict = {
            er.DATA_REGISTRY: self._entity_registry,
            dr.DATA_REGISTRY: self._device_registry,
        }

    def add_state(self, entity_id: str, state: str = "on", attributes: dict | None = None):
        self._states[entity_id] = MockState(entity_id, state, attributes or {})

    def add_registry_entry(self, entry: MockRegistryEntry) -> None:
        self._entity_registry.add(entry)
        # A disabled entity is in the registry and nowhere else: Home Assistant
        # never loads it, so it has no state. Handing it one here would hide
        # every bug that comes from reading the state machine alone.
        if entry.disabled_by is not None:
            self._states.pop(entry.entity_id, None)
            return
        if entry.entity_id not in self._states:
            self._states[entry.entity_id] = MockState(entry.entity_id)

    def add_device(self, device: MockDeviceEntry) -> None:
        self._device_registry._devices[device.id] = device

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        """No-op in tests — swallows background tasks like _auto_backup."""
        import asyncio
        try:
            coro.close()
        except Exception:
            pass
        return asyncio.Future()


# ═══════════════════════════════════════════════════════════════════════════
# Pytest fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_hass(tmp_path):
    """MockHass with a temporary config directory and standard YAML stubs."""
    hass = MockHass(config_dir=str(tmp_path))
    (tmp_path / "automations.yaml").write_text("[]", encoding="utf-8")
    (tmp_path / "scripts.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "scenes.yaml").write_text("[]", encoding="utf-8")
    return hass


@pytest.fixture
def mock_hass_fr(tmp_path):
    """French-language MockHass."""
    hass = MockHass(config_dir=str(tmp_path))
    hass.config.language = "fr"
    hass.data["config_auditor"] = {"user_language": "fr"}
    (tmp_path / "automations.yaml").write_text("[]", encoding="utf-8")
    (tmp_path / "scripts.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "scenes.yaml").write_text("[]", encoding="utf-8")
    return hass


@pytest.fixture
def translations_dir():
    return Path(__file__).parent.parent / "translations"


@pytest.fixture
def en_translations(translations_dir):
    with open(translations_dir / "en.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fr_translations(translations_dir):
    with open(translations_dir / "fr.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_automation():
    return {
        "id": "test_auto_001",
        "alias": "Test Automation",
        "description": "A test automation",
        "mode": "single",
        "triggers": [{"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
        "conditions": [],
        "actions": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
    }


@pytest.fixture
def god_automation():
    actions = [
        {"service": "light.turn_on", "target": {"entity_id": f"light.room_{i}"}}
        for i in range(20)
    ]
    actions += [
        {"condition": "state", "entity_id": f"sensor.temp_{i}", "state": "high"}
        for i in range(5)
    ]
    return {
        "id": "god_auto_001",
        "alias": "God Automation",
        "triggers": [
            {"platform": "state", "entity_id": f"sensor.motion_{i}"}
            for i in range(6)
        ],
        "conditions": [
            {"condition": "state", "entity_id": "input_boolean.enabled", "state": "on"},
        ] * 4,
        "actions": actions,
    }


# ── pytest-asyncio configuration ────────────────────────────────────────────
import pytest

def pytest_configure(config):
    """Register asyncio_mode so @pytest.mark.asyncio works without warnings."""
    try:
        config.addinivalue_line("markers", "asyncio: mark test as async")
    except Exception:
        pass
