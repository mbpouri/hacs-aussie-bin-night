"""Bin collection sensors for Aussie Bin Night."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import AussieBinNightCoordinator
from .const import (
    CONF_ADDRESS,
    CONF_BIN_TYPES,
    CONF_REMINDER_LEAD_TIME,
    DEFAULT_REMINDER_LEAD_TIME_HOURS,
    DOMAIN,
)

ATTR_COLLECTION_DATE = "collection_date"
ATTR_COUNCIL = "council"
ATTR_DAYS_UNTIL = "days_until"
ATTR_BIN_COLOUR = "bin_colour"
ATTR_FOLLOWING_COLLECTION_DATE = "following_collection_date"
ATTR_REMINDER_TIME = "reminder_time"

BIN_COLOURS = {
    "general": "red",
    "recycling": "yellow",
    "garden": "dark green",
    "fogo": "lime green",
    "glass": "purple",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add collection-date sensors for the configured bin streams."""
    coordinator: AussieBinNightCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        BinCollectionSensor(coordinator, entry, bin_type)
        for bin_type in entry.options.get(CONF_BIN_TYPES, entry.data[CONF_BIN_TYPES])
    )


class BinCollectionSensor(CoordinatorEntity[AussieBinNightCoordinator], SensorEntity):
    """Represent the next collection date for one bin stream."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: AussieBinNightCoordinator,
        entry: ConfigEntry,
        bin_type: str,
    ) -> None:
        """Initialize a bin collection sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._bin_type = bin_type
        self._attr_unique_id = f"{entry.entry_id}_{bin_type}"
        self.entity_id = f"sensor.bin_{bin_type}"
        self._attr_translation_key = "collection"
        self._attr_translation_placeholders = {"bin_type": bin_type.replace("_", " ").title()}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_ADDRESS],
            manufacturer="Bin Night Tonight",
            model="Household bin collection schedule",
        )

    @property
    def native_value(self) -> date | None:
        """Return the next collection date for this bin type."""
        event = self._next_event
        return event.collection_date if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return stable automation and display attributes."""
        event = self._next_event
        attributes: dict[str, Any] = {
            ATTR_ATTRIBUTION: "Data provided by Bin Night Tonight",
            ATTR_COUNCIL: self.coordinator.data.council_id,
        }
        if event:
            attributes[ATTR_COLLECTION_DATE] = event.collection_date.isoformat()
            attributes[ATTR_DAYS_UNTIL] = (event.collection_date - self._today).days
            lead_hours = int(
                self._entry.options.get(CONF_REMINDER_LEAD_TIME, DEFAULT_REMINDER_LEAD_TIME_HOURS)
            )
            collection_start = dt_util.start_of_local_day(event.collection_date)
            attributes[ATTR_REMINDER_TIME] = (collection_start - timedelta(hours=lead_hours)).isoformat()
            following_event = next(
                (
                    candidate
                    for candidate in self.coordinator.data.events
                    if candidate.collection_date > event.collection_date
                    and self._bin_type in candidate.bin_types
                ),
                None,
            )
            if following_event:
                attributes[ATTR_FOLLOWING_COLLECTION_DATE] = following_event.collection_date.isoformat()
        if colour := BIN_COLOURS.get(self._bin_type):
            attributes[ATTR_BIN_COLOUR] = colour
        return attributes

    @property
    def _next_event(self):
        """Return the first future or current event containing this stream."""
        return next(
            (
                event
                for event in self.coordinator.data.events
                if event.collection_date >= self._today and self._bin_type in event.bin_types
            ),
            None,
        )

    @property
    def _today(self) -> date:
        """Return the current date in the configured Home Assistant timezone."""
        return dt_util.now().date()
