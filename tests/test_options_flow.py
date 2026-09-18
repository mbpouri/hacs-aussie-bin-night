"""Tests for the options flow.

This is also a regression test for a real bug: the options flow used to
reference CONF_UPDATE_INTERVAL/CONF_REMINDER_LEAD_TIME without importing them,
which raised a NameError the instant a user opened "Configure".
"""

from custom_components.aussie_bin_night.const import CONF_BIN_TYPES, CONF_REMINDER_LEAD_TIME, CONF_UPDATE_INTERVAL, DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import sample_entry_data


async def test_options_flow_shows_a_form_with_defaults(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"


async def test_options_flow_saves_the_chosen_values(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(), options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: 3,
            CONF_REMINDER_LEAD_TIME: 6,
            CONF_BIN_TYPES: ["general"],
        },
    )

    assert result["type"] == "create_entry"
    assert entry.options[CONF_UPDATE_INTERVAL] == 3
    assert entry.options[CONF_REMINDER_LEAD_TIME] == 6
    assert entry.options[CONF_BIN_TYPES] == ["general"]
