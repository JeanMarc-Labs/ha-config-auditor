"""The HTTP surface: JSON-RPC dispatch, the two views, and their registration."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

try:
    # HA turned this into an AppKey at some point; importing it keeps the
    # lookup working either way (a bare "hass_user" string would miss).
    from homeassistant.components.http.const import KEY_HASS_USER
except ImportError:      # pragma: no cover — older layouts
    KEY_HASS_USER = "hass_user"

from ..const import DOMAIN
from .catalog import MCP_TOOLS, TOOL_HANDLERS
from .common import (
    _get_coordinator_data,
    _json_default,
    _LOGGER,
    _MCP_CALLER_USER_ID,
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
)


# ─── JSON-RPC handler ─────────────────────────────────────────────────────

async def _handle_jsonrpc(
    hass: HomeAssistant, body: dict, user_id: str | None = None
) -> dict:
    """Traite un message JSON-RPC 2.0 MCP et retourne la réponse.

    `user_id` est l'ID de l'utilisateur HA authentifié à l'origine de la requête.
    Il est publié dans `_MCP_CALLER_USER_ID` pour que tout appel de service émis
    par un outil soit attribué à cette personne dans le journal Home Assistant.
    """
    _MCP_CALLER_USER_ID.set(user_id)
    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    def _ok(result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _err(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": code, "message": message}}

    try:
        if method == "initialize":
            return _ok({
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": MCP_SERVER_VERSION,
                },
                "instructions": (
                    "H.A.C.A MCP Server — Full Home Assistant control + audit.\n"
                    "\n"
                    "=== CORE WORKFLOWS ===\n"
                    "START        : haca_get_score() → health overview.\n"
                    "AUDIT        : haca_get_issues() → haca_explain_issue() → haca_apply_fix()\n"
                    "FIX SINGLE   : haca_fix_batch(issue_id='HACA-XXX-YYY-hash') → dry_run preview → set dry_run=false to apply.\n"
                    "FIX BATCH    : haca_fix_batch(category?, type?, severity?) → preview all matching → dry_run=false to apply.\n"
                    "CATALOG      : haca_list_issue_catalog() → discover all categories, types, severities, fixable status.\n"
                    "CONTROL      : ha_get_entities() to discover, ha_call_service() to act.\n"
                    "AUTOMATE     : ha_create_automation() or ha_update_automation()\n"
                    "DELETE AUTO  : haca_get_automation() → confirm with the user → ha_remove_automation()\n"
                    "DEBUG        : ha_get_automation_traces() + ha_get_logbook() to diagnose failures.\n"
                    "DASHBOARD    : ha_get_lovelace() → ha_add_lovelace_card()\n"
                    "SCRIPTS      : ha_create_script() to build reusable sequences.\n"
                    "TEMPLATE     : ha_eval_template() to test Jinja2 before writing.\n"
                    "RENAME       : ha_rename_entity() to fix names, icons, or area assignments.\n"
                    "VALIDATE     : ha_check_config() after any YAML edit, before reloading.\n"
                    "HISTORY      : ha_get_history() for state changes, ha_get_statistics() for trends.\n"
                    "SEARCH       : ha_deep_search(query) to find all automations using an entity.\n"
                    "HELPERS      : ha_config_list_helpers() → ha_config_set_helper() / ha_config_remove_helper()\n"
                    "BLUEPRINT    : haca_get_automation() → ha_create_blueprint(automation_entity_id, name, description, inputs?)\n"
                    "BP EDIT      : ha_list_blueprints() → ha_get_blueprint(path) → ha_update_blueprint(path, ...) | ha_remove_blueprint(path)\n"
                    "BP IMPORT    : ha_import_blueprint(url) → reloaded automatically\n"
                    "SCRIPTS      : ha_get_script(entity_id) → ha_update_script() | ha_remove_script()\n"
                    "SCENES       : ha_get_scene(entity_id) → ha_update_scene() | ha_remove_scene() | ha_create_scene()\n"
                    "DASHBOARDS   : ha_list_dashboards() → ha_get_lovelace() → ha_update_lovelace_card() | ha_remove_lovelace_card()\n"
                    "HELPERS      : ha_get_helper(entity_id) → ha_update_helper() | ha_config_remove_helper()\n"
                    "ENTITIES     : ha_get_entity_detail(entity_id) → ha_enable_entity() | ha_remove_entity(force?)\n"
                    "SECURITY     : ha_get_config_file('secrets.yaml') → ha_update_config_file(patch_line) → ha_check_config()\n"
                    "LABELS       : ha_list_labels() → ha_create_label() → ha_manage_entity_labels()\n"
                    "\n"
                    "=== SAFETY RULES ===\n"
                    "1. Every tool that changes a file first copies it into /config/.haca_backups/ "
                    "and returns that copy's path as 'backup': tell the user. Call "
                    "ha_backup_create() (a full HA backup) only when the user asks for one, or "
                    "before a bulk refactor or a deletion no file copy covers (helper, entity).\n"
                    "2. ALWAYS call ha_check_config() after writing to YAML files and before reloading.\n"
                    "3. ALWAYS call ha_eval_template() to validate Jinja2 before inserting in automations.\n"
                    "4. ALWAYS call ha_get_entities() to find the real entity_id — never guess.\n"
                    "5. ALWAYS call ha_deep_search(entity_id) before renaming/deleting an entity "
                    "to find all automations that reference it.\n"
                    "\n"
                    "=== ADDITIONAL TOOLS ===\n"
                    "SYSTEM     : ha_get_system_health() for HA version & integration errors.\n"
                    "UPDATES    : ha_get_updates() to list pending HA/add-on updates.\n"
                    "RELOAD     : ha_reload_core(domain) to reload any domain after YAML edits.\n"
                    "SERVICES   : ha_list_services(domain) to discover available services before calling them.\n"
                    "AREAS      : ha_config_set_area() to create/update rooms before assigning entities.\n"
                    "LABELS     : ha_manage_entity_labels() to tag entities from HACA audit results.\n"
                    "BLUEPRINT  : ha_create_blueprint(automation_entity_id) to convert any automation "
                    "into a reusable Blueprint file saved in /config/blueprints/automation/haca/. "
                    "ALWAYS use this tool — never just describe or suggest a blueprint in text."
                ),
            })

        elif method == "notifications/initialized":
            # Notification côté client — aucune réponse requise
            return {}

        elif method == "tools/list":
            # "access" is HACA's internal read/write classification (see
            # MCP_WRITE_TOOLS); it is not part of the MCP tool schema, so it
            # stays out of the wire format.
            return _ok({
                "tools": [
                    {k: v for k, v in tool.items() if k != "access"}
                    for tool in MCP_TOOLS
                ]
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            handler = TOOL_HANDLERS.get(tool_name)
            if not handler:
                return _err(-32601, f"Unknown tool '{tool_name}'")

            result = await handler(hass, tool_args)
            return _ok({
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            result, ensure_ascii=False, indent=2, default=_json_default
                        ),
                    }
                ],
                "isError": "error" in result,
            })

        elif method == "ping":
            return _ok({})

        else:
            return _err(-32601, f"Method '{method}' not supported")

    except Exception as exc:
        # Le nom de l'outil est indispensable pour diagnostiquer : sans lui,
        # "Handler error for method 'tools/call'" ne dit pas quel outil a cassé.
        context = method
        if method == "tools/call":
            name = params.get("name", "?") if isinstance(params, dict) else "?"
            context = f"tools/call({name})"
        _LOGGER.error(
            "[HACA MCP] Handler error for method '%s': %s", context, exc, exc_info=True
        )
        return _err(-32603, f"Internal error: {exc}")


# ─── aiohttp Views ────────────────────────────────────────────────────────

def _require_admin(request: web.Request) -> str:
    """Retourne l'ID de l'utilisateur admin appelant, ou lève HTTPForbidden.

    `requires_auth = True` ne garantit qu'une session ouverte. Les outils MCP
    écrivent des fichiers de configuration et appellent n'importe quel service
    (`lock.unlock`, `alarm_control_panel.disarm`…) : Home Assistant réserve ces
    opérations aux administrateurs, HACA doit faire de même.
    """
    user = request.get(KEY_HASS_USER)
    if user is None or not user.is_admin:
        _LOGGER.warning(
            "[HACA MCP] Accès refusé — IP=%s user=%s (admin requis)",
            request.remote, getattr(user, "id", None) or "anonyme",
        )
        raise web.HTTPForbidden(reason="HACA MCP requires an administrator account")
    return user.id


class HacaMcpView(HomeAssistantView):
    """Vue HTTP principale MCP — POST (JSON-RPC) + GET (SSE keepalive).

    Uses requires_auth=True so HA handles Bearer token validation natively.
    This supports Long-Lived Access Tokens, OAuth tokens, and trusted networks.
    Admin status is checked separately — HA's requires_auth only proves the
    caller is logged in, not that they may reconfigure the instance.
    """

    url = "/api/haca_mcp"
    extra_urls = ["/api/haca_mcp/sse"]
    name = "api:haca_mcp"
    requires_auth = True  # HA handles Bearer token validation
    cors_allowed = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Reçoit et traite les messages JSON-RPC 2.0."""
        user_id = _require_admin(request)
        _LOGGER.debug("[HACA MCP] POST — IP=%s user=%s", request.remote, user_id)

        try:
            body = await request.json()
        except Exception as parse_exc:
            _LOGGER.warning("[HACA MCP] JSON parse error: %s", parse_exc)
            return web.Response(
                status=400,
                text=json.dumps({
                    "jsonrpc": "2.0", "id": None,
                    "error": {"code": -32700, "message": "Parse error — invalid JSON"}
                }),
                content_type="application/json",
            )

        # Batch requests (tableau de requêtes)
        if isinstance(body, list):
            _LOGGER.debug("[HACA MCP] Batch request — %d messages", len(body))
            responses = []
            for msg in body:
                resp = await _handle_jsonrpc(self._hass, msg, user_id)
                if resp:
                    responses.append(resp)
            return web.Response(
                text=json.dumps(responses, ensure_ascii=False, default=_json_default),
                content_type="application/json",
            )

        # Single request
        method = body.get("method", "?")
        _LOGGER.debug("[HACA MCP] method=%s user=%s", method, user_id)
        result = await _handle_jsonrpc(self._hass, body, user_id)
        if not result:
            return web.Response(status=204)

        return web.Response(
            text=json.dumps(result, ensure_ascii=False, default=_json_default),
            content_type="application/json",
        )

    async def get(self, request: web.Request) -> web.Response:
        """SSE endpoint — keepalive pour clients MCP compatibles SSE."""
        _require_admin(request)
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        await response.prepare(request)

        # Envoyer l'événement endpoint pour les clients MCP
        await response.write(
            f"event: endpoint\ndata: {json.dumps({'url': str(request.url)})}\n\n".encode()
        )

        # Keepalive toutes les 15 secondes
        try:
            while True:
                await asyncio.sleep(15)
                if request.transport and not request.transport.is_closing():
                    await response.write(b": keepalive\n\n")
                else:
                    break
        except (asyncio.CancelledError, ConnectionResetError):
            pass

        return response


class HacaMcpInfoView(HomeAssistantView):
    """Vue d'information — réservée aux administrateurs.

    Cet endpoint annonce le score de santé, le nombre d'issues et la liste
    nominative des 60 outils. Publié sans authentification, il confirmait à
    n'importe qui que HACA tourne sur l'instance et fuitait l'état de l'audit.
    Le serveur MCP lui-même étant admin-only, sa fiche de découverte l'est aussi.
    """

    url = "/api/haca_mcp/info"
    name = "api:haca_mcp_info"
    requires_auth = True
    cors_allowed = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        _require_admin(request)
        cdata = _get_coordinator_data(self._hass)
        info = {
            "name": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
            "protocol_version": MCP_PROTOCOL_VERSION,
            "description": "H.A.C.A — Home Assistant Config Auditor MCP Server",
            "endpoint": "/api/haca_mcp",
            "auth": "Bearer <HA Long-Lived Access Token>",
            "tools_count": len(MCP_TOOLS),
            "tools": [t["name"] for t in MCP_TOOLS],
            "health_score": cdata.get("health_score"),
            "total_issues": cdata.get("total_issues"),
            "claude_code_config": {
                "example": {
                    "mcpServers": {
                        "haca": {
                            "command": "npx",
                            "args": ["-y", "@modelcontextprotocol/server-proxy"],
                            "env": {
                                "MCP_SERVER_URL": "<HA_URL>/api/haca_mcp",
                                "MCP_AUTH_HEADER": "Authorization: Bearer <TOKEN>",
                            },
                        }
                    }
                }
            },
        }
        return web.Response(
            text=json.dumps(info, ensure_ascii=False, indent=2),
            content_type="application/json",
        )


# ─── Setup ────────────────────────────────────────────────────────────────

_MCP_VIEWS_KEY = f"{DOMAIN}_mcp_views_registered"


async def async_setup_mcp_server(hass: HomeAssistant) -> None:
    """Enregistre les vues HTTP MCP (une seule fois par process HA)."""
    if hass.data.get(_MCP_VIEWS_KEY):
        _LOGGER.debug("[HACA MCP] Views already registered — skipping")
        return

    try:
        hass.http.register_view(HacaMcpView(hass))
        hass.http.register_view(HacaMcpInfoView(hass))
        hass.data[_MCP_VIEWS_KEY] = True
        _LOGGER.info(
            "[HACA MCP] Server registered at /api/haca_mcp "
            "(auth: Bearer <HA Long-Lived Access Token>)"
        )
    except Exception as exc:
        _LOGGER.error("[HACA MCP] Registration error: %s", exc)
