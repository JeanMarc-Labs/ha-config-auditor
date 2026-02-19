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

from .translation_utils import TranslationHelper

_LOGGER = logging.getLogger(__name__)


class AutomationAnalyzer:
    """Analyze automations for best practice violations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the analyzer."""
        self.hass = hass
        self.issues: list[dict[str, Any]] = []
        self.automation_issues: list[dict[str, Any]] = []
        self.script_issues: list[dict[str, Any]] = []
        self.scene_issues: list[dict[str, Any]] = []
        self._automation_configs: dict[str, dict[str, Any]] = {}
        self._script_configs: dict[str, dict[str, Any]] = {}
        self._scene_configs: dict[str, dict[str, Any]] = {}
        self._translator = TranslationHelper(hass)

    async def analyze_all(self) -> list[dict[str, Any]]:
        """Analyze all automations."""
        self.issues = []
        
        # Load language for translations
        language = self.hass.config.language or "en"
        await self._translator.async_load_language(language)
        
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
        
        # Separate issues by entity_id prefix
        self.automation_issues = []
        self.script_issues = []
        self.scene_issues = []
        
        for issue in self.issues:
            entity_id = issue.get("entity_id", "")
            if entity_id.startswith("script."):
                self.script_issues.append(issue)
            elif entity_id.startswith("scene."):
                self.scene_issues.append(issue)
            else:
                # Everything else goes to automation issues
                self.automation_issues.append(issue)
        
        _LOGGER.info(
            "Automation analysis complete: %d automations, %d automation issues, %d script issues, %d scene issues",
            len(self._automation_configs),
            len(self.automation_issues),
            len(self.script_issues),
            len(self.scene_issues)
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
        t = self._translator.t
        
        # Check for missing description
        if not config.get("description"):
            self.issues.append({
                "entity_id": entity_id,
                "type": "no_description",
                "severity": "low",
                "message": t("script_no_description", alias=alias),
                "recommendation": t("add_description"),
            })
            
        # Check for missing sequence
        if not config.get("sequence"):
             self.issues.append({
                "entity_id": entity_id,
                "type": "empty_script",
                "severity": "high",
                "message": t("script_no_sequence", alias=alias),
                "recommendation": t("add_description"),
            })

    def _analyze_scene(self, entity_id: str, config: dict[str, Any]) -> None:
        """Analyze a single scene."""
        t = self._translator.t
        
        if not config.get("entities"):
             self.issues.append({
                "entity_id": entity_id,
                "type": "empty_scene",
                "severity": "medium",
                "message": t("scene_no_entities"),
                "recommendation": t("add_description"),
            })

    def _analyze_automation(self, entity_id: str, config: dict[str, Any]) -> None:
        """Analyze a single automation."""
        alias = config.get("alias", "")
        t = self._translator.t
        
        # Check for missing alias
        if not alias:
            self.issues.append({
                "entity_id": entity_id,
                "alias": entity_id,
                "type": "no_alias",
                "severity": "medium",
                "message": t("no_alias"),
                "location": "root",
                "recommendation": t("add_alias"),
                "fix_available": False,
            })
        
        # Check for missing description
        if not config.get("description"):
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias or entity_id,
                "type": "no_description",
                "severity": "low",
                "message": t("no_description"),
                "location": "root",
                "recommendation": t("add_description"),
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
        t = self._translator.t
        
        # Check for device_id in triggers (HIGH severity)
        # Peut être directement dans le trigger ou dans des sous-champs
        if "device_id" in trigger:
            _LOGGER.debug("Found device_id in trigger %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_trigger",
                "severity": "high",
                "message": t("trigger_uses_device_id", idx=idx),
                "location": f"trigger[{idx}]",
                "recommendation": t("use_entity_id_instead_device"),
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
                "message": t("trigger_uses_device_platform", idx=idx),
                "location": f"trigger[{idx}]",
                "recommendation": t("use_state_platform"),
                "fix_available": True,
            })
        
        # Check for zone trigger without entity
        if platform == "zone" and not trigger.get("entity_id"):
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "zone_no_entity",
                "severity": "medium",
                "message": t("zone_trigger_missing_entity", idx=idx),
                "location": f"trigger[{idx}]",
                "recommendation": t("specify_zone_entity"),
                "fix_available": False,
            })

    def _analyze_condition(
        self, entity_id: str, alias: str, condition: dict[str, Any], idx: int
    ) -> None:
        """Analyze a condition."""
        condition_type = condition.get("condition", "")
        t = self._translator.t
        
        # Check for device_id in conditions (similar to triggers/actions)
        if "device_id" in condition:
            _LOGGER.debug("Found device_id in condition %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_condition",
                "severity": "high",
                "message": t("condition_uses_device_id", idx=idx),
                "location": f"condition[{idx}]",
                "recommendation": t("use_entity_id_instead_device"),
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
                "message": t("condition_uses_device_platform", idx=idx),
                "location": f"condition[{idx}]",
                "recommendation": t("use_state_platform"),
                "fix_available": True,
            })
        
        # Check for template conditions that could be native
        if condition_type == "template":
            template = condition.get("value_template", "")
            
            # Check for simple state checks
            if "is_state(" in template:
                # Only flag purely simple is_state() checks:
                # exclude templates with logical operators, other HA functions, or Jinja2 filters.
                has_complex_logic = any(op in template.lower() for op in [" and ", " or ", " not "])
                has_other_functions = any(f in template for f in [
                    "is_state_attr(", "states(", "state_attr(", "expand(",
                    "namespace(", "trigger.", "this."
                ])
                has_jinja_filter = " | " in template
                if not has_complex_logic and not has_other_functions and not has_jinja_filter:
                    self.issues.append({
                        "entity_id": entity_id,
                        "alias": alias,
                        "type": "template_simple_state",
                        "severity": "high",
                        "message": t("template_simple_state", idx=idx),
                        "location": f"condition[{idx}]",
                        "recommendation": t("use_state_condition"),
                        "fix_available": True,
                    })
            
            # Check for numeric comparisons
            if re.search(r"(float|int)\s*[><]=?", template):
                self.issues.append({
                    "entity_id": entity_id,
                    "alias": alias,
                    "type": "template_numeric_comparison",
                    "severity": "high",
                    "message": t("template_numeric_comparison", idx=idx),
                    "location": f"condition[{idx}]",
                    "recommendation": t("use_numeric_state_condition"),
                    "fix_available": False,
                })
            
            # Check for time comparisons
            if "now().hour" in template or "now().minute" in template:
                self.issues.append({
                    "entity_id": entity_id,
                    "alias": alias,
                    "type": "template_time_check",
                    "severity": "medium",
                    "message": t("template_time_check", idx=idx),
                    "location": f"condition[{idx}]",
                    "recommendation": t("use_time_condition"),
                    "fix_available": False,
                })

    def _analyze_action(
        self, entity_id: str, alias: str, action: dict[str, Any], idx: int
    ) -> None:
        """Analyze an action."""
        t = self._translator.t
        
        # Check for device_id in actions - peut être dans action directement ou dans target
        if "device_id" in action:
            _LOGGER.debug("Found device_id in action %d of %s", idx, entity_id)
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "device_id_in_action",
                "severity": "high",
                "message": t("action_uses_device_id", idx=idx),
                "location": f"action[{idx}]",
                "recommendation": t("use_entity_id_in_target"),
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
                "message": t("action_target_uses_device_id", idx=idx),
                "location": f"action[{idx}].target",
                "recommendation": t("use_entity_id_in_target"),
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
                    "message": t("wait_template_state_check", idx=idx),
                    "location": f"action[{idx}]",
                    "recommendation": t("use_wait_for_trigger"),
                    "fix_available": False,
                })
        
        # Check for deprecated services
        service = action.get("service", action.get("action", ""))
        
        if service in ["homeassistant.turn_on", "homeassistant.turn_off", "homeassistant.toggle"]:
            self.issues.append({
                "entity_id": entity_id,
                "alias": alias,
                "type": "deprecated_service",
                "severity": "low",
                "message": t("generic_service", idx=idx, service=service),
                "location": f"action[{idx}]",
                "recommendation": t("use_domain_service", domain="light"),
                "fix_available": False,
            })

    def _analyze_mode(self, entity_id: str, alias: str, config: dict[str, Any]) -> None:
        """Analyze automation mode."""
        t = self._translator.t
        
        mode = config.get("mode", "single")
        
        triggers = config.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers] if triggers else []
        
        actions = config.get("action", [])
        if not isinstance(actions, list):
            actions = [actions] if actions else []
        
        # Check for motion/occupancy triggers with delays in single mode
        has_motion_trigger = False
        for tr in triggers:
            if isinstance(tr, dict):
                entity_id_in_trigger = tr.get("entity_id", "")
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
                "message": t("motion_single_mode"),
                "location": "mode",
                "recommendation": t("use_restart_mode"),
                "fix_available": True,
            })

    async def _check_never_triggered(self) -> None:
        """Check for automations that have never been triggered."""
        t = self._translator.t
        
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
                        "message": t("never_triggered"),
                        "location": "trigger",
                        "recommendation": t("verify_triggers"),
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
