"""Tests for integration setup: how the bundled card is served and loaded."""

import re
from unittest.mock import patch

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aussie_bin_night.const import DOMAIN, STATIC_URL
from custom_components.aussie_bin_night.coordinator import ISSUE_KEYS

from .conftest import SAMPLE_SCHEDULE, FakeBinNightTonightClient, sample_entry_data

CLIENT_PATH = "custom_components.aussie_bin_night.coordinator.BinNightTonightClient"
EXTRA_JS_PATH = "custom_components.aussie_bin_night.add_extra_js_url"

# Home Assistant's service worker serves anything matching this from its cache and ignores
# the query string, so a card under such a path can never be refreshed with "?v=<hash>".
# Copied from the service worker Home Assistant ships (registerRoute with ignoreSearch).
SERVICE_WORKER_CACHED_ASSET = re.compile(r"/(static|frontend_latest|frontend_es5)/.+")


def test_the_card_url_is_not_one_the_service_worker_caches_forever():
    assert not SERVICE_WORKER_CACHED_ASSET.search(f"{STATIC_URL}/bin-night-card.js")


async def test_setup_loads_the_card_from_the_versioned_url(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    with (
        patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)),
        patch(EXTRA_JS_PATH) as add_extra_js_url,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    add_extra_js_url.assert_called_once()
    assert re.fullmatch(
        rf"{re.escape(STATIC_URL)}/bin-night-card\.js\?v=[0-9a-f]{{12}}", add_extra_js_url.call_args.args[1]
    )
    await hass.config_entries.async_unload(entry.entry_id)


async def test_the_household_device_is_not_named_after_the_address(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "Bin collection"
    assert entry.data["address"] not in (device.name or "")
    assert hass.states.get("sensor.bin_general").name == "Bin collection General"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unloading_removes_every_repair_issue_for_the_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    issues = ir.async_get(hass)
    for issue_key in ISSUE_KEYS:
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{issue_key}_{entry.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=issue_key,
        )

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert "request_rejected" in ISSUE_KEYS
    for issue_key in ISSUE_KEYS:
        assert issues.async_get_issue(DOMAIN, f"{issue_key}_{entry.entry_id}") is None
