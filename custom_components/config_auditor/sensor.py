"""Sensor platform for H.A.C.A."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up H.A.C.A sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    sensors = [
        HACAHealthScoreSensor(coordinator, entry),
        HACAAutomationIssuesSensor(coordinator, entry),
        HACAEntityIssuesSensor(coordinator, entry),
        HACAPerformanceIssuesSensor(coordinator, entry),
        HACATotalIssuesSensor(coordinator, entry),
    ]
    
    async_add_entities(sensors)


class HACASensorBase(CoordinatorEntity, SensorEntity):
    """Base class for H.A.C.A sensors."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": NAME,
            "manufacturer": "Community",
            "model": "Config Auditor",
        }


class HACAHealthScoreSensor(HACASensorBase):
    """Sensor for health score."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_health_score"
        self._attr_name = "Health Score"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:heart-pulse"

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        if self.coordinator.data:
            return self.coordinator.data.get("health_score")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        
        score = self.coordinator.data.get("health_score", 0)
        
        if score >= 90:
            status = "excellent"
            color = "green"
        elif score >= 75:
            status = "good"
            color = "blue"
        elif score >= 60:
            status = "fair"
            color = "yellow"
        elif score >= 40:
            status = "poor"
            color = "orange"
        else:
            status = "critical"
            color = "red"
        
        return {
            "status": status,
            "color": color,
        }


class HACAAutomationIssuesSensor(HACASensorBase):
    """Sensor for automation issues."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_automation_issues"
        self._attr_name = "Automation Issues"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:robot"

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        if self.coordinator.data:
            return self.coordinator.data.get("automation_issues", 0)
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        
        return {
            "automation_issue_list": self.coordinator.data.get("automation_issue_list", [])
        }



class HACAEntityIssuesSensor(HACASensorBase):
    """Sensor for entity issues."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_entity_issues"
        self._attr_name = "Entity Issues"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:alert-circle"

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        if self.coordinator.data:
            return self.coordinator.data.get("entity_issues", 0)
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        
        return {
            "entity_issue_list": self.coordinator.data.get("entity_issue_list", [])
        }



class HACAPerformanceIssuesSensor(HACASensorBase):
    """Sensor for performance issues."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_performance_issues"
        self._attr_name = "Performance Issues"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:speedometer"

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        if self.coordinator.data:
            return self.coordinator.data.get("performance_issues", 0)
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        if not self.coordinator.data:
            return {}
        
        return {
            "performance_issue_list": self.coordinator.data.get("performance_issue_list", [])
        }



class HACATotalIssuesSensor(HACASensorBase):
    """Sensor for total issues."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_total_issues"
        self._attr_name = "Total Issues"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        if self.coordinator.data:
            return self.coordinator.data.get("total_issues", 0)
        return None
