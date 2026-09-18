"""Aussie Bin Night integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, STATIC_URL
from .coordinator import ISSUE_INVALID_RESPONSE, ISSUE_UNSUPPORTED_ADDRESS, AussieBinNightCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aussie Bin Night from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("static_path_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "static"), False)]
        )
        domain_data["static_path_registered"] = True

    coordinator = AussieBinNightCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    domain_data[entry.entry_id] = coordinator
    entry.async_on_unload(coordinator.async_cancel_reminder_refresh)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Aussie Bin Night config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        for issue_key in (ISSUE_INVALID_RESPONSE, ISSUE_UNSUPPORTED_ADDRESS):
            ir.async_delete_issue(hass, DOMAIN, f"{issue_key}_{entry.entry_id}")
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after the user changes its options."""
    await hass.config_entries.async_reload(entry.entry_id)
