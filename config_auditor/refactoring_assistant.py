"""Refactoring Assistant for H.A.C.A v1.2.0 - Module 5."""
from __future__ import annotations

from datetime import datetime
import logging
import re
from pathlib import Path
from typing import Any
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import BACKUP_DIR

_LOGGER = logging.getLogger(__name__)


class RefactoringAssistant:
    """Assistant for automated refactoring with preview and backup."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize refactoring assistant."""
        self.hass = hass
        self._backup_dir = Path(hass.config.config_dir) / BACKUP_DIR
        self._backup_dir.mkdir(exist_ok=True)
        self._automations_file = Path(hass.config.config_dir) / "automations.yaml"

    async def preview_device_id_fix(self, automation_id: str) -> dict[str, Any]:
        """Preview device_id to entity_id conversion without applying."""
        
        # Load automation config
        automation_config = await self._load_automation_by_id(automation_id)
        
        if not automation_config:
            return {
                "success": False,
                "error": f"Automation {automation_id} not found"
            }
        
        changes = []
        
        # --- TRIGGERS ---
        trigger_key = "triggers" if "triggers" in automation_config else "trigger"
        triggers = automation_config.get(trigger_key, [])
        if not isinstance(triggers, list):
            triggers = [triggers] if triggers else []
        
        for idx, trigger in enumerate(triggers):
            if not isinstance(trigger, dict):
                continue
            if "device_id" not in trigger:
                continue
                
            device_id = trigger["device_id"]
            domain = trigger.get("domain", "")
            trigger_type = trigger.get("type", "")
            _LOGGER.info("Trigger %d: device_id=%s, domain=%s, type=%s", idx, device_id, domain, trigger_type)
            
            # Resolve entity_id (HA stores UUID registry IDs, not actual entity_id strings)
            resolved_entity = await self._resolve_entity_id(
                device_id, trigger.get("entity_id"), domain
            )
            
            if resolved_entity:
                # Build native state trigger
                new_trigger = {
                    "platform": "state",
                    "entity_id": resolved_entity,
                }
                
                # Map device trigger types to state values
                type_to_state = {
                    "turned_on": "on", "turned on": "on",
                    "turned_off": "off", "turned off": "off",
                    "motion": "on", "occupied": "on", "not_occupied": "off",
                    "opened": "on", "closed": "off",
                    "detected": "on", "not_detected": "off",
                    "connected": "on", "disconnected": "off",
                }
                if trigger_type in type_to_state:
                    new_trigger["to"] = type_to_state[trigger_type]
                
                changes.append({
                    "section": "trigger",
                    "index": idx,
                    "to": new_trigger,
                    "description": f"Trigger {idx}: {domain}.{trigger_type} → platform: state, entity_id: {resolved_entity}"
                })
            else:
                _LOGGER.warning("Cannot resolve entity for trigger %d (device_id=%s)", idx, device_id)
        
        # --- CONDITIONS ---
        condition_key = "conditions" if "conditions" in automation_config else "condition"
        conditions = automation_config.get(condition_key, [])
        if not isinstance(conditions, list):
            conditions = [conditions] if conditions else []
        
        for idx, condition in enumerate(conditions):
            if not isinstance(condition, dict):
                continue
            if "device_id" not in condition:
                continue
                
            device_id = condition["device_id"]
            domain = condition.get("domain", "")
            cond_type = condition.get("type", "")
            _LOGGER.info("Condition %d: device_id=%s, domain=%s, type=%s", idx, device_id, domain, cond_type)
            
            resolved_entity = await self._resolve_entity_id(
                device_id, condition.get("entity_id"), domain
            )
            
            if resolved_entity:
                # Map device condition types to native conditions
                if cond_type.startswith("is_") and domain == "sensor":
                    # is_illuminance, is_temperature, is_humidity → numeric_state
                    new_condition = {
                        "condition": "numeric_state",
                        "entity_id": resolved_entity,
                    }
                    # Preserve threshold values
                    if "below" in condition:
                        new_condition["below"] = condition["below"]
                    if "above" in condition:
                        new_condition["above"] = condition["above"]
                else:
                    # Generic device condition → state condition
                    new_condition = {
                        "condition": "state",
                        "entity_id": resolved_entity,
                    }
                    # Map type to expected state
                    if cond_type in ("is_on",):
                        new_condition["state"] = "on"
                    elif cond_type in ("is_off",):
                        new_condition["state"] = "off"
                
                changes.append({
                    "section": "condition",
                    "index": idx,
                    "to": new_condition,
                    "description": f"Condition {idx}: {domain}.{cond_type} → {new_condition['condition']}, entity_id: {resolved_entity}"
                })
            else:
                _LOGGER.warning("Cannot resolve entity for condition %d (device_id=%s)", idx, device_id)
        
        # --- ACTIONS ---
        action_key = "actions" if "actions" in automation_config else "action"
        actions = automation_config.get(action_key, [])
        if not isinstance(actions, list):
            actions = [actions] if actions else []
        
        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            if "device_id" not in action:
                continue
                
            device_id = action["device_id"]
            domain = action.get("domain", "homeassistant")
            action_type = action.get("type", "toggle")
            _LOGGER.info("Action %d: device_id=%s, domain=%s, type=%s", idx, device_id, domain, action_type)
            
            resolved_entity = await self._resolve_entity_id(
                device_id, action.get("entity_id"), domain
            )
            
            if resolved_entity:
                service = f"{domain}.{action_type}"
                new_action = {
                    "action": service,
                    "target": {"entity_id": resolved_entity}
                }
                if "data" in action:
                    new_action["data"] = action["data"]
                
                changes.append({
                    "section": "action",
                    "index": idx,
                    "to": new_action,
                    "description": f"Action {idx}: {service} → entity_id: {resolved_entity}"
                })
            else:
                _LOGGER.warning("Cannot resolve entity for action %d (device_id=%s)", idx, device_id)
        
        # --- Generate YAML previews ---
        import copy
        current_yaml = yaml.dump(automation_config, default_flow_style=False, allow_unicode=True)
        
        new_config = copy.deepcopy(automation_config)
        
        # Apply all changes to the deep copy
        for change in changes:
            section = change["section"]
            idx = change["index"]
            
            if section == "trigger":
                key = trigger_key
            elif section == "condition":
                key = condition_key
            elif section == "action":
                key = action_key
            else:
                continue
            
            items = new_config.get(key, [])
            if not isinstance(items, list):
                items = [items] if items else []
            if idx < len(items):
                items[idx] = change["to"]
            new_config[key] = items
        
        new_yaml = yaml.dump(new_config, default_flow_style=False, allow_unicode=True)
        
        return {
            "success": True,
            "automation_id": automation_id,
            "alias": automation_config.get("alias", ""),
            "changes": changes,
            "changes_count": len(changes),
            "current_yaml": current_yaml,
            "new_yaml": new_yaml
        }

    async def apply_device_id_fix(self, automation_id: str, preview: dict = None, dry_run: bool = False) -> dict[str, Any]:
        """Apply device_id to entity_id conversion with backup."""
        
        # Get preview if not provided
        if not preview:
            preview = await self.preview_device_id_fix(automation_id)
        
        if not preview.get("success"):
            return preview
        
        if not preview.get("changes"):
            return {
                "success": False,
                "error": "No changes to apply"
            }
            
        if dry_run:
            return {
                "success": True,
                "automation_id": automation_id,
                "changes_applied": 0,
                "dry_run": True,
                "preview": preview,
                "message": "Dry run complete. No changes applied."
            }
        
        # Create backup
        backup_path = await self._create_backup()
        
        try:
            # Load all automations
            def read_automations():
                with open(self._automations_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or []
            
            automations = await self.hass.async_add_executor_job(read_automations)
            
            # Find and modify the automation
            for automation in automations:
                if automation.get("id") == automation_id:
                    
                    # Apply changes per section
                    for change in preview["changes"]:
                        section = change["section"]
                        idx = change["index"]
                        
                        # Detect correct key for each section
                        if section == "trigger":
                            key = "triggers" if "triggers" in automation else "trigger"
                        elif section == "condition":
                            key = "conditions" if "conditions" in automation else "condition"
                        elif section == "action":
                            key = "actions" if "actions" in automation else "action"
                        else:
                            continue
                        
                        items = automation.get(key, [])
                        if not isinstance(items, list):
                            items = [items] if items else []
                        if idx < len(items):
                            items[idx] = change["to"]
                        automation[key] = items
                    
                    break
            
            # Save modified automations
            def write_automations():
                with open(self._automations_file, "w", encoding="utf-8") as f:
                    yaml.dump(automations, f, default_flow_style=False, allow_unicode=True)
            
            await self.hass.async_add_executor_job(write_automations)
            
            return {
                "success": True,
                "automation_id": automation_id,
                "changes_applied": len(preview["changes"]),
                "backup_path": str(backup_path),
                "message": "Changes applied successfully. Restart Home Assistant to apply."
            }
            
        except Exception as e:
            _LOGGER.error("Error applying fixes: %s", e)
            return {
                "success": False,
                "error": str(e),
                "backup_path": str(backup_path)
            }

    async def preview_mode_fix(self, automation_id: str, new_mode: str) -> dict[str, Any]:
        """Preview automation mode change."""
        
        valid_modes = ["single", "restart", "queued", "parallel"]
        if new_mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid mode. Must be one of: {valid_modes}"
            }
        
        automation_config = await self._load_automation_by_id(automation_id)
        
        if not automation_config:
            return {
                "success": False,
                "error": f"Automation {automation_id} not found"
            }
        
        current_mode = automation_config.get("mode", "single")
        
        changes = [{
            "field": "mode",
            "from": current_mode,
            "to": new_mode,
            "description": f"Change mode from '{current_mode}' to '{new_mode}'"
        }]
        
        # Add max parameter for queued/parallel
        if new_mode in ["queued", "parallel"]:
            if "max" not in automation_config:
                changes.append({
                    "field": "max",
                    "from": None,
                    "to": 10,
                    "description": "Add max parameter (default: 10)"
                })
        
        # Generate YAML previews
        import copy
        current_yaml = yaml.dump(automation_config, default_flow_style=False, allow_unicode=True)
        
        # Create a deep copy to apply changes for preview
        new_config = copy.deepcopy(automation_config)
        new_config["mode"] = new_mode
        
        if new_mode in ["queued", "parallel"]:
            if "max" not in new_config:
                new_config["max"] = 10
                
        new_yaml = yaml.dump(new_config, default_flow_style=False, allow_unicode=True)
        
        return {
            "success": True,
            "automation_id": automation_id,
            "alias": automation_config.get("alias", ""),
            "changes": changes,
            "changes_count": len(changes),
            "current_yaml": current_yaml,
            "new_yaml": new_yaml
        }

    async def apply_mode_fix(self, automation_id: str, new_mode: str, dry_run: bool = False) -> dict[str, Any]:
        """Apply automation mode change with backup."""
        
        preview = await self.preview_mode_fix(automation_id, new_mode)
        
        if not preview.get("success"):
            return preview

        if dry_run:
            return {
                "success": True,
                "automation_id": automation_id,
                "new_mode": new_mode,
                "dry_run": True,
                "preview": preview,
                "message": "Dry run complete. No changes applied."
            }
        
        backup_path = await self._create_backup()
        
        try:
            def read_automations():
                with open(self._automations_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or []
            
            automations = await self.hass.async_add_executor_job(read_automations)
            
            for automation in automations:
                if automation.get("id") == automation_id:
                    automation["mode"] = new_mode
                    
                    if new_mode in ["queued", "parallel"]:
                        if "max" not in automation:
                            automation["max"] = 10
                    
                    break
            
            def write_automations():
                with open(self._automations_file, "w", encoding="utf-8") as f:
                    yaml.dump(automations, f, default_flow_style=False, allow_unicode=True)
            
            await self.hass.async_add_executor_job(write_automations)
            
            return {
                "success": True,
                "automation_id": automation_id,
                "new_mode": new_mode,
                "backup_path": str(backup_path),
                "message": "Mode changed successfully. Restart Home Assistant to apply."
            }
            
        except Exception as e:
            _LOGGER.error("Error changing mode: %s", e)
            return {
                "success": False,
                "error": str(e),
                "backup_path": str(backup_path)
            }

    async def preview_template_fix(self, automation_id: str) -> dict[str, Any]:
        """Preview template to native condition conversion."""
        automation_config = await self._load_automation_by_id(automation_id)
        
        if not automation_config:
            return {"success": False, "error": f"Automation {automation_id} not found"}
            
        changes = []
        
        # Check conditions
        condition_key = "conditions" if "conditions" in automation_config else "condition"
        conditions = automation_config.get(condition_key, [])
        if not isinstance(conditions, list):
            conditions = [conditions] if conditions else []
            
        for idx, condition in enumerate(conditions):
            if not isinstance(condition, dict) or condition.get("condition") != "template":
                continue
                
            template = condition.get("value_template", "")
            parsed = self._parse_is_state_template(template)
            
            if parsed:
                new_condition = {
                    "condition": "state",
                    "entity_id": parsed["entity_id"],
                    "state": parsed["state"]
                }
                
                changes.append({
                    "section": "condition",
                    "index": idx,
                    "to": new_condition,
                    "description": f"Condition {idx}: Template → state condition ({parsed['entity_id']} is {parsed['state']})"
                })

        if not changes:
            return {"success": False, "error": "No simple template conditions found to fix"}

        # Generate YAML previews
        import copy
        current_yaml = yaml.dump(automation_config, default_flow_style=False, allow_unicode=True)
        new_config = copy.deepcopy(automation_config)
        
        for change in changes:
            idx = change["index"]
            items = new_config.get(condition_key, [])
            if idx < len(items):
                items[idx] = change["to"]
                
        new_yaml = yaml.dump(new_config, default_flow_style=False, allow_unicode=True)
        
        return {
            "success": True,
            "automation_id": automation_id,
            "alias": automation_config.get("alias", ""),
            "changes": changes,
            "changes_count": len(changes),
            "current_yaml": current_yaml,
            "new_yaml": new_yaml
        }

    async def apply_template_fix(self, automation_id: str, dry_run: bool = False) -> dict[str, Any]:
        """Apply template fix with backup."""
        preview = await self.preview_template_fix(automation_id)
        if not preview.get("success"):
            return preview

        if dry_run:
            return {
                "success": True,
                "automation_id": automation_id,
                "dry_run": True,
                "preview": preview,
                "message": "Dry run complete."
            }
            
        backup_path = await self._create_backup()
        
        try:
            def read_automations():
                with open(self._automations_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or []
            
            automations = await self.hass.async_add_executor_job(read_automations)
            
            for automation in automations:
                if automation.get("id") == automation_id:
                    cond_key = "conditions" if "conditions" in automation else "condition"
                    items = automation.get(cond_key, [])
                    if not isinstance(items, list):
                        items = [items] if items else []
                        
                    for change in preview["changes"]:
                        idx = change["index"]
                        if idx < len(items):
                            items[idx] = change["to"]
                    automation[cond_key] = items
                    break
            
            def write_automations():
                with open(self._automations_file, "w", encoding="utf-8") as f:
                    yaml.dump(automations, f, default_flow_style=False, allow_unicode=True)
            
            await self.hass.async_add_executor_job(write_automations)
            
            return {
                "success": True,
                "automation_id": automation_id,
                "changes_applied": len(preview["changes"]),
                "backup_path": str(backup_path),
                "message": "Template fix applied successfully."
            }
        except Exception as e:
            _LOGGER.error("Error applying template fix: %s", e)
            return {"success": False, "error": str(e), "backup_path": str(backup_path)}

    def _parse_is_state_template(self, template: str) -> dict[str, str] | None:
        """Parse is_state('entity', 'state') from template string."""
        # Regex to match is_state('...', '...') or is_state("...", "...")
        # Supports optional spaces and different quote types
        pattern = r"is_state\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
        match = re.search(pattern, template)
        
        if match:
            return {
                "entity_id": match.group(1),
                "state": match.group(2)
            }
        return None

    async def list_backups(self) -> list[dict]:
        """List available backups."""
        
        if not self._backup_dir.exists():
            _LOGGER.debug("Backup directory does not exist: %s", self._backup_dir)
            return []
            
        def _scan_backups():
            results = []
            try:
                _LOGGER.debug("Scanning backups in: %s", self._backup_dir)
                for entry in self._backup_dir.iterdir():
                    if entry.is_file() and entry.name.startswith("automations_") and entry.name.endswith(".yaml"):
                        try:
                            stat = entry.stat()
                            results.append({
                                "path": str(entry.absolute()),
                                "name": entry.name,
                                "size": stat.st_size,
                                "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
                            })
                        except Exception as err:
                            _LOGGER.warning("Error reading backup file %s: %s", entry.name, err)
                            
                # Sort by reverse chronological order (newest first) based on created timestamp
                results.sort(key=lambda x: x["created"], reverse=True)
                return results[:10]
                
            except Exception as err:
                _LOGGER.error("Error scanning backup directory: %s", err)
                return []

        try:
            return await self.hass.async_add_executor_job(_scan_backups)
        except Exception as e:
            _LOGGER.error("Error listing backups: %s", e)
            return []

    async def restore_backup(self, backup_path: str) -> dict[str, Any]:
        """Restore automations from backup."""
        
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            return {
                "success": False,
                "error": "Backup file not found"
            }
        
        try:
            # Create backup of current state before restore
            pre_restore_backup = await self._create_backup()
            
            # Copy backup to automations.yaml
            def restore():
                import shutil
                shutil.copy2(backup_file, self._automations_file)
            
            await self.hass.async_add_executor_job(restore)
            
            return {
                "success": True,
                "restored_from": str(backup_file),
                "backup_before_restore": str(pre_restore_backup),
                "message": "Backup restored. Restart Home Assistant to apply."
            }
            
        except Exception as e:
            _LOGGER.error("Error restoring backup: %s", e)
            return {
                "success": False,
                "error": str(e)
            }

    async def create_backup(self) -> dict[str, Any]:
        """Create a manual backup."""
        try:
            backup_path = await self._create_backup()
            return {
                "success": True,
                "backup_path": str(backup_path),
                "message": f"Backup created: {backup_path.name}"
            }
        except Exception as e:
            _LOGGER.error("Error creating backup: %s", e)
            return {
                "success": False,
                "error": str(e)
            }

    async def _create_backup(self) -> Path:
        """Create backup of automations.yaml."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self._backup_dir / f"automations_{timestamp}.yaml"
        
        def create_backup():
            import shutil
            shutil.copy2(self._automations_file, backup_file)
        
        await self.hass.async_add_executor_job(create_backup)
        
        # Cleanup old backups (keep last 10)
        await self._cleanup_old_backups()
        
        _LOGGER.info("Created backup: %s", backup_file)
        return backup_file

    async def _cleanup_old_backups(self):
        """Keep only the last 10 backups."""
        backups = sorted(self._backup_dir.glob("automations_*.yaml"), reverse=True)
        
        for old_backup in backups[10:]:
            try:
                old_backup.unlink()
                _LOGGER.debug("Deleted old backup: %s", old_backup)
            except Exception as e:
                _LOGGER.warning("Failed to delete old backup %s: %s", old_backup, e)

    async def _load_automation_by_id(self, automation_id: str) -> dict | None:
        """Load a specific automation configuration."""
        
        def read_automations():
            with open(self._automations_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or []
        
        try:
            automations = await self.hass.async_add_executor_job(read_automations)
            
            for automation in automations:
                if automation.get("id") == automation_id:
                    return automation
            
            return None
            
        except Exception as e:
            _LOGGER.error("Error loading automation: %s", e)
            return None

    async def _get_entities_for_device(self, device_id: str) -> list[str]:
        """Get entity IDs for a device."""
        entity_reg = er.async_get(self.hass)
        
        entities = []
        for entity in entity_reg.entities.values():
            if entity.device_id == device_id:
                entities.append(entity.entity_id)
        
        return entities

    async def _resolve_entity_id(self, device_id: str, registry_uuid: str | None, domain: str = "") -> str | None:
        """Resolve an entity from device_id + registry UUID + domain.
        
        HA device automations store entity references as UUID registry entry IDs,
        not as human-readable entity_id strings. This method resolves to the actual
        entity_id string using a 3-step approach:
        1. Try to find the entity by its UUID in the entity registry
        2. Filter device entities by domain to pick the correct one
        3. Fallback to any entity for the device
        """
        entity_reg = er.async_get(self.hass)
        
        # Step 1: Try to resolve UUID → entity_id
        if registry_uuid:
            # Check if it's already a real entity_id (contains a dot like "binary_sensor.xxx")
            if "." in registry_uuid:
                return registry_uuid
            
            # It's a UUID — look it up in the registry
            for entity in entity_reg.entities.values():
                if entity.id == registry_uuid:
                    _LOGGER.info("Resolved UUID %s → %s", registry_uuid, entity.entity_id)
                    return entity.entity_id
            
            _LOGGER.warning("UUID %s not found in entity registry", registry_uuid)
        
        # Step 2: Get all entities for this device, filter by domain
        all_entities = await self._get_entities_for_device(device_id)
        
        if not all_entities:
            _LOGGER.warning("No entities found for device_id %s", device_id)
            return None
        
        if domain:
            # Filter by domain (e.g., "binary_sensor", "sensor", "light")
            domain_entities = [e for e in all_entities if e.startswith(f"{domain}.")]
            if domain_entities:
                _LOGGER.info("Resolved device %s + domain %s → %s", device_id, domain, domain_entities[0])
                return domain_entities[0]
        
        # Step 3: Fallback to first entity
        _LOGGER.info("Fallback: using first entity for device %s → %s", device_id, all_entities[0])
        return all_entities[0]
