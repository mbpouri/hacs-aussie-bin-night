# Changelog

## [Unreleased]

### Fixed

- After an unexpected response, the refresh is now retried after an hour. Previously nothing retried it until the next scheduled poll (up to the configured update interval, as long as 30 days), so the sensors stayed unavailable all that time. The last schedule is still not kept in place for this kind of failure.
- An HTTP 4xx response other than 429 (such as 403, 404 or 410) is now reported as the provider refusing the request, not as an unexpected response that suggests its API changed. It raises its own **Refused requests** repair issue, which clears once a refresh succeeds, is retried hourly, and shows a matching error during setup and reconfigure.
- Collection events are now sorted by date. The sensors used the first matching event, so a schedule returned out of order could show a later collection as the next one, or the wrong `following_collection_date`.

### Changed

- Confirmed the minimum Home Assistant version in `hacs.json` (2024.11.0) against Home Assistant core: it is the first release with `ConfigFlow._get_reconfigure_entry` and the `config_entry` argument to `DataUpdateCoordinator`, both of which the integration uses.

## [1.0.3] - 2026-09-20

### Fixed

- **The card picker preview hung on a spinner and the card could not be added** (`Custom element not found: bin-night-card` in the browser console).

### Added

- A manually run **Release** workflow (`.github/workflows/release.yml`). It checks that `manifest.json` and `CHANGELOG.md` agree on the version and that CI passed, then tags the head of `main` and publishes the GitHub release with notes from this file.

## [1.0.2] - 2026-09-20

### Fixed

- The household's street address no longer appears in Home Assistant log messages. The data coordinator was named after the config entry title, which is the address.
- **Reconfigure** now updates the entry's unique id and title along with its data. Previously both kept the old address, so duplicate detection worked against the wrong address and the UI still showed the old one.
- Deselecting a bin type in **Configure** now removes its sensor from the entity registry instead of leaving a permanently unavailable entity behind.
- A response body that isn't valid JSON, and unexpected 4xx statuses, are reported as an unexpected response rather than as a connection problem. Unhandled JSON decoding errors no longer escape the client.
- Diagnostics can be downloaded for an entry that failed to load.
- README: corrected the `time_date` trigger advice, the "night before" example automation (which fired at midnight on collection day), the update-interval units, and the description of how refreshes work.

### Changed

- A temporary connection problem or rate limit no longer makes every sensor unavailable until the next weekly poll. The last known schedule stays in place and the refresh is retried after an hour.
- An extra refresh is scheduled the day after the last known collection, so sensors don't sit on `unknown` until the next poll.
- Requests to Bin Night Tonight identify the integration with a `User-Agent`.
- Config entry runtime data moved to `entry.runtime_data`. Requires Home Assistant 2024.11 or newer, now declared in `hacs.json`.
- Diagnostics now include when the last successful refresh happened and whether a stale schedule is being served.
- Card: it only re-renders when something it shows has changed, instead of on every Home Assistant state change; a stream with no upcoming date says "No upcoming collection" instead of "Unavailable"; rows open the sensor's details when tapped or activated from the keyboard; the bin gradients are defined once per card; and it provides sizing hints for sections dashboards.

### Added

- Python unit tests now run in CI (`.github/workflows/tests.yml`) along with `ruff`, using pinned test requirements in `requirements_test.txt`. Dependabot watches them.
- Feature request issue template and pull request template.

## [1.0.1] - 2026-09-19

### Added

- The card shows labelled sample data in the card picker preview when there are no sensors yet.

### Changed

- README screenshots and visual-editor description.

## [1.0.0] - 2026-09-19

First release.

- Address search and selection through the Home Assistant UI, with the council detected automatically and no API key or council code to enter.
- One date sensor per bin stream (general waste, recycling, garden organics, FOGO, glass, hard waste) with `days_until`, `collection_date`, `council`, `bin_colour`, `reminder_time` and following-collection attributes.
- Reconfigure flow, and options for update interval, reminder lead time and shown bin types.
- Repair issues for unsupported addresses and unexpected provider responses; diagnostics with the address redacted.
- The bundled `custom:bin-night-card` Lovelace card, loaded automatically, with a visual editor and zero-configuration discovery of the integration's sensors.
