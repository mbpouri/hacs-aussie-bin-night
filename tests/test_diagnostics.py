"""Tests for diagnostics redaction."""

from unittest.mock import patch

from homeassistant.components.diagnostics import REDACTED
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aussie_bin_night.const import CONF_ADDRESS, CONF_LATITUDE, DOMAIN
from custom_components.aussie_bin_night.coordinator import AussieBinNightCoordinator
from custom_components.aussie_bin_night.diagnostics import async_get_config_entry_diagnostics

from .conftest import SAMPLE_SCHEDULE, FakeBinNightTonightClient, sample_entry_data

CLIENT_PATH = "custom_components.aussie_bin_night.coordinator.BinNightTonightClient"


async def test_diagnostics_redacts_the_household_address(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)):
        coordinator = AussieBinNightCoordinator(hass, entry)
        await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"][CONF_ADDRESS] == REDACTED
    assert diagnostics["entry_data"][CONF_LATITUDE] == REDACTED
    assert diagnostics["schedule"]["council_id"] == SAMPLE_SCHEDULE.council_id
    assert diagnostics["schedule"]["available_bin_types"] == list(SAMPLE_SCHEDULE.available_bin_types)
    assert diagnostics["last_update_success"] is True

    coordinator.async_cancel_reminder_refresh()
