import assert from "node:assert/strict";
import { test } from "node:test";
import { installDomStub } from "./dom-stub.mjs";

const definitions = installDomStub();
await import("../src/bin-night-card.js");
const BinNightCard = definitions.get("bin-night-card");

function createCard(config) {
  const card = new BinNightCard();
  card.connectedCallback();
  card.setConfig(config);
  return card;
}

test("registers itself in window.customCards for the card picker", () => {
  assert.ok(Array.isArray(window.customCards));
  assert.ok(window.customCards.some((entry) => entry.type === "bin-night-card"));
});

test("renders the README YAML shape with all three bin types", () => {
  const card = createCard({
    type: "custom:bin-night-card",
    entities: ["sensor.bin_general", "sensor.bin_recycling", "sensor.bin_garden"],
  });
  card.hass = {
    states: {
      "sensor.bin_general": {
        state: "2026-09-25",
        attributes: { friendly_name: "General Waste collection", collection_date: "2026-09-25", days_until: 3, bin_colour: "red" },
      },
      "sensor.bin_recycling": {
        state: "2026-09-20",
        attributes: { friendly_name: "Recycling collection", collection_date: "2026-09-20", days_until: 1, bin_colour: "yellow" },
      },
      "sensor.bin_garden": {
        state: "2026-09-19",
        attributes: { friendly_name: "Garden Waste collection", collection_date: "2026-09-19", days_until: 0, bin_colour: "dark green" },
      },
    },
  };
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /General Waste collection/);
  assert.match(html, /In 3 days/);
  assert.match(html, /Recycling collection/);
  assert.match(html, /Tomorrow/);
  assert.match(html, /Garden Waste collection/);
  assert.match(html, /Today/);
});

test("shows an unavailable row when the sensor has no upcoming collection", () => {
  const card = createCard({ entities: ["sensor.bin_general"] });
  card.hass = {
    states: {
      "sensor.bin_general": { state: "unknown", attributes: { friendly_name: "General Waste collection" } },
    },
  };
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /General Waste collection/);
  assert.match(html, /Unavailable/);
});

test("shows an unavailable row when the entity is unavailable", () => {
  const card = createCard({ entities: ["sensor.bin_general"] });
  card.hass = { states: { "sensor.bin_general": { state: "unavailable", attributes: {} } } };
  assert.match(card.shadowRoot.innerHTML, /Unavailable/);
});

test("shows an unavailable row when the configured entity does not exist", () => {
  const card = createCard({ entities: ["sensor.bin_missing"] });
  card.hass = { states: {} };
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /sensor\.bin_missing/);
  assert.match(html, /Unavailable/);
});

test("rejects missing configuration instead of rendering blank", () => {
  const card = new BinNightCard();
  assert.throws(() => card.setConfig({ entities: [] }), /Specify one or more/);
  assert.throws(() => card.setConfig({}), /Specify one or more/);
});

test("does not render before hass is set", () => {
  const card = new BinNightCard();
  card.connectedCallback();
  card.setConfig({ entities: ["sensor.bin_general"] });
  assert.equal(card.shadowRoot.innerHTML, "");
});

test("escapes characters that would otherwise break the aria-label attribute", () => {
  const card = createCard({ entities: ["sensor.bin_general"] });
  card.hass = {
    states: {
      "sensor.bin_general": {
        state: "2026-09-25",
        attributes: { friendly_name: 'General "Waste" <collection>', collection_date: "2026-09-25", days_until: 3 },
      },
    },
  };
  const html = card.shadowRoot.innerHTML;
  const expectedLabel = 'aria-label="General &quot;Waste&quot; &lt;collection&gt;, next collection 2026-09-25, In 3 days"';
  assert.ok(html.includes(expectedLabel), `expected escaped aria-label in:\n${html}`);
});
