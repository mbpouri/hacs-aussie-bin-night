// Renders strictly from entity state/attributes (never calls the Bin Night Tonight
// API directly). Contract, defined in custom_components/aussie_bin_night/sensor.py:
// state is an ISO date or "unknown"/"unavailable"; attributes used here are
// `days_until` (int) and `collection_date` (ISO date), both present only when
// the state isn't "unknown", plus `bin_colour` (optional str) and `friendly_name`.
class BinNightCard extends HTMLElement {
  static getConfigForm() {
    return { schema: [{ name: "entities", required: true, selector: { entity: { multiple: true, filter: { domain: "sensor" } } } }] };
  }

  static getStubConfig() { return { entities: [] }; }

  setConfig(config) {
    if (!Array.isArray(config.entities) || !config.entities.length) throw new Error("Specify one or more Aussie Bin Night sensor entities.");
    this.config = config;
    this._render();
  }

  set hass(hass) { this._hass = hass; this._render(); }

  connectedCallback() { if (!this.shadowRoot) this.attachShadow({ mode: "open" }); this._render(); }

  getCardSize() { return 3; }

  _render() {
    if (!this.shadowRoot || !this.config || !this._hass) return;
    this.shadowRoot.innerHTML = `<style>
      :host { display:block; } ha-card { background:var(--ha-card-background,var(--card-background-color)); border-radius:var(--ha-card-border-radius,12px); box-shadow:var(--ha-card-box-shadow,none); color:var(--primary-text-color); overflow:hidden; } header { font-size:1.1em; font-weight:500; padding:16px 16px 8px; } ul { list-style:none; margin:0; padding:0; } .row { align-items:center; border-top:1px solid var(--divider-color); display:grid; gap:12px; grid-template-columns:42px 1fr auto; padding:12px 16px; } .bin { align-items:center; background:var(--bin-colour,var(--primary-color)); border-radius:8px 8px 5px 5px; color:white; display:flex; font-size:22px; height:38px; justify-content:center; position:relative; width:32px; } .bin::before { background:currentColor; border-radius:2px; content:""; height:4px; left:-3px; opacity:.85; position:absolute; right:-3px; top:-5px; } .info { min-width:0; } .name,.date,.empty { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; } .name { font-weight:500; } .date,.empty { color:var(--secondary-text-color); font-size:.9em; margin-top:2px; } .days { font-size:.9em; font-weight:500; text-align:right; white-space:nowrap; }
      </style><ha-card><header>Bin night</header><ul>${this.config.entities.map((id) => this._row(id)).join("")}</ul></ha-card>`;
  }

  _row(entityId) {
    const state = this._hass.states[entityId];
    const name = state?.attributes?.friendly_name || entityId;
    if (!state || state.state === "unavailable" || state.state === "unknown") {
      return `<li class="row" aria-label="${this._escapeAttr(`${name}, unavailable`)}"><div class="bin" aria-hidden="true">🗑</div><div class="info"><div class="name">${this._escape(name)}</div><div class="empty">Unavailable</div></div><div></div></li>`;
    }
    const a = state.attributes; const days = Number(a.days_until);
    const countdown = Number.isFinite(days) ? (days === 0 ? "Today" : days === 1 ? "Tomorrow" : `In ${days} days`) : "";
    const date = a.collection_date || state.state;
    const summary = `${name}, next collection ${date}${countdown ? `, ${countdown}` : ""}`;
    return `<li class="row" aria-label="${this._escapeAttr(summary)}"><div class="bin" aria-hidden="true" style="--bin-colour:${this._colour(a.bin_colour)}">🗑</div><div class="info"><div class="name">${this._escape(name)}</div><div class="date">${this._escape(date)}</div></div><div class="days">${this._escape(countdown)}</div></li>`;
  }

  _colour(colour) { return { red:"#d32f2f", yellow:"#f9a825", "dark green":"#2e7d32", "lime green":"#7cb342", purple:"#7b1fa2" }[colour] || "var(--primary-color)"; }
  _escape(value) { const element = document.createElement("span"); element.textContent = String(value ?? ""); return element.innerHTML; }
  _escapeAttr(value) { return String(value ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
}

// The integration loads this module automatically, but a manually added dashboard
// resource would load it a second time, and redefining an element throws.
if (!customElements.get("bin-night-card")) {
  customElements.define("bin-night-card", BinNightCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type:"bin-night-card", name:"Bin Night", description:"Shows the next household bin collections and their countdowns.", preview:false });
}
