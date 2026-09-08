"""Dashboard tools -- reading a Lovelace config and editing its cards."""
from __future__ import annotations

from homeassistant.core import HomeAssistant


async def _tool_ha_get_lovelace(hass: HomeAssistant, params: dict) -> dict:
    """Lit la configuration Lovelace (dashboard)."""
    dashboard_id = params.get("dashboard_id") or "lovelace"

    try:
        dashboard, err = await _get_lovelace_dashboard(hass, dashboard_id)
        if err:
            return err

        config = await dashboard.async_load(force=False)
        if not config or not isinstance(config, dict):
            return {"error": f"Dashboard '{dashboard_id}' returned empty config."}

        if (strategy_err := _lovelace_strategy_error(dashboard_id, config)) is not None:
            return strategy_err

        views = config.get("views", [])
        return {
            "dashboard_id": dashboard_id,
            "mode": "storage",
            "title": config.get("title", "Home"),
            "views_count": len(views),
            "views": [
                {
                    "index": i,
                    "title": v.get("title", v.get("path", f"View {i}")),
                    "path": v.get("path", str(i)),
                    "cards_count": len(v.get("cards", [])),
                    "card_types": list({c.get("type", "unknown") for c in v.get("cards", []) if isinstance(c, dict)}),
                }
                for i, v in enumerate(views)
            ],
            "raw_config_available": True,
        }
    except Exception as exc:
        return {"error": f"Failed to read Lovelace config for '{dashboard_id}': {exc}"}


async def _tool_ha_add_lovelace_card(hass: HomeAssistant, params: dict) -> dict:
    """Ajoute une carte à un dashboard Lovelace (mode storage)."""
    dashboard_id = params.get("dashboard_id") or "lovelace"
    view_index = params.get("view_index")
    card = params.get("card")

    if not card or not isinstance(card, dict):
        return {"error": "card is required and must be an object with a 'type' field"}

    # ── Normalize card type ──────────────────────────────────────────────
    card_type = card.get("type", "")
    if not card_type:
        return {
            "error": "card must have a 'type' field. Common types: weather-forecast, "
                     "entities, button, light, thermostat, glance, gauge, history-graph, "
                     "sensor, tile, area, markdown, map, todo-list, mushroom-entity-card."
        }

    # ── Auto-detect entity for common card types ─────────────────────────
    if "entity" not in card:
        auto_domain = {
            "weather-forecast": "weather",
            "media-control": "media_player",
            "thermostat": "climate",
            "plant-status": "plant",
            "alarm-panel": "alarm_control_panel",
            "humidifier": "humidifier",
        }.get(card_type)
        if auto_domain:
            candidates = [s.entity_id for s in hass.states.async_all()
                          if s.entity_id.startswith(f"{auto_domain}.")]
            if len(candidates) == 1:
                card["entity"] = candidates[0]
            elif candidates:
                return {
                    "error": f"Multiple {auto_domain} entities found. Specify 'entity' in the card config.",
                    "candidates": candidates[:10],
                }
            else:
                return {"error": f"No {auto_domain} entity found in your HA instance."}

    try:
        dashboard, err = await _get_lovelace_dashboard(hass, dashboard_id)
        if err:
            return err

        if not hasattr(dashboard, "async_save"):
            return {"error": "Dashboard is read-only (YAML mode). Switch to storage mode in Settings → Dashboards."}

        config = await dashboard.async_load(force=True)
        if (strategy_err := _lovelace_strategy_error(dashboard_id, config)) is not None:
            return strategy_err

        views = config.get("views", [])

        if not views:
            return {"error": f"Dashboard '{dashboard_id}' has no views. Create a view first in the HA UI."}

        # Auto-select view 0 if only one view
        if view_index is None:
            view_index = 0
        view_index = int(view_index)

        if view_index >= len(views):
            return {"error": f"View index {view_index} out of range (dashboard has {len(views)} views)"}

        views[view_index].setdefault("cards", []).append(card)
        config["views"] = views
        await dashboard.async_save(config)

        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "view_index": view_index,
            "view_title": views[view_index].get("title", f"View {view_index}"),
            "card_type": card.get("type"),
            "entity": card.get("entity", ""),
            "message": f"Card '{card.get('type')}' added to view '{views[view_index].get('title', view_index)}'.",
        }
    except Exception as exc:
        return {"error": f"Failed to add Lovelace card to '{dashboard_id}': {exc}"}


# ── DASHBOARDS EDIT ───────────────────────────────────────────────────────────

async def _get_lovelace_dashboard(hass: HomeAssistant, dashboard_id: str = None):
    """Get a Lovelace dashboard object that supports async_load / async_save.
    
    Returns (dashboard_obj, error_dict). If dashboard_obj is None, error_dict
    explains why. Handles all HA versions.
    """
    dashboard_id = dashboard_id or "lovelace"
    lovelace = hass.data.get("lovelace")
    
    if lovelace is None:
        return None, {"error": "Lovelace component not loaded. Ensure frontend integration is active."}
    
    dashboard = None
    
    # Strategy 1: Object with .dashboards dict (HA 2024+)
    if hasattr(lovelace, "dashboards"):
        dbs = lovelace.dashboards
        if isinstance(dbs, dict) and dashboard_id in dbs:
            dashboard = dbs[dashboard_id]
        if not dashboard and dashboard_id in ("lovelace", "default", None):
            if hasattr(lovelace, "async_load"):
                dashboard = lovelace
    
    # Strategy 2: Dict-like
    if not dashboard and isinstance(lovelace, dict):
        sub = lovelace.get("dashboards", {})
        if isinstance(sub, dict) and dashboard_id in sub:
            dashboard = sub[dashboard_id]
        if not dashboard:
            dashboard = lovelace.get(dashboard_id)
        if not dashboard and dashboard_id in ("lovelace", "default"):
            dashboard = lovelace.get("lovelace")
        if not dashboard:
            cfg_obj = lovelace.get("config")
            if cfg_obj and hasattr(cfg_obj, "async_load"):
                dashboard = cfg_obj
    
    # Strategy 3: The object itself is the default dashboard
    if not dashboard and hasattr(lovelace, "async_load"):
        dashboard = lovelace
    
    if dashboard and hasattr(dashboard, "async_load"):
        return dashboard, None
    
    available = []
    if hasattr(lovelace, "dashboards") and isinstance(lovelace.dashboards, dict):
        available = list(lovelace.dashboards.keys())
    elif isinstance(lovelace, dict):
        sub = lovelace.get("dashboards", lovelace)
        if isinstance(sub, dict):
            available = [k for k in sub.keys() if k not in ("mode", "resources", "dashboards", "config")]
    
    return None, {
        "error": f"Dashboard '{dashboard_id}' not accessible in storage mode.",
        "available_dashboards": available,
        "suggestion": "Switch to storage mode: Settings → Dashboards → edit your dashboard. "
                      "Available: " + (", ".join(available) if available else "none detected"),
    }


def _lovelace_strategy_error(dashboard_id: str, config) -> dict | None:
    """Return an explicit error when a dashboard is strategy-generated.

    Strategy dashboards ('original-states', 'areas', custom strategies...)
    store no 'views' key: their content is generated at render time. Without
    this guard the tools silently report views_count: 0 or "no views", which
    is misleading — there is simply nothing stored to read or edit.
    """
    if not isinstance(config, dict) or "views" in config or "strategy" not in config:
        return None

    strategy = config.get("strategy")
    strategy_type = strategy.get("type", "unknown") if isinstance(strategy, dict) else "unknown"
    return {
        "error": (
            f"Dashboard '{dashboard_id}' uses the Lovelace strategy '{strategy_type}': "
            "its views are generated at render time and are not stored, so they cannot "
            "be introspected or edited."
        ),
        "strategy": strategy_type,
        "hint": (
            "Take control of the dashboard first (dashboard → pencil icon → 3-dot menu "
            "→ Take control) to convert it into editable stored views."
        ),
    }


async def _tool_ha_list_dashboards(hass: HomeAssistant, params: dict) -> dict:
    """List all Lovelace dashboards (default + custom)."""
    results: list[dict] = []
    results.append({
        "url_path": "lovelace",
        "title": "Default",
        "icon": "mdi:home",
        "is_default": True,
    })
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace is None:
            return {"dashboards": results, "total": 1, "note": "Lovelace data not loaded"}
        
        dashboards = {}
        if hasattr(lovelace, "dashboards") and isinstance(lovelace.dashboards, dict):
            dashboards = lovelace.dashboards
        elif isinstance(lovelace, dict):
            dashboards = lovelace.get("dashboards", {})
            if not isinstance(dashboards, dict):
                dashboards = {}
        
        # Check default dashboard mode
        if hasattr(lovelace, "async_load"):
            results[0]["mode"] = "storage"
        
        for url_path, dash in dashboards.items():
            if url_path in ("lovelace",):
                continue
            info: dict = {"url_path": url_path}
            if hasattr(dash, "config") and isinstance(dash.config, dict):
                cfg = dash.config
                info["title"] = cfg.get("title", url_path)
                info["icon"] = cfg.get("icon", "")
                info["show_in_sidebar"] = cfg.get("show_in_sidebar", True)
                info["mode"] = cfg.get("mode", "storage")
            elif hasattr(dash, "async_load"):
                info["title"] = url_path
                info["mode"] = "storage"
            results.append(info)
    except Exception as exc:
        results.append({"note": f"Could not enumerate dashboards: {exc}"})

    return {"dashboards": results, "total": len(results)}


async def _tool_ha_update_lovelace_card(hass: HomeAssistant, params: dict) -> dict:
    """Update an existing Lovelace card by view index + card index."""
    view_index = params.get("view_index", 0)
    card_index = params.get("card_index")
    card_id    = params.get("card_id", "")
    new_config = params.get("card_config")
    dashboard_id = params.get("dashboard_url") or params.get("dashboard_id") or "lovelace"

    if new_config is None:
        return {"error": "card_config required (dict with the full new card definition)"}
    if card_index is None and not card_id:
        return {"error": "Either card_index (int) or card_id (string) required"}

    try:
        dashboard, err = await _get_lovelace_dashboard(hass, dashboard_id)
        if err:
            return err

        ll = await dashboard.async_load(False)
        if (strategy_err := _lovelace_strategy_error(dashboard_id, ll)) is not None:
            return strategy_err

        views = ll.get("views", [])
        if view_index >= len(views):
            return {"error": f"view_index {view_index} out of range (dashboard has {len(views)} views)"}

        cards = views[view_index].get("cards", [])
        if card_id:
            target_idx = next(
                (i for i, c in enumerate(cards)
                 if isinstance(c, dict) and c.get("id") == card_id),
                None
            )
            if target_idx is None:
                return {"error": f"Card with id '{card_id}' not found in view {view_index}"}
            card_index = target_idx

        if card_index >= len(cards):
            return {"error": f"card_index {card_index} out of range (view has {len(cards)} cards)"}

        old_card = cards[card_index]
        cards[card_index] = new_config
        views[view_index]["cards"] = cards
        ll["views"] = views

        await dashboard.async_save(ll)
        return {
            "success": True,
            "view_index": view_index,
            "card_index": card_index,
            "old_type": old_card.get("type", "unknown"),
            "new_type": new_config.get("type", "unknown"),
            "message": "Card updated successfully.",
        }
    except Exception as exc:
        return {"error": f"Failed to update Lovelace card on '{dashboard_id}': {exc}"}


async def _tool_ha_remove_lovelace_card(hass: HomeAssistant, params: dict) -> dict:
    """Remove a card from a Lovelace view."""
    view_index = params.get("view_index", 0)
    card_index = params.get("card_index")
    card_id    = params.get("card_id", "")
    dashboard_id = params.get("dashboard_url") or params.get("dashboard_id") or "lovelace"

    if card_index is None and not card_id:
        return {"error": "Either card_index (int) or card_id (string) required"}

    try:
        dashboard, err = await _get_lovelace_dashboard(hass, dashboard_id)
        if err:
            return err

        ll = await dashboard.async_load(False)
        if (strategy_err := _lovelace_strategy_error(dashboard_id, ll)) is not None:
            return strategy_err

        views = ll.get("views", [])
        if view_index >= len(views):
            return {"error": f"view_index {view_index} out of range"}

        cards = views[view_index].get("cards", [])
        if card_id:
            target_idx = next(
                (i for i, c in enumerate(cards) if isinstance(c, dict) and c.get("id") == card_id),
                None
            )
            if target_idx is None:
                return {"error": f"Card with id '{card_id}' not found"}
            card_index = target_idx

        if card_index >= len(cards):
            return {"error": f"card_index {card_index} out of range"}

        removed = cards.pop(card_index)
        views[view_index]["cards"] = cards
        ll["views"] = views
        await dashboard.async_save(ll)

        return {
            "success": True,
            "removed_card_type": removed.get("type", "unknown"),
            "remaining_cards": len(cards),
            "message": f"Card (type={removed.get('type')}) removed from view {view_index}.",
        }
    except Exception as exc:
        return {"error": f"Failed to remove Lovelace card from '{dashboard_id}': {exc}"}
