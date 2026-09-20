// Runs in its own process (node --test isolates files), so it can import the card
// before Home Assistant's frontend exists, the way the real page does.
import assert from "node:assert/strict";
import { test } from "node:test";
import { installDomStub } from "./dom-stub.mjs";

const definitions = installDomStub({ definedElements: [] });
await import("../src/bin-night-card.js");

const cards = () => (window.customCards || []).filter((entry) => entry.type === "bin-night-card");

test("does not register until Home Assistant's frontend has loaded", async () => {
  assert.equal(definitions.get("bin-night-card"), undefined);
  assert.equal(cards().length, 0);

  // Home Assistant defines its own dashboard elements once its registry polyfill is in place.
  customElements.define("hui-view", class {});
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.ok(definitions.get("bin-night-card"), "card is defined once HA is ready");
  assert.equal(cards().length, 1);
  assert.equal(cards()[0].preview, true);
});

test("loading the module a second time neither throws nor registers the card twice", async () => {
  await import("../src/bin-night-card.js?second-copy");
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(cards().length, 1);
});
