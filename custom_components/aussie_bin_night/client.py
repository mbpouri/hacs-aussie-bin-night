"""Client for the Bin Night Tonight API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import API_BASE_URL, REQUEST_TIMEOUT_SECONDS


class BinNightTonightError(Exception):
    """Base exception for Bin Night Tonight failures."""


class BinNightTonightConnectionError(BinNightTonightError):
    """Raised when the API cannot be reached."""


class BinNightTonightInvalidResponseError(BinNightTonightError):
    """Raised when the API returns an unexpected payload."""


class BinNightTonightRateLimitedError(BinNightTonightError):
    """Raised when the API throttles requests with an HTTP 429 response."""


@dataclass(frozen=True, slots=True)
class AddressCandidate:
    """The selected-address data required for a schedule lookup."""

    display_name: str
    street: str
    suburb: str
    postcode: str
    state: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class CollectionEvent:
    """A collection event returned by the schedule API."""

    collection_date: date
    bin_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CollectionSchedule:
    """A household collection schedule."""

    council_id: str
    events: tuple[CollectionEvent, ...]

    @property
    def available_bin_types(self) -> tuple[str, ...]:
        """Return distinct collection streams in API order."""
        return tuple(dict.fromkeys(bin_type for event in self.events for bin_type in event.bin_types))


class BinNightTonightClient:
    """Fetch addresses and collection schedules from Bin Night Tonight."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def async_search_addresses(self, query: str) -> list[AddressCandidate]:
        """Return selectable Australian street-address matches for a query."""
        payload = await self._async_get_json("/geocode", {"q": query})
        features = payload.get("features")
        if not isinstance(features, list):
            raise BinNightTonightInvalidResponseError("Geocoder response has no features list")

        candidates: list[AddressCandidate] = []
        for feature in features:
            candidate = self._parse_address_candidate(feature)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    async def async_get_schedule(self, address: AddressCandidate) -> CollectionSchedule:
        """Return a schedule; the API resolves the council from coordinates."""
        payload = await self._async_get_json(
            "/bin-lookup",
            {
                "lat": str(address.latitude),
                "lon": str(address.longitude),
                "state": address.state,
                "street": address.street,
                "suburb": address.suburb,
                "postcode": address.postcode,
            },
        )
        council_id = payload.get("lgaId")
        events = payload.get("events")
        if not isinstance(council_id, str) or not isinstance(events, list):
            raise BinNightTonightInvalidResponseError("Schedule response is missing lgaId or events")

        parsed_events: list[CollectionEvent] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            value = event.get("date")
            bin_types = event.get("bins")
            if not isinstance(value, str) or not isinstance(bin_types, list):
                continue
            try:
                collection_date = date.fromisoformat(value)
            except ValueError:
                continue
            streams = tuple(item for item in bin_types if isinstance(item, str))
            if streams:
                parsed_events.append(CollectionEvent(collection_date, streams))

        return CollectionSchedule(council_id, tuple(parsed_events))

    async def _async_get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """Fetch and validate one JSON-object API response."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._session.get(f"{API_BASE_URL}{path}", params=params) as response:
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After", "a short wait")
                        raise BinNightTonightRateLimitedError(
                            f"Bin Night Tonight rate-limited this request; retry after {retry_after}"
                        )
                    response.raise_for_status()
                    payload = await response.json()
        except (ClientError, TimeoutError) as err:
            raise BinNightTonightConnectionError("Unable to reach Bin Night Tonight") from err

        if not isinstance(payload, dict):
            raise BinNightTonightInvalidResponseError("API response is not an object")
        return payload

    @staticmethod
    def _parse_address_candidate(feature: Any) -> AddressCandidate | None:
        """Convert one GeoJSON feature into a usable street-address candidate."""
        if not isinstance(feature, dict):
            return None
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            return None
        if properties.get("feature_type") != "address":
            return None

        coordinates = geometry.get("coordinates")
        context = properties.get("context")
        if not (isinstance(coordinates, list) and len(coordinates) >= 2 and isinstance(context, dict)):
            return None

        address_context = context.get("address")
        postcode_context = context.get("postcode")
        locality_context = context.get("locality") or context.get("place")
        region_context = context.get("region")
        if not all(isinstance(item, dict) for item in (address_context, postcode_context, locality_context, region_context)):
            return None

        street = address_context.get("name")
        postcode = postcode_context.get("name")
        suburb = locality_context.get("name")
        state = region_context.get("name")
        display_name = properties.get("full_address")
        if not all(isinstance(value, str) and value for value in (street, postcode, suburb, state, display_name)):
            return None
        try:
            longitude = float(coordinates[0])
            latitude = float(coordinates[1])
        except (TypeError, ValueError):
            return None

        return AddressCandidate(display_name, street, suburb, postcode, state, latitude, longitude)


def address_from_config(data: dict[str, Any]) -> AddressCandidate:
    """Create an address candidate from persisted config-entry data."""
    return AddressCandidate(
        display_name=str(data["address"]),
        street=str(data["street"]),
        suburb=str(data["suburb"]),
        postcode=str(data["postcode"]),
        state=str(data["state"]),
        latitude=float(data["latitude"]),
        longitude=float(data["longitude"]),
    )
