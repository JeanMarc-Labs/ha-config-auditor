"""Reading the device registry the supported way — audit 5-3, the real cause.

`DeviceRegistry.devices` is no longer a mapping. Every mapping method left on
it is deprecated, and each call runs `report_usage`, which walks the whole
Python stack to name the calling integration. The warning it produces is
printed once, so the log stays quiet while the stack walk keeps happening —
`_build_target_indexes` looked one device up per registry entry and spent
**10.1 s of CPU on the event loop** doing it, on a Raspberry Pi 3 with 539
entities and twelve automations.

`_DeviceRegistryLikeHA` below models the new core: iterating yields the
entries, and every mapping method raises. So these tests do not check a
convention, they take the API away.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from homeassistant.helpers import device_registry as dr

from custom_components.config_auditor.entity_analyzer import EntityAnalyzer
from custom_components.config_auditor.registry_utils import iter_devices
from custom_components.config_auditor.tests.conftest import (
    MockDeviceEntry,
    MockHass,
    MockRegistryEntry,
)

PACKAGE = Path(__file__).parent.parent


class _DeprecatedMappingView:
    """A values view whose mapping methods cost a stack walk — so they raise."""

    def __init__(self, devices: dict):
        self._devices = devices

    def __iter__(self):
        return iter(self._devices.values())

    def __len__(self) -> int:
        return len(self._devices)

    def _reported(self, *args, **kwargs):
        raise AssertionError(
            "mapping access on device_registry.devices — that is the deprecated "
            "path, and every call walks the Python stack"
        )

    get = values = keys = items = get_entry = _reported
    __getitem__ = _reported
    __contains__ = _reported


class _DeviceRegistryLikeHA:
    """What `dr.async_get(hass)` returns on a current core."""

    def __init__(self, devices: list):
        self._devices = {device.id: device for device in devices}

    @property
    def devices(self):
        return _DeprecatedMappingView(self._devices)

    def async_get(self, device_id: str):
        return self._devices.get(device_id)


def _entity_analyzer(hass):
    with patch(
        "custom_components.config_auditor.entity_analyzer.TranslationHelper"
    ) as TH:
        TH.return_value.t = lambda key, **kw: key
        TH.return_value.async_load_language = AsyncMock()
        analyzer = EntityAnalyzer(hass)
    analyzer._ignored_entity_ids = set()
    return analyzer


# ── The helper ───────────────────────────────────────────────────────────────

class TestIterDevices:

    def test_a_current_core_yields_its_entries(self):
        devices = [MockDeviceEntry("dev1"), MockDeviceEntry("dev2")]
        registry = _DeviceRegistryLikeHA(devices)

        assert iter_devices(registry) == devices

    def test_an_older_core_still_works(self):
        """There, `devices` is a real mapping and iterating it yields the ids."""
        devices = {"dev1": MockDeviceEntry("dev1"), "dev2": MockDeviceEntry("dev2")}

        class _OldCore:
            devices = None

        old = _OldCore()
        old.devices = devices
        assert iter_devices(old) == list(devices.values())

    def test_nothing_to_read_is_not_an_error(self):
        class _Empty:
            devices = {}

        class _Missing:
            pass

        assert iter_devices(_Empty()) == []
        assert iter_devices(_Missing()) == []
        assert iter_devices(_DeviceRegistryLikeHA([])) == []


# ── The call site that cost the ten seconds ──────────────────────────────────

class TestTheTargetIndexes:

    def _hass(self, tmp_path, devices, entries):
        hass = MockHass(config_dir=str(tmp_path))
        for entry in entries:
            hass.add_registry_entry(entry)
        hass.data[dr.DATA_REGISTRY] = _DeviceRegistryLikeHA(devices)
        return hass

    def test_a_device_is_never_looked_up_through_the_mapping(self, tmp_path):
        """539 entries meant 539 stack walks. The view raises now, so a lookup
        that comes back would fail this test rather than cost ten seconds."""
        hass = self._hass(
            tmp_path,
            [MockDeviceEntry("dev1", area_id="kitchen", labels={"upstairs"})],
            [MockRegistryEntry(f"light.l{i}", device_id="dev1") for i in range(50)],
        )
        analyzer = _entity_analyzer(hass)

        by_device, by_area, by_label = analyzer._build_target_indexes()

        assert by_device["dev1"] == {f"light.l{i}" for i in range(50)}

    def test_an_entity_still_inherits_its_device_area_and_labels(self, tmp_path):
        hass = self._hass(
            tmp_path,
            [MockDeviceEntry("dev1", area_id="kitchen", labels={"upstairs"})],
            [MockRegistryEntry("light.one", device_id="dev1")],
        )
        analyzer = _entity_analyzer(hass)

        _by_device, by_area, by_label = analyzer._build_target_indexes()

        assert by_area["kitchen"] == {"light.one"}
        assert by_label["upstairs"] == {"light.one"}

    def test_the_entity_own_area_and_labels_still_win_and_add_up(self, tmp_path):
        hass = self._hass(
            tmp_path,
            [MockDeviceEntry("dev1", area_id="kitchen", labels={"upstairs"})],
            [
                MockRegistryEntry(
                    "light.one", device_id="dev1", area_id="hall", labels={"night"}
                )
            ],
        )
        analyzer = _entity_analyzer(hass)

        _by_device, by_area, by_label = analyzer._build_target_indexes()

        assert by_area["hall"] == {"light.one"}
        assert "kitchen" not in by_area
        assert by_label["night"] == {"light.one"}
        assert by_label["upstairs"] == {"light.one"}

    def test_an_entity_without_a_device_is_untouched(self, tmp_path):
        hass = self._hass(
            tmp_path, [], [MockRegistryEntry("light.orphan", area_id="hall")]
        )
        analyzer = _entity_analyzer(hass)

        by_device, by_area, _by_label = analyzer._build_target_indexes()

        assert by_device == {}
        assert by_area["hall"] == {"light.orphan"}


# ── The other per-scan reader ────────────────────────────────────────────────

class TestTheIgnoreSet:
    """`haca_ignore` on a device means every entity of that device is skipped,
    and that walk runs on every scan too."""

    @pytest.mark.asyncio
    async def test_a_labelled_device_still_silences_its_entities(self, tmp_path):
        from custom_components.config_auditor.translation_utils import (
            async_get_haca_ignored_entity_ids,
        )

        hass = MockHass(config_dir=str(tmp_path))
        hass.add_registry_entry(MockRegistryEntry("light.one", device_id="dev1"))
        hass.add_registry_entry(MockRegistryEntry("light.two", device_id="dev1"))
        hass.add_registry_entry(MockRegistryEntry("light.elsewhere"))
        hass.add_registry_entry(
            MockRegistryEntry("light.named", labels={"haca_ignore"})
        )
        hass.data[dr.DATA_REGISTRY] = _DeviceRegistryLikeHA(
            [MockDeviceEntry("dev1", labels={"haca_ignore"})]
        )

        ignored = await async_get_haca_ignored_entity_ids(hass)

        assert ignored == {"light.one", "light.two", "light.named"}


# ── And nowhere else in the package ──────────────────────────────────────────

def test_no_module_reaches_for_the_deprecated_mapping():
    """The whole point of registry_utils is that this stays true. Three call
    sites used it; the two that only enumerate cost one stack walk per scan,
    the third cost one per entity."""
    banned = re.compile(r"\.devices\s*(\[|\.\s*(get|values|keys|items|get_entry)\b)")
    offenders = []
    for path in sorted(PACKAGE.glob("*.py")):
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if banned.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")

    assert offenders == [], (
        "use iter_devices() to enumerate and DeviceRegistry.async_get() to look "
        "one up:\n" + "\n".join(offenders)
    )
