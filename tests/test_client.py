"""Tests for the Bin Night Tonight client, using sanitized recorded-shape fixtures."""

import pytest
from aiohttp import ClientError

from custom_components.aussie_bin_night.client import (
    AddressCandidate,
    BinNightTonightClient,
    BinNightTonightConnectionError,
    BinNightTonightInvalidResponseError,
    BinNightTonightRateLimitedError,
    address_from_config,
)


class _FakeResponse:
    """A minimal stand-in for aiohttp's async response context manager."""

    def __init__(self, status=200, payload=None, headers=None, raise_on_enter=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {}
        self._raise_on_enter = raise_on_enter

    async def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status >= 400:
            raise ClientError(f"HTTP {self.status}")

    async def __aenter__(self):
        if self._raise_on_enter is not None:
            raise self._raise_on_enter
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """A minimal stand-in for aiohttp.ClientSession that returns one canned response."""

    def __init__(self, response):
        self._response = response
        self.requested = None

    def get(self, url, params=None):
        self.requested = (url, params)
        return self._response


def _address(**overrides):
    defaults = dict(
        display_name="1 Example Street, Sample Suburb VIC 3000",
        street="1 Example Street",
        suburb="Sample Suburb",
        postcode="3000",
        state="VIC",
        latitude=-37.8136,
        longitude=144.9631,
    )
    defaults.update(overrides)
    return AddressCandidate(**defaults)


async def test_search_addresses_parses_only_address_features(load_fixture):
    session = _FakeSession(_FakeResponse(payload=load_fixture("geocode_response.json")))
    client = BinNightTonightClient(session)

    candidates = await client.async_search_addresses("1 example street")

    assert len(candidates) == 1
    assert candidates[0] == _address()
    assert session.requested[1] == {"q": "1 example street"}


async def test_search_addresses_rejects_response_without_features_list():
    session = _FakeSession(_FakeResponse(payload={"not_features": []}))
    client = BinNightTonightClient(session)

    with pytest.raises(BinNightTonightInvalidResponseError):
        await client.async_search_addresses("anything")


async def test_get_schedule_parses_events_and_council(load_fixture):
    session = _FakeSession(_FakeResponse(payload=load_fixture("bin_lookup_response.json")))
    client = BinNightTonightClient(session)

    schedule = await client.async_get_schedule(_address())

    assert schedule.council_id == "sample-city-council"
    assert [event.collection_date.isoformat() for event in schedule.events] == [
        "2026-09-22",
        "2026-09-29",
        "2026-10-06",
    ]
    assert schedule.available_bin_types == ("general", "recycling", "garden")


async def test_get_schedule_rejects_missing_lga_or_events():
    session = _FakeSession(_FakeResponse(payload={"lgaId": "sample-city-council"}))
    client = BinNightTonightClient(session)

    with pytest.raises(BinNightTonightInvalidResponseError):
        await client.async_get_schedule(_address())


async def test_get_schedule_skips_malformed_individual_events():
    payload = {
        "lgaId": "sample-city-council",
        "events": [
            {"date": "2026-09-22", "bins": ["general"]},
            {"date": "not-a-date", "bins": ["general"]},
            {"date": "2026-09-29", "bins": "not-a-list"},
            "not-a-dict",
        ],
    }
    session = _FakeSession(_FakeResponse(payload=payload))
    client = BinNightTonightClient(session)

    schedule = await client.async_get_schedule(_address())

    assert [event.collection_date.isoformat() for event in schedule.events] == ["2026-09-22"]


async def test_rate_limited_response_raises_dedicated_error():
    session = _FakeSession(_FakeResponse(status=429, headers={"Retry-After": "30"}))
    client = BinNightTonightClient(session)

    with pytest.raises(BinNightTonightRateLimitedError):
        await client.async_search_addresses("anything")


async def test_http_error_raises_connection_error():
    session = _FakeSession(_FakeResponse(status=500))
    client = BinNightTonightClient(session)

    with pytest.raises(BinNightTonightConnectionError):
        await client.async_search_addresses("anything")


async def test_network_failure_raises_connection_error():
    session = _FakeSession(_FakeResponse(raise_on_enter=ClientError("boom")))
    client = BinNightTonightClient(session)

    with pytest.raises(BinNightTonightConnectionError):
        await client.async_search_addresses("anything")


async def test_non_object_response_is_invalid():
    session = _FakeSession(_FakeResponse(payload=["not", "an", "object"]))
    client = BinNightTonightClient(session)

    with pytest.raises(BinNightTonightInvalidResponseError):
        await client.async_search_addresses("anything")


def test_address_from_config_round_trips_stored_entry_data():
    address = _address()
    data = {
        "address": address.display_name,
        "street": address.street,
        "suburb": address.suburb,
        "postcode": address.postcode,
        "state": address.state,
        "latitude": address.latitude,
        "longitude": address.longitude,
    }

    assert address_from_config(data) == address
