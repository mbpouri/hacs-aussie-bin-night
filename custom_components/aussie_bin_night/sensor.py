"""Bin collection sensors for Aussie Bin Night.

Entity attribute contract for `sensor.bin_<bin_type>` (relied on by the bundled
`bin-night-card.js`, which reads only entity state/attributes and never calls
the Bin Night Tonight API itself; keep the two in sync if this contract changes):

- State: an ISO date (`SensorDeviceClass.DATE`) for the next collection, or
  `unknown` if the schedule currently has no upcoming event for this stream.
  The entity is `unavailable` only when the last coordinator refresh failed
  (connection, rate limit, or malformed response), never for a merely empty
  schedule.
- `collection_date` (str, ISO date): present only alongside a non-`unknown` state;
  duplicates the native value for template convenience.
- `days_until` (int): present only alongside a non-`unknown` state.
- `reminder_time` (str, ISO datetime, local timezone): present only alongside a
  non-`unknown` state; the configured reminder lead time before the start of
  `collection_date`.
- `following_collection_date` (str, ISO date, optional): the collection after
  the current one, when the schedule includes it.
- `council` (str): readable council name, e.g. "Sample City Council"; always present.
- `council_id` (str): the provider's raw LGA id, e.g. "sample-city-council"; always present.
- `bin_colour` (str, optional): present only for bin types with a known colour.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
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
ATTR_COUNCIL_ID = "council_id"
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

    async def async_added_to_hass(self) -> None:
        """Re-evaluate at local midnight so the date and `days_until` roll over daily.

        The coordinator only refreshes about weekly, but this sensor's state is
        derived from today's date, so it must be rewritten each day without
        another provider request.
        """
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._async_handle_midnight, hour=0, minute=0, second=0)
        )

    @callback
    def _async_handle_midnight(self, _now: datetime) -> None:
        """Write the state again now that the local date has changed."""
        self.async_write_ha_state()

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
            ATTR_COUNCIL: self.coordinator.data.council_name,
            ATTR_COUNCIL_ID: self.coordinator.data.council_id,
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
