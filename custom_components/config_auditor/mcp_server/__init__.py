"""H.A.C.A — MCP (Model Context Protocol) server, v1.6.1.

Exposes HACA as an MCP server any compatible AI agent (Claude Code, Cursor,
Copilot…) can reach over HTTP + JSON-RPC 2.0.

Authentication: Bearer token = a Home Assistant long-lived access token, and
an administrator on both routes (see :func:`.views._require_admin`).

Registered routes:
  POST /api/haca_mcp          — the JSON-RPC 2.0 endpoint
  GET  /api/haca_mcp          — SSE endpoint (keepalive + server events)
  GET  /api/haca_mcp/info     — informational endpoint (admin required)

MCP spec: https://modelcontextprotocol.io/specification (2024-11-05)

Package layout
--------------
This was one 6 000-line file until the 1.8.0 split. The modules read bottom-up;
no dependency points back the other way.

  ``common``             protocol constants, caller identity, JSON encoding,
                         the YAML read / write helpers (every write snapshots
                         the file it replaces into ``.haca_backups`` first)
  ``schemas``            the tool declarations (pure data)
  ``tools_system``       services, backups, reloads, raw config files
  ``tools_audit``        the ``haca_*`` tools, read off the coordinator
  ``tools_history``      history, statistics, logbook (recorder-backed)
  ``tools_registry``     entities, areas, labels, helpers
  ``tools_automation``   automation CRUD
  ``tools_script_scene`` script and scene CRUD
  ``tools_blueprint``    blueprint CRUD, import from a public URL
  ``tools_lovelace``     dashboards and their cards
  ``catalog``            assembles ``MCP_TOOLS`` and ``TOOL_HANDLERS``
  ``views``              JSON-RPC dispatch, the two HTTP views, registration

Only the names re-exported below are public: ``llm_api`` reads ``MCP_TOOLS``,
``TOOL_HANDLERS``, ``tool_access`` and ``json_safe``, and the integration's
``__init__`` calls ``async_setup_mcp_server``. A ``_tool_*`` handler is
imported from the module that defines it.
"""
from __future__ import annotations

from .catalog import MCP_TOOLS, TOOL_HANDLERS
from .common import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    json_safe,
)
from .schemas import MCP_WRITE_TOOLS, tool_access
from .views import HacaMcpInfoView, HacaMcpView, async_setup_mcp_server

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCP_SERVER_NAME",
    "MCP_SERVER_VERSION",
    "MCP_TOOLS",
    "MCP_WRITE_TOOLS",
    "TOOL_HANDLERS",
    "HacaMcpInfoView",
    "HacaMcpView",
    "async_setup_mcp_server",
    "json_safe",
    "tool_access",
]
