/*
 * ViewSonic Projector Card
 *
 * Source is write-only on this projector: it accepts "set source to HDMI" but
 * refuses "what source are you on?" (verified NAK 5/5, power confirmed on, on a
 * quiet line). The highlighted input is therefore the last commanded one, drawn
 * dashed with an "assumed" tag while the entity reports assumed_state. If that
 * read ever starts working the highlight becomes solid, with no change here.
 *
 * DEPLOYMENT NOTE: on the author's Home Assistant, /local/ serves nothing --
 * even resources registered long before this card 404 -- so this file is not
 * loaded from /config/www. It is registered as an INLINE dashboard resource
 * (a data: URI) instead. Edits here must be pushed to that resource to take
 * effect; copying the file alone does nothing on that instance.
 *
 *   type: custom:viewsonic-projector-card
 *   power: switch.viewsonic_projector_power        # all keys optional
 *   source: select.viewsonic_projector_source
 *   lamp_mode: select.viewsonic_projector_lamp_mode
 *   lamp_hours: sensor.viewsonic_projector_lamp_hours
 *   responding: binary_sensor.viewsonic_projector_responding
 *   button_prefix: button.theater_viewsonic_projector
 *   lamp_life_hours: 3000     # optional; the manual blanks the rated figure,
 *                             # so the wear bar only appears if you supply one
 */

const SOURCE_ICONS = {
  HDMI: "mdi:hdmi-port",
  VGA: "mdi:monitor",
  VGA2: "mdi:monitor-multiple",
  Composite: "mdi:video-input-component",
  "S-Video": "mdi:video-input-svideo",
};

const PICTURE = [
  { key: "brightness", label: "Brightness", ramp: "linear-gradient(90deg,#000,#fff)" },
  { key: "contrast", label: "Contrast", ramp: "linear-gradient(90deg,#555,#111 50%,#fff)" },
  { key: "saturation", label: "Saturation", ramp: "linear-gradient(90deg,#8a8a8a,#d81b60)" },
];

const DEFAULTS = {
  power: "switch.viewsonic_projector_power",
  source: "select.viewsonic_projector_source",
  lamp_mode: "select.viewsonic_projector_lamp_mode",
  lamp_hours: "sensor.viewsonic_projector_lamp_hours",
  responding: "binary_sensor.viewsonic_projector_responding",
  button_prefix: "button.theater_viewsonic_projector",
};

class ViewSonicProjectorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "simple";
    this._built = false;
  }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...(config || {}) };
    this._built = false;
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
  }

  getCardSize() { return this._tab === "advanced" ? 8 : 5; }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._update();
  }

  _obj(e) { return this._hass && this._hass.states[e]; }
  _state(e) { const s = this._obj(e); return s ? s.state : undefined; }
  _known(v) { return v !== undefined && v !== "unknown" && v !== "unavailable"; }
  _exists(e) { return !!this._obj(e); }

  _press(entityId, flashEl) {
    this._hass.callService("button", "press", { entity_id: entityId });
    if (flashEl) {
      flashEl.classList.remove("flash");
      void flashEl.offsetWidth;
      flashEl.classList.add("flash");
    }
  }

  _stepEntity(key, dir) { return this._config.button_prefix + "_" + key + "_" + dir; }

  _build() {
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 0; overflow: hidden; }

        .head { display: flex; align-items: center; gap: 8px; padding: 12px 16px 2px; }
        .title { font-size: 1.05rem; font-weight: 500; color: var(--primary-text-color); }
        .spacer { flex: 1; }
        .tabs { display: flex; gap: 3px; }
        .tab {
          appearance: none; border: 0; background: none; padding: 6px 12px;
          font: inherit; font-size: .82rem; color: var(--secondary-text-color);
          cursor: pointer; border-radius: 8px;
        }
        .tab[aria-selected="true"] { color: var(--text-primary-color, #fff); background: var(--primary-color); }
        .tab:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }

        .body { padding: 10px 16px 16px; }
        .hidden { display: none !important; }

        /* ---- power: an actual switch, not a tap target on artwork ---- */
        .powerrow {
          display: flex; align-items: center; gap: 14px;
          padding: 12px 14px; border-radius: 12px;
          border: 1px solid var(--divider-color); background: var(--secondary-background-color);
        }
        .powerrow ha-icon { --mdc-icon-size: 30px; color: var(--secondary-text-color); flex: none;
                            transition: color .35s ease; }
        .powerrow[data-on="true"] { border-color: var(--primary-color); }
        .powerrow[data-on="true"] ha-icon { color: var(--primary-color); }
        .pmeta { flex: 1; min-width: 0; }
        .pmeta .l1 { font-size: .95rem; font-weight: 500; color: var(--primary-text-color); }
        .pmeta .l2 { font-size: .78rem; color: var(--secondary-text-color); margin-top: 2px; }

        .sw {
          appearance: none; border: 0; cursor: pointer; flex: none;
          width: 54px; height: 31px; border-radius: 999px; position: relative;
          background: var(--divider-color); transition: background .22s ease; padding: 0;
        }
        .sw[data-on="true"] { background: var(--primary-color); }
        .sw i {
          position: absolute; top: 3px; left: 3px; width: 25px; height: 25px;
          border-radius: 50%; background: #fff; transition: transform .22s ease;
          box-shadow: 0 1px 3px rgba(0,0,0,.35);
        }
        .sw[data-on="true"] i { transform: translateX(23px); }
        .sw:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }

        /* ---- technical readout ---- */
        .label {
          font-size: .7rem; text-transform: uppercase; letter-spacing: .07em;
          color: var(--secondary-text-color); margin: 16px 0 7px;
          display: flex; align-items: center; gap: 7px;
        }
        .label .tag {
          text-transform: none; letter-spacing: 0; font-size: .68rem;
          border: 1px dashed var(--divider-color); border-radius: 999px; padding: 1px 7px;
        }

        .readout { border: 1px solid var(--divider-color); border-radius: 10px; overflow: hidden; }
        .rrow {
          display: flex; align-items: center; gap: 10px;
          padding: 8px 12px; font-size: .84rem;
          border-bottom: 1px solid var(--divider-color);
        }
        .rrow:last-child { border-bottom: 0; }
        .rrow .k { color: var(--secondary-text-color); flex: 1; }
        .rrow .v {
          color: var(--primary-text-color); font-variant-numeric: tabular-nums;
          font-family: var(--code-font-family, ui-monospace, SFMono-Regular, Menlo, monospace);
          font-size: .82rem;
        }
        .rrow .v.muted { color: var(--secondary-text-color); }
        .bar { height: 5px; border-radius: 3px; background: var(--divider-color); overflow: hidden; margin-top: 7px; }
        .bar > i { display: block; height: 100%; background: var(--primary-color); transition: width .5s ease; }

        /* ---- inputs ---- */
        .srcrow { display: flex; flex-wrap: wrap; gap: 7px; }
        .src {
          appearance: none; cursor: pointer; font: inherit;
          display: inline-flex; align-items: center; gap: 7px;
          padding: 8px 12px; border-radius: 10px; line-height: 1;
          border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--primary-text-color); transition: all .16s ease;
        }
        .src ha-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
        .src .nm { font-size: .82rem; }
        .src:hover { border-color: var(--primary-color); }
        .src:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
        .src[data-active="true"] {
          background: var(--primary-color); border-color: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        .src[data-active="true"] ha-icon { color: var(--text-primary-color, #fff); }
        .src[data-active="true"][data-assumed="true"] {
          background: color-mix(in srgb, var(--primary-color) 18%, transparent);
          color: var(--primary-text-color);
          border: 1px dashed var(--primary-color);
        }
        .src[data-active="true"][data-assumed="true"] ha-icon { color: var(--primary-color); }

        /* ---- advanced ---- */
        .pills { display: flex; flex-wrap: wrap; gap: 6px; }
        .pill {
          appearance: none; border: 1px solid var(--divider-color);
          background: var(--card-background-color); color: var(--primary-text-color);
          border-radius: 999px; padding: 7px 14px; font: inherit; font-size: .82rem; cursor: pointer;
        }
        .pill[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        .pill:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

        .geo { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
        .dpad { display: grid; grid-template-columns: repeat(3, 40px); grid-template-rows: repeat(3, 36px); gap: 5px; }
        .dpad .sp { visibility: hidden; }
        .nub {
          appearance: none; border: 1px solid var(--divider-color); border-radius: 9px;
          background: var(--card-background-color); color: var(--primary-text-color);
          font: inherit; font-size: .88rem; cursor: pointer; display: grid; place-items: center;
        }
        .nub:hover { background: var(--secondary-background-color); }
        .nub:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
        .nub.flash { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .nub.mid { border: 0; background: none; cursor: default; color: var(--secondary-text-color); font-size: .58rem; }

        .steprow { display: flex; align-items: center; gap: 10px; padding: 5px 0; }
        .steprow .nm { width: 6em; font-size: .84rem; color: var(--primary-text-color); }
        .ramp { flex: 1; height: 7px; border-radius: 4px; border: 1px solid var(--divider-color); }
        .grow { flex: 1; }
        .step {
          appearance: none; width: 38px; height: 32px; border-radius: 9px;
          border: 1px solid var(--divider-color); background: var(--card-background-color);
          color: var(--primary-text-color); font: inherit; font-size: .9rem;
          line-height: 1; cursor: pointer; flex: none;
        }
        .step:hover { background: var(--secondary-background-color); }
        .step:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
        .step.flash { background: var(--primary-color); color: var(--text-primary-color, #fff); }

        .note { margin-top: 12px; font-size: .72rem; line-height: 1.4; color: var(--secondary-text-color); }
      </style>

      <ha-card>
        <div class="head">
          <span class="title">Projector</span>
          <span class="spacer"></span>
          <div class="tabs" role="tablist">
            <button class="tab" id="tab-simple" role="tab">Simple</button>
            <button class="tab" id="tab-advanced" role="tab">Advanced</button>
          </div>
        </div>

        <div class="body">
          <div id="pane-simple">
            <div class="powerrow" id="powerrow">
              <ha-icon icon="mdi:projector"></ha-icon>
              <div class="pmeta">
                <div class="l1" id="pwrbig">Off</div>
                <div class="l2" id="pwrsub">Standby</div>
              </div>
              <button class="sw" id="sw" role="switch" aria-checked="false" aria-label="Projector power"><i></i></button>
            </div>

            <div class="label">Input<span class="tag hidden" id="srctag">assumed</span></div>
            <div class="srcrow" id="sources"></div>

            <div class="label">Status</div>
            <div class="readout">
              <div class="rrow"><span class="k">Lamp hours</span><span class="v" id="v-hours">&#8212;</span></div>
              <div class="rrow"><span class="k">Lamp mode</span><span class="v" id="v-mode">&#8212;</span></div>
              <div class="rrow"><span class="k">RS-232 link</span><span class="v" id="v-link">&#8212;</span></div>
            </div>
            <div class="bar hidden" id="lampbar"><i></i></div>
          </div>

          <div id="pane-advanced" class="hidden">
            <div id="modewrap">
              <div class="label">Lamp mode</div>
              <div class="pills" id="lampmodes"></div>
            </div>

            <div class="label" id="geomlabel">Geometry</div>
            <div class="geo">
              <div class="dpad" id="dpad"></div>
              <div class="grow" id="ktwrap">
                <div class="steprow">
                  <span class="nm">Keystone</span>
                  <span class="grow"></span>
                  <button class="step" id="kt-down" aria-label="Keystone down">&#8722;</button>
                  <button class="step" id="kt-up" aria-label="Keystone up">+</button>
                </div>
              </div>
            </div>

            <div class="label" id="piclabel">Picture</div>
            <div id="picture"></div>

            <div class="note">
              These are step commands. The projector accepts them but reports no value back,
              so nothing is displayed &#8212; watch the screen while you tap.
            </div>
          </div>
        </div>
      </ha-card>
    `;

    root.getElementById("tab-simple").addEventListener("click", () => this._setTab("simple"));
    root.getElementById("tab-advanced").addEventListener("click", () => this._setTab("advanced"));
    root.getElementById("sw").addEventListener("click", () => {
      this._hass.callService("switch", "toggle", { entity_id: this._config.power });
    });

    this._buildDpad();
    ["up", "down"].forEach((dir) => {
      const b = root.getElementById("kt-" + dir);
      b.dataset.ent = this._stepEntity("keystone_vertical", dir);
      b.addEventListener("click", () => this._press(b.dataset.ent, b));
    });
    this._buildPicture();

    this._built = true;
    this._setTab(this._tab);
  }

  _buildDpad() {
    const host = this.shadowRoot.getElementById("dpad");
    const mk = (label, key, dir) => {
      const b = document.createElement("button");
      b.className = "nub";
      b.textContent = label;
      b.setAttribute("aria-label", key.replace("_", " ") + " " + dir);
      b.dataset.ent = this._stepEntity(key, dir);
      b.addEventListener("click", () => this._press(b.dataset.ent, b));
      return b;
    };
    const sp = () => { const d = document.createElement("div"); d.className = "sp"; return d; };
    const mid = document.createElement("div");
    mid.className = "nub mid";
    mid.textContent = "shift";
    // horizontal_position: down = shift left, up = shift right.
    // vertical_position is the inverted one: 0x00 is up, 0x01 is down.
    host.append(
      sp(), mk("▲", "vertical_position", "up"), sp(),
      mk("◀", "horizontal_position", "down"), mid, mk("▶", "horizontal_position", "up"),
      sp(), mk("▼", "vertical_position", "down"), sp()
    );
  }

  _buildPicture() {
    const host = this.shadowRoot.getElementById("picture");
    PICTURE.forEach((p) => {
      const row = document.createElement("div");
      row.className = "steprow";
      row.id = "prow-" + p.key;

      const nm = document.createElement("div");
      nm.className = "nm";
      nm.textContent = p.label;

      const ramp = document.createElement("div");
      ramp.className = "ramp";
      ramp.style.background = p.ramp;

      const mkStep = (txt, dir) => {
        const b = document.createElement("button");
        b.className = "step";
        b.textContent = txt;
        b.setAttribute("aria-label", p.label + " " + dir);
        b.dataset.ent = this._stepEntity(p.key, dir);
        b.addEventListener("click", () => this._press(b.dataset.ent, b));
        return b;
      };

      row.append(nm, ramp, mkStep("−", "down"), mkStep("+", "up"));
      host.appendChild(row);
    });
  }

  _setTab(tab) {
    this._tab = tab;
    const root = this.shadowRoot;
    ["simple", "advanced"].forEach((t) => {
      root.getElementById("tab-" + t).setAttribute("aria-selected", String(t === tab));
      root.getElementById("pane-" + t).classList.toggle("hidden", t !== tab);
    });
  }

  _renderSources(current, assumed) {
    const host = this.shadowRoot.getElementById("sources");
    const obj = this._obj(this._config.source);
    const options = (obj && obj.attributes.options) || [];

    if (host.dataset.sig !== options.join("|")) {
      host.innerHTML = "";
      options.forEach((opt) => {
        const b = document.createElement("button");
        b.className = "src";
        b.dataset.opt = opt;
        b.innerHTML = '<ha-icon icon="' + (SOURCE_ICONS[opt] || "mdi:video-input-hdmi") + '"></ha-icon><span class="nm"></span>';
        b.querySelector(".nm").textContent = opt;
        b.addEventListener("click", () => {
          this._hass.callService("select", "select_option", {
            entity_id: this._config.source, option: opt,
          });
        });
        host.appendChild(b);
      });
      host.dataset.sig = options.join("|");
    }

    Array.from(host.children).forEach((b) => {
      const active = b.dataset.opt === current;
      b.dataset.active = String(active);
      b.dataset.assumed = String(active && assumed);
    });
    return options.length > 0;
  }

  _renderPills(hostId, entityId, currentState) {
    const host = this.shadowRoot.getElementById(hostId);
    const obj = this._obj(entityId);
    if (!obj) return false;
    const options = obj.attributes.options || [];
    if (host.dataset.sig !== options.join("|")) {
      host.innerHTML = "";
      options.forEach((opt) => {
        const b = document.createElement("button");
        b.className = "pill";
        b.textContent = opt;
        b.addEventListener("click", () => {
          this._hass.callService("select", "select_option", { entity_id: entityId, option: opt });
        });
        host.appendChild(b);
      });
      host.dataset.sig = options.join("|");
    }
    Array.from(host.children).forEach((b) => {
      b.setAttribute("aria-pressed", String(b.textContent === currentState));
    });
    return true;
  }

  _update() {
    const root = this.shadowRoot;
    const cfg = this._config;

    const power = this._state(cfg.power);
    const on = power === "on";
    root.getElementById("powerrow").dataset.on = String(on);
    const sw = root.getElementById("sw");
    sw.dataset.on = String(on);
    sw.setAttribute("aria-checked", String(on));
    root.getElementById("pwrbig").textContent =
      power === undefined ? "Unavailable" : on ? "On" : "Off";
    root.getElementById("pwrsub").textContent =
      power === undefined ? "No power state reported" : on ? "Lamp running" : "Standby";

    const srcObj = this._obj(cfg.source);
    const src = this._state(cfg.source);
    const srcKnown = this._known(src);
    const assumed = !!(srcObj && srcObj.attributes.assumed_state);
    this._renderSources(srcKnown ? src : null, assumed);
    root.getElementById("srctag").classList.toggle("hidden", !(srcKnown && assumed));

    const hours = this._state(cfg.lamp_hours);
    const hKnown = this._known(hours);
    const vh = root.getElementById("v-hours");
    vh.textContent = hKnown ? Number(hours).toLocaleString() + " h" : "not reported";
    vh.classList.toggle("muted", !hKnown);

    const mode = this._state(cfg.lamp_mode);
    const vm = root.getElementById("v-mode");
    vm.textContent = this._known(mode) ? mode : "not reported";
    vm.classList.toggle("muted", !this._known(mode));

    const responding = this._state(cfg.responding);
    const vl = root.getElementById("v-link");
    vl.textContent = responding === "on" ? "responding" : "no reply";
    vl.classList.toggle("muted", responding !== "on");

    // Wear bar only when a rated life is supplied. The manual blanks the
    // figure, so inventing one would be a fabrication.
    const bar = root.getElementById("lampbar");
    if (hKnown && cfg.lamp_life_hours) {
      const frac = Math.min(1, Number(hours) / Number(cfg.lamp_life_hours));
      bar.classList.remove("hidden");
      bar.firstElementChild.style.width = (frac * 100) + "%";
    } else {
      bar.classList.add("hidden");
    }

    root.getElementById("modewrap").classList.toggle(
      "hidden", !this._renderPills("lampmodes", cfg.lamp_mode, mode)
    );

    const hasGeo =
      this._exists(this._stepEntity("vertical_position", "up")) ||
      this._exists(this._stepEntity("horizontal_position", "up"));
    root.getElementById("dpad").classList.toggle("hidden", !hasGeo);

    const hasKt = this._exists(this._stepEntity("keystone_vertical", "up"));
    root.getElementById("ktwrap").classList.toggle("hidden", !hasKt);
    root.getElementById("geomlabel").classList.toggle("hidden", !(hasGeo || hasKt));

    let anyPic = false;
    PICTURE.forEach((p) => {
      const present = this._exists(this._stepEntity(p.key, "up"));
      root.getElementById("prow-" + p.key).classList.toggle("hidden", !present);
      anyPic = anyPic || present;
    });
    root.getElementById("piclabel").classList.toggle("hidden", !anyPic);
  }
}

customElements.define("viewsonic-projector-card", ViewSonicProjectorCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "viewsonic-projector-card",
  name: "ViewSonic Projector Card",
  description: "Projector power, input and lamp status, with an advanced tab for geometry and picture.",
  preview: false,
});
