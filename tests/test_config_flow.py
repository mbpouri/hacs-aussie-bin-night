"""Tests for the config and reconfigure flows."""

from unittest.mock import patch

from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aussie_bin_night.client import (
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
)
from custom_components.aussie_bin_night.const import CONF_ADDRESS, CONF_BIN_TYPES, CONF_COUNCIL_ID, DOMAIN

from .conftest import SAMPLE_CANDIDATE, SAMPLE_SCHEDULE, FakeBinNightTonightClient, sample_entry_data

CLIENT_PATH = "custom_components.aussie_bin_night.config_flow.BinNightTonightClient"
UNIQUE_ID = f"{SAMPLE_CANDIDATE.latitude:.6f},{SAMPLE_CANDIDATE.longitude:.6f}"


async def _run_happy_path(hass, *, context):
    fake_client = FakeBinNightTonightClient(candidates=[SAMPLE_CANDIDATE], schedule=SAMPLE_SCHEDULE)
    with patch(CLIENT_PATH, return_value=fake_client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context=context)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "1 example street"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "0"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"bin_types": ["general", "recycling"]}
        )
    return result


async def test_full_setup_flow_creates_entry(hass):
    result = await _run_happy_path(hass, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == "create_entry"
    assert result["title"] == SAMPLE_CANDIDATE.display_name
    assert result["data"][CONF_ADDRESS] == SAMPLE_CANDIDATE.display_name
    assert result["data"][CONF_COUNCIL_ID] == SAMPLE_SCHEDULE.council_id
    assert result["data"][CONF_BIN_TYPES] == ["general", "recycling"]


async def test_no_addresses_found_shows_error(hass):
    fake_client = FakeBinNightTonightClient(candidates=[])
    with patch(CLIENT_PATH, return_value=fake_client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "nowhere"})

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_addresses_found"}


async def test_search_connection_error_shows_error(hass):
    fake_client = FakeBinNightTonightClient(search_exc=BinNightTonightConnectionError("boom"))
    with patch(CLIENT_PATH, return_value=fake_client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "anywhere"})

    assert result["errors"] == {"base": "cannot_connect"}


async def test_search_rate_limited_shows_error(hass):
    fake_client = FakeBinNightTonightClient(search_exc=BinNightTonightRateLimitedError("slow down"))
    with patch(CLIENT_PATH, return_value=fake_client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "anywhere"})

    assert result["errors"] == {"base": "rate_limited"}


async def test_no_collections_found_shows_error(hass):
    empty_schedule = SAMPLE_SCHEDULE.__class__(council_id="sample-city-council", events=())
    fake_client = FakeBinNightTonightClient(candidates=[SAMPLE_CANDIDATE], schedule=empty_schedule)
    with patch(CLIENT_PATH, return_value=fake_client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "1 example street"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "0"})

    assert result["step_id"] == "select_address"
    assert result["errors"] == {"base": "no_collections_found"}


async def test_schedule_invalid_response_shows_error(hass):
    fake_client = FakeBinNightTonightClient(
        candidates=[SAMPLE_CANDIDATE],
        schedule_exc=BinNightTonightInvalidResponseError("bad payload"),
    )
    with patch(CLIENT_PATH, return_value=fake_client):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "1 example street"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "0"})

    assert result["errors"] == {"base": "invalid_response"}


async def test_duplicate_address_aborts(hass):
    existing = MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=sample_entry_data())
    existing.add_to_hass(hass)

    result = await _run_happy_path(hass, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_the_existing_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="-38.000000,145.000000", data=sample_entry_data(address="Old Address")
    )
    entry.add_to_hass(hass)

    result = await _run_happy_path(
        hass,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ADDRESS] == SAMPLE_CANDIDATE.display_name
    assert entry.unique_id == UNIQUE_ID


async def test_reconfigure_step_defaults_to_current_address(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="-38.000000,145.000000", data=sample_entry_data(address="Old Address")
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )

    assert result["step_id"] == "reconfigure"
    assert result["data_schema"]({})[CONF_ADDRESS] == "Old Address"


async def test_reconfigure_to_address_used_by_another_entry_aborts(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID, data=sample_entry_data()).add_to_hass(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="-38.000000,145.000000", data=sample_entry_data(address="Old Address")
    )
    entry.add_to_hass(hass)

    result = await _run_happy_path(
        hass,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_ADDRESS] == "Old Address"
