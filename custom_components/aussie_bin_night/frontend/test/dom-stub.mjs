// A hand-rolled stand-in for the handful of DOM APIs bin-night-card.js touches
// (HTMLElement, attachShadow, customElements, document.createElement for text
// escaping). Kept in-repo instead of pulling in jsdom so the frontend project
// stays dependency-free even for its tests.

function escapeText(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// `definedElements` are elements Home Assistant would already have defined by the time the
// card runs. The card waits for "hui-view", so tests that want it to register straight away
// leave the default, and tests of the waiting behaviour pass an empty list.
export function installDomStub({ definedElements = ["hui-view"] } = {}) {
  const definitions = new Map(definedElements.map((name) => [name, class {}]));
  const waiting = new Map();

  class FakeShadowRoot {
    constructor() {
      this.innerHTML = "";
      this.listeners = {};
    }

    addEventListener(type, handler) {
      (this.listeners[type] ||= []).push(handler);
    }

    // Test helper: deliver an event to the listeners the way the browser would.
    dispatch(type, event) {
      for (const handler of this.listeners[type] || []) handler(event);
    }
  }

  class FakeHTMLElement {
    attachShadow() {
      this.shadowRoot = new FakeShadowRoot();
      return this.shadowRoot;
    }

    // Records events the element fires so tests can assert on them.
    dispatchEvent(event) {
      (this.firedEvents ||= []).push(event);
      return true;
    }
  }

  globalThis.HTMLElement = FakeHTMLElement;
  globalThis.customElements = {
    define(name, ctor) {
      definitions.set(name, ctor);
      for (const resolve of waiting.get(name) || []) resolve(ctor);
      waiting.delete(name);
    },
    get(name) {
      return definitions.get(name);
    },
    whenDefined(name) {
      if (definitions.has(name)) return Promise.resolve(definitions.get(name));
      return new Promise((resolve) => waiting.set(name, [...(waiting.get(name) || []), resolve]));
    },
  };
  globalThis.window = globalThis;
  globalThis.document = {
    createElement() {
      let text = "";
      return {
        set textContent(value) {
          text = String(value ?? "");
        },
        get textContent() {
          return text;
        },
        get innerHTML() {
          return escapeText(text);
        },
      };
    },
  };

  return definitions;
}
