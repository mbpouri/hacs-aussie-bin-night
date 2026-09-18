"""Diagnostics support for Aussie Bin Night."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADDRESS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POSTCODE,
    CONF_STREET,
    CONF_SUBURB,
    DOMAIN,
)
from .coordinator import AussieBinNightCoordinator

# The household address and its coordinates identify a specific home and are
# redacted. The council/LGA id and the collection schedule itself are not
# household-identifying (they're shared by every home in that collection
# zone) and are kept, since they're what's most useful for diagnosing a
# provider or scheduling problem.
TO_REDACT = {CONF_ADDRESS, CONF_STREET, CONF_SUBURB, CONF_POSTCODE, CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry with the household address redacted."""
    coordinator: AussieBinNightCoordinator = hass.data[DOMAIN][entry.entry_id]
    schedule = coordinator.data

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "schedule": {
            "council_id": schedule.council_id,
            "available_bin_types": list(schedule.available_bin_types),
            "events": [
                {"collection_date": event.collection_date.isoformat(), "bin_types": list(event.bin_types)}
                for event in schedule.events
            ],
        },
    }
