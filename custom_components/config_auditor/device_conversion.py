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

A block is found wherever it sits: ``iter_blocks`` walks into ``choose:``,
``if:``, ``repeat:``, ``parallel:`` and the rest the way Home Assistant reads
them. Only the top level used to be looked at, so a device condition inside a
``choose:`` option was neither reported nor converted.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, MutableMapping
import copy
import functools
import re
from typing import Any, NamedTuple

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_validation import determine_script_action


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


def device_reference(role: str, item: Mapping) -> str | None:
    """`device_id` for a device trigger, condition or action, `target` for a
    service call aimed at a device, None for anything else."""
    if "device_id" in item:
        return "device_id"
    target = item.get("target") if role == "action" else None
    if isinstance(target, Mapping) and "device_id" in target:
        return "target"
    return None


def convert(hass: Any, role: str, item: Mapping, *, service_key: str = "action") -> Conversion | None:
    """The conversion of one trigger, condition or action, or None if it names no device."""
    if not isinstance(item, Mapping):
        return None
    reference = device_reference(role, item)
    if reference is None:
        return None
    if role == "trigger":
        return convert_trigger(hass, item)
    if role == "condition":
        return convert_condition(hass, item)
    if reference == "target":
        return convert_device_target(hass, item)
    return convert_action(hass, item, service_key=service_key) if "domain" in item else None


# -- Where the device blocks are ----------------------------------------------
#
# A path runs from the automation down to one block and reads as its location:
# ("action", 2, "choose", 0, "conditions", 1) is `action[2].choose[0].conditions[1]`.
# A slot Home Assistant reads through `ensure_list` may hold one block instead
# of a list; that block is index 0 all the same, so every location has one shape.

_ROLES = ("trigger", "condition", "action")

# Action kind, as HA's `determine_script_action` names it -> its plain slots.
# `choose:` options, `repeat:` and `parallel:` branches are walked apart.
_ACTION_SLOTS: dict[str, tuple[tuple[str, str], ...]] = {
    "choose": (("default", "action"),),
    "if": (("if", "condition"), ("then", "action"), ("else", "action")),
    "sequence": (("sequence", "action"),),
    "wait_for_trigger": (("wait_for_trigger", "trigger"),),
}


class Block(NamedTuple):
    """A trigger, condition or action of an automation, at any depth."""

    path: tuple[str | int, ...]
    role: str
    config: Mapping


def iter_blocks(automation: Mapping) -> Iterator[Block]:
    """Every trigger, condition and action, parents before what they hold.

    Down through `choose:`, `if:`, `repeat:`, `parallel:`, `sequence:`,
    `wait_for_trigger:`, the `and` / `or` / `not` conditions and their
    shorthands, and a `triggers:` sublist -- read as HA's config_validation
    reads them, so a condition used as an action step is a condition.
    """
    for role in _ROLES:
        yield from _slot(automation.get(_section_key(automation, role)), role, (role,))


def find(
    hass: Any, automation: Mapping, *, service_key: str, scope: tuple | None = None
) -> list[tuple[Block, Conversion]]:
    """Every device block at or under *scope* (the whole automation if None), converted."""
    found = []
    for block in iter_blocks(automation):
        if scope and block.path[:len(scope)] != scope:
            continue
        conversion = convert(hass, block.role, block.config, service_key=service_key)
        if conversion is not None:
            found.append((block, conversion))
    return found


def replace(automation: MutableMapping, path: tuple, new: Mapping) -> bool:
    """Put *new* in place of the device block *path* leads to.

    False, with nothing changed, when the path no longer leads to a block
    naming a device: the automation changed since the path was taken.
    """
    if not path or path[0] not in _ROLES:
        return False
    holder: Any = automation
    key: str | int = _section_key(automation, path[0])
    if key not in holder:
        return False
    for step in path[1:]:
        slot = holder[key]
        if isinstance(step, int):
            if isinstance(slot, list):
                if not 0 <= step < len(slot):
                    return False
                holder, key = slot, step
            elif step != 0:  # one block in place of a list is index 0
                return False
        elif isinstance(slot, MutableMapping) and step in slot:
            holder, key = slot, step
        else:
            return False
    node = holder[key]
    # "action" looks for both forms, the block's own device_id and a target's.
    if not isinstance(node, Mapping) or device_reference("action", node) is None:
        return False
    holder[key] = new
    return True


def location(path: tuple) -> str:
    """`action[2].choose[0].conditions[1]` -- the form an issue's location takes."""
    text = ""
    for step in path:
        text += f"[{step}]" if isinstance(step, int) else f".{step}" if text else step
    return text


_STEP = re.compile(r"\.?([A-Za-z_]+)|\[(\d+)\]")


def parse_location(text: str) -> tuple[str | int, ...] | None:
    """The path a location names, or None if it names no trigger, condition or action.

    A trailing `.target`, the device_id-in-target issue's, names the action itself.
    """
    path: list[str | int] = []
    pos = 0
    while pos < len(text):
        step = _STEP.match(text, pos)
        if step is None:
            return None
        path.append(step[1] if step[1] else int(step[2]))
        pos = step.end()
    if path and path[-1] == "target":
        path.pop()
    if len(path) < 2 or path[0] not in _ROLES or not isinstance(path[1], int):
        return None
    return tuple(path)


def label(path: tuple) -> str:
    """`Action 2`, or `Action 2 › choose[0].conditions[1]` for a nested block."""
    head = f"{str(path[0]).capitalize()} {path[1]}"
    return f"{head} › {location(path[2:])}" if len(path) > 2 else head


def _section_key(automation: Mapping, role: str) -> str:
    """`actions:` since HA 2024.10, `action:` before -- both still load."""
    return f"{role}s" if f"{role}s" in automation else role


def _as_list(node: Any) -> list:
    """What HA's `ensure_list` makes of a slot."""
    return node if isinstance(node, list) else [] if node is None else [node]


def _slot(node: Any, role: str, path: tuple) -> Iterator[Block]:
    for index, item in enumerate(_as_list(node)):
        if isinstance(item, Mapping):  # a template string is a condition too
            yield from _block(item, role, (*path, index))


def _block(item: Mapping, role: str, path: tuple) -> Iterator[Block]:
    if role == "trigger":
        if "triggers" in item and len(item) == 1:  # a sublist HA flattens
            yield from _slot(item["triggers"], "trigger", (*path, "triggers"))
        else:
            yield Block(path, "trigger", item)
        return

    kind = _action_kind(item) if role == "action" else "condition"
    if kind == "condition":
        yield Block(path, "condition", item)
        key = _nested_conditions_key(item)
        if key:
            yield from _slot(item[key], "condition", (*path, key))
        return

    yield Block(path, "action", item)
    if kind == "choose":
        for index, option in enumerate(_as_list(item.get("choose"))):
            if isinstance(option, Mapping):
                at = (*path, "choose", index)
                yield from _slot(option.get("conditions"), "condition", (*at, "conditions"))
                yield from _slot(option.get("sequence"), "action", (*at, "sequence"))
    elif kind == "repeat" and isinstance(item.get("repeat"), Mapping):
        for key, sub in (("while", "condition"), ("until", "condition"), ("sequence", "action")):
            yield from _slot(item["repeat"].get(key), sub, (*path, "repeat", key))
    elif kind == "parallel":
        # A branch is one action, or a list of them run in sequence.
        for index, branch in enumerate(_as_list(item.get("parallel"))):
            if isinstance(branch, list):
                yield from _slot(branch, "action", (*path, "parallel", index))
            elif isinstance(branch, Mapping):
                yield from _block(branch, "action", (*path, "parallel", index))
    for key, sub in _ACTION_SLOTS.get(kind or "", ()):
        yield from _slot(item.get(key), sub, (*path, key))


def _action_kind(item: Mapping) -> str | None:
    try:
        return determine_script_action(item)
    except ValueError:
        return None


def _nested_conditions_key(item: Mapping) -> str | None:
    """Where an and / or / not condition holds its own, in any of its spellings."""
    if "conditions" in item:
        return "conditions"
    for shorthand in ("and", "or", "not"):
        if shorthand in item:
            return shorthand
    return "condition" if isinstance(item.get("condition"), list) else None


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
