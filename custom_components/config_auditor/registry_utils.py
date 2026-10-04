"""Reading the device registry without paying for a deprecation warning.

Background: ``DeviceRegistry.devices`` used to be a mapping of device id to
entry. Home Assistant now returns a view over the entries instead, and every
mapping method left on it — ``get``, ``values``, ``[]``, ``in`` with a device
id — is deprecated and scheduled for removal in 2027.9. Each of those calls
goes through ``homeassistant.helpers.frame.report_usage``, which **walks the
whole Python stack** to work out which integration made the call.

The warning it produces is logged once per integration, which is what makes
this expensive to find: the log looks quiet while the stack walk keeps
happening on every single call. Audit 5-3 measured it on the user's Raspberry
Pi 3 — ``entity_analyzer._build_target_indexes`` looked up one device per
registry entry, 539 of them, and spent **10.1 seconds of CPU on the event
loop** doing so, for a config of twelve automations. The lookups themselves
are worth microseconds.

So: **never index or call a mapping method on ``dev_reg.devices``.** Look one
device up with ``DeviceRegistry.async_get(device_id)``, which reads the
underlying dict directly, and enumerate them with ``iter_devices`` below.

``disabled_automation_ids`` reads the entity registry, for the analyzers that
must tell an automation Home Assistant runs from one it never loads.
"""
from __future__ import annotations

from typing import Any

__all__ = ["iter_devices", "disabled_automation_ids"]


def iter_devices(dev_reg: Any) -> list[Any]:
    """Every device entry, on an old core and a new one.

    Iterating is the supported form and is never reported. On a new core it
    yields the entries themselves; on an older one ``devices`` is still a plain
    mapping, where iterating yields the device ids and subscripting is an
    ordinary dict lookup. The first item says which of the two we are holding.
    """
    container = getattr(dev_reg, "devices", None)
    if not container:
        return []
    items = list(container)
    if items and isinstance(items[0], str):
        # Old core: a real mapping. Subscripting it costs nothing there, and
        # this branch cannot be reached on a core that would report it.
        return [container[key] for key in items]
    return items


def disabled_automation_ids(ent_reg: Any) -> set[str]:
    """Automations whose entity is disabled in the entity registry.

    Disabling the entity is not turning the automation off. Home Assistant
    never adds a disabled entity to its platform, so the automation is not
    loaded at all: its triggers are never attached, it cannot run, and it has
    no state — which also takes it out of Settings → Automations, a list built
    from the state machine. Its configuration is still in automations.yaml,
    though, which is the file HACA audits. Users read that as "deleted", and
    HACA kept reporting problems in code that cannot execute.
    """
    return {
        entry.entity_id
        for entry in ent_reg.entities.values()
        if entry.entity_id.startswith("automation.")
        and getattr(entry, "disabled_by", None) is not None
    }
