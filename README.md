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

### Options

After setup, you can adjust via **Configure**:

| Option             | Description                                          | Default       |
| ------------------ | ---------------------------------------------------- | ------------- |
| Update interval    | How often to refresh schedule data                   | weekly        |
| Reminder lead time | Hours before collection to mark sensor as "upcoming" | 12            |
| Bin types shown    | Which bin sensors to create                          | All available |

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
- `council` — detected council/LGA name
- `bin_colour` — lid colour, if known (useful for card icons)

---

## 🔔 Example Automation

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

---

## 🖼️ Lovelace Card (optional)

A companion card is available in the `lovelace/` folder for a friendlier visual display. Add it as a resource:

```yaml
resources:
  - url: /hacsfiles/aussie-bin-night/bin-night-card.js
    type: module
```

Then add to a dashboard:

```yaml
type: custom:bin-night-card
entities:
  - sensor.bin_general
  - sensor.bin_recycling
  - sensor.bin_garden
```

---

## 🗺️ Supported Councils

All data are sourced from [Bin Night Tonight](https://binnighttonight.com/about/), which aggregates council data across Australia. See [Council coverage](https://binnighttonight.com/coverage) for a list of supported councils.

---

## 🐛 Troubleshooting

- **My address isn't found** — the address search relies on your council's published address list or geocoding; try entering just the street name and suburb
- **Dates look wrong** — some councils shift collections around public holidays; check `COUNCILS.md` to see if that council's data source accounts for this
- **Sensor shows "unavailable"** — check **Settings → Devices & Services → Aussie Bin Night → ⋮ → Reload**, and review the Home Assistant logs for this integration

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
