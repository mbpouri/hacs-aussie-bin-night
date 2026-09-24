"""Aussie Bin Night integration."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, STATIC_URL
from .coordinator import ISSUE_KEYS, AussieBinNightConfigEntry, AussieBinNightCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AussieBinNightConfigEntry) -> bool:
    """Set up Aussie Bin Night from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("static_path_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "static"), False)]
        )
        # Load the card on every dashboard so it shows up in the card picker without
        # a manual resource entry. The query string is a hash of the file itself, so
        # browsers refetch it whenever it changes, even within one integration version.
        card = Path(__file__).parent / "static" / "bin-night-card.js"
        digest = await hass.async_add_executor_job(lambda: hashlib.sha256(card.read_bytes()).hexdigest()[:12])
        add_extra_js_url(hass, f"{STATIC_URL}/bin-night-card.js?v={digest}")
        domain_data["static_path_registered"] = True

    coordinator = AussieBinNightCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_cancel_extra_refresh)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AussieBinNightConfigEntry) -> bool:
    """Unload an Aussie Bin Night config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        for issue_key in ISSUE_KEYS:
            ir.async_delete_issue(hass, DOMAIN, f"{issue_key}_{entry.entry_id}")
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: AussieBinNightConfigEntry) -> None:
    """Reload the integration after the user changes its options."""
    await hass.config_entries.async_reload(entry.entry_id)
