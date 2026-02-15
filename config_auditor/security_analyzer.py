import asyncio
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Regular expressions for sensitive data detection
SECRET_PATTERNS = [
    r"api_key[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?",
    r"password[:=]\s*['\"]?[a-zA-Z0-9_\-]{8,}['\"]?",
    r"token[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}['\"]?",
    r"secret[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?",
]

SENSITIVE_DATA_REGEX = re.compile("|".join(SECRET_PATTERNS), re.IGNORECASE)

class SecurityAnalyzer:
    """Analyze configurations for security vulnerabilities."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the security analyzer."""
        self.hass = hass
        self.issues: list[dict[str, Any]] = []

    async def analyze_all(self, automation_configs: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Run all security checks."""
        self.issues = []
        automation_configs = automation_configs or {}
        
        # 1. Scan for hardcoded secrets in automation configs
        await self._scan_for_hardcoded_secrets(automation_configs)
        
        # 2. Scan for sensitive data exposure in services (notifications, etc)
        await self._scan_for_data_exposure(automation_configs)
        
        _LOGGER.info("Security analysis complete: %d issues found", len(self.issues))
        return self.issues

    async def _scan_for_hardcoded_secrets(self, configs: dict[str, dict[str, Any]]) -> None:
        """Find strings that look like keys/passwords but aren't using !secret."""
        for idx, (entity_id, config) in enumerate(configs.items()):
            config_str = str(config)
            
            # This is a bit simplified as we often get the dict already parsed
            # and !secret values are already resolved or marked.
            # However, if someone typed a raw string, we can detect it.
            
            matches = SENSITIVE_DATA_REGEX.findall(config_str)
            if matches:
                self.issues.append({
                    "entity_id": entity_id,
                    "alias": config.get("alias", entity_id),
                    "type": "hardcoded_secret",
                    "severity": "high",
                    "message": "Potential hardcoded secret or API key detected",
                    "location": "configuration",
                    "recommendation": "Use !secret in secrets.yaml instead of hardcoding sensitive data",
                    "fix_available": False,
                })
            
            if idx % 10 == 0: await asyncio.sleep(0)

    async def _scan_for_data_exposure(self, configs: dict[str, dict[str, Any]]) -> None:
        """Check if sensitive info is being sent to external notification services."""
        for idx_config, (entity_id, config) in enumerate(configs.items()):
            actions = config.get("action", [])
            if not isinstance(actions, list):
                actions = [actions] if actions else []
                
            for idx, action in enumerate(actions):
                service = action.get("service") or action.get("action", "")
                
                # Check for notification services
                if "notify" in service or "persistent_notification" in service:
                    data = action.get("data", {})
                    message = str(data.get("message", ""))
                    
                    if SENSITIVE_DATA_REGEX.search(message):
                        self.issues.append({
                            "entity_id": entity_id,
                            "alias": config.get("alias", entity_id),
                            "type": "sensitive_data_exposure",
                            "severity": "high",
                            "message": f"Action {idx}: Potential exposure of sensitive data in notification",
                            "location": f"action[{idx}]",
                            "recommendation": "Avoid sending secrets or passwords in notification messages",
                            "fix_available": False,
                        })
            
            if idx_config % 10 == 0: await asyncio.sleep(0)

    def get_issue_summary(self) -> dict[str, Any]:
        """Get summary of security issues."""
        return {
            "total": len(self.issues),
            "high_severity": len([i for i in self.issues if i["severity"] == "high"]),
            "types": list(set(i["type"] for i in self.issues))
        }
