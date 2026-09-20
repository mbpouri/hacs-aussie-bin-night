import assert from "node:assert/strict";
import { test } from "node:test";
import { installDomStub } from "./dom-stub.mjs";

const definitions = installDomStub();
await import("../src/bin-night-card.js");
const BinNightCard = definitions.get("bin-night-card");

const ATTRIBUTION = "Data provided by Bin Night Tonight";

function createCard(config) {
  const card = new BinNightCard();
  card.connectedCallback();
  card.setConfig(config);
  return card;
}

function sensor(binType, date, days, extra = {}) {
  return {
    state: date,
    attributes: {
      friendly_name: `Some device ${binType} collection`,
      bin_type: binType,
      collection_date: date,
      days_until: days,
      attribution: ATTRIBUTION,
      ...extra,
    },
  };
}

function names(card) {
  return [...card.shadowRoot.innerHTML.matchAll(/<div class="name">([^<]*)<\/div>/g)].map((m) => m[1]);
}

test("registers itself in window.customCards for the card picker", () => {
  assert.ok(Array.isArray(window.customCards));
  assert.ok(window.customCards.some((entry) => entry.type === "bin-night-card"));
});

test("renders the README YAML shape with friendly names and long dates", () => {
  const card = createCard({
    type: "custom:bin-night-card",
    entities: ["sensor.bin_general", "sensor.bin_recycling", "sensor.bin_garden"],
  });
  card.hass = {
    states: {
      "sensor.bin_general": sensor("general", "2026-09-25", 3, { bin_colour: "red" }),
      "sensor.bin_recycling": sensor("recycling", "2026-09-20", 1, { bin_colour: "yellow" }),
      "sensor.bin_garden": sensor("garden", "2026-09-19", 0, { bin_colour: "dark green" }),
    },
  };
  const html = card.shadowRoot.innerHTML;
  assert.deepEqual(names(card), ["Garden organics", "Recycling", "General waste"]);
  assert.match(html, /Friday 25 September/);
  assert.match(html, /<div class="num today">Today<\/div><div class="unit">0 days away<\/div>/);
  assert.match(html, /<div class="num">1<\/div><div class="unit">day away<\/div>/);
  assert.match(html, /<div class="num">3<\/div><div class="unit">days away<\/div>/);
});

test("shows one row per bin with only its next collection, however many bins there are", () => {
  const states = {};
  for (const [i, type] of ["general", "recycling", "garden", "glass", "fogo"].entries()) {
    states[`sensor.bin_${type}`] = sensor(type, `2026-09-2${i}`, i + 2, { following_collection_date: "2026-10-20" });
  }
  const card = createCard({});
  card.hass = { states };
  assert.deepEqual(names(card), ["General waste", "Recycling", "Garden organics", "Glass", "Food &amp; garden organics"]);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /20 October/);
});

test("lists the soonest collection first", () => {
  const card = createCard({});
  card.hass = {
    states: {
      "sensor.bin_general": sensor("general", "2026-09-29", 10),
      "sensor.bin_recycling": sensor("recycling", "2026-09-22", 3),
    },
  };
  assert.deepEqual(names(card), ["Recycling", "General waste"]);
});

test("with no entities configured, discovers only this integration's sensors", () => {
  const card = createCard({});
  card.hass = {
    entities: { "sensor.bin_late": { platform: "aussie_bin_night" }, "sensor.other": { platform: "other" } },
    states: {
      "sensor.bin_late": sensor("general", "2026-09-29", 10),
      "sensor.other": { state: "5", attributes: { friendly_name: "Unrelated sensor" } },
      "light.kitchen": { state: "on", attributes: { friendly_name: "Kitchen light" } },
    },
  };
  assert.deepEqual(names(card), ["General waste"]);
});

test("an explicit entities list overrides discovery", () => {
  const card = createCard({ entities: ["sensor.bin_a"] });
  card.hass = {
    states: {
      "sensor.bin_a": sensor("recycling", "2026-09-22", 3),
      "sensor.bin_b": sensor("general", "2026-09-23", 4),
    },
  };
  assert.deepEqual(names(card), ["Recycling"]);
});

test("labels and colours every bin type the provider documents", () => {
  const card = createCard({});
  const types = { general: "red", recycling: "yellow", garden: "dark green", fogo: "lime green", glass: "purple", hard: "orange" };
  const states = {};
  for (const [i, [type, colour]] of Object.entries(types).entries()) states[`sensor.bin_${type}`] = sensor(type, `2026-09-2${i}`, i, { bin_colour: colour });
  card.hass = { states };
  assert.deepEqual(names(card), ["General waste", "Recycling", "Garden organics", "Food &amp; garden organics", "Glass", "Hard waste"]);
  for (const lid of ["#e53935", "#fbc02d", "#2e7d32", "#7cb342", "#7b1fa2", "#e67e22"]) assert.ok(card.shadowRoot.innerHTML.includes(`fill="${lid}"`), lid);
});

test("unknown bin types get a readable fallback label", () => {
  const card = createCard({});
  card.hass = { states: { "sensor.bin_hard_waste": sensor("hard_waste", "2026-09-22", 3) } };
  assert.deepEqual(names(card), ["Hard waste"]);
});

test("shows unavailable sensors after the collections instead of dropping them", () => {
  const card = createCard({ entities: ["sensor.bin_general", "sensor.bin_recycling", "sensor.bin_missing"] });
  card.hass = {
    states: {
      "sensor.bin_general": { state: "unavailable", attributes: { bin_type: "general" } },
      "sensor.bin_recycling": sensor("recycling", "2026-09-22", 3),
    },
  };
  const html = card.shadowRoot.innerHTML;
  assert.deepEqual(names(card), ["Recycling", "General waste", "sensor.bin_missing"]);
  assert.equal((html.match(/Unavailable/g) || []).length, 2);
});

test("shows labelled sample data when there are no sensors, so the picker preview is not empty", () => {
  const card = createCard({});
  card.hass = { states: { "light.kitchen": { state: "on", attributes: {} } } };
  assert.deepEqual(names(card), ["General waste", "Recycling", "Garden organics"]);
  assert.match(card.shadowRoot.innerHTML, /Sample data/);
});

test("does not show sample data next to real sensors", () => {
  const card = createCard({});
  card.hass = { states: { "sensor.bin_general": sensor("general", "2026-09-22", 3) } };
  assert.deepEqual(names(card), ["General waste"]);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /Sample data/);
});

test("is registered with a live preview in the card picker", () => {
  assert.equal(window.customCards.find((entry) => entry.type === "bin-night-card").preview, true);
});

test("rejects malformed configuration", () => {
  const card = new BinNightCard();
  assert.throws(() => card.setConfig({ entities: "sensor.bin_general" }), /must be a list/);
  assert.doesNotThrow(() => card.setConfig({}));
});

test("the config form only offers this integration's sensors and needs no entities", () => {
  const form = BinNightCard.getConfigForm();
  assert.equal(form.schema[0].selector.entity.filter.integration, "aussie_bin_night");
  assert.notEqual(form.schema[0].required, true);
  assert.equal(form.schema.length, 1);
  assert.deepEqual(BinNightCard.getStubConfig(), {});
});

test("does not render before hass is set", () => {
  const card = new BinNightCard();
  card.connectedCallback();
  card.setConfig({ entities: ["sensor.bin_general"] });
  assert.equal(card.shadowRoot.innerHTML, "");
});

test("gives each row one accessible summary, with attribute-breaking characters escaped", () => {
  const card = createCard({});
  card.hass = { states: { "sensor.bin_x": sensor('a"b<c>', "2026-09-25", 3) } };
  const html = card.shadowRoot.innerHTML;
  assert.ok(html.includes('aria-label="A&quot;b&lt;c&gt;, Friday 25 September, 3 days away"'), html);
});

test("shows a distinct message for a stream with no upcoming date versus an unavailable one", () => {
  const card = createCard({ entities: ["sensor.bin_hard", "sensor.bin_general"] });
  card.hass = {
    states: {
      "sensor.bin_hard": { state: "unknown", attributes: { bin_type: "hard" } },
      "sensor.bin_general": { state: "unavailable", attributes: { bin_type: "general" } },
    },
  };
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /Hard waste<\/div><div class="empty">No upcoming collection</);
  assert.match(html, /General waste<\/div><div class="empty">Unavailable</);
  assert.ok(html.includes('aria-label="Hard waste, no upcoming collection"'), html);
});

test("does not rebuild the DOM when an unrelated entity changes", () => {
  const card = createCard({});
  const states = { "sensor.bin_general": sensor("general", "2026-09-22", 3), "light.kitchen": { state: "on", attributes: {} } };
  card.hass = { states };
  let writes = 0;
  const root = card.shadowRoot;
  let html = root.innerHTML;
  Object.defineProperty(root, "innerHTML", { get: () => html, set: (value) => { writes++; html = value; } });

  card.hass = { states: { ...states, "light.kitchen": { state: "off", attributes: {} } } };
  assert.equal(writes, 0, "an unrelated light changing should not re-render");

  card.hass = { states: { ...states, "sensor.bin_general": sensor("general", "2026-09-22", 2) } };
  assert.equal(writes, 1, "the days_until rollover should re-render");
  assert.match(html, /<div class="num">2<\/div>/);

  card.setConfig({ entities: ["sensor.bin_general"] });
  assert.equal(writes, 2, "a new config should always re-render");
});

test("defines the bin gradients once per card, not once per row", () => {
  const card = createCard({});
  card.hass = {
    states: {
      "sensor.bin_general": sensor("general", "2026-09-22", 3),
      "sensor.bin_recycling": sensor("recycling", "2026-09-23", 4),
      "sensor.bin_garden": sensor("garden", "2026-09-24", 5),
    },
  };
  const html = card.shadowRoot.innerHTML;
  assert.equal((html.match(/id="bnBody"/g) || []).length, 1);
  assert.equal((html.match(/id="bnLid"/g) || []).length, 1);
  assert.equal((html.match(/url\(#bnBody\)/g) || []).length, 3);
});

test("real rows are keyboard-focusable buttons that open more-info", () => {
  const card = createCard({});
  card.hass = { states: { "sensor.bin_general": sensor("general", "2026-09-22", 3) } };
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /role="button" tabindex="0" data-entity="sensor.bin_general"/);

  const target = { closest: () => ({ dataset: { entity: "sensor.bin_general" } }) };
  let prevented = 0;
  const event = (extra) => ({ target, preventDefault: () => prevented++, ...extra });

  card.shadowRoot.dispatch("click", event());
  card.shadowRoot.dispatch("keydown", event({ key: "Enter" }));
  card.shadowRoot.dispatch("keydown", event({ key: " " }));
  card.shadowRoot.dispatch("keydown", event({ key: "a" }));

  assert.equal(card.firedEvents.length, 3, "click, Enter and Space open more-info; other keys do not");
  assert.equal(prevented, 3);
  for (const fired of card.firedEvents) {
    assert.equal(fired.type, "hass-more-info");
    assert.equal(fired.detail.entityId, "sensor.bin_general");
    assert.equal(fired.bubbles, true);
    assert.equal(fired.composed, true);
  }
});

test("ignores activation that did not land on a row", () => {
  const card = createCard({});
  card.hass = { states: { "sensor.bin_general": sensor("general", "2026-09-22", 3) } };
  card.shadowRoot.dispatch("click", { target: { closest: () => null }, preventDefault() {} });
  assert.equal(card.firedEvents, undefined);
});

test("sample rows and missing entities are not buttons", () => {
  const sample = createCard({});
  sample.hass = { states: {} };
  assert.doesNotMatch(sample.shadowRoot.innerHTML, /role="button"/);

  const missing = createCard({ entities: ["sensor.bin_missing"] });
  missing.hass = { states: {} };
  assert.doesNotMatch(missing.shadowRoot.innerHTML, /role="button"/);
  assert.match(missing.shadowRoot.innerHTML, /sensor\.bin_missing/);
});

test("offers sizing hints for sections dashboards", () => {
  const card = createCard({});
  const options = card.getGridOptions();
  assert.equal(options.columns, 12);
  assert.ok(options.min_columns <= options.columns);
});
