"""Shared pytest fixtures for the Aussie Bin Night test suite."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from custom_components.aussie_bin_night.client import AddressCandidate, CollectionEvent, CollectionSchedule
from custom_components.aussie_bin_night.const import (
    CONF_ADDRESS,
    CONF_BIN_TYPES,
    CONF_COUNCIL_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POSTCODE,
    CONF_STATE,
    CONF_STREET,
    CONF_SUBURB,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load this repository's custom_components without a HA deployment."""
    yield


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    """Return a callable that parses a JSON fixture from tests/fixtures/."""

    def _load(name: str):
        return json.loads((FIXTURES_DIR / name).read_text())

    return _load


SAMPLE_CANDIDATE = AddressCandidate(
    display_name="1 Example Street, Sample Suburb VIC 3000",
    street="1 Example Street",
    suburb="Sample Suburb",
    postcode="3000",
    state="VIC",
    latitude=-37.8136,
    longitude=144.9631,
)

def _relative_date(days_from_today: int) -> date:
    """Return a date offset from today, so fixed test fixtures never go stale."""
    return date.today() + timedelta(days=days_from_today)


SAMPLE_SCHEDULE = CollectionSchedule(
    council_id="sample-city-council",
    events=(
        CollectionEvent(_relative_date(3), ("general", "recycling")),
        CollectionEvent(_relative_date(10), ("general", "garden")),
        CollectionEvent(_relative_date(17), ("general", "recycling")),
    ),
)


def sample_entry_data(**overrides):
    """Return config-entry `data` for a household already past setup."""
    data = {
        CONF_ADDRESS: SAMPLE_CANDIDATE.display_name,
        CONF_STREET: SAMPLE_CANDIDATE.street,
        CONF_SUBURB: SAMPLE_CANDIDATE.suburb,
        CONF_POSTCODE: SAMPLE_CANDIDATE.postcode,
        CONF_STATE: SAMPLE_CANDIDATE.state,
        CONF_LATITUDE: SAMPLE_CANDIDATE.latitude,
        CONF_LONGITUDE: SAMPLE_CANDIDATE.longitude,
        CONF_COUNCIL_ID: SAMPLE_SCHEDULE.council_id,
        CONF_BIN_TYPES: ["general", "recycling", "garden"],
    }
    data.update(overrides)
    return data


class FakeBinNightTonightClient:
    """A canned stand-in for BinNightTonightClient used by config-flow tests."""

    def __init__(self, candidates=None, schedule=None, search_exc=None, schedule_exc=None):
        self._candidates = candidates
        self._schedule = schedule
        self._search_exc = search_exc
        self._schedule_exc = schedule_exc

    async def async_search_addresses(self, query):
        if self._search_exc:
            raise self._search_exc
        return self._candidates or []

    async def async_get_schedule(self, address):
        if self._schedule_exc:
            raise self._schedule_exc
        return self._schedule
