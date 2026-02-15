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
        """Process a sentence."""
        text = user_input.text.lower()
        
        # Simple rule-based logic for HACA specific questions
        data = self.hass.data.get(DOMAIN, {})
        coordinator = None
        for entry_id in data:
            if isinstance(data[entry_id], dict) and "coordinator" in data[entry_id]:
                coordinator = data[entry_id]["coordinator"]
                break
        
        if not coordinator or not coordinator.data:
            response = "Je n'ai pas encore de données d'audit disponibles. Essayez de lancer un scan."
        elif any(k in text for k in ["score", "santé", "health", "état", "installation"]):
            score = coordinator.data.get("health_score", 0)
            issues = coordinator.data.get("total_issues", 0)
            response = f"Votre score de santé Home Assistant est de {score}%. J'ai détecté {issues} problèmes au total."
        elif any(k in text for k in ["problème", "issue", "erreur", "quoi de neuf", "quoi faire", "aider"]):
            autos = coordinator.data.get("automation_issues", 0)
            ents = coordinator.data.get("entity_issues", 0)
            perf = coordinator.data.get("performance_issues", 0)
            response = f"L'audit actuel montre {autos} problèmes d'automation, {ents} problèmes d'entités et {perf} optimisations de performance. Je vous conseille de commencer par traiter les problèmes d'entités indisponibles."
        else:
            # Fallback to default agent
            return conversation.ConversationResult(
                response=intent.IntentResponse(language=user_input.language),
                unmatched_identifier=True
            )

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response)
        return conversation.ConversationResult(
            response=intent_response,
            conversation_id=user_input.conversation_id
        )

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
        # Try to find a smarter agent if default is just Assist
        agent_id = None
        # In modern HA, we might want to check agent features or list agents
        # For now, we try to converse and check if it understood.
        
        result = await conversation.async_converse(
            hass,
            text=prompt,
            conversation_id=None,
            context=None,
            agent_id=None 
        )
        
        reply = result.response.speech.get("plain", {}).get("speech", "")
        
        # If the reply looks like a generic 'I don't understand' from Assist
        if not reply or any(k in reply.lower() for k in ["pas compris", "comprends pas", "unable to", "error", "désolé"]):
             return _get_local_fallback_explanation(issue_data)
             
        return reply
        
    except Exception as e:
        _LOGGER.debug("AI call failed, using local fallback: %s", e)
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
