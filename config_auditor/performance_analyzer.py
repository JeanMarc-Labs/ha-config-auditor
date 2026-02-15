"""Performance analyzer for H.A.C.A - Module 3."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from .const import (
    ISSUE_HIGH_FREQUENCY,
    ISSUE_VERY_HIGH_FREQUENCY,
    ISSUE_BURST_PATTERN,
    HIGH_FREQUENCY_TRIGGERS_PER_HOUR,
    VERY_HIGH_FREQUENCY_TRIGGERS_PER_HOUR,
    BURST_TRIGGERS_IN_MINUTES,
    BURST_WINDOW_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

class PerformanceAnalyzer:
    """Analyze automation performance and trigger patterns."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the performance analyzer."""
        self.hass = hass
        self.issues: list[dict[str, Any]] = []
        _LOGGER.debug("PerformanceAnalyzer initialized")

    async def analyze_all(self, automation_configs: dict[str, dict[str, Any]] = None) -> list[dict[str, Any]]:
        """Analyze performance of all automations."""
        self.issues = []
        automation_configs = automation_configs or {}
        
        automations = self.hass.states.async_all("automation")
        
        for idx, state in enumerate(automations):
            entity_id = state.entity_id
            alias = state.attributes.get("friendly_name", entity_id)
            
            # Check for high frequency based on last_triggered
            await self._analyze_trigger_rate(state, alias)
            
            # Check complexity if config is available
            config = automation_configs.get(entity_id)
            
            # Fallback: try to match by friendly_name/alias if entity_id mismatch
            if not config:
                for cfg_id, cfg in automation_configs.items():
                    if cfg.get("alias") == alias:
                        config = cfg
                        break
            
            if config:
                self._analyze_complexity(entity_id, alias, config)
                self._detect_potential_loops(entity_id, alias, config)
            else:
                _LOGGER.debug("No config found for %s, skipping complexity check", entity_id)

        # 2. Analyze Noisy Entities (Database Impact)
        await self._detect_noisy_entities()

        _LOGGER.info("Performance analysis complete: %d issues found, analyzed %d states", 
                     len(self.issues), len(automations))
        return self.issues

    async def _analyze_trigger_rate(self, state: Any, alias: str) -> None:
        """Analyze the trigger rate for a specific automation."""
        last_triggered = state.attributes.get("last_triggered")
        
        # If triggered in the last few seconds, it might be part of a loop
        if last_triggered:
            try:
                # Handle both aware and naive datetimes
                now = datetime.now(last_triggered.tzinfo)
                delta = (now - last_triggered).total_seconds()
                
                # Check for extremely frequent triggers (< 2 seconds)
                if delta < 2.0:
                    self.issues.append({
                        "entity_id": state.entity_id,
                        "alias": alias,
                        "type": "high_frequency_trigger",
                        "severity": "high",
                        "message": f"Triggered very recently ({delta:.1f}s ago), possible loop",
                        "location": "trigger",
                        "recommendation": "Check for infinite loops or add a delay",
                        "fix_available": False,
                    })
            except Exception as e:
                _LOGGER.warning("Error checking trigger rate for %s: %s", alias, e)

    def _analyze_complexity(self, entity_id: str, alias: str, config: dict[str, Any]) -> None:
        """Analyze automation complexity."""
        triggers = config.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers] if triggers else []
            
        actions = config.get("action", [])
        if not isinstance(actions, list):
            actions = [actions] if actions else []
            
        # Complexity check: Too many actions (lowered threshold)
        if len(actions) > 10:
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "high_complexity_actions",
                "severity": "medium",
                "message": f"Automation has {len(actions)} actions, which is complex",
                "location": "root",
                "recommendation": "Split into scripts or multiple automations",
                "fix_available": False,
            })
            
        # Parallel mode with high max (lowered threshold)
        mode = config.get("mode", "single")
        if mode == "parallel":
            max_runs = config.get("max", 10)
            if max_runs > 5:
                 self.issues.append({
                    "entity_id": entity_id,
                    "alias": alias,
                    "type": "high_parallel_max",
                    "severity": "medium",
                    "message": f"Parallel mode with max={max_runs} can consume resources",
                    "location": "mode",
                    "recommendation": "Reduce max concurrency or use queued mode",
                    "fix_available": False,
                })

    def _detect_potential_loops(self, entity_id: str, alias: str, config: dict[str, Any]) -> None:
        """Detect if an automation might trigger itself in a loop."""
        triggers = config.get("trigger", [])
        if not isinstance(triggers, list): triggers = [triggers]
        
        actions = config.get("action", [])
        if not isinstance(actions, list): actions = [actions]

        # Entities in triggers
        trigger_entities = set()
        for t in triggers:
            if isinstance(t, dict):
                ent = t.get("entity_id")
                if isinstance(ent, list): trigger_entities.update(ent)
                elif isinstance(ent, str): trigger_entities.add(ent)

        # Entities in actions
        action_entities = set()
        for a in actions:
            if isinstance(a, dict):
                data = a.get("data", {})
                ent = a.get("entity_id") or data.get("entity_id")
                if isinstance(ent, list): action_entities.update(ent)
                elif isinstance(ent, str): action_entities.add(ent)

        # Potential self-loop
        intersection = trigger_entities.intersection(action_entities)
        if intersection:
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "potential_self_loop",
                "severity": "medium",
                "message": f"Automation triggers on and modifies the same entities: {', '.join(intersection)}",
                "location": "logic",
                "recommendation": "Add a condition to check state changes or use a delay to break loops",
                "fix_available": False,
            })

    async def _detect_noisy_entities(self) -> None:
        """Detect entities with high update frequency or missing optimizations."""
        all_states = self.hass.states.async_all()
        for state in all_states:
            if state.domain == "automation" or state.entity_id.startswith("sensor.h_a_c_a_"):
                continue
                
            if state.domain == "sensor":
                # Missing state_class for frequent sensors
                if any(k in state.entity_id for k in ["power", "energy", "voltage", "current"]):
                    if "state_class" not in state.attributes:
                        self.issues.append({
                            "entity_id": state.entity_id,
                            "type": "missing_state_class",
                            "severity": "low",
                            "message": "Power/Energy sensor missing state_class, impacting long-term stats",
                            "recommendation": "Add state_class (measurement or total_increasing) to the sensor configuration",
                            "fix_available": False,
                        })

    def get_issue_summary(self) -> dict[str, Any]:
        """Get a summary of performance issues."""
        return {
            "total": len(self.issues),
            "loops": len([i for i in self.issues if "loop" in i.get("type", "")]),
            "database": len([i for i in self.issues if "state_class" in i.get("type", "")]),
            "complexity": len([i for i in self.issues if "complexity" in i.get("type", "")]),
        }
