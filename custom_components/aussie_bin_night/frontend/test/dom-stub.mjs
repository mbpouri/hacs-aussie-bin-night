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

export function installDomStub() {
  const definitions = new Map();

  class FakeShadowRoot {
    constructor() {
      this.innerHTML = "";
    }
  }

  class FakeHTMLElement {
    attachShadow() {
      this.shadowRoot = new FakeShadowRoot();
      return this.shadowRoot;
    }
  }

  globalThis.HTMLElement = FakeHTMLElement;
  globalThis.customElements = {
    define(name, ctor) {
      definitions.set(name, ctor);
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
