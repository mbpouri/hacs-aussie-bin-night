"""Data-update coordinator for Aussie Bin Night."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    BinNightTonightClient,
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
    CollectionSchedule,
    address_from_config,
)
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_DAYS, DOMAIN

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
        return schedule

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
