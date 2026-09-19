// Renders strictly from entity state/attributes (never calls the Bin Night Tonight
// API directly). Contract, defined in custom_components/aussie_bin_night/sensor.py:
// state is an ISO date or "unknown"/"unavailable"; attributes used here are
// `collection_date` (ISO date) and `days_until` (int), present only when the state
// isn't "unknown", plus `bin_type`, `bin_colour` and `attribution`. With no
// `entities` configured the card discovers this integration's sensors itself. It
// shows one row per bin with its next collection, soonest first.
const DOMAIN = "aussie_bin_night";
const ATTRIBUTION = "Data provided by Bin Night Tonight";

const LABELS = {
  general: "General waste",
  recycling: "Recycling",
  garden: "Garden organics",
  fogo: "Food & garden organics",
  glass: "Glass",
  hard: "Hard waste",
};
const LID_COLOURS = { red: "#e53935", yellow: "#fbc02d", "dark green": "#2e7d32", "lime green": "#7cb342", purple: "#7b1fa2", orange: "#e67e22" };

class BinNightCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [{ name: "entities", selector: { entity: { multiple: true, filter: { integration: DOMAIN, domain: "sensor" } } } }],
      computeLabel: () => "Sensors (leave empty to show all)",
    };
  }

  static getStubConfig() { return {}; }

  setConfig(config) {
    if (config.entities !== undefined && !Array.isArray(config.entities)) throw new Error("`entities` must be a list of Aussie Bin Night sensor entities.");
    this.config = config;
    this._render();
  }

  set hass(hass) { this._hass = hass; this._render(); }

  connectedCallback() { if (!this.shadowRoot) this.attachShadow({ mode: "open" }); this._render(); }

  getCardSize() { return Math.max(2, this._rowCount || 3); }

  _render() {
    if (!this.shadowRoot || !this.config || !this._hass) return;
    const rows = this._rows();
    this._rowCount = rows.length;
    this.shadowRoot.innerHTML = `<style>
      :host { display:block; } ha-card { background:var(--ha-card-background,var(--card-background-color)); border-radius:var(--ha-card-border-radius,12px); box-shadow:var(--ha-card-box-shadow,none); color:var(--primary-text-color); overflow:hidden; }
      ul { list-style:none; margin:0; padding:4px 0; }
      .row { align-items:center; display:grid; gap:14px; grid-template-columns:36px 1fr auto; padding:12px 16px; }
      .row + .row { border-top:1px solid var(--divider-color); }
      .icon svg { display:block; filter:drop-shadow(0 1px 1px rgba(0,0,0,.25)); height:52px; margin:0 auto; width:34px; }
      .info { min-width:0; }
      .name { font-size:1.05em; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .date,.empty { color:var(--secondary-text-color); font-size:.9em; margin-top:2px; }
      .empty { white-space:normal; }
      .count { text-align:right; white-space:nowrap; }
      .num { font-size:1.3em; font-weight:700; line-height:1.2; }
      .num.today { color:var(--success-color,#2e7d32); }
      .unit { color:var(--secondary-text-color); font-size:.8em; }
    </style><ha-card><ul aria-label="Upcoming bin collections">${rows.join("")}</ul></ha-card>`;
  }

  _rows() {
    const ids = this._entityIds();
    const entries = [];
    const unavailable = [];
    for (const id of ids) {
      const state = this._hass.states[id];
      if (!state || state.state === "unavailable" || state.state === "unknown") { unavailable.push(id); continue; }
      const a = state.attributes;
      const date = a.collection_date || state.state;
      const days = Number(a.days_until);
      entries.push({ id, date, days: Number.isFinite(days) ? days : null, a });
    }
    entries.sort((x, y) => x.date.localeCompare(y.date) || this._label(x.id, x.a).localeCompare(this._label(y.id, y.a)));
    const rows = entries.map((e) => this._row(e));
    rows.push(...unavailable.map((id) => this._unavailableRow(id)));
    if (!rows.length) rows.push(`<li class="row" aria-label="No Aussie Bin Night sensors found"><div></div><div class="info"><div class="empty">No Aussie Bin Night sensors found. Set up the integration first.</div></div><div></div></li>`);
    return rows;
  }

  _entityIds() {
    if (this.config.entities && this.config.entities.length) return this.config.entities;
    const states = this._hass.states;
    return Object.keys(states).filter((id) => id.startsWith("sensor.") && (this._hass.entities?.[id]?.platform === DOMAIN || states[id].attributes.attribution === ATTRIBUTION));
  }

  _row({ id, date, days, a }) {
    const name = this._label(id, a);
    const when = this._formatDate(date);
    const today = days === 0;
    const num = today ? "Today" : days === null ? "" : String(days);
    const unit = days === null ? "" : `${days === 1 ? "day" : "days"} away`;
    const summary = `${name}, ${when}${days === null ? "" : today ? ", today" : `, ${days} ${unit}`}`;
    return `<li class="row" aria-label="${this._escapeAttr(summary)}"><div class="icon" aria-hidden="true">${this._bin(LID_COLOURS[a.bin_colour])}</div><div class="info"><div class="name">${this._escape(name)}</div><div class="date">${this._escape(when)}</div></div><div class="count"><div class="num${today ? " today" : ""}">${this._escape(num)}</div><div class="unit">${this._escape(today ? "0 days away" : unit)}</div></div></li>`;
  }

  _unavailableRow(id) {
    const state = this._hass.states[id];
    const name = state ? this._label(id, state.attributes) : id;
    return `<li class="row" aria-label="${this._escapeAttr(`${name}, unavailable`)}"><div class="icon" aria-hidden="true">${this._bin()}</div><div class="info"><div class="name">${this._escape(name)}</div><div class="empty">Unavailable</div></div><div></div></li>`;
  }

  _label(id, a) {
    const type = a.bin_type || id.replace(/^sensor\.bin_/, "");
    return LABELS[type] || type.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }

  _formatDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    if (!y || !m || !d) return iso;
    const parts = new Intl.DateTimeFormat(this._hass.locale?.language || "en-AU", { weekday: "long", day: "numeric", month: "long" }).formatToParts(new Date(y, m - 1, d));
    const get = (type) => parts.find((p) => p.type === type)?.value;
    return `${get("weekday")} ${get("day")} ${get("month")}`;
  }

  _bin(lid = "var(--disabled-text-color,#9e9e9e)") {
    return `<svg viewBox="0 0 32 50" focusable="false">`
      + `<defs><linearGradient id="bnBody" x1="0" x2="1"><stop offset="0" stop-color="#5a6472"/><stop offset=".45" stop-color="#3b4451"/><stop offset="1" stop-color="#242b35"/></linearGradient>`
      + `<linearGradient id="bnLid" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".5"/><stop offset=".5" stop-color="#fff" stop-opacity=".05"/><stop offset="1" stop-color="#000" stop-opacity=".28"/></linearGradient></defs>`
      + `<ellipse cx="16" cy="48" rx="12" ry="1.5" fill="rgba(0,0,0,.22)"/>`
      + `<path d="M6.5 13H25.5L23.8 43a2 2 0 0 1-2 1.9H10.2a2 2 0 0 1-2-1.9Z" fill="url(#bnBody)"/>`
      + `<path d="M7 14h3.2l1 28.6h-.9a1.4 1.4 0 0 1-1.4-1.3Z" fill="#fff" opacity=".1"/>`
      + `<rect x="11" y="17" width="1.2" height="22" rx=".6" fill="#fff" opacity=".08"/><rect x="15.4" y="17" width="1.2" height="22" rx=".6" fill="#fff" opacity=".08"/><rect x="19.8" y="17" width="1.2" height="22" rx=".6" fill="#fff" opacity=".08"/>`
      + `<rect x="5.5" y="13" width="21" height="2" rx="1" fill="#000" opacity=".3"/>`
      + `<rect x="11" y="3.5" width="10" height="5" rx="2" fill="${lid}"/><rect x="11" y="3.5" width="10" height="5" rx="2" fill="#000" opacity=".2"/><rect x="13" y="5.1" width="6" height="1.8" rx=".9" fill="#000" opacity=".4"/>`
      + `<rect x="4" y="7.5" width="24" height="6.5" rx="2.2" fill="${lid}"/><rect x="4" y="7.5" width="24" height="6.5" rx="2.2" fill="url(#bnLid)"/>`
      + `<rect x="6" y="8.4" width="20" height="1" rx=".5" fill="#fff" opacity=".35"/>`
      + `<circle cx="11" cy="45.4" r="2.7" fill="#171c22"/><circle cx="21" cy="45.4" r="2.7" fill="#171c22"/><circle cx="11" cy="45.4" r="1" fill="#8b95a3"/><circle cx="21" cy="45.4" r="1" fill="#8b95a3"/>`
      + `</svg>`;
  }

  _escape(value) { const element = document.createElement("span"); element.textContent = String(value ?? ""); return element.innerHTML; }
  _escapeAttr(value) { return String(value ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
}

// The integration loads this module automatically, but a manually added dashboard
// resource would load it a second time, and redefining an element throws.
if (!customElements.get("bin-night-card")) {
  customElements.define("bin-night-card", BinNightCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type:"bin-night-card", name:"Bin Night", description:"Shows your upcoming household bin collections with day countdowns.", preview:false });
}
