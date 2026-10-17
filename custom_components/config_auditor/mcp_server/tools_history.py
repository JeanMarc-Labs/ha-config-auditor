"""Recorder-backed tools: state history, long-term statistics, logbook."""
from __future__ import annotations

from homeassistant.core import HomeAssistant


# ── Handlers — medium priority tools ────────────────────────────────────────

async def _tool_ha_get_history(hass: HomeAssistant, params: dict) -> dict:
    """Retrieve entity state history."""
    from datetime import datetime, timedelta, timezone
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_significant_states

    # entity_id too: ha_get_logbook takes the singular, and agents carry it over.
    raw_ids = params.get("entity_ids") or params.get("entity_id") or []
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    if not raw_ids:
        return {"error": "entity_ids (or entity_id) is required"}

    now = datetime.now(timezone.utc)
    try:
        start_dt = datetime.fromisoformat(params["start"]).astimezone(timezone.utc) if params.get("start") else now - timedelta(hours=24)
        end_dt = datetime.fromisoformat(params["end"]).astimezone(timezone.utc) if params.get("end") else now
    except (ValueError, TypeError) as e:
        return {"error": f"Invalid datetime format: {e}. Use ISO 8601, e.g. '2025-01-15T00:00:00'"}

    limit = int(params.get("limit", 50))

    try:
        recorder = get_instance(hass)
        history = await recorder.async_add_executor_job(
            get_significant_states,
            hass, start_dt, end_dt, raw_ids, None, True, True, False
        )

        result: dict[str, list] = {}
        for eid, states in history.items():
            entries = []
            for s in states[-limit:]:
                entries.append({
                    "state": s.state,
                    "timestamp": s.last_changed.isoformat() if s.last_changed else None,
                    "attributes": {k: v for k, v in s.attributes.items() if k in ("unit_of_measurement", "friendly_name")},
                })
            result[eid] = entries

        total = sum(len(v) for v in result.values())
        return {
            "success": True,
            "entity_count": len(result),
            "total_states": total,
            "period": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
            "history": result,
        }

    except Exception as exc:
        return {"error": f"History query failed: {exc}"}


async def _tool_ha_get_statistics(hass: HomeAssistant, params: dict) -> dict:
    """Retrieve long-term statistics."""
    from datetime import datetime, timedelta, timezone

    raw_ids = params.get("statistic_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]

    period = params.get("period", "hour")
    now = datetime.now(timezone.utc)
    try:
        start_dt = datetime.fromisoformat(params["start"]).astimezone(timezone.utc) if params.get("start") else now - timedelta(days=7)
        end_dt = datetime.fromisoformat(params["end"]).astimezone(timezone.utc) if params.get("end") else now
    except (ValueError, TypeError) as e:
        return {"error": f"Invalid datetime format: {e}"}

    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import statistics_during_period

        recorder = get_instance(hass)
        stats = await recorder.async_add_executor_job(
            statistics_during_period,
            hass, start_dt, end_dt, set(raw_ids), period, None, {"mean", "min", "max", "sum", "state"}
        )

        result: dict[str, list] = {}
        for sid, rows in stats.items():
            result[sid] = [
                {
                    "start": r["start"].isoformat() if hasattr(r.get("start"), "isoformat") else str(r.get("start")),
                    "mean": r.get("mean"),
                    "min": r.get("min"),
                    "max": r.get("max"),
                    "sum": r.get("sum"),
                    "state": r.get("state"),
                }
                for r in rows
            ]

        return {
            "success": True,
            "period": period,
            "range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
            "statistics": result,
        }

    except Exception as exc:
        return {"error": f"Statistics query failed: {exc}"}


async def _tool_ha_get_logbook(hass: HomeAssistant, params: dict) -> dict:
    """Retrieve logbook entries."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    try:
        start_dt = datetime.fromisoformat(params["start"]).astimezone(timezone.utc) if params.get("start") else now - timedelta(hours=24)
        end_dt = datetime.fromisoformat(params["end"]).astimezone(timezone.utc) if params.get("end") else now
    except (ValueError, TypeError) as e:
        return {"error": f"Invalid datetime format: {e}"}

    entity_id = params.get("entity_id")
    limit = int(params.get("limit", 50))

    if "logbook" not in hass.config.components:
        return {
            "success": False,
            "error": "The logbook integration is not loaded.",
            "hint": "Use ha_get_history() as an alternative to get state changes.",
        }

    try:
        # The query Home Assistant's own /api/logbook runs: the logbook has no
        # public function for it.
        from homeassistant.components.logbook.helpers import async_determine_event_types
        from homeassistant.components.logbook.processor import EventProcessor
        from homeassistant.components.recorder import get_instance

        entity_ids = [entity_id] if entity_id else None
        processor = EventProcessor(
            hass,
            async_determine_event_types(hass, entity_ids, None),
            entity_ids,
            None,
            None,
            timestamp=False,
            include_entity_name=True,
        )
        entries = await get_instance(hass).async_add_executor_job(
            processor.get_events, start_dt, end_dt
        )
    except Exception as exc:
        return {"success": False, "error": f"Logbook query failed: {exc}"}

    # Oldest first, like the history: keep the most recent ones.
    return {
        "success": True,
        "period": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        "entity_filter": entity_id,
        "total_entries": len(entries),
        "truncated": len(entries) > limit,
        "entries": entries[-limit:],
    }
