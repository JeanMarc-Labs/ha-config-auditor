"""HACA Battery Library — battery-type lookup.

Provides battery_type and battery_quantity for a device given its
manufacturer/model from the HA device registry.

The library is bundled with the integration and covers ~2000 devices
(HACA-curated entries + the public Battery Notes library, MIT licence).
No external integration is required. Users extend it through their own
``haca_battery_library_user.json`` in the Home Assistant config folder —
outside the integration directory, which HACS replaces wholesale on every
update.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

_LOGGER = logging.getLogger(__name__)

_SEED_FILE_NAME = "battery_library_seed.json"
_USER_FILE_NAME = "haca_battery_library_user.json"


class BatteryLibrary:
    """Lookup of battery type/quantity by manufacturer + model.

    Reads the bundled seed, then the user's own file on top of it. A user
    entry that repeats a bundled manufacturer/model replaces it, so the
    bundled seed never has to be edited — and an entry added there survives
    the next HACA update, which the seed file does not.
    """

    def __init__(self, hass) -> None:
        self.hass = hass
        self._entries: list[dict] = []
        # manufacturer (normalised) -> entries, in library order. The
        # manufacturer is always compared for exact equality, so it makes a
        # perfect hash key: a lookup only ever walks the handful of entries
        # that share the device's brand instead of all ~2100 of them.
        self._by_manufacturer: dict[str, list[dict]] = {}
        self._user_count = 0
        self._loaded = False

    @property
    def _data_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    @property
    def _seed_path(self) -> str:
        return os.path.join(self._data_dir, _SEED_FILE_NAME)

    @property
    def _user_path(self) -> str:
        return os.path.join(self.hass.config.config_dir, _USER_FILE_NAME)

    async def async_load(self) -> None:
        """Load the bundled seed, then merge the user's own file over it."""
        seed = await self.hass.async_add_executor_job(self._load_from_disk, self._seed_path)
        user = await self.hass.async_add_executor_job(self._load_from_disk, self._user_path)
        self._entries = _merge_entries(seed or [], user or [])
        self._by_manufacturer = _build_index(self._entries)
        self._user_count = len(user or [])
        self._loaded = bool(self._entries)
        _LOGGER.info(
            "[HACA BatteryLib] Loaded %d entries (%d from %s)",
            len(self._entries), self._user_count, _USER_FILE_NAME,
        )

    def _load_from_disk(self, path: str) -> list[dict] | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("devices") or []
            return entries if isinstance(entries, list) else []
        except FileNotFoundError:
            return []
        except Exception as exc:
            _LOGGER.warning("[HACA BatteryLib] Failed to load %s: %s", path, exc)
            return []

    def lookup(self, manufacturer: str, model: str, hw_version: str = "") -> dict | None:
        """Return {'battery_type', 'battery_quantity'} or None if unknown.

        Entries are normalised once at load time and grouped by manufacturer,
        so this walks only the entries of the device's own brand. It used to
        scan the whole library and re-run ``strip().lower()`` on every field of
        every entry, for every device — around 640 000 iterations per scan on
        an installation with 300 battery devices.
        """
        if not manufacturer or not model:
            return None
        mfr = manufacturer.strip().lower()
        mdl = model.strip().lower()
        hw  = (hw_version or "").strip().lower()

        for entry in self._by_manufacturer.get(mfr, ()):
            e_mdl = entry[_K_MODEL]
            method = entry[_K_METHOD]
            if method == "exact":
                if e_mdl != mdl:
                    continue
            elif method == "startswith":
                if not mdl.startswith(e_mdl):
                    continue
            elif method == "endswith":
                if not mdl.endswith(e_mdl):
                    continue
            elif method == "contains":
                if e_mdl not in mdl:
                    continue
            e_hw = entry[_K_HW]
            if e_hw and e_hw != hw:
                continue
            btype = entry.get("battery_type", "")
            if btype in ("MANUAL", ""):
                continue
            return {
                "battery_type": btype,
                "battery_quantity": int(entry.get("battery_quantity", 1) or 1),
            }
        return None

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def user_count(self) -> int:
        """How many entries came from the user's own file."""
        return self._user_count

    @property
    def seed_path(self) -> str:
        """Public path of the bundled seed file (for the panel to display)."""
        return self._seed_path

    @property
    def user_path(self) -> str:
        """Public path of the user's own library file — the one to edit."""
        return self._user_path


# Normalised fields cached on each entry at load time. Prefixed so they cannot
# collide with a key coming from the JSON library.
_K_MODEL  = "_haca_model"
_K_HW     = "_haca_hw"
_K_METHOD = "_haca_method"


def _build_index(entries: list[dict]) -> dict[str, list[dict]]:
    """Normalise every entry once, then group them by manufacturer.

    Order inside a manufacturer bucket is the library order, so a user entry
    still shadows the bundled one it replaces — ``lookup`` takes the first
    match, exactly as it did over the flat list.
    """
    index: dict[str, list[dict]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        mfr = str(entry.get("manufacturer", "")).strip().lower()
        entry[_K_MODEL]  = str(entry.get("model", "")).strip().lower()
        entry[_K_HW]     = str(entry.get("hw_version", "")).strip().lower()
        entry[_K_METHOD] = str(entry.get("model_match_method", "exact") or "exact").strip().lower()
        index.setdefault(mfr, []).append(entry)
    return index


def _entry_key(entry: dict) -> tuple[str, str, str, str]:
    """Identity of a library entry, for user-over-seed replacement."""
    return (
        str(entry.get("manufacturer", "")).strip().lower(),
        str(entry.get("model", "")).strip().lower(),
        str(entry.get("hw_version", "")).strip().lower(),
        str(entry.get("model_match_method", "exact")).strip().lower(),
    )


def _merge_entries(seed: list[dict], user: list[dict]) -> list[dict]:
    """User entries first, then the bundled entries they do not replace.

    `lookup` takes the first match, so ordering alone would be enough to give
    the user the last word; dropping the shadowed seed entries as well keeps
    `size` honest and the scan a little shorter.
    """
    user_entries = [e for e in user if isinstance(e, dict)]
    shadowed = {_entry_key(e) for e in user_entries}
    return user_entries + [
        e for e in seed if isinstance(e, dict) and _entry_key(e) not in shadowed
    ]
