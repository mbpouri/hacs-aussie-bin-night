# 🗑️ Aussie Bin Night

A custom [Home Assistant](https://www.home-assistant.io/) integration that lets you pick your home address anywhere in Australia and shows you when your next kerbside household bin collection is — general waste, recycling, and green waste/FOGO, depending on what your local council collects.

Distributed via [HACS](https://hacs.xyz/) as a custom repository.

---

## ✨ Features

- 📍 **Address-based setup** — search and select your suburb/street during the config flow, no manual API keys or council codes required
- 🗓️ **Next collection sensor(s)** — one sensor per bin type (e.g. `sensor.bin_general`, `sensor.bin_recycling`, `sensor.bin_garden`)
- 🔔 **Automation-friendly** — trigger notifications the night before collection day
- 🖼️ **Lovelace card support** — optional companion card showing a friendly bin-icon countdown
- 🔁 **Auto-refresh** — polls council data sources to stay in sync with schedule changes (public holidays, roadworks, etc.)

---

## 📦 Installation

### Via HACS (recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations** → **⋮ (top right)** → **Custom repositories**
3. Add this repository URL and select category **Integration**
4. Search for **"Aussie Bin Night"** in HACS and click **Download**
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration** and search for **Aussie Bin Night**

### Manual installation

1. Copy the `custom_components/aussie_bin_night` folder from this repo into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services → Add Integration**

---

## ⚙️ Configuration

Configuration is done entirely through the UI (config flow) — no YAML required.

1. **Settings → Devices & Services → Add Integration → Aussie Bin Night**
2. Start typing your home address
3. Select your address from the autocomplete results
4. Confirm your council/LGA is detected correctly
5. Choose which bin types you want sensors for (some councils only offer a subset)
6. Done — sensors will appear under the integration's device page

Moved house, or picked the wrong address? Go to **Settings → Devices & Services → Aussie Bin Night → ⋮ → Reconfigure** to search for a new address without removing and re-adding the integration.

### Options

After setup, you can adjust via **Configure**:

| Option             | Description                                                      | Default       |
| ------------------ | ----------------------------------------------------------------- | ------------- |
| Update interval    | How often to refresh schedule data                                | weekly        |
| Reminder lead time | Hours before the collection date that `reminder_time` should fall | 12            |
| Bin types shown    | Which bin sensors to create                                       | All available |

The integration also schedules one extra refresh shortly before each `reminder_time`, so an automation firing on it sees up-to-date data even if a public holiday moved the collection since the last weekly poll.

---

## 🧩 Entities Created

| Entity                 | Description                                                 |
| ---------------------- | ----------------------------------------------------------- |
| `sensor.bin_general`   | Date of next general waste collection                       |
| `sensor.bin_recycling` | Date of next recycling collection                           |
| `sensor.bin_garden`    | Date of next green waste/FOGO collection (where applicable) |

Each sensor exposes attributes:

- `days_until` — number of days until next collection
- `collection_date` — ISO date of next collection
- `reminder_time` — timestamp, the configured reminder lead time before the start of `collection_date`; use it as a `time_date` automation trigger
- `following_collection_date` — ISO date of the collection after this one, when the schedule includes it
- `council` — detected council/LGA name
- `bin_colour` — lid colour, if known (useful for card icons)

Sensors only ever go `unavailable` when the last refresh actually failed (a connection problem, rate limiting, or an unexpected provider response). If the address itself has no more scheduled collections, the sensor instead reports `unknown` and a repair issue is raised under **Settings → Repairs** — see [Troubleshooting](#-troubleshooting).

---

## 🔔 Example Automation

A simple day-based reminder:

```yaml
automation:
  - alias: "Bin night reminder"
    trigger:
      - platform: numeric_state
        entity_id: sensor.bin_general
        attribute: days_until
        below: 1
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🗑️ Put the bins out!"
          message: "General waste collection is tomorrow morning."
```

Or, to fire exactly at the configured reminder lead time instead of once a day out:

```yaml
automation:
  - alias: "Bin night reminder (precise)"
    trigger:
      - platform: template
        value_template: >
          {{ now() >= (state_attr('sensor.bin_general', 'reminder_time') | as_datetime) }}
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🗑️ Put the bins out!"
          message: "General waste collection is coming up."
```

---

## 🖼️ Lovelace Card (optional)

The integration bundles a companion card for a friendlier visual display. Home Assistant serves it directly, so add it as a dashboard resource:

```yaml
resources:
  - url: /api/aussie_bin_night/static/bin-night-card.js
    type: module
```

Then add a card to a dashboard, either by searching for **"Bin Night"** in the card picker and choosing your sensors from its visual editor, or with YAML:

```yaml
type: custom:bin-night-card
entities:
  - sensor.bin_general
  - sensor.bin_recycling
  - sensor.bin_garden
```

The card shows each configured entity's name, next collection date, and a day countdown, with an "Unavailable" row for any entity that has no data.

---

## 🗺️ Supported Councils

All data are sourced from [Bin Night Tonight](https://binnighttonight.com/about/), which aggregates council data across Australia. See [Council coverage](https://binnighttonight.com/coverage) for a list of supported councils.

---

### Privacy

The selected address, its coordinates, detected council ID, and chosen bin types
are stored locally in Home Assistant's config entry so the integration can refresh
the collection schedule. Raw address-search responses are not stored. The selected
address details are sent to Bin Night Tonight only when looking up or refreshing
the household schedule. The integration never asks for or stores an API key or
other credential. Home Assistant's diagnostics download for this integration
(**Settings → Devices & Services → Aussie Bin Night → Download diagnostics**)
redacts the address, coordinates, and postcode; it keeps the council/LGA id and
collection schedule, since those are shared by every household in that
collection zone rather than identifying yours specifically.

---

## 🐛 Troubleshooting

- **My address isn't found** — the address search relies on your council's published address list or geocoding; try entering just the street name and suburb
- **I picked the wrong address, or moved house** — use **Settings → Devices & Services → Aussie Bin Night → ⋮ → Reconfigure** to search again; this keeps your automations and options intact
- **Dates look wrong** — some councils shift collections around public holidays; check [Council coverage](https://binnighttonight.com/coverage) to see if that council's data source accounts for this
- **Sensor shows "unavailable"** — the last refresh failed (connection issue, or the provider is rate-limiting requests); it clears on its own once refreshes succeed again. Check **Settings → Devices & Services → Aussie Bin Night → ⋮ → Reload** and the Home Assistant logs for this integration if it persists
- **Sensor shows "unknown" with no collection date** — the provider returned a valid but empty schedule for this address, which usually means it's dropped coverage; check **Settings → Repairs** for an actionable notice, and try **Reconfigure** to confirm the address
- **"Unexpected response" repair issue** — the provider's API returned data this integration doesn't recognise, which usually means its API changed; please [open an issue](https://github.com/mbpouri/hacs-aussie-bin-night/issues) with the details

---

## 🙏 Credits

Built on the [Home Assistant](https://www.home-assistant.io/) integration framework and distributed via [HACS](https://hacs.xyz/).
Bin collection data is sourced from [Bin Night Tonight](https://binnighttonight.com/about/).
This project is not affiliated with any local council or waste authority.

---

## 📄 License

[MIT](./LICENSE)

---

## Support

Please use the repository's issue tracker for bugs and feature requests. Do not include your complete home address or API credentials in public issues.
