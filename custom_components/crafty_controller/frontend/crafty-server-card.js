/*
 * Crafty Minecraft Server card for Home Assistant.
 * Loaded automatically by the crafty_controller integration.
 *
 *   type: custom:crafty-server-card
 *   device_id: <Minecraft server device>
 *   title: Optional override
 *   show_players: true
 *   show_stats: true
 *   show_controls: true
 */
const CARD_VERSION = "0.1.0";
const PLATFORM = "crafty_controller";

const KEYS = {
  running: "binary_sensor",
  crashed: "binary_sensor",
  players_online: "sensor",
  version: "sensor",
  started: "sensor",
  cpu: "sensor",
  memory: "sensor",
  world_size: "sensor",
  server: "switch",
  start: "button",
  stop: "button",
  restart: "button",
  backup: "button",
  player_activity: "event",
};

function findEntities(hass, deviceId) {
  const found = {};
  if (!hass || !deviceId) return found;
  const entries = Object.values(hass.entities || {}).filter(
    (e) => e.device_id === deviceId && (!e.platform || e.platform === PLATFORM)
  );
  for (const [key, domain] of Object.entries(KEYS)) {
    const match =
      entries.find((e) => e.translation_key === key && e.entity_id.startsWith(domain + ".")) ||
      entries.find((e) => e.entity_id.startsWith(domain + ".") && e.entity_id.endsWith("_" + key));
    if (match) found[key] = match.entity_id;
  }
  return found;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function duration(fromIso) {
  if (!fromIso) return "";
  const ms = Date.now() - new Date(fromIso).getTime();
  if (!isFinite(ms) || ms < 0) return "";
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

function hueFor(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

class CraftyServerCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("crafty-server-card-editor");
  }

  static getStubConfig(hass) {
    const sw = Object.values(hass?.entities || {}).find(
      (e) => e.platform === PLATFORM && e.entity_id.startsWith("switch.") && e.device_id
    );
    return { device_id: sw ? sw.device_id : "", show_players: true, show_stats: true, show_controls: true };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { show_players: true, show_stats: true, show_controls: true, ...config };
    this._confirm = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._lastKey = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const ents = findEntities(hass, this._config?.device_id);
    this._ents = ents;
    const key = Object.values(ents)
      .map((id) => {
        const s = hass.states[id];
        return s ? `${id}=${s.state}|${s.last_updated}` : id;
      })
      .join(";");
    if (key !== this._lastKey) {
      this._lastKey = key;
      this._render();
    }
  }

  connectedCallback() {
    this._tick = setInterval(() => this._render(), 60000);
  }

  disconnectedCallback() {
    clearInterval(this._tick);
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _state(key) {
    const id = this._ents?.[key];
    return id ? this._hass?.states[id] : undefined;
  }

  _fmt(key) {
    const s = this._state(key);
    if (!s || s.state === "unavailable" || s.state === "unknown") return "\u2014";
    if (this._hass.formatEntityState) return this._hass.formatEntityState(s);
    const unit = s.attributes.unit_of_measurement;
    return unit ? `${s.state} ${unit}` : s.state;
  }

  _press(key) {
    const id = this._ents?.[key];
    if (!id) return;
    if ((key === "stop" || key === "restart") && this._confirm !== key) {
      this._confirm = key;
      clearTimeout(this._confirmTimer);
      this._confirmTimer = setTimeout(() => {
        this._confirm = null;
        this._render();
      }, 4000);
      this._render();
      return;
    }
    this._confirm = null;
    this._hass.callService("button", "press", { entity_id: id });
    this._render();
  }

  _moreInfo(key) {
    const entityId = this._ents?.[key];
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } })
    );
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const cfg = this._config;
    const hass = this._hass;

    if (!cfg.device_id) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="empty">Choose a Minecraft server in the card editor.</div></ha-card>`;
      return;
    }
    if (!hass) return;
    if (!this._ents || !this._ents.running) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="empty">No Crafty server entities found for this device.</div></ha-card>`;
      return;
    }

    const device = hass.devices?.[cfg.device_id];
    const title = cfg.title || device?.name_by_user || device?.name || "Minecraft";
    const running = this._state("running")?.state === "on";
    const crashed = this._state("crashed")?.state === "on";
    const unavailable = this._state("running")?.state === "unavailable";
    const status = unavailable ? "offline" : crashed ? "crashed" : running ? "running" : "stopped";
    const statusLabel = { offline: "Unavailable", crashed: "Crashed", running: "Running", stopped: "Stopped" }[status];

    const playersState = this._state("players_online");
    const attrs = playersState?.attributes || {};
    const details = attrs.player_details || (attrs.players || []).map((n) => ({ name: n }));
    const count = running ? Number(playersState?.state) || 0 : 0;
    const max = attrs.max_players;
    const edition = attrs.edition === "bedrock" ? "Bedrock" : attrs.edition === "java" ? "Java" : "";
    const version = this._fmt("version");
    const started = this._state("started")?.state;
    const uptime = running && started && started !== "unknown" ? duration(started) : "";

    const last = this._state("player_activity");
    let lastLine = "";
    if (last && last.state && !["unknown", "unavailable"].includes(last.state) && last.attributes.player) {
      const verb = last.attributes.event_type === "joined" ? "joined" : "left";
      lastLine = `${esc(last.attributes.player)} ${verb} ${esc(duration(last.state))}${duration(last.state) === "just now" ? "" : " ago"}`;
    }

    const playersHtml = !cfg.show_players
      ? ""
      : `<div class="section">
          <div class="section-head" data-more="players_online">
            <span>Players</span><span class="count">${count}${max ? ` / ${esc(max)}` : ""}</span>
          </div>
          ${
            running && details.length
              ? `<div class="players">${details
                  .map((p) => {
                    const name = String(p.name || "");
                    const since = duration(p.since);
                    return `<div class="player" title="${esc(name)}">
                      <div class="avatar" style="--h:${hueFor(name)}">${esc(name.replace(/^\./, "").charAt(0).toUpperCase())}</div>
                      <div class="pname">${esc(name)}</div>
                      ${since ? `<div class="since">${esc(since)}</div>` : ""}
                    </div>`;
                  })
                  .join("")}</div>`
              : `<div class="muted">${running ? "Nobody online" : "Server is not running"}</div>`
          }
          ${lastLine ? `<div class="last" data-more="player_activity">${lastLine}</div>` : ""}
        </div>`;

    const statsHtml = !cfg.show_stats
      ? ""
      : `<div class="stats">
          ${[
            ["cpu", "CPU"],
            ["memory", "Memory"],
            ["world_size", "World"],
          ]
            .filter(([k]) => this._ents[k])
            .map(
              ([k, label]) =>
                `<div class="stat" data-more="${k}"><div class="sv">${esc(this._fmt(k))}</div><div class="sl">${label}</div></div>`
            )
            .join("")}
        </div>`;

    const btn = (key, icon, label, show = true) =>
      this._ents[key] && show
        ? `<button class="btn ${this._confirm === key ? "confirm" : ""}" data-press="${key}">
             <ha-icon icon="${icon}"></ha-icon><span>${this._confirm === key ? "Confirm?" : label}</span>
           </button>`
        : "";

    const controlsHtml = !cfg.show_controls
      ? ""
      : `<div class="controls">
          ${btn("start", "mdi:play", "Start", !running)}
          ${btn("stop", "mdi:stop", "Stop", running)}
          ${btn("restart", "mdi:restart", "Restart", running)}
          ${btn("backup", "mdi:backup-restore", "Backup")}
        </div>`;

    this.shadowRoot.innerHTML = `${STYLE}
      <ha-card>
        <div class="header">
          <div class="icon ${status}"><ha-icon icon="mdi:minecraft"></ha-icon></div>
          <div class="titles">
            <div class="title">${esc(title)}</div>
            <div class="sub">${[edition, version !== "\u2014" ? version : "", uptime ? `up ${uptime}` : ""]
              .filter(Boolean)
              .map(esc)
              .join(" \u00b7 ")}</div>
          </div>
          <div class="pill ${status}" data-more="running">${statusLabel}</div>
        </div>
        ${playersHtml}
        ${statsHtml}
        ${controlsHtml}
      </ha-card>`;

    this.shadowRoot.querySelectorAll("[data-press]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._press(el.dataset.press);
      })
    );
    this.shadowRoot.querySelectorAll("[data-more]").forEach((el) =>
      el.addEventListener("click", () => this._moreInfo(el.dataset.more))
    );
  }
}

const STYLE = `<style>
  ha-card { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
  .empty { color: var(--secondary-text-color); padding: 8px 0; }
  .header { display: flex; align-items: center; gap: 12px; }
  .icon { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center;
    background: var(--secondary-background-color); color: var(--secondary-text-color); flex: none; }
  .icon.running { background: rgba(76,175,80,.18); color: var(--success-color, #43a047); }
  .icon.crashed { background: rgba(244,67,54,.18); color: var(--error-color, #e53935); }
  .titles { flex: 1; min-width: 0; }
  .title { font-size: 1.15em; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { color: var(--secondary-text-color); font-size: .85em; margin-top: 2px; }
  .pill { font-size: .78em; font-weight: 600; padding: 4px 10px; border-radius: 999px; cursor: pointer;
    background: var(--secondary-background-color); color: var(--secondary-text-color); flex: none; }
  .pill.running { background: rgba(76,175,80,.18); color: var(--success-color, #43a047); }
  .pill.crashed { background: rgba(244,67,54,.18); color: var(--error-color, #e53935); }
  .section { display: flex; flex-direction: column; gap: 8px; }
  .section-head { display: flex; justify-content: space-between; font-weight: 500; cursor: pointer; }
  .count { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .muted { color: var(--secondary-text-color); font-size: .9em; }
  .players { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 10px; }
  .player { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; }
  .avatar { width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center;
    font-weight: 700; color: #fff; background: hsl(var(--h), 55%, 45%);
    box-shadow: inset 0 -4px 0 rgba(0,0,0,.18); }
  .pname { font-size: .8em; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .since { font-size: .72em; color: var(--secondary-text-color); }
  .last { font-size: .8em; color: var(--secondary-text-color); cursor: pointer; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(80px, 1fr)); gap: 8px; }
  .stat { background: var(--secondary-background-color); border-radius: 10px; padding: 8px 10px; cursor: pointer; }
  .sv { font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .sl { font-size: .75em; color: var(--secondary-text-color); }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; }
  .controls:empty { display: none; }
  .btn { flex: 1 1 auto; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    border: none; border-radius: 10px; padding: 9px 12px; cursor: pointer; font: inherit; font-size: .9em;
    background: var(--secondary-background-color); color: var(--primary-text-color); }
  .btn:hover { filter: brightness(1.08); }
  .btn.confirm { background: var(--warning-color, #ffa000); color: #000; }
  .btn ha-icon { --mdc-icon-size: 18px; }
</style>`;

const EDITOR_SCHEMA = [
  {
    name: "device_id",
    required: true,
    selector: { device: { integration: PLATFORM, entity: [{ domain: "switch" }] } },
  },
  { name: "title", selector: { text: {} } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "show_players", selector: { boolean: {} } },
      { name: "show_stats", selector: { boolean: {} } },
      { name: "show_controls", selector: { boolean: {} } },
    ],
  },
];

const EDITOR_LABELS = {
  device_id: "Minecraft server",
  title: "Title (optional)",
  show_players: "Players",
  show_stats: "Stats",
  show_controls: "Controls",
};

class CraftyServerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _update() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => EDITOR_LABELS[s.name] ?? s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this._config = ev.detail.value;
        this.dispatchEvent(
          new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })
        );
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = EDITOR_SCHEMA;
    this._form.data = { show_players: true, show_stats: true, show_controls: true, ...this._config };
  }
}

if (!customElements.get("crafty-server-card")) customElements.define("crafty-server-card", CraftyServerCard);
if (!customElements.get("crafty-server-card-editor"))
  customElements.define("crafty-server-card-editor", CraftyServerCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "crafty-server-card")) {
  window.customCards.push({
    type: "crafty-server-card",
    name: "Crafty Minecraft Server",
    description: "Status, players, stats and controls for a Minecraft server managed by Crafty Controller.",
    preview: true,
    documentationURL: "https://github.com/geoffreykobrien/bedrock-homeassistant",
  });
}

console.info(`%c CRAFTY-SERVER-CARD %c v${CARD_VERSION} `, "background:#4caf50;color:#fff", "");
