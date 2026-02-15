import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


class EntityAnalyzer:
    """Analyze entities for issues."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the analyzer."""
        self.hass = hass
        self.issues: list[dict[str, Any]] = []
        self._entity_references: dict[str, list[str]] = defaultdict(list)

    async def analyze_all(self, automation_configs: dict[str, dict] = None) -> list[dict[str, Any]]:
        """Analyze all entities."""
        self.issues = []
        
        # Build entity reference map
        if automation_configs:
            await self._build_entity_references(automation_configs)
        
        # Analyze entity states
        await self._analyze_entity_states()
        
        # Analyze zombie entities
        await self._analyze_zombie_entities()
        
        # Analyze entity registry
        await self._analyze_entity_registry()
        
        _LOGGER.info("Entity analysis complete: %d issues found", len(self.issues))
        
        return self.issues

    async def _build_entity_references(self, automation_configs: dict[str, dict]) -> None:
        """Build a map of which automations reference which entities."""
        self._entity_references.clear()
        
        for idx, (automation_id, config) in enumerate(automation_configs.items()):
            # Extract entity_ids from triggers
            triggers = config.get("trigger", [])
            if not isinstance(triggers, list):
                triggers = [triggers] if triggers else []
            
            for trigger in triggers:
                entity_id = trigger.get("entity_id")
                if entity_id:
                    if isinstance(entity_id, list):
                        for eid in entity_id:
                            self._entity_references[eid].append(automation_id)
                    else:
                        self._entity_references[entity_id].append(automation_id)
            
            # Extract from conditions
            conditions = config.get("condition", [])
            if not isinstance(conditions, list):
                conditions = [conditions] if conditions else []
            
            for condition in conditions:
                entity_id = condition.get("entity_id")
                if entity_id:
                    if isinstance(entity_id, list):
                        for eid in entity_id:
                            self._entity_references[eid].append(automation_id)
                    else:
                        self._entity_references[entity_id].append(automation_id)
            
            # Extract from actions
            actions = config.get("action", [])
            if not isinstance(actions, list):
                actions = [actions] if actions else []
            
            for action in actions:
                target = action.get("target", {})
                entity_id = target.get("entity_id")
                if entity_id:
                    if isinstance(entity_id, list):
                        for eid in entity_id:
                            self._entity_references[eid].append(automation_id)
                    else:
                        self._entity_references[entity_id].append(automation_id)
            
            if idx % 10 == 0: await asyncio.sleep(0)

    async def _analyze_entity_states(self) -> None:
        """Analyze entity states."""
        all_entities = self.hass.states.async_all()
        
        for idx, entity in enumerate(all_entities):
            entity_id = entity.entity_id
            
            # Skip HACA's own sensors to avoid self-reporting
            if entity_id.startswith("sensor.h_a_c_a_"):
                continue
            
            # Check for unavailable entities
            if entity.state == "unavailable":
                referencing_automations = self._entity_references.get(entity_id, [])
                severity = "high" if referencing_automations else "medium"
                
                message = "Entity is unavailable"
                if referencing_automations:
                    message += f" (used by {len(referencing_automations)} automation(s))"
                
                self.issues.append({
                    "entity_id": entity_id,
                    "type": "unavailable_entity",
                    "severity": severity,
                    "message": message,
                    "recommendation": "Check if device is online",
                })
            
            # Check for unknown state
            elif entity.state == "unknown":
                self.issues.append({
                    "entity_id": entity_id,
                    "type": "unknown_state",
                    "severity": "medium",
                    "message": "Entity has unknown state",
                    "recommendation": "Verify entity is receiving updates",
                })
            
            # Check for stale entities (>7 days without update)
            if entity.last_updated:
                time_since_update = datetime.now(entity.last_updated.tzinfo) - entity.last_updated
                
                if time_since_update > timedelta(days=7):
                    # Skip certain domains
                    skip_domains = ["sun", "zone", "person", "automation", "script"]
                    if not any(entity_id.startswith(f"{domain}.") for domain in skip_domains):
                        referencing_automations = self._entity_references.get(entity_id, [])
                        severity = "medium" if referencing_automations else "low"
                        
                        self.issues.append({
                            "entity_id": entity_id,
                            "type": "stale_entity",
                            "severity": severity,
                            "message": f"Entity hasn't updated in {time_since_update.days} days",
                            "recommendation": "Entity may be broken or no longer in use",
                        })
            
            if idx % 50 == 0: await asyncio.sleep(0)

    async def _analyze_zombie_entities(self) -> None:
        """Detect zombie entities - referenced but don't exist."""
        all_entities = self.hass.states.async_all()
        existing_entities = {entity.entity_id for entity in all_entities}
        
        for idx, (entity_id, automations) in enumerate(self._entity_references.items()):
            if entity_id not in existing_entities:
                self.issues.append({
                    "entity_id": entity_id,
                    "type": "zombie_entity",
                    "severity": "high",
                    "message": f"Referenced by {len(automations)} automation(s) but doesn't exist",
                    "recommendation": "Remove references or recreate entity",
                })
            if idx % 50 == 0: await asyncio.sleep(0)

    async def _analyze_entity_registry(self) -> None:
        """Analyze entity registry."""
        entity_reg = er.async_get(self.hass)
        
        for idx, entry in enumerate(entity_reg.entities.values()):
            entity_id = entry.entity_id
            
            # Check for disabled entities that are referenced
            if entry.disabled_by is not None:
                referencing_automations = self._entity_references.get(entity_id, [])
                if referencing_automations:
                    self.issues.append({
                        "entity_id": entity_id,
                        "type": "disabled_but_referenced",
                        "severity": "high",
                        "message": f"Disabled but referenced by {len(referencing_automations)} automation(s)",
                        "recommendation": "Enable entity or remove references",
                    })
            if idx % 50 == 0: await asyncio.sleep(0)

    def get_issue_summary(self) -> dict[str, Any]:
        """Get a summary of entity issues."""
        summary = {
            "total": len(self.issues),
            "by_severity": {"high": 0, "medium": 0, "low": 0},
            "by_type": {},
            "zombie_entities": 0,
            "unavailable_entities": 0,
            "stale_entities": 0
        }
        
        for issue in self.issues:
            severity = issue.get("severity", "low")
            issue_type = issue.get("type", "unknown")
            
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1
            summary["by_type"][issue_type] = summary["by_type"].get(issue_type, 0) + 1
            
            if issue_type == "zombie_entity":
                summary["zombie_entities"] += 1
            elif issue_type == "unavailable_entity":
                summary["unavailable_entities"] += 1
            elif issue_type == "stale_entity":
                summary["stale_entities"] += 1
        
        return summary
