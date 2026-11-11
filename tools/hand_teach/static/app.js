const NAMES = ["thumb_flex", "thumb_abd", "index", "middle", "ring", "pinky"];

const liveBars = document.getElementById("liveBars");
const sliders = document.getElementById("sliders");
const presetsEl = document.getElementById("presets");
const modeLabel = document.getElementById("modeLabel");
const sessionLabel = document.getElementById("sessionLabel");
const serialLabel = document.getElementById("serialLabel");
const ageLabel = document.getElementById("ageLabel");
const errorLabel = document.getElementById("errorLabel");
const speedInput = document.getElementById("speedInput");
const btnReady = document.getElementById("btnReady");
const btnApply = document.getElementById("btnApply");
const btnClose = document.getElementById("btnClose");
const btnSync = document.getElementById("btnSync");

const targets = Object.fromEntries(NAMES.map((n) => [n, 100]));

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function buildLive() {
  liveBars.innerHTML = "";
  for (const name of NAMES) {
    const row = el("div", "bar");
    row.appendChild(el("span", null, name));
    const track = el("div", "track");
    const fill = el("div", "fill");
    fill.id = `live-${name}`;
    track.appendChild(fill);
    row.appendChild(track);
    const val = el("code", null, "—");
    val.id = `live-val-${name}`;
    row.appendChild(val);
    liveBars.appendChild(row);
  }
}

function buildSliders() {
  sliders.innerHTML = "";
  for (const name of NAMES) {
    const row = el("div", "slider-row");
    row.appendChild(el("span", null, name));
    const range = document.createElement("input");
    range.type = "range";
    range.min = "0";
    range.max = "100";
    range.step = "1";
    range.value = String(targets[name]);
    range.id = `range-${name}`;
    const num = document.createElement("input");
    num.type = "number";
    num.min = "0";
    num.max = "100";
    num.step = "1";
    num.value = String(targets[name]);
    num.id = `num-${name}`;
    const sync = (v) => {
      const n = Math.max(0, Math.min(100, Number(v)));
      targets[name] = n;
      range.value = String(n);
      num.value = String(n);
    };
    range.addEventListener("input", () => sync(range.value));
    num.addEventListener("change", () => sync(num.value));
    row.appendChild(range);
    row.appendChild(num);
    sliders.appendChild(row);
  }
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || res.statusText);
  }
  return data;
}

function renderState(state) {
  modeLabel.textContent = state.enable_hand ? "ENABLE_HAND" : "READ_ONLY";
  sessionLabel.textContent = state.session_open ? "open" : "closed";
  serialLabel.textContent = state.serial_number || "—";
  ageLabel.textContent =
    state.age_s == null ? "—" : `${Number(state.age_s).toFixed(2)} s`;
  if (state.last_error) {
    errorLabel.hidden = false;
    errorLabel.textContent = state.last_error;
  } else {
    errorLabel.hidden = true;
  }
  btnApply.disabled = !(state.enable_hand && state.session_open);
  speedInput.max = String(state.max_speed_percent || 15);
  const angles = state.angles_percent || [];
  NAMES.forEach((name, i) => {
    const v = angles[i];
    const fill = document.getElementById(`live-${name}`);
    const label = document.getElementById(`live-val-${name}`);
    if (v == null || Number.isNaN(v)) {
      fill.style.width = "0%";
      label.textContent = "—";
      return;
    }
    fill.style.width = `${v}%`;
    label.textContent = v.toFixed(1);
  });
  if (presetsEl.childElementCount === 0 && state.presets) {
    for (const [key, values] of Object.entries(state.presets)) {
      const b = el("button", null, key);
      b.type = "button";
      b.addEventListener("click", () => {
        NAMES.forEach((name, i) => {
          targets[name] = values[i];
          document.getElementById(`range-${name}`).value = String(values[i]);
          document.getElementById(`num-${name}`).value = String(values[i]);
        });
      });
      presetsEl.appendChild(b);
    }
  }
}

async function refresh() {
  try {
    const data = await api("/api/state");
    renderState(data.state);
  } catch (err) {
    errorLabel.hidden = false;
    errorLabel.textContent = String(err.message || err);
  }
}

btnReady.addEventListener("click", async () => {
  try {
    const data = await api("/api/session/open", {
      method: "POST",
      body: JSON.stringify({ confirm: "READY" }),
    });
    renderState(data.state);
  } catch (err) {
    alert(err.message || err);
  }
});

btnClose.addEventListener("click", async () => {
  try {
    const data = await api("/api/session/close", { method: "POST", body: "{}" });
    renderState(data.state);
  } catch (err) {
    alert(err.message || err);
  }
});

btnApply.addEventListener("click", async () => {
  try {
    const payload = {
      confirm: "APPLY",
      speed_percent: Number(speedInput.value),
      angles_percent: NAMES.map((n) => targets[n]),
    };
    const data = await api("/api/apply", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderState(data.snapshot);
  } catch (err) {
    alert(err.message || err);
  }
});

btnSync.addEventListener("click", async () => {
  const data = await api("/api/state");
  const angles = data.state.angles_percent || [];
  NAMES.forEach((name, i) => {
    if (angles[i] == null) return;
    targets[name] = Math.round(angles[i]);
    document.getElementById(`range-${name}`).value = String(targets[name]);
    document.getElementById(`num-${name}`).value = String(targets[name]);
  });
  renderState(data.state);
});

buildLive();
buildSliders();
refresh();
setInterval(refresh, 500);
