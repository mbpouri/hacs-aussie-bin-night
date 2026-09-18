"""Tests for the data-update coordinator, including its repair issues."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.aussie_bin_night.client import (
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
    CollectionSchedule,
)
from custom_components.aussie_bin_night.const import CONF_REMINDER_LEAD_TIME, DOMAIN
from custom_components.aussie_bin_night.coordinator import (
    ISSUE_INVALID_RESPONSE,
    ISSUE_UNSUPPORTED_ADDRESS,
    AussieBinNightCoordinator,
)

from .conftest import SAMPLE_SCHEDULE, FakeBinNightTonightClient, sample_entry_data

CLIENT_PATH = "custom_components.aussie_bin_night.coordinator.BinNightTonightClient"


def _issue_id(issue_key: str, entry) -> str:
    return f"{issue_key}_{entry.entry_id}"


async def _make_coordinator(hass, entry, **client_kwargs) -> AussieBinNightCoordinator:
    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(**client_kwargs)):
        coordinator = AussieBinNightCoordinator(hass, entry)
        await coordinator.async_refresh()
    return coordinator


async def test_successful_refresh_returns_schedule(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    coordinator = await _make_coordinator(hass, entry, schedule=SAMPLE_SCHEDULE)

    assert coordinator.last_update_success is True
    assert coordinator.data == SAMPLE_SCHEDULE
    coordinator.async_cancel_reminder_refresh()


async def test_rate_limited_marks_update_failed_without_a_repair_issue(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    coordinator = await _make_coordinator(
        hass, entry, schedule_exc=BinNightTonightRateLimitedError("slow down")
    )

    assert coordinator.last_update_success is False
    assert ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_INVALID_RESPONSE, entry)) is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_UNSUPPORTED_ADDRESS, entry)) is None


async def test_connection_error_marks_update_failed_without_a_repair_issue(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    coordinator = await _make_coordinator(
        hass, entry, schedule_exc=BinNightTonightConnectionError("unreachable")
    )

    assert coordinator.last_update_success is False
    assert ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_INVALID_RESPONSE, entry)) is None


async def test_invalid_response_raises_a_repair_issue(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    coordinator = await _make_coordinator(
        hass, entry, schedule_exc=BinNightTonightInvalidResponseError("unexpected shape")
    )

    assert coordinator.last_update_success is False
    issue = ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_INVALID_RESPONSE, entry))
    assert issue is not None
    assert issue.translation_placeholders == {"address": entry.title}


async def test_unsupported_address_raises_a_repair_issue_but_still_succeeds(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    empty_schedule = CollectionSchedule(council_id="sample-city-council", events=())

    coordinator = await _make_coordinator(hass, entry, schedule=empty_schedule)

    assert coordinator.last_update_success is True
    issue = ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_UNSUPPORTED_ADDRESS, entry))
    assert issue is not None


async def test_a_recovered_fetch_clears_previous_repair_issues(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    empty_schedule = CollectionSchedule(council_id="sample-city-council", events=())

    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=empty_schedule)):
        coordinator = AussieBinNightCoordinator(hass, entry)
        await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_UNSUPPORTED_ADDRESS, entry)) is not None

    with patch(CLIENT_PATH, return_value=FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)):
        await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_UNSUPPORTED_ADDRESS, entry)) is None
    coordinator.async_cancel_reminder_refresh()


async def test_schedules_a_refresh_shortly_before_the_soonest_reminder(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(), options={CONF_REMINDER_LEAD_TIME: 12})
    entry.add_to_hass(hass)

    fetch_count = 0

    class _CountingClient(FakeBinNightTonightClient):
        async def async_get_schedule(self, address):
            nonlocal fetch_count
            fetch_count += 1
            return SAMPLE_SCHEDULE

    with patch(CLIENT_PATH, return_value=_CountingClient()):
        coordinator = AussieBinNightCoordinator(hass, entry)
        await coordinator.async_refresh()
        assert fetch_count == 1

        earliest_reminder = dt_util.start_of_local_day(SAMPLE_SCHEDULE.events[0].collection_date) - timedelta(
            hours=12
        )
        refresh_at = earliest_reminder - timedelta(minutes=5)
        assert coordinator._unsub_reminder_refresh is not None

        async_fire_time_changed(hass, refresh_at + timedelta(seconds=1))
        await hass.async_block_till_done()

    assert fetch_count == 2
    coordinator.async_cancel_reminder_refresh()


async def test_cancel_reminder_refresh_is_a_no_op_when_nothing_is_scheduled(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = AussieBinNightCoordinator(hass, entry)

    coordinator.async_cancel_reminder_refresh()
