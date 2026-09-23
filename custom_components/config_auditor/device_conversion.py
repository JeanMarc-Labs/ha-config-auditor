"""A device trigger, condition or action, rewritten on its entity -- the way HA runs it.

A device block is a thin wrapper. Each entity domain's ``device_trigger``,
``device_condition`` and ``device_action`` module turns it, at run time, into a
state or numeric_state trigger, a state condition, or a service call on one
entity. The tables below mirror those modules as of Home Assistant 2026.9, so
the replacement does exactly what the device block did -- down to the ``for:``
it passes on or ignores, and the ``id:`` a ``choose:`` reads back.

What they do not cover stays as it is, with the reason. An integration's own
device trigger -- a ZHA button press, an MQTT event -- has no entity to watch,
and an unknown type has no known equivalent. Guessing one used to be the
fallback: the device's first entity, a state trigger with no ``to:``, every
unknown key poured into ``data:``. Home Assistant's validator accepts all of
those, and the automation then does something else.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
import functools
from typing import Any, NamedTuple

from homeassistant.helpers import entity_registry as er


class Conversion(NamedTuple):
    """The entity-based replacement, or None, and a note saying which or why."""

    new: dict | None
    note: str


# Keys every trigger, condition or action may carry, whatever its type: a
# trigger's `id` is what `trigger.id` reads back, so dropping it breaks the
# `choose:` built on it.
_TRIGGER_KEEP = ("id", "alias", "enabled", "variables")
_CONDITION_KEEP = ("alias", "enabled")
_ACTION_KEEP = ("alias", "enabled", "continue_on_error")

_NO_EQUIVALENT = "no entity-based equivalent is known for this type"


# -- Triggers -----------------------------------------------------------------

_TOGGLE_TRIGGERS = {"turned_on": "on", "turned_off": "off"}

# Device trigger type -> the `to:` of the state trigger HA attaches.
_TRIGGER_TO: dict[str, dict[str, str]] = {
    "alarm_control_panel": {
        t: t for t in (
            "triggered", "disarmed", "arming",
            "armed_home", "armed_away", "armed_night", "armed_vacation",
        )
    },
    "cover": {"opened": "open", "closed": "closed", "opening": "opening", "closing": "closing"},
    "lock": {
        t: t for t in ("jammed", "locked", "locking", "open", "opening", "unlocked", "unlocking")
    },
    "media_player": {
        **_TOGGLE_TRIGGERS,
        "buffering": "buffering", "idle": "idle", "paused": "paused", "playing": "playing",
    },
    "vacuum": {"cleaning": "cleaning", "docked": "docked"},
    **{d: _TOGGLE_TRIGGERS for d in ("fan", "humidifier", "light", "remote", "switch", "update")},
}

# `changed_states`: any change of state, not of an attribute -- `to: null`.
_CHANGED_STATES = {"fan", "humidifier", "light", "media_player", "remote", "switch", "update"}

# Device trigger type -> (attribute read, whether HA passes `for:` on).
_TRIGGER_NUMERIC: dict[str, dict[str, tuple[str | None, bool]]] = {
    "climate": {
        "current_temperature_changed": ("current_temperature", True),
        "current_humidity_changed": ("current_humidity", True),
    },
    "cover": {
        "position": ("current_position", False),
        "tilt_position": ("current_tilt_position", False),
    },
    "humidifier": {
        "target_humidity_changed": ("humidity", True),
        "current_humidity_changed": ("current_humidity", True),
    },
}


def _trigger(domain: str, kind: str, config: Mapping, entity_id: str) -> tuple[str, dict] | None:
    """The platform and fields of the trigger HA attaches, or None."""
    platform, body, passes_for = "state", {"entity_id": entity_id}, True

    if domain == "binary_sensor":
        on_types, off_types = _binary_sensor_types("device_trigger", "TURNED_ON", "TURNED_OFF")
        if kind not in on_types and kind not in off_types:
            return None
        body["to"] = "on" if kind in on_types else "off"
    elif kind in _TRIGGER_TO.get(domain, {}):
        body["to"] = _TRIGGER_TO[domain][kind]
    elif kind == "changed_states" and domain in _CHANGED_STATES:
        body["to"] = None
    elif domain == "climate" and kind == "hvac_mode_changed":
        modes = _hvac_modes()
        if config.get("to") not in modes:
            return None
        # From every other mode, not from `unavailable`: that is what HA attaches.
        body["from"] = [mode for mode in modes if mode != config["to"]]
        body["to"] = config["to"]
    elif domain == "select" and kind == "current_option_changed":
        body.update({k: config[k] for k in ("from", "to") if k in config})
    elif domain == "button" and kind == "pressed":
        passes_for = False
    elif domain == "device_tracker" and kind in ("enters", "leaves"):
        if "zone" not in config:
            return None
        return "zone", {
            "entity_id": entity_id,
            "zone": config["zone"],
            "event": "enter" if kind == "enters" else "leave",
        }
    elif (numeric := _numeric_trigger(domain, kind)) is not None:
        attribute, passes_for = numeric
        bounds = {k: config[k] for k in ("above", "below") if k in config}
        if not bounds:
            return None
        platform = "numeric_state"
        if attribute:
            body["attribute"] = attribute
        body.update(bounds)
    else:
        return None

    if passes_for and "for" in config:
        body["for"] = config["for"]
    return platform, body


def _numeric_trigger(domain: str, kind: str) -> tuple[str | None, bool] | None:
    if domain == "sensor":
        return None, True  # every sensor trigger type is a numeric_state on the state
    return _TRIGGER_NUMERIC.get(domain, {}).get(kind)


def convert_trigger(hass: Any, trigger: Mapping) -> Conversion:
    """The state, numeric_state or zone trigger a device trigger stands for."""
    domain, kind = str(trigger.get("domain", "")), str(trigger.get("type", ""))
    entity_id, why = _entity(hass, trigger, domain, "an event")
    if entity_id is None:
        return Conversion(None, f"{domain}.{kind}: {why}")
    found = _trigger(domain, kind, trigger, entity_id)
    if found is None:
        return Conversion(None, f"{domain}.{kind}: {_NO_EQUIVALENT}")

    platform, body = found
    # The same key the device trigger used: `trigger:` since HA 2024.10,
    # `platform:` before -- both still load.
    key = "trigger" if "trigger" in trigger else "platform"
    new = {key: platform, **body, **_kept(trigger, _TRIGGER_KEEP)}
    return Conversion(new, f"{domain}.{kind} → {platform} trigger on {_describe(body)}")


# -- Conditions ---------------------------------------------------------------

_TOGGLE_CONDITIONS = {"is_on": "on", "is_off": "off"}

# Device condition type -> the state the entity must be in.
_CONDITION_STATE: dict[str, dict[str, str | list[str]]] = {
    "alarm_control_panel": {
        f"is_{s}": s for s in (
            "triggered", "disarmed", "armed_home", "armed_away",
            "armed_night", "armed_vacation", "armed_custom_bypass",
        )
    },
    "cover": {"is_open": "open", "is_closed": "closed", "is_opening": "opening", "is_closing": "closing"},
    "device_tracker": {"is_home": "home"},
    "lock": {
        f"is_{s}": s for s in ("jammed", "locked", "locking", "open", "opening", "unlocked", "unlocking")
    },
    "media_player": {
        **_TOGGLE_CONDITIONS,
        "is_buffering": "buffering", "is_idle": "idle", "is_paused": "paused", "is_playing": "playing",
    },
    "vacuum": {"is_docked": ["docked"], "is_cleaning": ["cleaning", "returning"]},
    **{d: _TOGGLE_CONDITIONS for d in ("fan", "humidifier", "light", "remote", "switch")},
}

# Domains whose device condition passes `for:` on (the others' schemas refuse it).
_CONDITION_FOR = {"binary_sensor", "humidifier", "light", "remote", "select", "switch"}

# Device condition type -> (attribute compared, config key holding the value).
_CONDITION_ATTRIBUTE: dict[str, dict[str, tuple[str | None, str]]] = {
    "climate": {"is_hvac_mode": (None, "hvac_mode"), "is_preset_mode": ("preset_mode", "preset_mode")},
    "humidifier": {"is_mode": ("mode", "mode")},
    "select": {"selected_option": (None, "option")},
}

_CONDITION_POSITION = {"is_position": "current_position", "is_tilt_position": "current_tilt_position"}


def _condition(domain: str, kind: str, config: Mapping, entity_id: str) -> dict | None:
    """The condition HA evaluates, or None."""
    body: dict[str, Any] = {"condition": "state", "entity_id": entity_id}

    if domain == "binary_sensor":
        on_types, off_types = _binary_sensor_types("device_condition", "IS_ON", "IS_OFF")
        if kind not in on_types and kind not in off_types:
            return None
        body["state"] = "on" if kind in on_types else "off"
    elif kind in _CONDITION_STATE.get(domain, {}):
        body["state"] = _CONDITION_STATE[domain][kind]
    elif domain == "device_tracker" and kind == "is_not_home":
        return {"condition": "not", "conditions": [{**body, "state": "home"}]}
    elif kind in _CONDITION_ATTRIBUTE.get(domain, {}):
        attribute, value_key = _CONDITION_ATTRIBUTE[domain][kind]
        if value_key not in config:
            return None
        if attribute:
            body["attribute"] = attribute
        body["state"] = config[value_key]
    elif domain == "sensor" or (domain == "cover" and kind in _CONDITION_POSITION):
        bounds = {k: config[k] for k in ("above", "below") if k in config}
        if not bounds:
            return None
        body["condition"] = "numeric_state"
        if domain == "cover":
            body["attribute"] = _CONDITION_POSITION[kind]
        return {**body, **bounds}
    else:
        return None

    if domain in _CONDITION_FOR and "for" in config:
        body["for"] = config["for"]
    return body


def convert_condition(hass: Any, condition: Mapping) -> Conversion:
    """The state or numeric_state condition a device condition stands for."""
    domain, kind = str(condition.get("domain", "")), str(condition.get("type", ""))
    entity_id, why = _entity(hass, condition, domain, "a check")
    if entity_id is None:
        return Conversion(None, f"{domain}.{kind}: {why}")
    body = _condition(domain, kind, condition, entity_id)
    if body is None:
        return Conversion(None, f"{domain}.{kind}: {_NO_EQUIVALENT}")
    new = {**body, **_kept(condition, _CONDITION_KEEP)}
    return Conversion(new, f"{domain}.{kind} → {body['condition']} condition on {_describe(body)}")


# -- Actions ------------------------------------------------------------------

def _fields(*names: str) -> Callable[[Mapping], dict]:
    """Copy required fields into the service data; a missing one raises KeyError."""
    return lambda config: {name: config[name] for name in names}


def _nothing(config: Mapping) -> dict:
    return {}


def _alarm_code(config: Mapping) -> dict:
    return {"code": config["code"]} if "code" in config else {}


def _light_turn_on(config: Mapping) -> dict:
    """light/device_action.py: every `turn_on` flavour is a light.turn_on."""
    kind, data = config["type"], {}
    if kind == "brightness_increase":
        data["brightness_step_pct"] = 10
    elif kind == "brightness_decrease":
        data["brightness_step_pct"] = -10
    elif "brightness_pct" in config:
        data["brightness_pct"] = config["brightness_pct"]
    if kind == "flash":
        data["flash"] = config.get("flash", "short")
    return data


def _cycle(config: Mapping) -> dict:
    return {"cycle": config.get("cycle", True)}  # the schema's default


_TOGGLE_ACTIONS = {t: (t, _nothing) for t in ("turn_on", "turn_off", "toggle")}

# Device action type -> (service in the entity's domain, service data builder).
_ACTIONS: dict[str, dict[str, tuple[str, Callable[[Mapping], dict]]]] = {
    "alarm_control_panel": {
        "arm_away": ("alarm_arm_away", _alarm_code),
        "arm_home": ("alarm_arm_home", _alarm_code),
        "arm_night": ("alarm_arm_night", _alarm_code),
        "arm_vacation": ("alarm_arm_vacation", _alarm_code),
        "disarm": ("alarm_disarm", _alarm_code),
        "trigger": ("alarm_trigger", _alarm_code),
    },
    "button": {"press": ("press", _nothing)},
    "climate": {
        "set_hvac_mode": ("set_hvac_mode", _fields("hvac_mode")),
        "set_preset_mode": ("set_preset_mode", _fields("preset_mode")),
    },
    "cover": {
        "open": ("open_cover", _nothing),
        "close": ("close_cover", _nothing),
        "stop": ("stop_cover", _nothing),
        "open_tilt": ("open_cover_tilt", _nothing),
        "close_tilt": ("close_cover_tilt", _nothing),
        "set_position": ("set_cover_position", lambda c: {"position": c["position"]}),
        # The device action names it `position` for the tilt too.
        "set_tilt_position": ("set_cover_tilt_position", lambda c: {"tilt_position": c["position"]}),
    },
    "fan": _TOGGLE_ACTIONS,
    "humidifier": {
        **_TOGGLE_ACTIONS,
        "set_humidity": ("set_humidity", _fields("humidity")),
        "set_mode": ("set_mode", _fields("mode")),
    },
    "light": {
        "turn_off": ("turn_off", _nothing),
        "toggle": ("toggle", _nothing),
        **{t: ("turn_on", _light_turn_on) for t in ("turn_on", "brightness_increase", "brightness_decrease", "flash")},
    },
    "lock": {t: (t, _nothing) for t in ("lock", "unlock", "open")},
    "number": {"set_value": ("set_value", _fields("value"))},
    "remote": _TOGGLE_ACTIONS,
    "select": {
        "select_option": ("select_option", _fields("option")),
        "select_first": ("select_first", _nothing),
        "select_last": ("select_last", _nothing),
        "select_next": ("select_next", _cycle),
        "select_previous": ("select_previous", _cycle),
    },
    "switch": _TOGGLE_ACTIONS,
    "text": {"set_value": ("set_value", _fields("value"))},
    "vacuum": {"clean": ("start", _nothing), "dock": ("return_to_base", _nothing)},
    "water_heater": {t: (t, _nothing) for t in ("turn_on", "turn_off")},
}


def convert_action(hass: Any, action: Mapping, *, service_key: str) -> Conversion:
    """The service call a device action makes, on its entity.

    *service_key* is `action` or `service`, whichever the automation's other
    actions use (`action:` needs HA 2024.8).
    """
    domain, kind = str(action.get("domain", "")), str(action.get("type", ""))
    entity_id, why = _entity(hass, action, domain, "an action")
    if entity_id is None:
        return Conversion(None, f"{domain}.{kind}: {why}")
    found = _ACTIONS.get(domain, {}).get(kind)
    if found is None:
        return Conversion(None, f"{domain}.{kind}: {_NO_EQUIVALENT}")
    service, build = found
    try:
        data = build(action)
    except KeyError as missing:
        return Conversion(None, f"{domain}.{kind}: the device action has no {missing}")

    new: dict[str, Any] = {service_key: f"{domain}.{service}", "target": {"entity_id": entity_id}}
    if data:
        new["data"] = data
    new.update(_kept(action, _ACTION_KEEP))
    return Conversion(new, f"{domain}.{kind} → {domain}.{service} on {entity_id}")


def convert_device_target(hass: Any, action: Mapping) -> Conversion:
    """A service call's `target: device_id:`, as the entities HA would act on.

    Home Assistant expands a device target to the device's entities -- and its
    child devices', minus hidden, disabled, config and diagnostic ones -- then
    the service keeps those of its own domain. A service that acts through
    another domain (`homeassistant.turn_on`, `zwave_js.set_value`) has no such
    list to write down, and stays as it is.
    """
    service_key = "action" if "action" in action else "service"
    service = action.get(service_key)
    target = action.get("target")
    if not isinstance(service, str) or not isinstance(target, Mapping):
        return Conversion(None, "target.device_id: the action names no service")
    device_ids = target.get("device_id")
    device_ids = [device_ids] if isinstance(device_ids, str) else list(device_ids or [])
    if not device_ids or any(not isinstance(d, str) or "{" in d for d in [service, *device_ids]):
        return Conversion(None, "target.device_id: a template, resolved only when the action runs")

    domain = service.split(".", 1)[0]
    if domain == "homeassistant":
        return Conversion(None, f"target.device_id: {service} acts on every domain of the device")
    entities = sorted(e for e in _device_entities(hass, device_ids) if e.split(".", 1)[0] == domain)
    if not entities:
        return Conversion(None, f"target.device_id: no {domain} entity on the device for {service} to act on")

    new = copy.deepcopy(dict(action))
    new_target = dict(target)
    del new_target["device_id"]
    existing = new_target.get("entity_id")
    existing = [existing] if isinstance(existing, str) else list(existing or [])
    merged = existing + [e for e in entities if e not in existing]
    new_target["entity_id"] = merged[0] if len(merged) == 1 else merged
    new["target"] = new_target
    return Conversion(new, f"{service}: target.device_id → target.entity_id: {', '.join(entities)}")


def convert(hass: Any, section: str, item: Mapping, *, service_key: str = "action") -> Conversion | None:
    """The conversion of one trigger, condition or action, or None if it names no device."""
    if not isinstance(item, Mapping):
        return None
    if section == "trigger":
        return convert_trigger(hass, item) if "device_id" in item else None
    if section == "condition":
        return convert_condition(hass, item) if "device_id" in item else None
    if "device_id" in item and "domain" in item:
        return convert_action(hass, item, service_key=service_key)
    target = item.get("target")
    if isinstance(target, Mapping) and "device_id" in target:
        return convert_device_target(hass, item)
    return None


# -- Shared -------------------------------------------------------------------

def _entity(hass: Any, config: Mapping, domain: str, what: str) -> tuple[str | None, str]:
    """The entity a device block acts on, resolved from its registry id."""
    raw = config.get("entity_id")
    if not isinstance(raw, str):
        # Entity-based device automations always carry one; an integration's
        # own (ZHA, MQTT, Hue remote...) never does.
        return None, f"{what} of the {domain} integration itself, with no entity equivalent"
    entity_id = er.async_resolve_entity_id(er.async_get(hass), raw)
    if entity_id is None:
        return None, "its entity is no longer in the registry"
    if entity_id.split(".", 1)[0] != domain:
        return None, f"{entity_id} is not a {domain} entity"
    return entity_id, ""


def _kept(config: Mapping, keys: tuple[str, ...]) -> dict:
    return {key: config[key] for key in keys if key in config}


def _describe(body: Mapping) -> str:
    rest = ", ".join(f"{k}: {v}" for k, v in body.items() if k not in ("entity_id", "condition"))
    return f"{body.get('entity_id', '')}{f' ({rest})' if rest else ''}"


def _device_entities(hass: Any, device_ids: list[str]) -> set[str]:
    """What Home Assistant's own target resolution expands these devices to."""
    try:
        from homeassistant.helpers.target import (
            TargetSelection,
            async_extract_referenced_entity_ids,
        )
    except ImportError:
        # Before target resolution moved out of helpers.service: the device's
        # own entities, filtered the way HA filtered them then.
        registry = er.async_get(hass)
        return {
            entry.entity_id
            for device_id in device_ids
            for entry in er.async_entries_for_device(registry, device_id)
            if entry.hidden_by is None and entry.entity_category is None
        }
    selected = async_extract_referenced_entity_ids(
        hass, TargetSelection({"device_id": device_ids}), expand_group=False
    )
    return set(selected.indirectly_referenced)


@functools.cache
def _binary_sensor_types(module: str, on: str, off: str) -> tuple[frozenset, frozenset]:
    """The device-class types HA reads as on and as off -- some sixty of them.

    Taken from Home Assistant rather than copied, so a device class it adds is
    converted too.
    """
    try:
        imported = __import__(
            f"homeassistant.components.binary_sensor.{module}", fromlist=[on, off]
        )
        return frozenset(getattr(imported, on)), frozenset(getattr(imported, off))
    except (ImportError, AttributeError):
        return frozenset(), frozenset()


@functools.cache
def _hvac_modes() -> tuple[str, ...]:
    try:
        from homeassistant.components.climate.const import HVAC_MODES
    except ImportError:
        return ()
    return tuple(str(mode) for mode in HVAC_MODES)
