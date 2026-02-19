"""Conversation integration for H.A.C.A - AI Assist."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_conversation(hass: HomeAssistant, entry: Any) -> None:
    """Set up HACA conversation integration."""
    _LOGGER.info("Setting up HACA Conversation Agent")
    
    agent = HacaConversationAgent(hass)
    conversation.async_set_agent(hass, entry, agent)

class HacaConversationAgent(conversation.AbstractConversationAgent):
    """HACA conversation agent."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the agent."""
        self.hass = hass

    @property
    def supported_languages(self) -> list[str] | str:
        """Return a list of supported languages."""
        return ["fr", "en"]

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a sentence in the user's language (fr/en)."""
        text = user_input.text.lower()
        lang = (user_input.language or "en").lower()
        # Treat any French locale variant as "fr", otherwise use "en"
        is_fr = lang.startswith("fr")

        # Simple rule-based logic for HACA specific questions
        data = self.hass.data.get(DOMAIN, {})
        coordinator = None
        for entry_id in data:
            if isinstance(data[entry_id], dict) and "coordinator" in data[entry_id]:
                coordinator = data[entry_id]["coordinator"]
                break

        if not coordinator or not coordinator.data:
            response = (
                "Je n'ai pas encore de données d'audit disponibles. Essayez de lancer un scan."
                if is_fr else
                "No audit data available yet. Please try running a scan first."
            )

        elif any(k in text for k in [
            # FR keywords
            "score", "santé", "état", "installation",
            # EN keywords
            "health", "status", "how is",
        ]):
            score = coordinator.data.get("health_score", 0)
            issues = coordinator.data.get("total_issues", 0)
            response = (
                f"Votre score de santé Home Assistant est de {score}%. "
                f"J'ai détecté {issues} problème(s) au total."
                if is_fr else
                f"Your Home Assistant health score is {score}%. "
                f"I detected {issues} issue(s) in total."
            )

        elif any(k in text for k in [
            # FR keywords
            "problème", "erreur", "quoi de neuf", "quoi faire", "aider", "aide",
            # EN keywords
            "issue", "problem", "error", "what's wrong", "help", "fix",
        ]):
            autos = coordinator.data.get("automation_issues", 0)
            ents = coordinator.data.get("entity_issues", 0)
            perf = coordinator.data.get("performance_issues", 0)
            sec = coordinator.data.get("security_issues", 0)
            response = (
                f"L'audit actuel montre {autos} problème(s) d'automation, "
                f"{ents} problème(s) d'entités, {perf} optimisation(s) de performance "
                f"et {sec} alerte(s) de sécurité. "
                f"Je vous conseille de commencer par traiter les entités indisponibles."
                if is_fr else
                f"The current audit shows {autos} automation issue(s), "
                f"{ents} entity issue(s), {perf} performance optimization(s) "
                f"and {sec} security alert(s). "
                f"I recommend starting with unavailable entities."
            )

        else:
            # Not a HACA-specific question — pass through to default agent
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.NO_INTENT_MATCH,
                "not_handled" if not is_fr else "non_géré",
            )
            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id,
            )

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response)
        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id,
        )

async def _async_find_llm_agent(hass: HomeAssistant) -> dict[str, str] | None:
    """Find the best available LLM agent with multi-domain priority."""
    try:
        # Priority: Gemini/Google > OpenAI > others
        priority_patterns = ["gemini", "google_generative_ai", "google", "openai", "gpt", "anthropic", "mistral", "ollama"]
        ignore_patterns = ["homeassistant", "home_assistant", "assist"]
        
        candidates: list[dict[str, Any]] = []

        # 1. Search in AI Task entities
        ai_task_entities = hass.states.async_entity_ids("ai_task")
        for entity_id in ai_task_entities:
            state = hass.states.get(entity_id)
            friendly_name = state.attributes.get("friendly_name", "").lower() if state else ""
            _LOGGER.info("AI Task Discovery: Checking '%s' (%s)", entity_id, friendly_name)
            
            eid_lower = entity_id.lower()
            for rank, p in enumerate(priority_patterns):
                if p in eid_lower or p in friendly_name:
                    candidates.append({"type": "ai_task", "id": entity_id, "priority": rank})
                    break

        # 2. Search in Conversation agents
        agents_info = conversation.async_get_agent_info(hass)
        agents = agents_info if isinstance(agents_info, list) else [agents_info] if agents_info else []
        for agent in agents:
            # Type guard for agents
            if not hasattr(agent, "id"):
                continue
                
            agent_id = agent.id.lower()
            agent_name = getattr(agent, "name", "").lower()
            
            # Skip basic assistants
            if any(p in agent_id for p in ignore_patterns):
                continue
                
            _LOGGER.info("Conversation Discovery: Checking '%s' (%s)", agent.id, agent_name)
            for rank, p in enumerate(priority_patterns):
                if p in agent_id or p in agent_name:
                    candidates.append({"type": "conversation", "id": agent.id, "priority": rank})
                    break
            else:
                # Add as low priority if it's not a known ignore but not a known smart pattern
                candidates.append({"type": "conversation", "id": agent.id, "priority": 99})

        if not candidates:
            _LOGGER.warning("No suitable AI agents found in any domain.")
            return None

        # Sort by priority (rank)
        candidates.sort(key=lambda x: x["priority"])
        best = candidates[0]
        _LOGGER.info("Smart Selection: Picked %s (priority %d)", best["id"], best["priority"])
        
        return {"type": str(best["type"]), "id": str(best["id"])}
                
    except Exception as e:
        _LOGGER.error("Error in AI discovery: %s (%s)", e, type(e))
        
    return None

async def explain_issue_ai(hass: HomeAssistant, issue_data: dict[str, Any]) -> str:
    """Use configured conversation agent or fallback to local explanation."""
    
    # Check if we have an LLM configured (OpenAI, Gemini, Ollama...)
    # Avoid the default 'homeassistant' agent which is just 'Assist' (regex-based)
    # as it cannot handle free-form explanation prompts.
    
    prompt = f"""
    En tant qu'expert Home Assistant, explique ce problème détecté par l'auditeur HACA et donne des conseils pour le résoudre.
    
    Issue: {issue_data.get('message')}
    Type: {issue_data.get('type')}
    Sévérité: {issue_data.get('severity')}
    Entité/Source: {issue_data.get('entity_id') or issue_data.get('alias')}
    
    Réponds de manière concise et pédagogique en français.
    """
    
    try:
        # Try to find a smarter agent (AI Task or Conversation)
        agent_data = await _async_find_llm_agent(hass)
        _LOGGER.info("Using AI backend: %s", agent_data)
        
        reply = ""
        
        if agent_data and agent_data["type"] == "ai_task":
            # Usage of ai_task.generate_data
            _LOGGER.info("Calling ai_task.generate_data for %s", agent_data["id"])
            result = await hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "entity_id": agent_data["id"],
                    "task_name": "HACA Issue Explanation",
                    "instructions": prompt
                },
                blocking=True,
                return_response=True
            )
            _LOGGER.info("AI Task Raw Result: %s", result)
            
            if result:
                # Handle potential nesting (sometimes results are keyed by entity_id)
                if agent_data["id"] in result and isinstance(result[agent_data["id"]], dict):
                    reply = result[agent_data["id"]].get("data", "")
                else:
                    reply = result.get("data", "")
            
        elif agent_data:
            # Usage of conversation (legacy or improved)
            agent_id = agent_data["id"]
            result = await conversation.async_converse(
                hass,
                text=prompt,
                conversation_id=None,
                context=None,
                agent_id=agent_id
            )
            _LOGGER.info("Conversation response: %s", result)
            reply = result.response.speech.get("plain", {}).get("speech", "")
        
        _LOGGER.info("Final AI Reply (raw): %s", reply[:100] + "..." if reply and len(reply) > 100 else reply)
        
        if not reply:
             _LOGGER.warning("AI returned empty response")
             return _get_local_fallback_explanation(issue_data)
        
        # Refined failure detection: only catch specific default Assist failures
        fail_markers = ["pas compris", "comprends pas", "unable to", "no such service"]
        if len(reply) < 100 and any(k in reply.lower() for k in fail_markers):
             _LOGGER.warning("AI response looks like a failure: %s", reply)
             return _get_local_fallback_explanation(issue_data)
             
        return reply
        
    except Exception as e:
        _LOGGER.error("AI call failed: %s (%s)", e, type(e))
        return _get_local_fallback_explanation(issue_data)

def _get_local_fallback_explanation(issue_data: dict[str, Any]) -> str:
    """Provide a rule-based explanation when AI is not available."""
    issue_type = issue_data.get("type", "")
    message = issue_data.get("message", "Problème inconnu")
    entity = issue_data.get("entity_id") or issue_data.get("alias", "inconnu")
    
    explanation = f"Je n'ai pas pu contacter un assistant IA avancé (OpenAI/Gemini), voici donc une analyse locale : \n\n"
    explanation += f"**Problème détecté :** {message}\n"
    explanation += f"**Impact :** "
    
    if "device_id" in issue_type:
        explanation += "L'utilisation de 'device_id' au lieu d'entités fragilise votre automation car le remplacement du matériel cassera le lien."
    elif "unavailable" in issue_type or "zombie" in issue_type:
        explanation += "Cette entité n'existe plus ou est hors-ligne, ce qui peut paralyser vos dashboards ou automations."
    elif "mode" in issue_type:
        explanation += "Le mode d'exécution ('single') risque d'ignorer des déclenchements importants si l'automation est déjà en cours."
    elif "secret" in issue_type or "security" in issue_type:
        explanation += "Des données sensibles sont exposées en clair, ce qui représente un risque de sécurité."
    else:
        explanation += "Ce problème peut affecter la stabilité ou les performances de votre système."
        
    explanation += f"\n\n**Recommandation :** {issue_data.get('recommendation', 'Vérifiez la configuration manuellement.')}"
    
    return explanation
