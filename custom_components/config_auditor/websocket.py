"""WebSocket API pour H.A.C.A."""
from __future__ import annotations

import asyncio
import io
import logging
import json
from pathlib import Path
from time import monotonic as _monotonic
from typing import Any, NamedTuple

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN
from .yaml_sources import (
    contains_ha_tag,
    iter_domain_files,
    read_roundtrip_yaml,
    skipped_note,
    write_roundtrip_yaml,
)

# Issue categories the panel can ask for, and the coordinator key each one holds.
# Used both to validate `category` and to build the response, so the two can
# never drift apart again.
ISSUE_CATEGORY_MAP: dict[str, str] = {
    "automation":  "automation_issue_list",
    "script":      "script_issue_list",
    "scene":       "scene_issue_list",
    "blueprint":   "blueprint_issue_list",
    "entity":      "entity_issue_list",
    "helper":      "helper_issue_list",
    "performance": "performance_issue_list",
    "security":    "security_issue_list",
    "dashboard":   "dashboard_issue_list",
    "compliance":  "compliance_issue_list",
}

# A manual scan that has been "in progress" for longer than this is treated as
# dead: the lock is taken again rather than left blocking every further scan.
SCAN_LOCK_TIMEOUT = 600  # seconds

# How many issues per category one `haca/get_data` call returns by default.
# Deliberately larger than any realistic category on a real installation: the
# panel filters and paginates client-side, so a low ceiling silently hid issues.
DEFAULT_ISSUE_LIMIT = 2000


def _ts(hass, section: str, key: str, connection=None, **kwargs) -> str:
    """Get a translation string from the in-memory cache (websocket-local copy).

    When the caller has the connection in hand, the answer follows *that*
    user's profile language. Without it, the last language seen by
    ``haca/get_translations`` is the best guess available.
    """
    store = hass.data.get("config_auditor", {})
    lang = None
    user_id = getattr(getattr(connection, "user", None), "id", None)
    if user_id:
        lang = (store.get("user_languages") or {}).get(user_id)
    lang = lang or store.get("user_language") or hass.config.language or "en"
    # Import cache lazily to avoid circular import at module load time
    try:
        from . import _TS_CACHE  # noqa: PLC0415
        data = _TS_CACHE.get(lang) or _TS_CACHE.get("en") or {}
    except Exception:
        data = {}
    val = data.get(section, {}).get(key, key)
    try:
        return val.format(**kwargs) if kwargs else val
    except Exception:
        return val

_LOGGER = logging.getLogger(__name__)


def _safe_language(requested: str | None, fallback: str | None) -> str:
    """Return a language code that is safe to interpolate into a file path.

    ``language`` arrives straight from the browser and used to be pasted into
    ``translations/<language>.json`` without a check, so a value such as
    ``../../../../secrets`` walked out of the folder — and the ``exists()``
    probe alone was already a file-presence oracle.

    Only codes HACA actually ships are accepted. The allow-list is the set of
    translation files loaded into ``_TS_CACHE`` at setup, so adding a language
    needs no change here; anything else falls back to English.
    """
    try:
        from . import _TS_CACHE  # noqa: PLC0415
        known = set(_TS_CACHE)
    except Exception:
        known = set()
    known = known or {"en"}

    for candidate in (requested, fallback):
        if candidate and candidate in known:
            return candidate
    if requested:
        _LOGGER.debug("HACA: unsupported language %r — falling back to English", requested)
    return "en"


# ── Simple per-command rate limiter for write-sensitive handlers ────────────
# Prevents spam on save_options and apply_field_fix (YAML writes).
# Dict of { "command_key" : last_call_monotonic_time }
_WS_RATE_LIMITS: dict[str, float] = {}
_WS_RATE_LIMIT_SECONDS = 2.0  # minimum seconds between calls per command+user


def _rate_limited(key: str, seconds: float = _WS_RATE_LIMIT_SECONDS) -> bool:
    """Return True if the call should be rejected (too soon since last call)."""
    import time
    now = time.monotonic()
    last = _WS_RATE_LIMITS.get(key, 0.0)
    if now - last < seconds:
        return True
    _WS_RATE_LIMITS[key] = now
    return False


def async_register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register WebSocket handlers."""
    websocket_api.async_register_command(hass, handle_get_data)
    websocket_api.async_register_command(hass, handle_scan_all)
    websocket_api.async_register_command(hass, handle_preview_fix)
    websocket_api.async_register_command(hass, handle_apply_fix)
    websocket_api.async_register_command(hass, handle_list_backups)
    websocket_api.async_register_command(hass, handle_restore_backup)
    websocket_api.async_register_command(hass, handle_get_translations)
    websocket_api.async_register_command(hass, handle_explain_issue)
    websocket_api.async_register_command(hass, handle_ai_suggest_fix)
    websocket_api.async_register_command(hass, handle_apply_field_fix)
    websocket_api.async_register_command(hass, handle_purge_recorder_orphans)
    websocket_api.async_register_command(hass, handle_get_history)
    websocket_api.async_register_command(hass, handle_delete_history)
    websocket_api.async_register_command(hass, handle_chat)
    websocket_api.async_register_command(hass, handle_get_options)
    websocket_api.async_register_command(hass, handle_save_options)
    websocket_api.async_register_command(hass, handle_recorder_exclude_entity)
    websocket_api.async_register_command(hass, handle_mark_battery_replaced)
    websocket_api.async_register_command(hass, handle_get_battery_library_info)
    websocket_api.async_register_command(hass, handle_set_log_level)
    # ── v1.4.0 ─────────────────────────────────────────────────────────────
    websocket_api.async_register_command(hass, handle_mcp_status)
    websocket_api.async_register_command(hass, handle_agent_status)
    websocket_api.async_register_command(hass, handle_agent_force_report)
    websocket_api.async_register_command(hass, handle_record_fix_outcome)
    # ── v1.5.0 ─────────────────────────────────────────────────────────────
    websocket_api.async_register_command(hass, handle_get_battery_predictions)
    websocket_api.async_register_command(hass, handle_export_battery_csv)
    websocket_api.async_register_command(hass, handle_get_report_url)
    websocket_api.async_register_command(hass, handle_get_area_complexity)
    websocket_api.async_register_command(hass, handle_get_redundancy)
    websocket_api.async_register_command(hass, handle_get_recorder_impact)
    websocket_api.async_register_command(hass, handle_get_integrations)
    websocket_api.async_register_command(hass, handle_get_history_diff)
    _LOGGER.info("[HACA] WebSocket handlers registered")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_data",
        vol.Optional("limit", default=DEFAULT_ISSUE_LIMIT): int,
        vol.Optional("offset", default=0): int,
        vol.Optional("category"): vol.In(list(ISSUE_CATEGORY_MAP)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get data request with optional pagination."""
    try:
        entry, data = _get_entry_data(hass)
        if not entry:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        if not data:
            connection.send_error(msg["id"], "no_data", "No data available")
            return

        coordinator = data["coordinator"]
        cdata = coordinator.data or {}

        limit  = msg.get("limit", DEFAULT_ISSUE_LIMIT)
        offset = msg.get("offset", 0)
        category = msg.get("category")

        # Full lists, straight from the coordinator, before any slicing.
        full: dict[str, list] = {
            key: (cdata.get(key) or []) for key in ISSUE_CATEGORY_MAP.values()
        }

        def _get_list(key: str) -> list:
            """The slice of one issue list to send back.

            Asking for a category narrows the answer to that category — every
            other list comes back empty. Without a category, every list is sent,
            each one sliced to the same window.
            """
            if category and ISSUE_CATEGORY_MAP[category] != key:
                return []
            return full[key][offset: offset + limit]

        # Per-category truncation flags, so the panel can say "200 of 247 shown"
        # instead of quietly dropping the rest.
        truncated = {
            name: len(_get_list(key)) < len(full[key])
            for name, key in ISSUE_CATEGORY_MAP.items()
            if not category or name == category
        }

        payload = {
            "health_score":         cdata.get("health_score", 0),
            "automation_issues":    cdata.get("automation_issues", 0),
            "script_issues":        cdata.get("script_issues", 0),
            "scene_issues":         cdata.get("scene_issues", 0),
            "blueprint_issues":     cdata.get("blueprint_issues", 0),
            "entity_issues":        cdata.get("entity_issues", 0),
            "helper_issues":        cdata.get("helper_issues", 0),
            "performance_issues":   cdata.get("performance_issues", 0),
            "security_issues":      cdata.get("security_issues", 0),
            "dashboard_issues":     cdata.get("dashboard_issues", 0),
            "compliance_issues":    cdata.get("compliance_issues", 0),
            "total_issues":         cdata.get("total_issues", 0),
            "last_scan":            cdata.get("last_scan"),
            # Dependency graph
            "dependency_graph": cdata.get("dependency_graph", {"nodes": [], "edges": []}),
            # Battery monitor
            "battery_list":   cdata.get("battery_list", []),
            "battery_count":  cdata.get("battery_count", 0),
            "battery_alerts": cdata.get("battery_alerts", 0),
            # Complexity / stats tables
            "complexity_scores":         cdata.get("complexity_scores", []),
            "script_complexity_scores":  cdata.get("script_complexity_scores", []),
            "scene_stats":               cdata.get("scene_stats", []),
            "blueprint_stats":           cdata.get("blueprint_stats", []),
            # Recorder orphan data (not paginated, usually small)
            "recorder_orphans":          cdata.get("recorder_orphans", []),
            "recorder_orphan_count":      cdata.get("recorder_orphan_count", 0),
            "recorder_wasted_mb":         cdata.get("recorder_wasted_mb", 0.0),
            "recorder_db_available":      cdata.get("recorder_db_available", False),
            # Pagination metadata
            "pagination": {
                "limit":  limit,
                "offset": offset,
                "category": category,
                "truncated": truncated,
                **{
                    f"total_{name}": len(full[key])
                    for name, key in ISSUE_CATEGORY_MAP.items()
                },
            },
        }
        # Paginated lists
        payload.update({key: _get_list(key) for key in ISSUE_CATEGORY_MAP.values()})

        connection.send_result(msg["id"], payload)
    except Exception as e:
        _LOGGER.error("Error getting data: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/scan_all",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_scan_all(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle scan all request — fire-and-forget.

    Ne bloque PAS la connexion WebSocket pendant le scan (qui peut durer
    10-30s sur une grande installation). Répond immédiatement avec
    {"accepted": true}, puis fire l'event HA "haca_scan_complete" quand
    le coordinator a fini, ce que le frontend écoute via subscribeEvents.
    """
    try:
        entry, data = _get_entry_data(hass)
        if not entry:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        if not data:
            connection.send_error(msg["id"], "no_data", "No H.A.C.A data found")
            return

        # Guard anti-spam : si un scan est déjà en cours, on rejette sans bloquer.
        # Le drapeau est daté : un scan qui dépasse SCAN_LOCK_TIMEOUT est de toute
        # façon anormal, et un verrou resté coincé ne doit pas condamner tous les
        # scans manuels jusqu'au rechargement de l'intégration.
        started_at = data.get("_scan_started_at")
        if data.get("_scan_in_progress"):
            age = _monotonic() - started_at if started_at else None
            if age is None or age < SCAN_LOCK_TIMEOUT:
                connection.send_result(msg["id"], {"accepted": False, "reason": "scan_in_progress"})
                _LOGGER.warning("[HACA WS] Scan already in progress — request ignored")
                return
            _LOGGER.warning(
                "[HACA WS] Stale scan lock (%.0fs old) — starting a new scan anyway", age
            )

        coordinator = data["coordinator"]

        # Répondre IMMÉDIATEMENT — le scan tourne en tâche de fond.
        # send_result peut lever si l'utilisateur a fermé l'onglet entre-temps ;
        # le drapeau n'est posé qu'ensuite, juste avant de lancer la tâche, pour
        # qu'un échec d'envoi ne laisse pas le verrou fermé à vie.
        connection.send_result(msg["id"], {"accepted": True})

        data["_scan_in_progress"] = True
        data["_scan_started_at"] = _monotonic()

        async def _run_scan() -> None:
            try:
                await coordinator.async_refresh()
                _LOGGER.info("[HACA WS] Background scan complete — firing haca_scan_complete")
            except Exception as scan_err:
                _LOGGER.error("[HACA WS] Background scan error: %s", scan_err, exc_info=True)
            finally:
                data["_scan_in_progress"] = False
                data["_scan_started_at"] = None
                # Notifier le frontend via l'event bus HA
                hass.bus.async_fire("haca_scan_complete", {
                    "entry_id": entry.entry_id,
                    "success": True,
                })

        try:
            hass.async_create_task(_run_scan())
        except Exception:
            # The task never started, so nothing will ever clear the flag.
            data["_scan_in_progress"] = False
            data["_scan_started_at"] = None
            raise

    except Exception as e:
        _LOGGER.error("Error starting scan: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/preview_fix",
        vol.Required("automation_id"): str,
        vol.Required("fix_type"): str,
        vol.Optional("mode"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_preview_fix(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle preview fix request."""
    try:
        entry, data = _get_entry_data(hass)
        if not entry:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        refactoring = data.get("refactoring_assistant") if data else None
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        automation_id = msg["automation_id"]
        fix_type = msg["fix_type"]
        
        if fix_type == "device_id":
            result = await refactoring.preview_device_id_fix(automation_id)
        elif fix_type == "mode":
            mode = msg.get("mode", "restart")
            result = await refactoring.preview_mode_fix(automation_id, mode)
        else:
            connection.send_error(msg["id"], "invalid_type", f"Unknown fix type: {fix_type}")
            return
        
        connection.send_result(msg["id"], result)
        
    except Exception as e:
        _LOGGER.error("Error previewing fix: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/apply_fix",
        vol.Required("automation_id"): str,
        vol.Required("fix_type"): str,
        vol.Optional("mode"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_apply_fix(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle apply fix request."""
    try:
        entry, data = _get_entry_data(hass)
        if not entry:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        refactoring = data.get("refactoring_assistant") if data else None
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        automation_id = msg["automation_id"]
        fix_type = msg["fix_type"]
        
        if fix_type == "device_id":
            result = await refactoring.apply_device_id_fix(automation_id)
        elif fix_type == "mode":
            mode = msg.get("mode", "restart")
            result = await refactoring.apply_mode_fix(automation_id, mode)
        else:
            connection.send_error(msg["id"], "invalid_type", f"Unknown fix type: {fix_type}")
            return
        
        connection.send_result(msg["id"], result)
        
    except Exception as e:
        _LOGGER.error("Error applying fix: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/list_backups",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_list_backups(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle list backups request."""
    try:
        entry, data = _get_entry_data(hass)
        if not entry:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        refactoring = data.get("refactoring_assistant") if data else None
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        backups = await refactoring.list_backups()
        
        connection.send_result(
            msg["id"],
            {
                "backups": backups,
                "count": len(backups),
            },
        )
        
    except Exception as e:
        _LOGGER.error("Error listing backups: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/restore_backup",
        vol.Required("backup_path"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_restore_backup(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle restore backup request."""
    try:
        entry, data = _get_entry_data(hass)
        if not entry:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return

        refactoring = data.get("refactoring_assistant") if data else None
        
        if not refactoring:
            connection.send_error(msg["id"], "no_refactoring", "Refactoring module not available")
            return

        backup_path = msg["backup_path"]
        result = await refactoring.restore_backup(backup_path)
        
        connection.send_result(msg["id"], result)
        
    except Exception as e:
        _LOGGER.error("Error restoring backup: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))



# ── Orphan purge tuning ─────────────────────────────────────────────────────
# Rows deleted per transaction when we do direct SQL (statistics tables only).
# Small on purpose: the write lock is only held for the duration of one batch,
# so the recorder thread can always slip in between two of them.  Mirrors HA's
# own MAX_ROWS_TO_PURGE.
_PURGE_BATCH_SIZE = 1000
# How long we wait for HA's PurgeEntitiesTask to drain the `states` rows before
# returning a partial result.  Exceeding it is not an error — the task keeps
# running safely inside the recorder, it just is not finished yet.
_PURGE_STATES_TIMEOUT = 900.0
_PURGE_POLL_INTERVAL = 2.0


def _purge_fetch_targets(instance, entity_ids: list[str]) -> tuple[dict, dict]:
    """Resolve entity_id → metadata ids.  Read-only: takes no write lock."""
    from sqlalchemy import text

    states_meta: dict[str, int] = {}
    stats_meta: dict[str, int] = {}

    with instance.engine.connect() as conn:
        for eid in entity_ids:
            row = conn.execute(
                text("SELECT metadata_id FROM states_meta WHERE entity_id = :eid"),
                {"eid": eid},
            ).fetchone()
            if row:
                states_meta[eid] = row[0]

            row = conn.execute(
                text(
                    "SELECT id FROM statistics_meta "
                    "WHERE statistic_id = :eid AND source = 'recorder'"
                ),
                {"eid": eid},
            ).fetchone()
            if row:
                stats_meta[eid] = row[0]

    return states_meta, stats_meta


def _purge_states_remaining(instance, metadata_ids: list[int]) -> list[int]:
    """Return the metadata_ids that still have at least one row in `states`.

    Uses EXISTS-style ``LIMIT 1`` rather than COUNT(*) so the check stays cheap
    even on an entity with hundreds of thousands of rows — it is called
    repeatedly while we poll.
    """
    from sqlalchemy import text

    remaining: list[int] = []
    with instance.engine.connect() as conn:
        for mid in metadata_ids:
            row = conn.execute(
                text("SELECT 1 FROM states WHERE metadata_id = :mid LIMIT 1"),
                {"mid": mid},
            ).fetchone()
            if row:
                remaining.append(mid)
    return remaining


def _purge_delete_batched(session, table: str, pk: str, metadata_id: int) -> int:
    """Delete every row of `table` for one metadata_id, committing per batch.

    `table` and `pk` are module-local literals, never user input, so the
    f-string interpolation is safe; every value is a bound parameter.

    ``DELETE … LIMIT`` is not portable (PostgreSQL rejects it, and CPython's
    bundled SQLite is usually built without SQLITE_ENABLE_UPDATE_DELETE_LIMIT),
    so we page over primary keys and delete by id — the approach HA uses too.
    """
    from sqlalchemy import text

    total = 0
    while True:
        ids = [
            r[0]
            for r in session.execute(
                text(
                    f"SELECT {pk} FROM {table} WHERE metadata_id = :mid "
                    f"LIMIT {int(_PURGE_BATCH_SIZE)}"
                ),
                {"mid": metadata_id},
            ).fetchall()
        ]
        if not ids:
            return total

        placeholders = ", ".join(f":i{i}" for i in range(len(ids)))
        session.execute(
            text(f"DELETE FROM {table} WHERE {pk} IN ({placeholders})"),
            {f"i{i}": v for i, v in enumerate(ids)},
        )
        # Commit per batch — this is what keeps the write lock short-lived.
        session.commit()

        total += len(ids)
        if len(ids) < _PURGE_BATCH_SIZE:
            return total


def _purge_open_session(instance):
    """Open a DB session, supporting both the old and the new recorder API."""
    if hasattr(instance, "get_session"):
        return instance.get_session()
    from sqlalchemy.orm import Session as _Session

    return _Session(bind=instance.engine)


def _purge_statistics_sql(instance, stats_meta: dict[str, int]) -> dict[str, dict]:
    """Delete long-term statistics for the given entities, in small batches.

    This is the half ``recorder.purge_entities`` cannot do: it only looks at
    states_meta, so an entity that survives *only* as long-term statistics is
    invisible to it.

    On error the current batch is rolled back and the exception propagates.
    Batches already committed stay deleted — that is intentional and harmless,
    the rows are orphaned data either way, and it is the price of never holding
    one long transaction.
    """
    from sqlalchemy import text

    session = _purge_open_session(instance)
    deleted: dict[str, dict] = {}
    try:
        for eid, mid in stats_meta.items():
            counts = {
                "statistics": _purge_delete_batched(session, "statistics", "id", mid),
                "statistics_short_term": _purge_delete_batched(
                    session, "statistics_short_term", "id", mid
                ),
            }
            session.execute(
                text("DELETE FROM statistics_meta WHERE id = :mid"), {"mid": mid}
            )
            session.commit()
            counts["statistics_meta"] = 1
            _LOGGER.info("[HACA Purge] statistics purged for '%s': %s", eid, counts)
            deleted[eid] = counts
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return deleted


def _purge_drop_states_meta(instance, states_meta: dict[str, int]) -> list[str]:
    """Drop states_meta rows whose `states` rows are all gone (one row each)."""
    from sqlalchemy import text

    session = _purge_open_session(instance)
    dropped: list[str] = []
    try:
        for eid, mid in states_meta.items():
            still_there = session.execute(
                text("SELECT 1 FROM states WHERE metadata_id = :mid LIMIT 1"),
                {"mid": mid},
            ).fetchone()
            if still_there:
                # Purge still running for this entity — leaving the meta row is
                # harmless, HA reuses it if the entity ever comes back.
                continue
            session.execute(
                text("DELETE FROM states_meta WHERE metadata_id = :mid"), {"mid": mid}
            )
            session.commit()
            dropped.append(eid)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return dropped


def _purge_wal_checkpoint(instance) -> None:
    """PASSIVE checkpoint so readers see the deletes, without blocking anyone.

    Deliberately not TRUNCATE: TRUNCATE waits for every reader to finish and can
    stall for a long time while the recorder is active.  PASSIVE returns right
    away and checkpoints whatever it can, which is all we need here.
    """
    from sqlalchemy import text

    try:
        with instance.engine.connect() as conn:
            row = conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)")).fetchone()
        _LOGGER.debug("[HACA Purge] WAL checkpoint: %s", tuple(row) if row else None)
    except Exception as exc:
        # Non-SQLite backend, or checkpoint refused. Neither undoes our commits.
        _LOGGER.debug("[HACA Purge] WAL checkpoint skipped: %s", exc)


async def _purge_await_states(instance, states_meta: dict[str, int]) -> list[str]:
    """Wait for HA's PurgeEntitiesTask to drain `states`, bounded by a timeout.

    ``Recorder.async_block_till_done()`` is not enough on its own: the purge task
    re-queues itself whenever it hits its row cap, so the wait token can be
    processed while work is still pending.  We poll the states table instead.

    Returns the entity_ids that still have rows when we stop waiting.  That is
    not a failure — the recorder keeps purging them in the background, without
    ever holding the write lock.
    """
    import time

    by_mid = {mid: eid for eid, mid in states_meta.items()}
    pending = list(states_meta.values())
    deadline = time.monotonic() + _PURGE_STATES_TIMEOUT

    while True:
        pending = await instance.async_add_executor_job(
            _purge_states_remaining, instance, pending
        )
        if not pending:
            return []
        if time.monotonic() >= deadline:
            _LOGGER.warning(
                "[HACA Purge] %d entity(ies) still pending after %.0fs — the "
                "recorder will finish them in the background",
                len(pending), _PURGE_STATES_TIMEOUT,
            )
            return [by_mid[mid] for mid in pending]
        await asyncio.sleep(_PURGE_POLL_INTERVAL)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/purge_recorder_orphans",
        vol.Required("entity_ids"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_purge_recorder_orphans(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Purge orphaned entity data from the recorder database.

    Split in two stages on purpose, because the two halves carry very different
    risk:

    1. `states` / `state_attributes` / `old_state_id` are handled by HA's own
       ``recorder.purge_entities`` service.  It runs inside the recorder thread
       and commits every ~1000 rows, so the SQLite write lock is never held for
       more than a few milliseconds at a time, and it already knows how to
       honour the foreign keys HA enables on SQLite.
    2. `statistics` / `statistics_short_term` / `statistics_meta` are deleted
       here in direct SQL, also batched with a commit after every batch.  This
       part cannot be delegated: ``purge_entities`` only looks at states_meta,
       so an entity that survives *only* as long-term statistics is invisible
       to it.  This was the original reason for going direct-SQL at all.

    ⚠️  Do not reintroduce a single long transaction here.  The previous
    implementation staged every DELETE for every entity and committed once at
    the end.  On a large database the first statement took the SQLite write
    lock and held it for the whole run, so the recorder could no longer commit
    ("Error in database connectivity during commit: database is locked") until
    Home Assistant was restarted.  Batch size and per-batch commits are the
    load-bearing part of this handler.
    """
    entity_ids: list[str] = msg.get("entity_ids", [])
    _LOGGER.info(
        "[HACA Purge] request for %d entity(ies): %s", len(entity_ids), entity_ids
    )

    if not entity_ids:
        connection.send_error(msg["id"], "no_entities", "No entity_ids provided")
        return

    try:
        from homeassistant.helpers.recorder import get_instance
        instance = get_instance(hass)
    except Exception as exc:
        _LOGGER.warning("[HACA Purge] Recorder unavailable: %s", exc)
        connection.send_error(msg["id"], "recorder_unavailable", str(exc))
        return

    if not hass.services.has_service("recorder", "purge_entities"):
        # We deliberately do not fall back to deleting `states` ourselves:
        # doing that safely means honouring the old_state_id / attributes_id
        # foreign keys HA enables on SQLite, which is exactly the code path
        # that used to lock the database.
        _LOGGER.warning("[HACA Purge] recorder.purge_entities service unavailable")
        connection.send_error(
            msg["id"],
            "purge_unavailable",
            "The recorder.purge_entities service is not available",
        )
        return

    try:
        states_meta, stats_meta = await instance.async_add_executor_job(
            _purge_fetch_targets, instance, entity_ids
        )
    except Exception as exc:
        _LOGGER.warning("[HACA Purge] could not resolve metadata ids: %s", exc)
        connection.send_error(msg["id"], "purge_failed", str(exc))
        return

    detail: dict[str, dict] = {}
    pending: list[str] = []

    try:
        # ── 1. states / state_attributes — delegated to HA, batched ───────
        if states_meta:
            await hass.services.async_call(
                "recorder",
                "purge_entities",
                {"entity_id": list(states_meta), "keep_days": 0},
                blocking=True,
            )
            pending = await _purge_await_states(instance, states_meta)
            for eid in states_meta:
                detail.setdefault(eid, {})["states"] = (
                    "pending" if eid in pending else "purged"
                )

            # states_meta rows are only dropped once their states are gone.
            dropped = await instance.async_add_executor_job(
                _purge_drop_states_meta,
                instance,
                {eid: mid for eid, mid in states_meta.items() if eid not in pending},
            )
            for eid in dropped:
                detail[eid]["states_meta"] = 1

        # ── 2. statistics — direct SQL, batched ───────────────────────────
        if stats_meta:
            stats_detail = await instance.async_add_executor_job(
                _purge_statistics_sql, instance, stats_meta
            )
            for eid, counts in stats_detail.items():
                detail.setdefault(eid, {}).update(counts)

        await instance.async_add_executor_job(_purge_wal_checkpoint, instance)

    except Exception as exc:
        _LOGGER.warning("[HACA Purge] failed: %s", exc, exc_info=True)
        connection.send_error(msg["id"], "purge_failed", str(exc))
        return

    _LOGGER.info(
        "[HACA Purge] complete. pending=%s detail=%s", pending, detail
    )

    purged_set = set(entity_ids)

    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if entries:
            domain_data = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {})

            # ── Mark purged in RecorderAnalyzer cache ─────────────────────
            # Covers the pending entities too: the recorder will finish them,
            # and the TTL is long enough that the next scan does not re-list
            # rows that are on their way out.
            rec_analyzer = domain_data.get("recorder_analyzer")
            if rec_analyzer:
                rec_analyzer.mark_purged(entity_ids)

            # ── Patch coordinator.data immediately ────────────────────────
            # Any haca/get_data call between now and the next full scan would
            # otherwise return stale orphan data from coordinator.data.
            coordinator = domain_data.get("coordinator")
            if coordinator and coordinator.data:
                cached = coordinator.data
                old_orphans = cached.get("recorder_orphans", [])
                new_orphans = [
                    o for o in old_orphans if o["entity_id"] not in purged_set
                ]
                new_mb = round(sum(o["est_mb"] for o in new_orphans), 2)
                coordinator.data = {
                    **cached,
                    "recorder_orphans":      new_orphans,
                    "recorder_orphan_count": len(new_orphans),
                    "recorder_wasted_mb":    new_mb,
                }
                _LOGGER.debug(
                    "[HACA Purge] coordinator.data patched: %d → %d orphan(s)",
                    len(old_orphans), len(new_orphans),
                )

    except Exception as cache_exc:
        _LOGGER.debug("[HACA Purge] could not patch coordinator cache: %s", cache_exc)

    connection.send_result(
        msg["id"],
        {
            "purged": len(entity_ids),
            "entity_ids": entity_ids,
            "detail": detail,
            "pending": pending,
        },
    )



@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_history",
        vol.Optional("limit", default=90): int,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return audit history snapshots for the history tab / sparkline."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_result(msg["id"], {"history": []})
            return

        domain_data = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {})
        history_manager = domain_data.get("history_manager")

        if not history_manager:
            connection.send_result(msg["id"], {"history": []})
            return

        limit = min(msg.get("limit", 90), 365)
        history = await history_manager.async_get_history(limit)
        connection.send_result(msg["id"], {"history": history})
    except Exception as exc:
        _LOGGER.error("HACA get_history error: %s", exc)
        connection.send_error(msg["id"], "history_error", str(exc))


@websocket_api.websocket_command({
    vol.Required("type"): "haca/delete_history",
    vol.Required("timestamps"): [str],
})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_delete_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Supprime des entrées de l'historique par timestamp."""
    # `hass.data[DOMAIN]` is not a dict of entries only: it also carries the
    # panel language slots and the per-scan caches. Taking `next(iter(...))`
    # as the entry id worked while the entry happened to be inserted first,
    # but a reload pops the entry and puts it back *after* those keys — the
    # handler then read a string where it expected the entry dict.
    _entry, data = _get_entry_data(hass)
    if not data:
        connection.send_error(msg["id"], "not_ready", "HACA not initialized")
        return
    history_manager = data.get("history_manager")
    if not history_manager:
        connection.send_error(msg["id"], "no_history", "History manager unavailable")
        return
    try:
        timestamps = msg["timestamps"]
        deleted = await history_manager.async_delete_entries(timestamps)
        connection.send_result(msg["id"], {"deleted": deleted})
    except Exception as exc:
        _LOGGER.error("HACA delete_history error: %s", exc)
        connection.send_error(msg["id"], "delete_error", str(exc))


# Server-emitted text (persistent notifications, Repairs, scan messages) follows
# the panel user's profile language through the ``notification_language_auto``
# entry option. Persisting it wrote to `.storage/core.config_entries` every time
# the value changed, so two admins in two languages opening the panel in turn
# produced one disk write each. At most one write per hour is enough: the option
# only decides the language of background notifications.
_AUTO_LANG_MIN_INTERVAL = 3600.0
_AUTO_LANG_LAST_WRITE_KEY = "_auto_language_last_write"


def _track_auto_notification_language(hass: HomeAssistant, language: str) -> None:
    """Persist the panel profile language for server-side notifications.

    Skipped when the entry already carries this language, and rate-limited to
    one write per hour so that alternating users cannot turn every panel open
    into a config-entry write. An explicit ``notification_language`` set from
    the Configuration tab always wins and is never overwritten — see
    ``translation_utils.resolve_notification_language``.
    """
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return
        entry = entries[0]
        if (entry.options or {}).get("notification_language_auto") == language:
            return

        store = hass.data.setdefault(DOMAIN, {})
        last = store.get(_AUTO_LANG_LAST_WRITE_KEY)
        now = _monotonic()
        if last is not None and now - last < _AUTO_LANG_MIN_INTERVAL:
            _LOGGER.debug(
                "HACA: auto-tracked language %s not persisted yet (last write %.0fs ago)",
                language, now - last,
            )
            return

        new_options = dict(entry.options or {})
        new_options["notification_language_auto"] = language
        hass.config_entries.async_update_entry(entry, options=new_options)
        store[_AUTO_LANG_LAST_WRITE_KEY] = now
        _LOGGER.info(
            "[HACA] Tracked panel profile language for notifications: %s", language
        )
    except Exception as exc:  # noqa: BLE001 — never break the panel over this
        _LOGGER.debug("HACA: could not persist auto-tracked language: %s", exc)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_translations",
        vol.Optional("language"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_translations(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle get translations request for the panel.

    Served entirely from ``_TS_PANEL_CACHE``, which ``_async_preload_ts_cache``
    fills with all 13 files at setup. This used to re-read and re-parse a
    ~130 KB JSON from disk on every panel open, next to a copy of the same
    file already sitting in memory.
    """
    try:
        # Language comes from the frontend (= user profile language, not system
        # language). Only the codes HACA actually ships are accepted — see
        # _safe_language().
        language = _safe_language(msg.get("language"), hass.config.language)
        store = hass.data.setdefault(DOMAIN, {})
        # Remembered per user: a single shared slot meant that the last admin
        # to open the panel decided the language of everyone else's websocket
        # answers. The shared slot is kept as a fallback for callers that have
        # no connection in hand.
        user_id = getattr(getattr(connection, "user", None), "id", None)
        if user_id:
            store.setdefault("user_languages", {})[user_id] = language
        store["user_language"] = language
        _LOGGER.debug("HACA: user language = %s", language)

        _track_auto_notification_language(hass, language)

        # The panel navigates from `panel.*`, so it gets the raw subtree — not
        # the merged tree the server-side helpers read.
        from . import _TS_PANEL_CACHE  # noqa: PLC0415
        panel_translations = (
            _TS_PANEL_CACHE.get(language)
            or _TS_PANEL_CACHE.get("en")
            or {}
        )
        if not panel_translations:
            _LOGGER.warning(
                "HACA: translation cache is empty — panel will show raw keys"
            )

        connection.send_result(
            msg["id"],
            {
                "language": language,
                "translations": panel_translations,
            },
        )

    except Exception as e:
        _LOGGER.error("Error getting translations: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/explain_issue",
        vol.Required("issue"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_explain_issue(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Explain a HACA issue using AI (IA locale ou fallback textuel)."""
    try:
        from .conversation import explain_issue_ai
        issue_data = msg.get("issue", {})
        explanation = await explain_issue_ai(hass, issue_data)
        connection.send_result(msg["id"], {"explanation": explanation})
    except Exception as e:
        _LOGGER.error("Error in haca/explain_issue: %s", e, exc_info=True)
        connection.send_error(msg["id"], "error", str(e))


class _EntryMatch(NamedTuple):
    """One automation/script entry, found in the file HA actually loads it from."""

    path: str | None
    yaml: Any           # the ruamel instance that parsed `document`
    document: Any       # file root: a list for automations, a mapping for scripts
    entry: Any          # the matched mapping, still attached to `document`
    files: list[str]    # every file the domain key resolved to
    skipped: list[str]  # files that could not be parsed for editing


def _find_entry_sync(config_dir: str, entity_id: str, alias: str) -> _EntryMatch:
    """Locate an automation or script across the config HA actually loads.

    A split config (`automation: !include_dir_merge_list automations/`) keeps its
    entries in several files; the flat `<config>/automations.yaml` this used to
    read may not even exist. Every candidate file is parsed in ruamel round-trip
    mode, so the caller can edit the entry without flattening the comments and
    formatting around it.

    Matching runs in priority passes over *all* files, so an exact `id` always
    wins over an alias that happens to collide in another file.
    """
    is_script = entity_id.startswith("script.")
    key, default_filename = ("script", "scripts.yaml") if is_script else ("automation", "automations.yaml")
    slug = entity_id.split(".", 1)[-1]
    alias = (alias or "").strip()
    alias_lower = alias.lower()

    files = iter_domain_files(config_dir, key, default_filename)
    skipped: list[str] = []
    loaded: list[tuple[str, Any, Any]] = []

    for path in files:
        try:
            yaml, data = read_roundtrip_yaml(path)
        except Exception:  # noqa: BLE001 — syntax error, unreadable file
            skipped.append(path)
            continue
        # An empty parse, the wrong shape, or a Home Assistant tag we would have
        # to rewrite: skip rather than risk replacing the file with something else.
        if data is None or contains_ha_tag(data):
            skipped.append(path)
            continue
        if not isinstance(data, dict if is_script else list):
            skipped.append(path)
            continue
        loaded.append((path, yaml, data))

    def _entries(document):
        """(key, mapping) pairs of one file, whatever shape the domain has."""
        if is_script:
            return [(k, v) for k, v in document.items() if isinstance(v, dict)]
        return [(None, item) for item in document if isinstance(item, dict)]

    def _slugified(entry) -> str:
        return str(entry.get("alias", "")).strip().lower().replace(" ", "_")

    if is_script:
        passes = [
            lambda k, e: k == slug,
            lambda k, e: bool(alias) and str(e.get("alias", "")).strip() == alias,
            lambda k, e: bool(alias) and str(e.get("alias", "")).strip().lower() == alias_lower,
        ]
    else:
        passes = [
            lambda k, e: bool(str(e.get("id", "")).strip()) and str(e.get("id", "")).strip() == slug,
            lambda k, e: bool(alias) and str(e.get("alias", "")).strip() == alias,
            lambda k, e: bool(alias) and str(e.get("alias", "")).strip().lower() == alias_lower,
            lambda k, e: _slugified(e) == slug,
        ]

    for matches in passes:
        for path, yaml, document in loaded:
            for entry_key, entry in _entries(document):
                if matches(entry_key, entry):
                    return _EntryMatch(path, yaml, document, entry, files, skipped)

    return _EntryMatch(None, None, None, None, files, skipped)


def _entry_not_found_message(entity_id: str, alias: str, match: _EntryMatch) -> str:
    """Miss message that says what was searched — same wording as the MCP tools."""
    return (
        f"'{entity_id}' (alias={alias!r}) was not found in any YAML file for its "
        f"domain ({len(match.files)} scanned). Only YAML entries can be edited "
        f"this way." + skipped_note(match.skipped)
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/ai_suggest_fix",
        vol.Required("issue"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_ai_suggest_fix(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Génère par IA la valeur manquante pour une issue simple (description, alias…).

    Retourne {field, suggestion, entity_id} — pas de modification effectuée.
    L'utilisateur peut éditer la suggestion dans la modale avant d'appliquer.
    """
    from .conversation import _async_call_ai

    issue      = msg.get("issue", {})
    issue_type = issue.get("type", "")
    entity_id  = issue.get("entity_id", "")
    alias      = issue.get("alias") or entity_id

    # ── Déterminer le champ cible ────────────────────────────────────────
    FIELD_MAP = {
        "no_description": "description",
        "no_alias":       "alias",
    }
    field = FIELD_MAP.get(issue_type)
    if not field:
        connection.send_error(msg["id"], "unsupported_type",
                              f"Issue type '{issue_type}' n'est pas une correction simple")
        return

    # ── Lire le YAML de l'automation/script ─────────────────────────────
    # Passe par le résolveur partagé : sur une config éclatée, l'entrée ne vit
    # pas dans <config>/automations.yaml, et la suggestion sortait sans contexte.
    yaml_snippet = ""
    try:
        def _read_snippet() -> str:
            match = _find_entry_sync(hass.config.config_dir, entity_id, alias)
            if match.entry is None:
                _LOGGER.debug(
                    "[HACA suggest] %s not found in %d file(s)%s",
                    entity_id, len(match.files), skipped_note(match.skipped),
                )
                return ""
            buffer = io.StringIO()
            match.yaml.dump(match.entry, buffer)
            return buffer.getvalue()

        yaml_snippet = await hass.async_add_executor_job(_read_snippet)
    except Exception as exc:
        _LOGGER.debug("[HACA suggest] Could not read YAML for %s: %s", entity_id, exc)

    # ── Construire le prompt ─────────────────────────────────────────────
    lang = hass.config.language or "fr"

    if field == "description":
        prompt = (
            f"You are a Home Assistant expert. Generate a concise, helpful description "
            f"(1–2 sentences, max 120 characters) for this {'script' if entity_id.startswith('script.') else 'automation'}.\n"
            f"Name: {alias}\n"
        )
        if yaml_snippet:
            prompt += f"YAML:\n```yaml\n{yaml_snippet[:2000]}\n```\n"
        prompt += (
            f"Respond in {lang}. "
            f"Return ONLY the description text — no quotes, no explanation, no prefix."
        )
    elif field == "alias":
        prompt = (
            f"You are a Home Assistant expert. Generate a short, clear alias (name) "
            f"for this {'script' if entity_id.startswith('script.') else 'automation'}.\n"
            f"Entity ID: {entity_id}\n"
        )
        if yaml_snippet:
            prompt += f"YAML:\n```yaml\n{yaml_snippet[:2000]}\n```\n"
        prompt += (
            f"Respond in {lang}. "
            f"Return ONLY the alias text — no quotes, no explanation."
        )

    # ── Appeler l'IA ─────────────────────────────────────────────────────
    try:
        suggestion = await _async_call_ai(hass, prompt, "HACA Simple Fix")
        suggestion = suggestion.strip().strip('"').strip("'")
        if not suggestion:
            connection.send_error(msg["id"], "no_suggestion", "L'IA n'a pas retourné de suggestion")
            return
        connection.send_result(msg["id"], {
            "field":     field,
            "suggestion": suggestion,
            "entity_id": entity_id,
        })
    except Exception as exc:
        _LOGGER.error("[HACA suggest] AI error: %s", exc)
        connection.send_error(msg["id"], "ai_error", str(exc))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/apply_field_fix",
        vol.Required("entity_id"): str,
        vol.Required("field"): str,
        vol.Required("value"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_apply_field_fix(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Applique une correction simple (description, alias) directement dans le YAML.

    L'écriture est en round-trip ruamel : commentaires, ordre des clés, styles de
    guillemets et ancres du fichier survivent à l'édition. Une sauvegarde est
    prise avant toute écriture, dans le même dossier que celles du module de
    refactoring — donc restaurable depuis le panneau.
    Recharge les automations/scripts après modification.
    """
    # Rate-limit: prevent spamming YAML writes
    user_id = connection.user.id if connection.user else "anon"
    if _rate_limited(f"apply_field_fix:{user_id}"):
        connection.send_error(msg["id"], "rate_limited", "Too many requests — please wait a moment")
        return

    entity_id = msg["entity_id"]
    field     = msg["field"]
    value     = msg["value"].strip()
    alias     = msg.get("alias", "").strip()

    if field not in ("description", "alias"):
        connection.send_error(msg["id"], "unsupported_field", f"Champ '{field}' non supporté")
        return

    domain = "script" if entity_id.startswith("script.") else "automation"

    try:
        match = await hass.async_add_executor_job(
            _find_entry_sync, hass.config.config_dir, entity_id, alias
        )
        if match.entry is None:
            connection.send_error(
                msg["id"], "not_found", _entry_not_found_message(entity_id, alias, match)
            )
            return

        # Backup first — this rewrites a file the user maintains by hand.
        entry_data = _get_entry_data(hass)[1] or {}
        refactoring = entry_data.get("refactoring_assistant")
        if refactoring is None:
            # Refactoring module disabled: build one just for its backup logic,
            # so the naming stays compatible with the panel's restore list.
            from .refactoring_assistant import RefactoringAssistant
            refactoring = RefactoringAssistant(hass)
        backup_path = await refactoring._create_backup(Path(match.path))

        def _write() -> None:
            match.entry[field] = value
            write_roundtrip_yaml(match.path, match.yaml, match.document)

        await hass.async_add_executor_job(_write)

        # Recharger pour que HA prenne en compte
        await hass.services.async_call(domain, "reload", {}, blocking=True)
        connection.send_result(msg["id"], {
            "success": True,
            "field": field,
            "value": value,
            "file": Path(match.path).name,
            "backup": Path(backup_path).name,
        })
    except Exception as exc:
        _LOGGER.error("[HACA apply_field_fix] %s: %s", entity_id, exc)
        connection.send_error(msg["id"], "apply_error", str(exc))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/chat",
        vol.Required("message"): str,
        vol.Optional("conversation_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_chat(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Chat IA avec fallback automatique entre tous les agents configurés dans HA.

    L'agent préféré (pipeline Assist) est essayé en premier.
    Si il échoue (quota épuisé, timeout, erreur), HACA tente les autres agents
    disponibles dans l'ordre : Gemini, Llama, etc.

    Chaque agent doit avoir le LLM API HACA activé pour utiliser les 60 outils :
      HA Settings → Voice Assistants → [agent] → LLM API → HACA
    """
    from homeassistant.core import Context
    from homeassistant.components.conversation import async_converse
    from .conversation import _async_find_all_conversation_agents, _is_llm_error_reply
    import inspect as _inspect

    user_msg = msg["message"].strip()
    conv_id  = msg.get("conversation_id")

    if not user_msg:
        connection.send_error(msg["id"], "empty_message", "Empty message")
        return

    # Tous les agents disponibles — préféré en premier
    agents = await _async_find_all_conversation_agents(hass)
    if not agents:
        connection.send_result(
            msg["id"],
            {
                "reply": _ts(hass, "misc", "no_ai_model", connection=connection),
                "conversation_id": conv_id,
                "agent_id": None,
            },
        )
        return

    # Préparer les kwargs async_converse une seule fois
    params = set(_inspect.signature(async_converse).parameters)

    def _make_kwargs(agent_id: str) -> dict:
        kw: dict = {
            "hass": hass,
            "text": user_msg,
            "conversation_id": conv_id,
            "context": Context(),
            "agent_id": agent_id,
        }
        if "language" in params:
            kw["language"] = hass.config.language or "en"
        if "device_id" in params:
            kw["device_id"] = None
        return kw

    def _extract_reply(result) -> str:
        if not result or not result.response:
            return ""
        speech = result.response.speech
        if not isinstance(speech, dict):
            return ""
        return (
            speech.get("plain", {}).get("speech", "")
            or next((v.get("speech", "") for v in speech.values() if isinstance(v, dict)), "")
        )

    last_error = ""
    for agent_id in agents:
        try:
            _LOGGER.info("[HACA Chat] Trying agent=%s msg=%.80s", agent_id, user_msg)
            result = await async_converse(**_make_kwargs(agent_id))
            reply  = _extract_reply(result)

            if not reply:
                _LOGGER.warning("[HACA Chat] %s: empty reply → trying next", agent_id)
                continue

            if _is_llm_error_reply(reply):
                _LOGGER.warning("[HACA Chat] %s: error reply (%.80s) → trying next", agent_id, reply)
                last_error = reply
                continue

            # Succès
            returned_conv_id = conv_id
            try:
                returned_conv_id = result.conversation_id or conv_id
            except Exception:
                pass

            _LOGGER.info("[HACA Chat] OK %s", agent_id)
            connection.send_result(
                msg["id"],
                {"reply": reply, "conversation_id": returned_conv_id, "agent_id": agent_id},
            )
            return

        except Exception as exc:
            last_error = str(exc)
            _LOGGER.warning("[HACA Chat] %s failed: %s → trying next", agent_id, exc)

    # Tous les agents ont échoué
    _LOGGER.error("[HACA Chat] All agents failed. Last error: %s", last_error)
    connection.send_result(
        msg["id"],
        {
            "reply": last_error or _ts(hass, "misc", "ai_error", connection=connection),
            "conversation_id": conv_id,
            "agent_id": None,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_options",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_options(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Retourne les options courantes de l'intégration HACA."""
    entry, _ = _get_entry_data(hass)
    if not entry:
        connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
        return
    opts = dict(entry.options)
    connection.send_result(msg["id"], {"options": opts})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/save_options",
        vol.Required("options"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_save_options(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Sauvegarde les options HACA depuis le panel (remplace le flux options HA natif)."""
    # Rate-limit: prevent spamming config writes
    user_id = connection.user.id if connection.user else "anon"
    if _rate_limited(f"save_options:{user_id}"):
        connection.send_error(msg["id"], "rate_limited", "Too many requests — please wait a moment")
        return

    entry, _ = _get_entry_data(hass)
    if not entry:
        connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
        return

    new_options = dict(entry.options)
    incoming = msg.get("options", {})

    ALLOWED_KEYS = {
        "scan_interval", "startup_delay_seconds", "startup_scan_enabled",
        "event_monitoring_enabled", "event_debounce_seconds",
        "excluded_categories", "excluded_issue_types",
        "battery_critical", "battery_low", "battery_warning",
        "history_retention_days", "backup_enabled",
        "debug_mode",
        "excluded_compliance_types",
        "report_frequency",   # daily | weekly | monthly | never
        "repairs_enabled",    # true (default) | false — push HIGH issues to HA Repairs
        "battery_notifications_enabled",  # true (default) | false — battery persistent notifications
        "notify_high_severity",    # true (default) — persistent notification for HIGH issues
        "notify_medium_severity",  # false (default) — persistent notification for MEDIUM issues
        "notify_low_severity",     # false (default) — persistent notification for LOW issues
        "battery_last_replaced",   # dict {entity_id: ISO datetime} — battery replacement tracking
        "noisy_scan_exclude_patterns",  # list[str] — glob patterns to skip in noisy entity scan
        "llm_write_enabled",   # false (default) — let conversation agents use HACA write tools
    }
    for key, value in incoming.items():
        if key in ALLOWED_KEYS and value is not None:  # ignorer les None (token non modifié)
            new_options[key] = value

    hass.config_entries.async_update_entry(entry, options=new_options)

    # Si debug_mode a changé, appliquer le niveau de log immédiatement
    if "debug_mode" in incoming:
        import logging as _logging
        _level = _logging.DEBUG if incoming["debug_mode"] else _logging.INFO
        _logging.getLogger("custom_components.config_auditor").setLevel(_level)
        try:
            await hass.services.async_call(
                "logger", "set_level",
                {"custom_components.config_auditor": "debug" if incoming["debug_mode"] else "info"},
                blocking=False,
            )
        except Exception:
            pass

    # Appliquer dynamiquement les options qui le permettent sans redémarrer HA
    domain_data = hass.data.get(DOMAIN, {})
    for entry_data in domain_data.values():
        if not isinstance(entry_data, dict):
            continue

        # excluded_issue_types → démarrer/arrêter le tracker noisy en direct.
        # Il écoute EVENT_STATE_CHANGED pour toute l'instance : inutile de le
        # laisser tourner si l'utilisateur a désactivé le type "noisy_entity".
        if "excluded_issue_types" in incoming:
            tracker = entry_data.get("noisy_tracker")
            if tracker is not None:
                from .performance_analyzer import noisy_scan_enabled
                enabled = noisy_scan_enabled(hass)
                tracker.start() if enabled else tracker.stop()
                _LOGGER.info(
                    "[HACA] noisy-entity scan %s",
                    "enabled" if enabled else "disabled",
                )

        # scan_interval → mettre à jour l'intervalle du coordinator (0 = manual only)
        if "scan_interval" in incoming:
            coordinator = entry_data.get("coordinator")
            if coordinator is not None:
                from datetime import timedelta as _td
                val = int(incoming["scan_interval"])
                coordinator.update_interval = _td(minutes=max(1, val)) if val > 0 else None
                _LOGGER.info("[HACA] scan_interval updated: %s", "manual" if val == 0 else f"{val} min")

    _LOGGER.info("[HACA] Options saved via panel: %s", list(incoming.keys()))
    connection.send_result(msg["id"], {"success": True, "options": new_options})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/recorder_exclude_entity",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_recorder_exclude_entity(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Add an entity to ``recorder.exclude.entities`` in configuration.yaml.

    Behaviour (per the in-app contract documented next to the button):
      - configuration.yaml is backed up to ``<config>/.haca_backups/`` first
      - ruamel.yaml round-trip preserves comments and formatting
      - the result is validated via ``homeassistant.check_config``; on failure
        the file is restored from the backup
      - the change becomes effective at the next HACA scan (and the live
        recorder filter only honours it after the user restarts HA)

    Reply schema mirrors ``recorder_yaml_editor.async_add_entity_to_recorder_exclude``.
    """
    from .recorder_yaml_editor import async_add_entity_to_recorder_exclude
    entity_id: str = msg["entity_id"]
    try:
        result = await async_add_entity_to_recorder_exclude(hass, entity_id)
    except Exception as exc:
        _LOGGER.error("[HACA] recorder_exclude_entity failed: %s", exc, exc_info=True)
        connection.send_error(msg["id"], "exclude_failed", str(exc))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/mark_battery_replaced",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_mark_battery_replaced(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Record today's date as last battery replacement for an entity."""
    from datetime import datetime
    entry, _ = _get_entry_data(hass)
    if not entry:
        connection.send_error(msg["id"], "not_found", "HACA entry not found")
        return

    eid: str = msg["entity_id"]
    today_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    current = dict(entry.options.get("battery_last_replaced", {}) or {})
    current[eid] = today_iso

    new_options = dict(entry.options)
    new_options["battery_last_replaced"] = current
    hass.config_entries.async_update_entry(entry, options=new_options)

    connection.send_result(msg["id"], {"success": True, "entity_id": eid, "date": today_iso})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/get_battery_library_info",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_battery_library_info(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the paths of the HACA battery library — bundled seed and user file."""
    seed_path = ""
    user_path = ""
    size = 0
    user_count = 0
    try:
        lib = hass.data.get("haca_battery_library")
        if lib is not None:
            seed_path = lib.seed_path
            user_path = lib.user_path
            size = lib.size
            user_count = lib.user_count
    except Exception as exc:
        _LOGGER.debug("[HACA] battery_library_info: %s", exc)

    connection.send_result(msg["id"], {
        "seed_path": seed_path,
        "user_path": user_path,
        "size": size,
        "user_count": user_count,
    })


@websocket_api.websocket_command(
    {
        vol.Required("type"): "haca/set_log_level",
        vol.Required("level"): vol.In(["debug", "info", "warning", "error"]),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def handle_set_log_level(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Change dynamiquement le niveau de log de tous les loggers HACA.

    Équivalent à ajouter dans configuration.yaml :
      logger:
        logs:
          custom_components.config_auditor: debug

    Mais appliqué immédiatement sans redémarrage, via le service logger de HA.
    """
    import logging
    level_str = msg["level"].upper()
    level = getattr(logging, level_str, logging.INFO)

    # Appliquer au logger parent — tous les sous-loggers héritent
    parent_logger = logging.getLogger("custom_components.config_auditor")
    parent_logger.setLevel(level)

    # Propager aussi via le service logger de HA si disponible (persiste dans les logs UI)
    try:
        await hass.services.async_call(
            "logger",
            "set_level",
            {"custom_components.config_auditor": level_str.lower()},
            blocking=False,
        )
    except Exception:
        pass  # Le service logger peut ne pas être chargé

    _LOGGER.info("[HACA] Log level set to %s for custom_components.config_auditor", level_str)
    connection.send_result(msg["id"], {"success": True, "level": level_str})


# ─── v1.4.0 WebSocket Handlers ────────────────────────────────────────────

@websocket_api.websocket_command({"type": "haca/mcp_status"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_mcp_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Retourne le statut et l'URL du serveur MCP HACA."""
    try:
        import json as _json
        base_url = hass.config.external_url or hass.config.internal_url or "http://homeassistant.local:8123"
        mcp_url = f"{base_url.rstrip('/')}/api/haca_mcp"

        claude_code_config = {
            "mcpServers": {
                "haca": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-proxy"],
                    "env": {
                        "MCP_SERVER_URL": mcp_url,
                        "MCP_AUTH_HEADER": "Authorization: Bearer <YOUR_HA_LONG_LIVED_TOKEN>",
                    },
                }
            }
        }
        connection.send_result(msg["id"], {
            "active": True,
            "url": "/api/haca_mcp",
            "full_url": mcp_url,
            "info_url": f"{mcp_url}/info",
            "auth": "Bearer <HA Long-Lived Access Token>",
            "tools": [
                "haca_get_score", "haca_get_issues", "haca_get_automation",
                "haca_fix_suggestion", "haca_apply_fix",
                "haca_get_batteries", "haca_explain_issue",
            ],
            "claude_code_snippet": _json.dumps(claude_code_config, indent=2, ensure_ascii=False),
        })
    except Exception as exc:
        connection.send_error(msg["id"], "mcp_error", str(exc))


@websocket_api.websocket_command({"type": "haca/agent_status"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_agent_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Retourne le statut de l'agent IA proactif."""
    try:
        from .proactive_agent import get_agent
        agent = get_agent(hass)

        if not agent:
            connection.send_result(msg["id"], {"active": False, "correlations": []})
            return

        correlations = await agent.analyze_correlations()
        prefs = agent.get_preferences()

        entries = hass.config_entries.async_entries(DOMAIN)
        entry_data = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {}) if entries else {}
        last_report = entry_data.get("last_weekly_report")
        entry = entries[0] if entries else None
        report_frequency = entry.options.get("report_frequency", "weekly") if entry else "weekly"

        connection.send_result(msg["id"], {
            "active": True,
            "correlations": correlations[:10],
            "last_weekly_report": last_report,
            "preferred_fix_types": prefs.get_preferred_fix_types(),
            "report_frequency": report_frequency,
        })
    except Exception as exc:
        connection.send_error(msg["id"], "agent_error", str(exc))


@websocket_api.websocket_command({"type": "haca/agent_force_report"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_agent_force_report(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Force l'envoi immédiat du rapport hebdomadaire et retourne le contenu MD."""
    try:
        from .proactive_agent import get_agent
        agent = get_agent(hass)
        if not agent:
            connection.send_error(msg["id"], "no_agent", "Agent not running")
            return
        # Reset last report date pour forcer l'envoi
        entries = hass.config_entries.async_entries(DOMAIN)
        entry_data: dict = {}
        if entries:
            entry_data = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {})
            entry_data.pop("last_weekly_report", None)
            entry_data.pop("last_report_markdown", None)

        await agent._check_weekly_report_async()

        # Récupérer le markdown généré
        markdown = entry_data.get("last_report_markdown", "")
        report_file = entry_data.get("last_report_file", "")
        filename = ""
        if report_file:
            from pathlib import Path
            filename = Path(report_file).name

        connection.send_result(msg["id"], {
            "success": True,
            "markdown": markdown,
            "filename": filename,
            "report_file": report_file,
        })
    except Exception as exc:
        connection.send_error(msg["id"], "force_report_error", str(exc))


@websocket_api.websocket_command({
    vol.Required("type"): "haca/record_fix_outcome",
    vol.Required("issue_type"): str,
    vol.Required("accepted"): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_record_fix_outcome(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Enregistre si un fix a été accepté ou refusé (apprentissage agent)."""
    try:
        from .proactive_agent import get_agent
        agent = get_agent(hass)
        if agent:
            agent.record_fix_outcome(msg["issue_type"], msg["accepted"])
        connection.send_result(msg["id"], {"success": True})
    except Exception as exc:
        connection.send_error(msg["id"], "outcome_error", str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
#  v1.5.0 — WebSocket handlers
# ═══════════════════════════════════════════════════════════════════════════════

def _get_entry_data(hass) -> tuple:
    """Return (entry, entry_data_dict) or (None, None).

    Centralises the repeated entries[0] + hass.data[DOMAIN][entry_id] lookup
    that appears in almost every WebSocket handler.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None, None
    entry = entries[0]
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    return entry, data


def _get_coordinator(hass):
    """Helper: return (entry, coordinator) or (None, None)."""
    entry, data = _get_entry_data(hass)
    if not data:
        return None, None
    return entry, data.get("coordinator")


# ── Battery predictions ────────────────────────────────────────────────────────

@websocket_api.websocket_command({vol.Required("type"): "haca/get_battery_predictions"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_battery_predictions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return battery discharge predictions."""
    try:
        entry, coord = _get_coordinator(hass)
        if not coord:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        data = coord.data or {}
        connection.send_result(msg["id"], {
            "predictions": data.get("battery_predictions", []),
            "alert_7d":    data.get("battery_alert_7d", 0),
        })
    except Exception as exc:
        connection.send_error(msg["id"], "prediction_error", str(exc))


@websocket_api.websocket_command({vol.Required("type"): "haca/export_battery_csv"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_export_battery_csv(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return full battery history as CSV string."""
    try:
        from .const import MODULE_18_BATTERY_PREDICTOR
        if not MODULE_18_BATTERY_PREDICTOR:
            connection.send_result(msg["id"], {"csv": "date,entity_id,level\n"})
            return
        # Reuse the loaded instance so we hit the in-memory .storage cache
        entries = hass.config_entries.async_entries(DOMAIN)
        domain_data = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {}) if entries else {}
        predictor = domain_data.get("battery_predictor")
        if predictor is None:
            from .battery_predictor import BatteryPredictor
            predictor = BatteryPredictor(hass)
        csv_data = await predictor.async_export_csv()
        connection.send_result(msg["id"], {"csv": csv_data})
    except Exception as exc:
        connection.send_error(msg["id"], "csv_error", str(exc))


# ── Reports ────────────────────────────────────────────────────────────────

@websocket_api.websocket_command({
    vol.Required("type"): "haca/get_report_url",
    vol.Required("filename"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_report_url(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return a short-lived signed URL for one report file.

    The reports endpoint requires authentication, which an <iframe src> or a
    download link cannot carry. A signed path can: HA validates the signature
    and resolves it back to this admin's refresh token.
    """
    from datetime import timedelta

    from .const import REPORTS_DIR
    from .report_generator import resolve_report_path
    from .report_view import REPORT_URL_PREFIX

    reports_dir = Path(hass.config.path(REPORTS_DIR))
    path = await hass.async_add_executor_job(
        resolve_report_path, reports_dir, msg["filename"]
    )
    if path is None:
        connection.send_error(
            msg["id"], "not_found", f"Report '{msg['filename']}' not found"
        )
        return

    try:
        from homeassistant.components.http.auth import async_sign_path
    except ImportError:      # older layouts re-export it from the package
        from homeassistant.components.http import async_sign_path

    try:
        signed = async_sign_path(
            hass,
            f"{REPORT_URL_PREFIX}/{path.name}",
            timedelta(minutes=30),
            refresh_token_id=connection.refresh_token_id,
        )
    except Exception as exc:
        _LOGGER.error("HACA: could not sign report URL: %s", exc)
        connection.send_error(msg["id"], "sign_error", str(exc))
        return

    connection.send_result(msg["id"], {"url": signed})


# ── Area complexity ────────────────────────────────────────────────────────────

@websocket_api.websocket_command({vol.Required("type"): "haca/get_area_complexity"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_area_complexity(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return area complexity heatmap data."""
    try:
        entry, coord = _get_coordinator(hass)
        if not coord:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        data = coord.data or {}
        connection.send_result(msg["id"], data.get("area_complexity", {}))
    except Exception as exc:
        connection.send_error(msg["id"], "area_error", str(exc))


# ── Redundancy ─────────────────────────────────────────────────────────────────

@websocket_api.websocket_command({vol.Required("type"): "haca/get_redundancy"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_redundancy(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return redundancy analysis results."""
    try:
        entry, coord = _get_coordinator(hass)
        if not coord:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        data = coord.data or {}
        connection.send_result(msg["id"], data.get("redundancy", {}))
    except Exception as exc:
        connection.send_error(msg["id"], "redundancy_error", str(exc))


# ── Recorder impact ────────────────────────────────────────────────────────────

@websocket_api.websocket_command({vol.Required("type"): "haca/get_recorder_impact"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_recorder_impact(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return recorder DB impact analysis."""
    try:
        entry, coord = _get_coordinator(hass)
        if not coord:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        data = coord.data or {}
        connection.send_result(msg["id"], data.get("recorder_impact", {}))
    except Exception as exc:
        connection.send_error(msg["id"], "recorder_impact_error", str(exc))


# ── Integration monitor ───────────────────────────────────────────────────────

@websocket_api.websocket_command({vol.Required("type"): "haca/get_integrations"})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_integrations(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return integration monitor analysis results (on-demand, no scan required)."""
    try:
        entry, entry_data = _get_entry_data(hass)
        if not entry_data:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        analyzer = entry_data.get("integration_analyzer")
        if not analyzer:
            connection.send_error(msg["id"], "not_available", "Integration analyzer not available")
            return
        result = await analyzer.async_analyze()
        connection.send_result(msg["id"], result)
    except Exception as exc:
        connection.send_error(msg["id"], "integration_error", str(exc))


# ── History diff ───────────────────────────────────────────────────────────────

@websocket_api.websocket_command({
    vol.Required("type"): "haca/get_history_diff",
    vol.Required("ts"): str,      # timestamp of the scan to diff
})
@websocket_api.require_admin
@websocket_api.async_response
async def handle_get_history_diff(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return diff between a scan and its predecessor (new/resolved issues)."""
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            connection.send_error(msg["id"], "no_entry", "No H.A.C.A entry found")
            return
        entry = entries[0]
        coord_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
        history_manager = coord_data.get("history_manager")
        if not history_manager:
            connection.send_result(msg["id"], {"diff": None, "error": "history_not_available"})
            return

        history = await history_manager.async_get_history(limit=365)
        target_ts = msg["ts"]

        # Find target and predecessor
        target = next((h for h in history if h.get("ts") == target_ts), None)
        if not target:
            connection.send_error(msg["id"], "not_found", f"Scan {target_ts} not found")
            return

        target_idx = history.index(target)
        predecessor = history[target_idx - 1] if target_idx > 0 else None

        if not predecessor:
            connection.send_result(msg["id"], {
                "target": target,
                "predecessor": None,
                "diff": None,
            })
            return

        # Compute diff on issue counts per category
        categories = ["automation", "script", "scene", "entity", "performance",
                      "security", "blueprint", "dashboard"]
        diff = {}
        for cat in categories:
            old_val = predecessor.get(cat, 0)
            new_val = target.get(cat, 0)
            diff[cat] = {
                "old": old_val,
                "new": new_val,
                "delta": new_val - old_val,
            }

        # Top issues diff (new issues vs resolved)
        prev_top_ids = {i.get("entity_id") + i.get("type", "") for i in (predecessor.get("top_issues") or [])}
        curr_top     = target.get("top_issues") or []

        new_issues      = [i for i in curr_top if (i.get("entity_id", "") + i.get("type", "")) not in prev_top_ids]
        prev_top        = predecessor.get("top_issues") or []
        curr_top_ids    = {i.get("entity_id") + i.get("type", "") for i in curr_top}
        resolved_issues = [i for i in prev_top if (i.get("entity_id", "") + i.get("type", "")) not in curr_top_ids]

        connection.send_result(msg["id"], {
            "target":      target,
            "predecessor": predecessor,
            "diff":        diff,
            "new_issues":      new_issues,
            "resolved_issues": resolved_issues,
            "score_delta": target.get("score", 0) - predecessor.get("score", 0),
        })
    except Exception as exc:
        _LOGGER.warning("History diff error: %s", exc)
        connection.send_error(msg["id"], "diff_error", str(exc))



