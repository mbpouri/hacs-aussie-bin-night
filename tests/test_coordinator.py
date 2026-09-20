"""Tests for the data-update coordinator, including its repair issues."""

from datetime import timedelta
from unittest.mock import patch

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.aussie_bin_night.client import (
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
    CollectionEvent,
    CollectionSchedule,
)
from custom_components.aussie_bin_night.const import CONF_REMINDER_LEAD_TIME, DOMAIN, STALE_RETRY_DELAY
from custom_components.aussie_bin_night.coordinator import (
    ISSUE_INVALID_RESPONSE,
    ISSUE_UNSUPPORTED_ADDRESS,
    AussieBinNightCoordinator,
    enabled_bin_types,
)

from .conftest import SAMPLE_CANDIDATE, SAMPLE_SCHEDULE, FakeBinNightTonightClient, sample_entry_data

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
    coordinator.async_cancel_extra_refresh()


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

    coordinator._client = FakeBinNightTonightClient(schedule=SAMPLE_SCHEDULE)
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(ISSUE_UNSUPPORTED_ADDRESS, entry)) is None
    coordinator.async_cancel_extra_refresh()


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
        assert coordinator._unsub_extra_refresh is not None

        async_fire_time_changed(hass, refresh_at + timedelta(seconds=1))
        await hass.async_block_till_done()

    assert fetch_count == 2
    coordinator.async_cancel_extra_refresh()


async def test_cancel_extra_refresh_is_a_no_op_when_nothing_is_scheduled(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = AussieBinNightCoordinator(hass, entry)

    coordinator.async_cancel_extra_refresh()


class _CountingClient(FakeBinNightTonightClient):
    """Return one schedule (or raise one error) and count how often it is asked."""

    def __init__(self, schedule=None, schedule_exc=None):
        super().__init__(schedule=schedule, schedule_exc=schedule_exc)
        self.fetch_count = 0

    async def async_get_schedule(self, address):
        self.fetch_count += 1
        return await super().async_get_schedule(address)


async def test_coordinator_name_does_not_contain_the_address(hass):
    entry = MockConfigEntry(domain=DOMAIN, title=SAMPLE_CANDIDATE.display_name, data=sample_entry_data())
    entry.add_to_hass(hass)

    coordinator = AussieBinNightCoordinator(hass, entry)

    assert SAMPLE_CANDIDATE.display_name not in coordinator.name
    assert SAMPLE_CANDIDATE.street not in coordinator.name


async def test_a_transient_failure_keeps_serving_the_last_schedule_then_recovers(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_coordinator(hass, entry, schedule=SAMPLE_SCHEDULE)

    coordinator._client = _CountingClient(schedule_exc=BinNightTonightConnectionError("down"))
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == SAMPLE_SCHEDULE
    assert coordinator.serving_stale is True
    assert coordinator._unsub_extra_refresh is not None

    recovered = _CountingClient(schedule=SAMPLE_SCHEDULE)
    coordinator._client = recovered
    async_fire_time_changed(hass, dt_util.utcnow() + STALE_RETRY_DELAY + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert recovered.fetch_count == 1
    assert coordinator.serving_stale is False
    coordinator.async_cancel_extra_refresh()


async def test_a_rate_limit_also_keeps_serving_the_last_schedule(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_coordinator(hass, entry, schedule=SAMPLE_SCHEDULE)

    coordinator._client = _CountingClient(schedule_exc=BinNightTonightRateLimitedError("slow down"))
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.serving_stale is True
    coordinator.async_cancel_extra_refresh()


async def test_an_invalid_response_does_not_keep_serving_stale_data(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)
    coordinator = await _make_coordinator(hass, entry, schedule=SAMPLE_SCHEDULE)

    coordinator._client = _CountingClient(schedule_exc=BinNightTonightInvalidResponseError("changed"))
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert coordinator.serving_stale is False
    coordinator.async_cancel_extra_refresh()


async def test_a_successful_refresh_records_when_it_happened(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data())
    entry.add_to_hass(hass)

    coordinator = await _make_coordinator(hass, entry, schedule=SAMPLE_SCHEDULE)

    assert coordinator.last_successful_update is not None
    coordinator.async_cancel_extra_refresh()


async def test_refreshes_the_day_after_the_last_known_collection(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(), options={CONF_REMINDER_LEAD_TIME: 12})
    entry.add_to_hass(hass)
    today = dt_util.now().date()
    # The only event is today, so its reminder is already in the past and the
    # schedule runs out at the end of today.
    schedule = CollectionSchedule("sample-city-council", (CollectionEvent(today, ("general",)),))
    client = _CountingClient(schedule=schedule)

    with patch(CLIENT_PATH, return_value=client):
        coordinator = AussieBinNightCoordinator(hass, entry)
        await coordinator.async_refresh()
        assert client.fetch_count == 1
        assert coordinator._unsub_extra_refresh is not None

        async_fire_time_changed(
            hass, dt_util.start_of_local_day(today + timedelta(days=1)) + timedelta(seconds=1)
        )
        await hass.async_block_till_done()

    assert client.fetch_count == 2
    coordinator.async_cancel_extra_refresh()


def test_enabled_bin_types_adds_streams_the_user_was_never_shown():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=sample_entry_data(bin_types=["general", "recycling"], known_bin_types=["general", "recycling"]),
    )

    assert enabled_bin_types(entry, ("general", "recycling", "hard")) == ["general", "recycling", "hard"]


def test_enabled_bin_types_keeps_deliberately_deselected_streams_off():
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=sample_entry_data(bin_types=["general"], known_bin_types=["general", "glass"]),
    )

    assert enabled_bin_types(entry, ("general", "glass")) == ["general"]


def test_enabled_bin_types_falls_back_to_chosen_types_for_older_entries():
    entry = MockConfigEntry(domain=DOMAIN, data=sample_entry_data(bin_types=["general", "recycling"]))

    assert enabled_bin_types(entry, ("general", "recycling")) == ["general", "recycling"]
