"""Data-update coordinator for Aussie Bin Night."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import (
    BinNightTonightClient,
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
    CollectionSchedule,
    address_from_config,
)
from .const import (
    CONF_BIN_TYPES,
    CONF_KNOWN_BIN_TYPES,
    CONF_REMINDER_LEAD_TIME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_REMINDER_LEAD_TIME_HOURS,
    DEFAULT_UPDATE_INTERVAL_DAYS,
    DOMAIN,
)

def enabled_bin_types(entry: ConfigEntry, available: tuple[str, ...]) -> list[str]:
    """Return the bin streams that should have a sensor.

    That is every stream the user chose, plus any stream the provider offers that
    the user has never been shown (not in the known set), so a stream that appears
    later, such as an occasional hard-waste collection, gets a sensor by default.
    A stream the user deliberately deselected stays off because saving the options
    records everything they were shown as known.
    """
    chosen = list(entry.options.get(CONF_BIN_TYPES, entry.data[CONF_BIN_TYPES]))
    known = set(entry.options.get(CONF_KNOWN_BIN_TYPES, entry.data.get(CONF_KNOWN_BIN_TYPES, chosen)))
    return chosen + [bin_type for bin_type in available if bin_type not in known and bin_type not in chosen]


ISSUE_UNSUPPORTED_ADDRESS = "unsupported_address"
ISSUE_INVALID_RESPONSE = "invalid_response"


class AussieBinNightCoordinator(DataUpdateCoordinator[CollectionSchedule]):
    """Fetch one household's bin schedule on a weekly cadence."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator for a config entry."""
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(
                days=int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_DAYS))
            ),
        )
        self._client = BinNightTonightClient(async_get_clientsession(hass))
        self._address = address_from_config(dict(entry.data))
        self._entry = entry
        self._unsub_reminder_refresh: CALLBACK_TYPE | None = None

    async def _async_update_data(self) -> CollectionSchedule:
        """Fetch the current schedule, raising actionable repairs for persistent problems."""
        try:
            schedule = await self._client.async_get_schedule(self._address)
        except BinNightTonightRateLimitedError as err:
            # Rate limits are transient and resolve on their own once traffic eases,
            # so entities go unavailable without a repair issue cluttering the list.
            raise UpdateFailed(str(err)) from err
        except BinNightTonightConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except BinNightTonightInvalidResponseError as err:
            self._async_raise_issue(ISSUE_INVALID_RESPONSE, ir.IssueSeverity.ERROR)
            raise UpdateFailed(str(err)) from err

        if schedule.available_bin_types:
            self._async_clear_issue(ISSUE_INVALID_RESPONSE)
            self._async_clear_issue(ISSUE_UNSUPPORTED_ADDRESS)
        else:
            # A well-formed response with no collection events at all almost always
            # means the provider has stopped covering this address.
            self._async_raise_issue(ISSUE_UNSUPPORTED_ADDRESS, ir.IssueSeverity.WARNING)
        self._async_schedule_reminder_refresh(schedule)
        return schedule

    def _async_schedule_reminder_refresh(self, schedule: CollectionSchedule) -> None:
        """Schedule one extra refresh shortly before the next reminder is due.

        The weekly cadence alone could leave stale data in place right when an
        automation is about to act on it, for example if a public holiday moved
        a collection after the last poll. This tops up the data just ahead of
        the configured reminder window instead of waiting for the next poll.
        """
        if self._unsub_reminder_refresh is not None:
            self._unsub_reminder_refresh()
            self._unsub_reminder_refresh = None

        lead_hours = int(self._entry.options.get(CONF_REMINDER_LEAD_TIME, DEFAULT_REMINDER_LEAD_TIME_HOURS))
        now = dt_util.utcnow()
        reminder_times = (
            dt_util.start_of_local_day(event.collection_date) - timedelta(hours=lead_hours)
            for event in schedule.events
        )
        upcoming_reminder = min((reminder for reminder in reminder_times if reminder > now), default=None)
        if upcoming_reminder is None:
            return

        refresh_at = upcoming_reminder - timedelta(minutes=5)
        if refresh_at <= now:
            return
        self._unsub_reminder_refresh = async_track_point_in_time(
            self.hass, self._async_handle_reminder_refresh, refresh_at
        )

    async def _async_handle_reminder_refresh(self, _now) -> None:
        """Refresh the schedule just before a reminder is due."""
        self._unsub_reminder_refresh = None
        await self.async_request_refresh()

    def async_cancel_reminder_refresh(self) -> None:
        """Cancel any pending pre-reminder refresh, for use as an unload callback."""
        if self._unsub_reminder_refresh is not None:
            self._unsub_reminder_refresh()
            self._unsub_reminder_refresh = None

    def _async_raise_issue(self, issue_key: str, severity: ir.IssueSeverity) -> None:
        """Create or refresh a repair issue naming this household's config entry."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{issue_key}_{self._entry.entry_id}",
            is_fixable=False,
            severity=severity,
            translation_key=issue_key,
            translation_placeholders={"address": self._entry.title},
        )

    def _async_clear_issue(self, issue_key: str) -> None:
        """Remove a previously raised repair issue once a fetch recovers."""
        ir.async_delete_issue(self.hass, DOMAIN, f"{issue_key}_{self._entry.entry_id}")
