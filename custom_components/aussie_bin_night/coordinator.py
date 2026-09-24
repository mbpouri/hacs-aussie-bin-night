"""Data-update coordinator for Aussie Bin Night."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
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
    BinNightTonightRequestRejectedError,
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
    STALE_RETRY_DELAY,
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
ISSUE_REQUEST_REJECTED = "request_rejected"
ISSUE_KEYS = (ISSUE_UNSUPPORTED_ADDRESS, ISSUE_INVALID_RESPONSE, ISSUE_REQUEST_REJECTED)


class AussieBinNightCoordinator(DataUpdateCoordinator[CollectionSchedule]):
    """Fetch one household's bin schedule on a weekly cadence."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator for a config entry."""
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            # The entry id, not its title: the title is the household's street address
            # and Home Assistant writes the coordinator name into its log messages.
            name=f"{DOMAIN} {entry.entry_id}",
            config_entry=entry,
            update_interval=timedelta(
                days=int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_DAYS))
            ),
        )
        self._client = BinNightTonightClient(async_get_clientsession(hass))
        self._address = address_from_config(dict(entry.data))
        self._entry = entry
        self._unsub_extra_refresh: CALLBACK_TYPE | None = None
        self.last_successful_update: datetime | None = None
        self.serving_stale = False

    async def _async_update_data(self) -> CollectionSchedule:
        """Fetch the current schedule, raising actionable repairs for persistent problems."""
        try:
            schedule = await self._client.async_get_schedule(self._address)
        except (BinNightTonightRateLimitedError, BinNightTonightConnectionError) as err:
            # Both are transient and resolve on their own. A previously fetched schedule's
            # dates stay valid, so keep serving it and retry soon instead of leaving every
            # sensor unavailable until the next (weekly) poll. Only the very first fetch,
            # which has nothing to fall back on, fails outright.
            if self.data is None:
                raise UpdateFailed(str(err)) from err
            log = self.logger.debug if self.serving_stale else self.logger.warning
            log("Could not refresh the bin schedule (%s); keeping the last known schedule and retrying", err)
            self.serving_stale = True
            self._async_schedule_extra_refresh(dt_util.utcnow() + STALE_RETRY_DELAY)
            return self.data
        except (BinNightTonightInvalidResponseError, BinNightTonightRequestRejectedError) as err:
            # Not served stale: the provider may have changed or dropped this address, so the
            # sensors go unavailable. The failed refresh is often the scheduled extra refresh,
            # so without a retry here nothing would try again until the next (up to 30-day)
            # poll. The first refresh needs none: setup retries it via ConfigEntryNotReady.
            rejected = isinstance(err, BinNightTonightRequestRejectedError)
            self._async_raise_issue(
                ISSUE_REQUEST_REJECTED if rejected else ISSUE_INVALID_RESPONSE, ir.IssueSeverity.ERROR
            )
            if self.data is not None:
                self._async_schedule_extra_refresh(dt_util.utcnow() + STALE_RETRY_DELAY)
            raise UpdateFailed(str(err)) from err

        self.serving_stale = False
        self.last_successful_update = dt_util.utcnow()
        if schedule.available_bin_types:
            for issue_key in ISSUE_KEYS:
                self._async_clear_issue(issue_key)
        else:
            # A well-formed response with no collection events at all almost always
            # means the provider has stopped covering this address.
            self._async_raise_issue(ISSUE_UNSUPPORTED_ADDRESS, ir.IssueSeverity.WARNING)
            self._async_clear_issue(ISSUE_INVALID_RESPONSE)
            self._async_clear_issue(ISSUE_REQUEST_REJECTED)
        self._async_schedule_next_extra_refresh(schedule)
        return schedule

    def _async_schedule_next_extra_refresh(self, schedule: CollectionSchedule) -> None:
        """Schedule one extra refresh ahead of when the current data could go stale.

        The weekly cadence alone could leave stale data in place at the moments it
        matters most, so this picks the earlier of two points:

        - shortly before the next reminder is due, so an automation acting on it
          sees fresh data even if a public holiday moved a collection since the
          last poll;
        - the day after the last known collection, when every stream would
          otherwise sit on `unknown` until the next poll.
        """
        self.async_cancel_extra_refresh()

        lead_hours = int(self._entry.options.get(CONF_REMINDER_LEAD_TIME, DEFAULT_REMINDER_LEAD_TIME_HOURS))
        now = dt_util.utcnow()
        candidates: list[datetime] = []

        reminder_times = (
            dt_util.start_of_local_day(event.collection_date) - timedelta(hours=lead_hours)
            for event in schedule.events
        )
        if (upcoming_reminder := min((r for r in reminder_times if r > now), default=None)) is not None:
            candidates.append(upcoming_reminder - timedelta(minutes=5))

        if schedule.events:
            last_event = max(event.collection_date for event in schedule.events)
            candidates.append(dt_util.start_of_local_day(last_event + timedelta(days=1)))

        if (refresh_at := min((c for c in candidates if c > now), default=None)) is not None:
            self._async_schedule_extra_refresh(refresh_at)

    @callback
    def _async_schedule_extra_refresh(self, refresh_at: datetime) -> None:
        """Replace any pending extra refresh with one at the given time."""
        self.async_cancel_extra_refresh()
        self._unsub_extra_refresh = async_track_point_in_time(
            self.hass, self._async_handle_extra_refresh, refresh_at
        )

    async def _async_handle_extra_refresh(self, _now: datetime) -> None:
        """Refresh the schedule at an extra point chosen by this coordinator."""
        self._unsub_extra_refresh = None
        await self.async_request_refresh()

    def async_cancel_extra_refresh(self) -> None:
        """Cancel any pending extra refresh, for use as an unload callback."""
        if self._unsub_extra_refresh is not None:
            self._unsub_extra_refresh()
            self._unsub_extra_refresh = None

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


type AussieBinNightConfigEntry = ConfigEntry[AussieBinNightCoordinator]
