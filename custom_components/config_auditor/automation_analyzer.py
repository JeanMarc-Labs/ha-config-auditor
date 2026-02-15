"""Automation analyzer for H.A.C.A - Comprehensive best practices checker."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


class AutomationAnalyzer:
    """Analyze automations for best practice violations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the analyzer."""
        self.hass = hass
        self.issues: list[dict[str, Any]] = []
        self._automation_configs: dict[str, dict[str, Any]] = {}
        self._script_configs: dict[str, dict[str, Any]] = {}
        self._scene_configs: dict[str, dict[str, Any]] = {}

    async def analyze_all(self) -> list[dict[str, Any]]:
        """Analyze all automations."""
        self.issues = []
        
        # Load configurations
        await self._load_automation_configs()
        await self._load_script_configs()
        await self._load_scene_configs()
        
        _LOGGER.debug("Analyzing %d automations, %d scripts, %d scenes", 
                     len(self._automation_configs), len(self._script_configs), len(self._scene_configs))
        
        # Analyze each automation
        for idx, (entity_id, config) in enumerate(self._automation_configs.items()):
            self._analyze_automation(entity_id, config)
            if idx % 10 == 0: await asyncio.sleep(0)
            
        # Analyze each script
        for idx, (entity_id, config) in enumerate(self._script_configs.items()):
            self._analyze_script(entity_id, config)
            if idx % 10 == 0: await asyncio.sleep(0)
            
        # Analyze each scene
        for idx, (entity_id, config) in enumerate(self._scene_configs.items()):
            self._analyze_scene(entity_id, config)
            if idx % 10 == 0: await asyncio.sleep(0)
        
        # Check for never-triggered automations
        await self._check_never_triggered()
        
        _LOGGER.info(
            "Automation analysis complete: %d automations, %d issues",
            len(self._automation_configs),
            len(self.issues)
        )
        
        return self.issues

    async def _load_automation_configs(self) -> None:
        """Load automation configurations from automations.yaml."""
        self._automation_configs = {}
        
        config_dir = Path(self.hass.config.config_dir)
        automations_file = config_dir / "automations.yaml"
        
        if not automations_file.exists():
            _LOGGER.warning("automations.yaml not found at %s", automations_file)
            return
        
        try:
            def read_automations():
                with open(automations_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    return content if content is not None else []
            
            automations = await self.hass.async_add_executor_job(read_automations)
            
            if not isinstance(automations, list):
                _LOGGER.warning("automations.yaml is not a list, got %s", type(automations))
                return
            
            _LOGGER.debug("Loaded %d automations from file", len(automations))
            
            # Map automations to entity_ids
            entity_reg = er.async_get(self.hass)
            
            for config in automations:
                if not isinstance(config, dict):
                    continue
                    
                automation_id = config.get("id")
                alias = config.get("alias", "")
                
                entity_id = None
                # Find matching entity by unique_id
                for entity in entity_reg.entities.values():
                    if entity.platform == "automation" and entity.unique_id == automation_id:
                        entity_id = entity.entity_id
                        break
                
                # Fallback to alias-based entity_id
                if not entity_id and alias:
                    entity_id = f"automation.{alias.lower().replace(' ', '_').replace('-', '_')}"
                    # Check if this entity exists in the registry
                    if not any(e.entity_id == entity_id for e in entity_reg.entities.values()):
                        entity_id = None
                
                # Last resort: use generic identifier
                if not entity_id:
                    entity_id = f"automation.unknown_{automation_id or len(self._automation_configs)}"
                
                self._automation_configs[entity_id] = config
                _LOGGER.debug("Mapped automation '%s' to %s", alias or automation_id, entity_id)
            
            _LOGGER.info("Loaded %d automation configs successfully", len(self._automation_configs))
        except Exception as e:
            _LOGGER.error("Error loading automations.yaml: %s", e, exc_info=True)

    async def _load_script_configs(self) -> None:
        """Load script configurations from scripts.yaml."""
        config_dir = Path(self.hass.config.config_dir)
        scripts_file = config_dir / "scripts.yaml"
        if not scripts_file.exists(): return
        
        try:
            def read_scripts():
                with open(scripts_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    return content if content is not None else {}
            
            scripts = await self.hass.async_add_executor_job(read_scripts)
            for slug, config in scripts.items():
                self._script_configs[f"script.{slug}"] = config
        except Exception as e:
            _LOGGER.error("Error loading scripts.yaml: %s", e)

    async def _load_scene_configs(self) -> None:
        """Load scene configurations from scenes.yaml."""
        config_dir = Path(self.hass.config.config_dir)
        scenes_file = config_dir / "scenes.yaml"
        if not scenes_file.exists(): return
        
        try:
            def read_scenes():
                with open(scenes_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    return content if content is not None else []
            
            scenes = await self.hass.async_add_executor_job(read_scenes)
            for config in scenes:
                if isinstance(config, dict) and "id" in config:
                    self._scene_configs[f"scene.{config.get('name', config['id']).lower().replace(' ', '_')}"] = config
        except Exception as e:
            _LOGGER.error("Error loading scenes.yaml: %s", e)

    def _analyze_script(self, entity_id: str, config: dict[str, Any]) -> None:
        """Analyze a single script."""
        alias = config.get("alias", entity_id)
        
        # Check for missing description
        if not config.get("description"):
            self.issues.append({
                "entity_id": entity_id,
                "type": "no_description",
                "severity": "low",
                "message": f"Script '{alias}' has no description",
                "recommendation": "Add a description to clarify script purpose",
            })
            
        # Check for missing sequence
        if not config.get("sequence"):
             self.issues.append({
                "entity_id": entity_id,
                "type": "empty_script",
                "severity": "high",
                "message": f"Script '{alias}' has no sequence of actions",
                "recommendation": "Add actions to the script sequence",
            })

    def _analyze_scene(self, entity_id: str, config: dict[str, Any]) -> None:
        """Analyze a single scene."""
        if not config.get("entities"):
             self.issues.append({
                "entity_id": entity_id,
                "type": "empty_scene",
                "severity": "medium",
                "message": "Scene has no entities defined",
                "recommendation": "Add entities to the scene state definition",
            })

    def _analyze_automation(self, entity_id: str, config: dict[str, Any]) -> None:
        """Analyze a single automation."""
        alias = config.get("alias", "")
        
        # Check for missing alias
        if not alias:
            self.issues.append({
                "entity_id": entity_id,
                "alias": entity_id,
                "type": "no_alias",
                "severity": "medium",
                "message": "Automation has no alias/name",
                "location": "root",
                "recommendation": "Add an alias to make automation identifiable",
                "fix_available": False,
            })
        
        # Check for missing description
        if not config.get("description"):
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias or entity_id,
                "type": "no_description",
                "severity": "low",
                "message": "Automation has no description",
                "location": "root",
                "recommendation": "Add a description to document automation purpose",
                "fix_available": False,
            })
        
        # Analyze triggers - support both 'trigger' (old) and 'triggers' (new UI format)
        triggers = config.get("triggers") or config.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers] if triggers else []
        
        _LOGGER.debug("Analyzing %d triggers for %s", len(triggers), entity_id)
        
        for idx, trigger in enumerate(triggers):
            if isinstance(trigger, dict):
                self._analyze_trigger(entity_id, alias or entity_id, trigger, idx)
        
        # Analyze conditions - support both 'condition' and 'conditions'
        conditions = config.get("conditions") or config.get("condition", [])
        if not isinstance(conditions, list):
            conditions = [conditions] if conditions else []
        
        for idx, condition in enumerate(conditions):
            if isinstance(condition, dict):
                self._analyze_condition(entity_id, alias or entity_id, condition, idx)
        
        # Analyze actions
        actions = config.get("action", [])
        if not isinstance(actions, list):
            actions = [actions] if actions else []
        
        for idx, action in enumerate(actions):
            if isinstance(action, dict):
                self._analyze_action(entity_id, alias or entity_id, action, idx)
        
        # Analyze mode
        self._analyze_mode(entity_id, alias or entity_id, config)

    def _analyze_trigger(
        self, entity_id: str, alias: str, trigger: dict[str, Any], idx: int
    ) -> None:
        """Analyze a trigger."""
        platform = trigger.get("platform") or trigger.get("trigger", "")
        
        # Check for device_id in triggers (HIGH severity)
        # Peut être directement dans le trigger ou dans des sous-champs
        if "device_id" in trigger:
            _LOGGER.debug("Found device_id in trigger %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_trigger",
                "severity": "high",
                "message": f"Trigger {idx} uses device_id which breaks when device is re-added",
                "location": f"trigger[{idx}]",
                "recommendation": "Use entity_id instead of device_id for reliability",
                "fix_available": True,
            })
        
        # Check aussi dans platform: device
        if platform == "device":
            _LOGGER.debug("Found device platform in trigger %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_trigger_platform",
                "severity": "high",
                "message": f"Trigger {idx} uses 'device' platform which is fragile",
                "location": f"trigger[{idx}]",
                "recommendation": "Use state/numeric_state platform with entity_id instead",
                "fix_available": True,
            })
        
        # Check for zone trigger without entity
        if platform == "zone" and not trigger.get("entity_id"):
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "zone_no_entity",
                "severity": "medium",
                "message": f"Trigger {idx}: zone trigger missing entity_id",
                "location": f"trigger[{idx}]",
                "recommendation": "Specify which entity to track in the zone",
                "fix_available": False,
            })

    def _analyze_condition(
        self, entity_id: str, alias: str, condition: dict[str, Any], idx: int
    ) -> None:
        """Analyze a condition."""
        condition_type = condition.get("condition", "")
        
        # Check for device_id in conditions (similar to triggers/actions)
        if "device_id" in condition:
            _LOGGER.debug("Found device_id in condition %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_condition",
                "severity": "high",
                "message": f"Condition {idx} uses device_id which breaks when device is re-added",
                "location": f"condition[{idx}]",
                "recommendation": "Use state/numeric_state condition with entity_id instead of device condition",
                "fix_available": True,
            })
        
        # Check for device condition platform
        if condition_type == "device":
            _LOGGER.debug("Found device condition in condition %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_condition_platform",
                "severity": "high",
                "message": f"Condition {idx} uses 'device' condition type which is fragile",
                "location": f"condition[{idx}]",
                "recommendation": "Use state/numeric_state condition type with entity_id instead",
                "fix_available": True,
            })
        
        # Check for template conditions that could be native
        if condition_type == "template":
            template = condition.get("value_template", "")
            
            # Check for simple state checks
            if "is_state(" in template:
                # Simple state check: {{ is_state('light.x', 'on') }}
                if not any(op in template.lower() for op in [" and ", " or ", " not ", "=="]):
                    self.issues.append({
                        "entity_id": entity_id,
                        "alias": alias,
                        "type": "template_simple_state",
                        "severity": "high",
                        "message": f"Condition {idx} uses template for simple state check",
                        "location": f"condition[{idx}]",
                        "recommendation": "Use native 'state' condition instead of template",
                        "fix_available": True,
                    })
            
            # Check for numeric comparisons
            if re.search(r"(float|int)\s*[><]=?", template):
                self.issues.append({
                    "entity_id": entity_id,
                    "alias": alias,
                    "type": "template_numeric_comparison",
                    "severity": "high",
                    "message": f"Condition {idx} uses template for numeric comparison",
                    "location": f"condition[{idx}]",
                    "recommendation": "Use 'numeric_state' condition for validation at load time",
                    "fix_available": False,
                })
            
            # Check for time comparisons
            if "now().hour" in template or "now().minute" in template:
                self.issues.append({
                    "entity_id": entity_id,
                    "alias": alias,
                    "type": "template_time_check",
                    "severity": "medium",
                    "message": f"Condition {idx} uses template for time check",
                    "location": f"condition[{idx}]",
                    "recommendation": "Use 'time' condition with after/before parameters",
                    "fix_available": False,
                })

    def _analyze_action(
        self, entity_id: str, alias: str, action: dict[str, Any], idx: int
    ) -> None:
        """Analyze an action."""
        # Check for device_id in actions - peut être dans action directement ou dans target
        if "device_id" in action:
            _LOGGER.debug("Found device_id in action %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_action",
                "severity": "high",
                "message": f"Action {idx} uses device_id which breaks when device is re-added",
                "location": f"action[{idx}]",
                "recommendation": "Use target with entity_id instead of device_id",
                "fix_available": True,
            })
        
        # Check aussi dans target.device_id
        target = action.get("target", {})
        if isinstance(target, dict) and "device_id" in target:
            _LOGGER.debug("Found device_id in target of action %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_target",
                "severity": "high",
                "message": f"Action {idx} uses device_id in target which breaks when device is re-added",
                "location": f"action[{idx}].target",
                "recommendation": "Use entity_id in target instead of device_id",
                "fix_available": True,
            })
        
        # Check for wait_template instead of wait_for_trigger
        if "wait_template" in action:
            template = action.get("wait_template", "")
            if "is_state(" in template:
                self.issues.append({
                    "entity_id": entity_id,
                    "alias": alias,
                    "type": "wait_template_vs_wait_for_trigger",
                    "severity": "medium",
                    "message": f"Action {idx} uses wait_template for state check",
                    "location": f"action[{idx}]",
                    "recommendation": "Use wait_for_trigger with state trigger (event-driven, not polling)",
                    "fix_available": False,
                })
        
        # Check for deprecated services
        service = action.get("service", action.get("action", ""))
        deprecated_services = {
            "homeassistant.turn_on": "Use domain-specific services like light.turn_on",
            "homeassistant.turn_off": "Use domain-specific services like light.turn_off",
            "homeassistant.toggle": "Use domain-specific services like light.toggle",
        }
        
        if service in deprecated_services:
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "deprecated_service",
                "severity": "low",
                "message": f"Action {idx} uses generic service '{service}'",
                "location": f"action[{idx}]",
                "recommendation": deprecated_services[service],
                "fix_available": False,
            })

    def _analyze_mode(self, entity_id: str, alias: str, config: dict[str, Any]) -> None:
        """Analyze automation mode."""
        mode = config.get("mode", "single")
        
        triggers = config.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers] if triggers else []
        
        actions = config.get("action", [])
        if not isinstance(actions, list):
            actions = [actions] if actions else []
        
        # Check for motion/occupancy triggers with delays in single mode
        has_motion_trigger = False
        for t in triggers:
            if isinstance(t, dict):
                entity_id_in_trigger = t.get("entity_id", "")
                if isinstance(entity_id_in_trigger, str):
                    entity_lower = entity_id_in_trigger.lower()
                    if "motion" in entity_lower or "occupancy" in entity_lower:
                        has_motion_trigger = True
                        break
        
        # Check for delays or waits in actions
        has_delay_or_wait = False
        for a in actions:
            if isinstance(a, dict):
                if "delay" in a or "wait_template" in a or "wait_for_trigger" in a:
                    has_delay_or_wait = True
                    break
        
        if has_motion_trigger and has_delay_or_wait and mode == "single":
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "incorrect_mode_motion_single",
                "severity": "high",
                "message": "Motion automation uses 'single' mode with delays/waits",
                "location": "mode",
                "recommendation": "Use 'restart' mode - re-triggers must reset the timer",
                "fix_available": True,
            })

    async def _check_never_triggered(self) -> None:
        """Check for automations that have never been triggered."""
        for entity_id in list(self.hass.states.async_entity_ids("automation")):
            state = self.hass.states.get(entity_id)
            
            if state:
                last_triggered = state.attributes.get("last_triggered")
                alias = state.attributes.get("friendly_name", entity_id)
                
                if last_triggered is None:
                    self.issues.append({
                        "entity_id": entity_id,
                        "alias": alias,
                        "type": "never_triggered",
                        "severity": "low",
                        "message": "Automation has never been triggered since HA restart",
                        "location": "trigger",
                        "recommendation": "Verify triggers are configured correctly or automation is needed",
                        "fix_available": False,
                    })

    def get_issue_summary(self) -> dict[str, Any]:
        """Get a summary of issues."""
        summary = {
            "total": len(self.issues),
            "by_severity": {"high": 0, "medium": 0, "low": 0},
            "by_type": {},
            "automations_analyzed": len(self._automation_configs)
        }
        
        for issue in self.issues:
            severity = issue.get("severity", "low")
            issue_type = issue.get("type", "unknown")
            
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1
            summary["by_type"][issue_type] = summary["by_type"].get(issue_type, 0) + 1
        
        return summary
