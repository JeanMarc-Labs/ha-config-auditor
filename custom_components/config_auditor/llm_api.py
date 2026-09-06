"""HACA LLM API — expose les outils HACA à n'importe quel agent HA (Mistral, OpenAI…).

Configuration utilisateur (une seule fois) :
  HA Settings → Voice Assistants → [votre agent] → LLM API → HACA

Ensuite, chaque appel à async_converse sur cet agent injecte automatiquement
les outils HACA. L'agent fait ses tool_calls nativement, HA route vers
HacaTool.async_call → TOOL_HANDLERS → exécution réelle.

Lecture seule par défaut
------------------------
Attacher l'API HACA à un agent, c'est la donner à tout ce qui parle à cet
agent : un satellite Assist, un haut-parleur, une intégration Alexa ou Google.
Les outils qui écrivent (fichiers de configuration, appels de service) ne sont
donc exposés que si l'option ``llm_write_enabled`` est activée **et** que la
personne à l'origine de la conversation est administratrice. Les outils de
lecture — diagnostiquer, expliquer, suggérer — restent toujours disponibles.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

HACA_LLM_API_ID   = "haca"
HACA_LLM_API_NAME = "HACA"

# Option d'entrée qui débloque les outils d'écriture pour les agents LLM.
CONF_LLM_WRITE_ENABLED = "llm_write_enabled"
DEFAULT_LLM_WRITE_ENABLED = False

# Délimiteurs du bloc de données dans le prompt système (voir _sanitize_for_prompt).
_DATA_BLOCK_OPEN  = "<<<HACA_DATA"
_DATA_BLOCK_CLOSE = "HACA_DATA>>>"

# Tout ce qui n'est pas imprimable sur une ligne : sauts de ligne, tabulations,
# caractères de contrôle. Un alias d'automation peut en contenir.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_for_prompt(value: Any, limit: int = 80) -> str:
    """Aplatit une valeur pour l'insérer dans un bloc de données du prompt.

    Un alias d'automation ou un ``friendly_name`` n'est pas forcément écrit par
    l'administrateur : MQTT discovery, Bluetooth et mDNS créent des entités dont
    le nom vient de l'appareil. Ce texte partait tel quel dans le prompt système
    d'un agent capable d'appeler des services — soit une injection de prompt
    indirecte aux conséquences physiques.

    On retire donc les caractères de contrôle (qui permettent de simuler une
    nouvelle section du prompt), on neutralise les délimiteurs du bloc, et on
    tronque court.
    """
    text = _CONTROL_CHARS.sub(" ", str(value or ""))
    text = text.replace(_DATA_BLOCK_OPEN, "").replace(_DATA_BLOCK_CLOSE, "")
    text = " ".join(text.split())
    return text[:limit]


async def _llm_write_allowed(
    hass: HomeAssistant, llm_context: llm.LLMContext
) -> bool:
    """Les outils d'écriture sont-ils autorisés pour cette conversation ?

    Deux conditions cumulatives :
      1. l'option ``llm_write_enabled`` est activée sur l'entrée HACA ;
      2. la conversation est rattachée à un utilisateur administrateur.

    Une conversation sans ``user_id`` — satellite vocal, appel système, la
    plupart des passerelles Alexa/Google — n'est jamais administrateur.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return False
    if not entries[0].options.get(CONF_LLM_WRITE_ENABLED, DEFAULT_LLM_WRITE_ENABLED):
        return False

    context = getattr(llm_context, "context", None)
    user_id = getattr(context, "user_id", None)
    if not user_id:
        return False
    try:
        user = await hass.auth.async_get_user(user_id)
    except Exception:       # pragma: no cover — auth store unavailable
        return False
    return bool(user and user.is_admin)


# ─── JSON Schema → voluptuous ──────────────────────────────────────────────────

def _json_type_to_validator(prop: dict) -> Any:
    """Convert one JSON Schema property to a voluptuous validator."""
    enum = prop.get("enum")
    if enum:
        return vol.In(enum)
    t = prop.get("type", "string")
    if t == "string":
        return str
    if t == "integer":
        return vol.Coerce(int)
    if t == "number":
        return vol.Coerce(float)
    if t == "boolean":
        return bool
    if t == "array":
        return list
    # object or unknown → passthrough
    return object


def _input_schema_to_vol(input_schema: dict) -> vol.Schema:
    """Convert a MCP inputSchema (JSON Schema object) to a voluptuous Schema."""
    if not input_schema or input_schema.get("type") != "object":
        return vol.Schema({})

    properties     = input_schema.get("properties", {})
    required_names = set(input_schema.get("required", []))
    validators: dict = {}

    for name, prop in properties.items():
        validator = _json_type_to_validator(prop)
        if name in required_names:
            validators[vol.Required(name)] = validator
        else:
            default = prop.get("default", vol.UNDEFINED)
            if default is not vol.UNDEFINED:
                validators[vol.Optional(name, default=default)] = validator
            else:
                validators[vol.Optional(name)] = validator

    return vol.Schema(validators)


# ─── HacaTool ─────────────────────────────────────────────────────────────────

class HacaTool(llm.Tool):
    """Un outil HACA exposé à l'agent IA via le LLM API de HA."""

    def __init__(self, tool_def: dict) -> None:
        self.name        = tool_def["name"]
        self.description = tool_def.get("description", "")
        self.parameters  = _input_schema_to_vol(tool_def.get("inputSchema", {}))
        # MCP_TOOLS entries carry "access"; fall back to the shared
        # classification so a hand-built tool_def is judged the same way.
        from .mcp_server import tool_access      # noqa: PLC0415
        self.access      = tool_def.get("access") or tool_access(self.name)

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Exécute l'outil HACA via TOOL_HANDLERS."""
        from .mcp_server import TOOL_HANDLERS, json_safe

        # Deuxième barrière : async_get_api_instance ne publie déjà pas les
        # outils d'écriture dans ce cas, mais un agent peut rejouer un nom
        # d'outil mémorisé d'un tour précédent, ou d'une autre conversation.
        if self.access == "write" and not await _llm_write_allowed(hass, llm_context):
            _LOGGER.warning(
                "[HACA LLM] Refus de l'outil d'écriture %s — "
                "llm_write_enabled désactivé ou appelant non administrateur",
                self.name,
            )
            return {
                "error": (
                    f"Tool '{self.name}' writes to this Home Assistant instance and is "
                    "not available: HACA exposes write tools only when the "
                    "'llm_write_enabled' option is on and the person speaking is an "
                    "administrator. Read-only tools remain available."
                )
            }

        handler = TOOL_HANDLERS.get(self.name)
        if not handler:
            raise HomeAssistantError(f"HACA tool '{self.name}' not found")

        try:
            result = await handler(hass, tool_input.tool_args)
            _LOGGER.debug("[HACA LLM] Tool %s → %s", self.name, str(result)[:200])
            # Les résultats portent des données HA brutes (attributs d'état,
            # logbook…) où un datetime peut traîner : l'agent qui sérialise
            # derrière nous n'a pas de `default=`, on normalise ici.
            return json_safe(result)  # type: ignore[return-value]
        except Exception as exc:
            _LOGGER.error("[HACA LLM] Tool %s failed: %s", self.name, exc)
            return {"error": str(exc)}


# ─── HacaLLMAPI ───────────────────────────────────────────────────────────────

class HacaLLMAPI(llm.API):
    """HACA LLM API — expose les outils d'audit et de contrôle HA à tout agent LLM."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass=hass, id=HACA_LLM_API_ID, name=HACA_LLM_API_NAME)

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Construit l'instance avec le contexte HA courant et les outils permis.

        Les outils d'écriture ne sont pas seulement refusés à l'appel : ils ne
        sont pas publiés du tout, pour que l'agent réponde « je n'ai pas cet
        outil » plutôt que d'échouer au milieu d'une opération.
        """
        from .mcp_server import MCP_TOOLS

        api_prompt = await self._build_api_prompt()
        allow_write = await _llm_write_allowed(self.hass, llm_context)
        tools = [
            HacaTool(t) for t in MCP_TOOLS
            if allow_write or t.get("access") == "read"
        ]

        _LOGGER.debug(
            "[HACA LLM] API instance: %d tools (write %s)",
            len(tools), "autorisée" if allow_write else "refusée",
        )
        return llm.APIInstance(
            api=self,
            api_prompt=api_prompt,
            llm_context=llm_context,
            tools=tools,
        )

    async def _build_api_prompt(self) -> str:
        """Contexte HACA injecté dans le system prompt de l'agent — multilingue."""
        hass = self.hass

        # ── Load prompt translations ─────────────────────────────────────
        # The LLM API surface is global to the HA instance (other AI agents
        # invoke it server-side), so we use the system-resolved language.
        from .translation_utils import TranslationHelper, resolve_notification_language
        th = TranslationHelper(hass)
        lang = resolve_notification_language(hass)
        await th.async_load_language_section(lang, "llm_prompt")
        p = th.t  # shortcut

        # ── Gather HA context ────────────────────────────────────────────
        try:
            entries    = hass.config_entries.async_entries(DOMAIN)
            cdata_raw  = hass.data.get(DOMAIN, {}).get(entries[0].entry_id, {}) if entries else {}
            coordinator = cdata_raw.get("coordinator")
            cdata       = coordinator.data if coordinator and coordinator.data else {}

            score        = cdata.get("health_score", "?")
            total_issues = cdata.get("total_issues", 0)
            all_issues   = (
                list(cdata.get("automation_issue_list", []))
                + list(cdata.get("entity_issue_list", []))
                + list(cdata.get("security_issue_list", []))
            )
            sev_order = {"high": 0, "medium": 1, "low": 2}
            top5 = sorted(
                all_issues,
                key=lambda i: sev_order.get(i.get("severity", "low"), 2)
            )[:5]
            top5_txt = "\n".join(
                f"  - [{_sanitize_for_prompt(i.get('severity', '?'), 10).upper()}] "
                f"{_sanitize_for_prompt(i.get('alias') or i.get('entity_id') or '?')}: "
                f"{_sanitize_for_prompt(i.get('message'))}"
                for i in top5
            ) or f"  {p('no_issues')}"
        except Exception:
            score        = "?"
            total_issues = 0
            top5_txt     = f"  {p('context_unavailable')}"

        auto_count   = len(hass.states.async_entity_ids("automation"))
        script_count = len(hass.states.async_entity_ids("script"))

        return (
            f"{p('system_role')}\n"
            f"{p('health_score', score=score)}\n"
            f"{p('issues_detected', total=total_issues, auto=auto_count, scripts=script_count)}\n"
            f"{p('top_issues')}\n"
            f"{_DATA_BLOCK_OPEN}\n{top5_txt}\n{_DATA_BLOCK_CLOSE}\n"
            f"{p('data_block_notice')}\n\n"
            f"{p('rules_title')}\n"
            f"- {p('rule_backup')}\n"
            f"- {p('rule_explain')}\n"
            f"- {p('rule_confirm')}\n"
            f"- {p('rule_use_tools')}\n"
            f"- {p('rule_use_haca_id')}\n"
            f"- {p('rule_proactive')}\n\n"
            f"{p('workflow_fix_title')}\n{p('workflow_fix')}\n\n"
            f"{p('workflow_lovelace_title')}\n{p('workflow_lovelace')}\n\n"
            f"{p('workflow_auto_title')}\n{p('workflow_auto')}\n\n"
            f"{p('workflow_scripts_title')}\n{p('workflow_scripts')}\n"
        )
