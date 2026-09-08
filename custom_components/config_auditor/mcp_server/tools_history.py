"""Recorder-backed tools: state history, long-term statistics, logbook."""
from __future__ import annotations

from homeassistant.core import HomeAssistant


# ── Handlers — medium priority tools ────────────────────────────────────────

async def _tool_ha_get_history(hass: HomeAssistant, params: dict) -> dict:
    """Retrieve entity state history."""
    from datetime import datetime, timedelta, timezone
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_significant_states

    raw_ids = params.get("entity_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]

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

    try:
        from homeassistant.components import logbook

        entity_ids = [entity_id] if entity_id else None

        entries = await logbook.async_get_logbook_entries(
            hass,
            start_time=start_dt,
            end_time=end_dt,
            entity_ids=entity_ids,
        )

        # entries is an async generator or list depending on HA version
        results: list[dict] = []
        if hasattr(entries, "__aiter__"):
            async for e in entries:
                results.append(e)
                if len(results) >= limit:
                    break
        else:
            results = list(entries)[:limit]

        return {
            "success": True,
            "period": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
            "entity_filter": entity_id,
            "total_entries": len(results),
            "entries": results,
        }

    except Exception as exc:
        # Fallback: use recorder directly
        try:
            return {
                "success": False,
                "error": f"Logbook API unavailable: {exc}",
                "hint": "Ensure the logbook integration is enabled. "
                        "Use ha_get_history() as an alternative to get state changes.",
            }
        except Exception:
            return {"error": f"Logbook query failed: {exc}"}
