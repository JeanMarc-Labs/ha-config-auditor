"""Shared plumbing for the MCP tool handlers.

Protocol constants, the caller identity carried into the handlers, JSON
encoding of raw Home Assistant values, and the read / write helpers every
tool module builds on. Nothing here answers a tool call.
"""
from __future__ import annotations

import contextvars
import json
import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from homeassistant.core import Context, HomeAssistant

from ..const import DOMAIN
from ..yaml_sources import (
    default_write_target,
    ListScan,
    NamedScan,
    read_plain_yaml,
    scan_list_domain,
    scan_named_domain,
    skipped_note,
)
from ..yaml_writer import (
    async_write_and_reload,
    atomic_write,
    DomainEdit,
    EditScan,
    EditTarget,
    open_domain_for_edit,
    scan_list_domain_for_edit,
    scan_named_domain_for_edit,
)


# The whole package logs under the name the module had before it became
# one, so a `logger:` filter on custom_components.config_auditor.mcp_server
# keeps catching every line the MCP server writes.
_LOGGER = logging.getLogger(__package__)

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "haca-mcp"
MCP_SERVER_VERSION = "1.6.1"


# Identité de l'appelant MCP, portée jusqu'aux handlers d'outils.
# Les 69 handlers reçoivent (hass, params) : plutôt que de changer 69 signatures,
# _handle_jsonrpc dépose l'ID utilisateur ici et _caller_context() le relit, ce qui
# permet d'attribuer chaque appel de service à la bonne personne dans le journal HA.
_MCP_CALLER_USER_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "haca_mcp_caller_user_id", default=None
)


def _caller_context() -> Context | None:
    """Contexte HA portant l'ID de l'appelant MCP, ou None hors requête HTTP."""
    user_id = _MCP_CALLER_USER_ID.get()
    return Context(user_id=user_id) if user_id else None


def _json_default(obj: Any) -> Any:
    """Fallback serializer for values json.dumps() cannot encode natively.

    Tool results carry raw Home Assistant data — state attributes, logbook
    entries, registry entries, backup metadata — and integrations are free to
    put datetime, date, timedelta, Enum or set values in there. A single such
    value used to abort the whole tools/call with
    "Object of type datetime is not JSON serializable" (-32603).
    """
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(str(v) for v in obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    as_dict = getattr(obj, "as_dict", None)
    if callable(as_dict):  # HA State, Event, Context, registry entries…
        try:
            return as_dict()
        except Exception:  # noqa: BLE001 — never let serialization kill the call
            pass
    return str(obj)


def json_safe(value: Any) -> Any:
    """Return `value` with every non-JSON-native object converted in place.

    Used by callers that must hand a plain dict to someone else's serializer
    (HA's LLM API), where `default=` is not an option.
    """
    return json.loads(json.dumps(value, default=_json_default))


def _slugify(text: str, max_length: int = 60) -> str:
    """Convert a human-readable name to a safe filesystem/entity slug.

    Properly handles accented characters by decomposing Unicode (NFKD)
    and stripping combining marks:  é→e, ç→c, ñ→n, ü→u, etc.

    Example: "Allumer une lumière avec un capteur de présence"
           → "allumer_une_lumiere_avec_un_capteur_de_presence"
    """
    import unicodedata
    import re as _re
    # NFKD decomposition: é → e + combining accent
    text = unicodedata.normalize("NFKD", text)
    # Strip combining characters (accents, diacritics)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Lowercase and replace non-alphanumeric with underscore
    text = _re.sub(r"[^a-z0-9_]", "_", text.lower())
    # Collapse multiple underscores and strip edges
    text = _re.sub(r"_+", "_", text).strip("_")
    return text[:max_length]


# ─── Helper : récupérer les données du coordinator ────────────────────────

def _get_coordinator_data(hass: HomeAssistant) -> dict[str, Any]:
    """Retourne les données du coordinator ou un dict vide."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return {}
        data = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {})
        coordinator = data.get("coordinator")
        return coordinator.data or {} if coordinator else {}
    except Exception:
        return {}


def _atomic_write(path, content: str, encoding: str = "utf-8") -> None:
    """Écriture atomique — voir :func:`yaml_writer.atomic_write`.

    Pour le contenu que HACA produit lui-même (un blueprint rendu, un export).
    L'édition d'un fichier maintenu par l'utilisateur passe par
    :func:`_safe_edit_and_reload`, qui préserve les commentaires.
    """
    atomic_write(str(path), content, encoding)


async def _safe_edit_and_reload(
    hass: "HomeAssistant",
    target: EditTarget,
    reload_domain: str,
    *,
    entry: Any = None,
    key: str | None = None,
) -> str:
    """Validate, round-trip write, reload -- rolling the file back if the reload fails.

    :func:`yaml_writer.async_write_and_reload`, with the reloads attributed to
    the MCP caller. An *entry* Home Assistant's own editor would reject raises
    :class:`yaml_writer.RejectedByHomeAssistant` before anything is written; a
    removal passes no entry.

    Returns the backup path.
    """
    return await async_write_and_reload(
        hass, target, reload_domain, entry=entry, key=key, context=_caller_context()
    )


def _read_plain_yaml(path: str):
    """Plain-PyYAML read for the read-only tools — see yaml_sources."""
    return read_plain_yaml(path)


def _skipped_note(skipped: list[str]) -> str:
    """One sentence naming the files skipped above — see yaml_sources."""
    return skipped_note(skipped)


async def _async_scan_list_domain(
    hass: "HomeAssistant", key: str, default_filename: str, match
) -> ListScan:
    """:func:`yaml_sources.scan_list_domain`, off the event loop."""
    return await hass.async_add_executor_job(
        scan_list_domain, hass.config.config_dir, key, default_filename, match
    )


async def _async_scan_list_for_edit(
    hass: "HomeAssistant", key: str, default_filename: str, match
) -> EditScan:
    """:func:`yaml_writer.scan_list_domain_for_edit`, off the event loop."""
    return await hass.async_add_executor_job(
        scan_list_domain_for_edit,
        hass.config.config_dir, key, default_filename, match,
    )


async def _async_scan_named_for_edit(
    hass: "HomeAssistant", key: str, default_filename: str, match
) -> EditScan:
    """:func:`yaml_writer.scan_named_domain_for_edit`, off the event loop."""
    return await hass.async_add_executor_job(
        scan_named_domain_for_edit,
        hass.config.config_dir, key, default_filename, match,
    )


async def _async_scan_named_domain(
    hass: "HomeAssistant", key: str, default_filename: str, match
) -> NamedScan:
    """:func:`yaml_sources.scan_named_domain`, off the event loop."""
    return await hass.async_add_executor_job(
        scan_named_domain, hass.config.config_dir, key, default_filename, match
    )


async def _async_open_domain_for_edit(
    hass: "HomeAssistant", key: str, default_filename: str, shape: type
) -> DomainEdit:
    """:func:`yaml_writer.open_domain_for_edit`, off the event loop."""
    return await hass.async_add_executor_job(
        open_domain_for_edit, hass.config.config_dir, key, default_filename, shape
    )


async def _async_write_target(
    hass: "HomeAssistant", key: str, default_filename: str, split_filename: str
) -> str:
    """Where a newly created entry should be written, off the event loop."""
    return await hass.async_add_executor_job(
        default_write_target,
        hass.config.config_dir,
        key,
        default_filename,
        split_filename,
    )


async def _async_read_file(hass: "HomeAssistant", path: str, encoding: str = "utf-8") -> str:
    """Lire un fichier de façon non-bloquante via executor."""
    return await hass.async_add_executor_job(
        lambda: open(path, encoding=encoding).read()
    )


async def _async_write_file(hass: "HomeAssistant", path: str, content: str, encoding: str = "utf-8") -> None:
    """Écrire un fichier de façon non-bloquante via executor (atomique)."""
    await hass.async_add_executor_job(_atomic_write, path, content, encoding)
