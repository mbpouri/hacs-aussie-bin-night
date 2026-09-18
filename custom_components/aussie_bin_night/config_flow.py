"""Config flow for Aussie Bin Night."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import (
    AddressCandidate,
    BinNightTonightClient,
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
    CollectionSchedule,
)
from .const import (
    CONF_ADDRESS,
    CONF_BIN_TYPES,
    CONF_COUNCIL_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POSTCODE,
    CONF_REMINDER_LEAD_TIME,
    CONF_STATE,
    CONF_STREET,
    CONF_SUBURB,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)


class AussieBinNightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aussie Bin Night."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AussieBinNightOptionsFlow:
        """Return the options flow for an existing household."""
        return AussieBinNightOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Keep only minimal, transient address-search state in this flow."""
        self._candidates: list[AddressCandidate] = []
        self._selected_address: AddressCandidate | None = None
        self._schedule: CollectionSchedule | None = None
        self._reconfigure = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Search for an Australian household address."""
        self._reconfigure = False
        return await self._async_step_search(user_input, "user")

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Search for a replacement address for an existing household."""
        self._reconfigure = True
        return await self._async_step_search(user_input, "reconfigure")

    async def _async_step_search(self, user_input: dict[str, Any] | None, step_id: str) -> ConfigFlowResult:
        """Search for a household address, shared by the setup and reconfigure flows."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._candidates = await self._client.async_search_addresses(user_input[CONF_ADDRESS].strip())
            except BinNightTonightConnectionError:
                errors["base"] = "cannot_connect"
            except BinNightTonightRateLimitedError:
                errors["base"] = "rate_limited"
            except BinNightTonightInvalidResponseError:
                errors["base"] = "invalid_response"
            else:
                if self._candidates:
                    return await (
                        self.async_step_reconfigure_select_address()
                        if self._reconfigure
                        else self.async_step_select_address()
                    )
                errors["base"] = "no_addresses_found"

        address_key = (
            vol.Required(CONF_ADDRESS, default=self._get_reconfigure_entry().data[CONF_ADDRESS])
            if self._reconfigure
            else vol.Required(CONF_ADDRESS)
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({address_key: vol.All(str, vol.Length(min=4))}),
            errors=errors,
        )

    async def async_step_select_address(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select an address and validate its collection schedule."""
        return await self._async_step_select_address(user_input, "select_address")

    async def async_step_reconfigure_select_address(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select a replacement address and validate its collection schedule."""
        return await self._async_step_select_address(user_input, "reconfigure_select_address")

    async def _async_step_select_address(self, user_input: dict[str, Any] | None, step_id: str) -> ConfigFlowResult:
        """Select an address, shared by the setup and reconfigure flows."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._selected_address = self._candidates[int(user_input[CONF_ADDRESS])]
            except (IndexError, TypeError, ValueError):
                errors["base"] = "invalid_address"
            else:
                try:
                    self._schedule = await self._client.async_get_schedule(self._selected_address)
                except BinNightTonightConnectionError:
                    errors["base"] = "cannot_connect"
                except BinNightTonightRateLimitedError:
                    errors["base"] = "rate_limited"
                except BinNightTonightInvalidResponseError:
                    errors["base"] = "invalid_response"
                else:
                    if self._schedule.available_bin_types:
                        return await (
                            self.async_step_reconfigure_confirm()
                            if self._reconfigure
                            else self.async_step_bin_types()
                        )
                    errors["base"] = "no_collections_found"

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[selector.SelectOptionDict(value=str(index), label=candidate.display_name) for index, candidate in enumerate(self._candidates)],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_bin_types(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose which available bin streams become sensors for a new household."""
        return await self._async_step_bin_types(user_input, "bin_types")

    async def async_step_reconfigure_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose which available bin streams become sensors after an address change."""
        return await self._async_step_bin_types(user_input, "reconfigure_confirm")

    async def _async_step_bin_types(self, user_input: dict[str, Any] | None, step_id: str) -> ConfigFlowResult:
        """Choose bin streams and finish the flow, shared by setup and reconfigure."""
        assert self._selected_address is not None
        assert self._schedule is not None
        available = self._schedule.available_bin_types
        if user_input is not None:
            address = self._selected_address
            data = {
                CONF_ADDRESS: address.display_name,
                CONF_STREET: address.street,
                CONF_SUBURB: address.suburb,
                CONF_POSTCODE: address.postcode,
                CONF_STATE: address.state,
                CONF_LATITUDE: address.latitude,
                CONF_LONGITUDE: address.longitude,
                CONF_COUNCIL_ID: self._schedule.council_id,
                CONF_BIN_TYPES: user_input[CONF_BIN_TYPES],
            }
            unique_id = f"{address.latitude:.6f},{address.longitude:.6f}"
            if self._reconfigure:
                reconfigure_entry = self._get_reconfigure_entry()
                for other_entry in self._async_current_entries():
                    if other_entry.entry_id != reconfigure_entry.entry_id and other_entry.unique_id == unique_id:
                        return self.async_abort(reason="already_configured")
                await self.async_set_unique_id(unique_id)
                return self.async_update_reload_and_abort(reconfigure_entry, data=data)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=address.display_name, data=data)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BIN_TYPES, default=list(available)): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=list(available), multiple=True, mode=selector.SelectSelectorMode.LIST)
                    )
                }
            ),
            description_placeholders={"council": self._schedule.council_id.replace("-", " ").title()},
        )

    @property
    def _client(self) -> BinNightTonightClient:
        """Return a client using Home Assistant's shared HTTP session."""
        return BinNightTonightClient(async_get_clientsession(self.hass))


class AussieBinNightOptionsFlow(OptionsFlow):
    """Handle options for an existing Aussie Bin Night entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage update cadence, reminder timing, and shown bin streams."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        available = self._entry.data[CONF_BIN_TYPES]
        defaults = self._entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=defaults.get(CONF_UPDATE_INTERVAL, 7),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=30, step=1, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Required(
                        CONF_REMINDER_LEAD_TIME,
                        default=defaults.get(CONF_REMINDER_LEAD_TIME, 12),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=72, step=1, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Required(
                        CONF_BIN_TYPES,
                        default=defaults.get(CONF_BIN_TYPES, available),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=available, multiple=True, mode=selector.SelectSelectorMode.LIST)
                    ),
                }
            ),
        )
