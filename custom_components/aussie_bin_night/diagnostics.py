"""Diagnostics support for Aussie Bin Night."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADDRESS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POSTCODE,
    CONF_STREET,
    CONF_SUBURB,
)
from .coordinator import AussieBinNightConfigEntry

# The household address and its coordinates identify a specific home and are
# redacted. The council/LGA id and the collection schedule itself are not
# household-identifying (they're shared by every home in that collection
# zone) and are kept, since they're what's most useful for diagnosing a
# provider or scheduling problem.
TO_REDACT = {CONF_ADDRESS, CONF_STREET, CONF_SUBURB, CONF_POSTCODE, CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: AussieBinNightConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry with the household address redacted.

    Works for an entry that failed to load too, since that is exactly when a
    diagnostics download is most useful; it then omits the schedule.
    """
    coordinator = getattr(entry, "runtime_data", None)
    schedule = coordinator.data if coordinator is not None else None

    diagnostics: dict[str, Any] = {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "entry_state": str(entry.state),
        "schedule": None,
    }
    if coordinator is not None:
        last_update = coordinator.last_successful_update
        diagnostics["last_update_success"] = coordinator.last_update_success
        diagnostics["serving_stale_schedule"] = coordinator.serving_stale
        diagnostics["last_successful_update"] = last_update.isoformat() if last_update else None
    if schedule is not None:
        diagnostics["schedule"] = {
            "council_id": schedule.council_id,
            "available_bin_types": list(schedule.available_bin_types),
            "events": [
                {"collection_date": event.collection_date.isoformat(), "bin_types": list(event.bin_types)}
                for event in schedule.events
            ],
        }
    return diagnostics
