"""Tests for the bin collection sensor entity."""

from datetime import timedelta
from unittest.mock import patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.aussie_bin_night.const import CONF_REMINDER_LEAD_TIME, DOMAIN
from custom_components.aussie_bin_night.coordinator import AussieBinNightCoordinator
from custom_components.aussie_bin_night.sensor import BinCollectionSensor

from .conftest import SAMPLE_SCHEDULE, FakeBinNightTonightClient, sample_entry_data

CLIENT_PATH = "custom_components.aussie_bin_night.coordinator.BinNightTonightClient"


async def _make_ready_coordinator(hass, entry):
    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)):
        coordinator = AussieBinNightCoordinator(hass, entry)
        await coordinator.async_refresh()
    return coordinator


async def test_general_waste_sensor_reports_next_collection(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(), options={CONF_REMINDER_LEAD_TIME: 12})
    entry.add_to_hass(hass)
    coordinator = await _make_ready_coordinator(hass, entry)

    sensor = BinCollectionSensor(coordinator, entry, "general")

    assert sensor.entity_id == "sensor.bin_general"
    assert sensor.unique_id == f"{entry.entry_id}_general"
    assert sensor.native_value == SAMPLE_SCHEDULE.events[0].collection_date

    attributes = sensor.extra_state_attributes
    assert attributes["council"] == "Sample City Council"
    assert attributes["council_id"] == SAMPLE_SCHEDULE.council_id
    assert attributes["collection_date"] == SAMPLE_SCHEDULE.events[0].collection_date.isoformat()
    assert attributes["days_until"] == (SAMPLE_SCHEDULE.events[0].collection_date - dt_util.now().date()).days
    assert attributes["bin_colour"] == "red"
    # events[1] is the next event after events[0] that still includes "general"
    assert attributes["following_collection_date"] == SAMPLE_SCHEDULE.events[1].collection_date.isoformat()

    coordinator.async_cancel_reminder_refresh()


async def test_reminder_time_uses_the_configured_lead_time(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(), options={CONF_REMINDER_LEAD_TIME: 6})
    entry.add_to_hass(hass)
    coordinator = await _make_ready_coordinator(hass, entry)

    sensor = BinCollectionSensor(coordinator, entry, "general")
    expected = dt_util.start_of_local_day(SAMPLE_SCHEDULE.events[0].collection_date) - timedelta(hours=6)

    assert sensor.extra_state_attributes["reminder_time"] == expected.isoformat()

    coordinator.async_cancel_reminder_refresh()


async def test_recycling_sensor_skips_an_event_missing_its_stream(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_ready_coordinator(hass, entry)

    sensor = BinCollectionSensor(coordinator, entry, "recycling")

    assert sensor.native_value == SAMPLE_SCHEDULE.events[0].collection_date
    assert sensor.extra_state_attributes["bin_colour"] == "yellow"
    # events[1] has no recycling, so the following date should skip to events[2]
    assert (
        sensor.extra_state_attributes["following_collection_date"]
        == SAMPLE_SCHEDULE.events[2].collection_date.isoformat()
    )

    coordinator.async_cancel_reminder_refresh()


async def test_garden_waste_sensor_finds_its_own_next_event(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_ready_coordinator(hass, entry)

    sensor = BinCollectionSensor(coordinator, entry, "garden")

    assert sensor.native_value == SAMPLE_SCHEDULE.events[1].collection_date
    assert sensor.extra_state_attributes["bin_colour"] == "dark green"
    # only one garden event in the fixture, so there's no following collection
    assert "following_collection_date" not in sensor.extra_state_attributes

    coordinator.async_cancel_reminder_refresh()


async def test_sensor_has_no_upcoming_date_when_the_stream_is_absent(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_ready_coordinator(hass, entry)

    sensor = BinCollectionSensor(coordinator, entry, "glass")

    assert sensor.native_value is None
    attributes = sensor.extra_state_attributes
    assert "collection_date" not in attributes
    assert "days_until" not in attributes
    assert "reminder_time" not in attributes
    assert attributes["council"] == "Sample City Council"
    assert attributes["council_id"] == SAMPLE_SCHEDULE.council_id
    assert attributes["bin_colour"] == "purple"

    coordinator.async_cancel_reminder_refresh()


async def test_sensor_is_attached_to_a_household_device(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_ready_coordinator(hass, entry)

    sensor = BinCollectionSensor(coordinator, entry, "general")

    assert sensor.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}
    assert sensor.device_info["name"] == entry.data["address"]

    coordinator.async_cancel_reminder_refresh()


async def test_days_until_rolls_over_at_local_midnight(hass, freezer):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        before = hass.states.get("sensor.bin_general").attributes["days_until"]

        next_midnight = dt_util.start_of_local_day(dt_util.now().date() + timedelta(days=1))
        freezer.move_to(next_midnight)
        async_fire_time_changed(hass, next_midnight)
        await hass.async_block_till_done()

        after = hass.states.get("sensor.bin_general").attributes["days_until"]

    assert after == before - 1
    await hass.config_entries.async_unload(entry.entry_id)
