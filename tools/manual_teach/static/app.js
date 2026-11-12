const armRoot = document.getElementById("arm");
const handRoot = document.getElementById("hand");
const modeBadge = document.getElementById("modeBadge");
const stateWord = document.getElementById("stateWord");
const dot = document.getElementById("dot");
const sampleCount = document.getElementById("sampleCount");
const elapsed = document.getElementById("elapsed");
const measuredHz = document.getElementById("measuredHz");
const fileName = document.getElementById("fileName");
const fileLabel = document.getElementById("fileLabel");
const directory = document.getElementById("directory");
const handSession = document.getElementById("handSession");
const poseGrasp = document.getElementById("poseGrasp");
const poseRelease = document.getElementById("poseRelease");
const fileList = document.getElementById("fileList");
const errorEl = document.getElementById("error");
const speed = document.getElementById("speed");
const speedVal = document.getElementById("speedVal");
const btnStart = document.getElementById("btnStart");
const btnPause = document.getElementById("btnPause");
const btnEnd = document.getElementById("btnEnd");
const btnReady = document.getElementById("btnReady");
const btnGrasp = document.getElementById("btnGrasp");
const btnRelease = document.getElementById("btnRelease");

let built = false;
let polling = false;
let busy = false;

function fmtRad(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const text = n.toFixed(3);
  return n >= 0 ? text : text;
}

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(1);
}

function fmtPose(values) {
  return (values || []).map((v) => Number(v).toFixed(1)).join("  ");
}

function showError(message) {
  if (!message) {
    errorEl.hidden = true;
    errorEl.textContent = "";
    return;
  }
  errorEl.hidden = false;
  errorEl.textContent = String(message);
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

function ensureRows(state) {
  if (built) return;
  state.arm.names.forEach((name, i) => {
    const row = document.createElement("div");
    row.className = "readout arm";
    row.innerHTML = `<span class="name">${name}</span><div class="num"><b id="arm-${i}">—</b><small>弧度</small></div>`;
    armRoot.appendChild(row);
  });
  state.hand.labels.forEach((label, i) => {
    const row = document.createElement("div");
    row.className = "readout hand";
    row.innerHTML =
      `<span class="name">${label}</span>` +
      `<div class="track"><i class="knob" id="knob-${i}"></i></div>` +
      `<div class="num"><b id="hand-${i}">—</b><small>读数</small><span class="target" id="target-${i}"></span></div>`;
    handRoot.appendChild(row);
  });
  built = true;
}

function render(state) {
  ensureRows(state);
  const recording = state.record.state === "recording";
  const paused = state.record.state === "paused";
  document.body.classList.toggle("is-recording", recording);
  const link = state.link || {};
  if (state.mock) modeBadge.textContent = "模拟";
  else if (link.arm_ok && link.hand_ok) modeBadge.textContent = "实况";
  else modeBadge.textContent = "未连上";
  stateWord.textContent = recording ? "记录中" : paused ? "已暂停" : "空闲";
  dot.hidden = !recording;
  sampleCount.textContent = String(state.record.samples ?? 0);
  elapsed.textContent = Number(state.record.elapsed_s || 0).toFixed(1);
  measuredHz.textContent = state.record.measured_hz == null ? "—" : `${state.record.measured_hz} Hz`;
  if (state.record.name) {
    fileLabel.textContent = paused ? "同一份" : "文件";
    fileName.textContent = state.record.name;
  } else if (state.record.last_name) {
    fileLabel.textContent = "上一份";
    fileName.textContent = state.record.last_name;
  } else {
    fileLabel.textContent = "文件";
    fileName.textContent = "尚未开始";
  }
  directory.textContent = state.directory || "";
  if (link.hand_url) {
    const hz = link.arm_read_hz == null ? "" : `，臂采样 ${link.arm_read_hz} Hz`;
    handSession.textContent = link.hand_ok
      ? `抓取和松开走手接口${hz}`
      : "手接口没连上";
  } else {
    handSession.textContent = state.session_open ? "手已准备，可以抓取或松开" : "先点准备手，才能抓取或松开";
  }
  const armAge = document.getElementById("armAge");
  const handAge = document.getElementById("handAge");
  if (armAge) armAge.textContent = state.arm.age_s == null ? "" : `${Number(state.arm.age_s).toFixed(2)} 秒前`;
  if (handAge) handAge.textContent = state.hand.age_s == null ? "" : `${Number(state.hand.age_s).toFixed(2)} 秒前`;
  poseGrasp.textContent = fmtPose(state.presets.grasp);
  poseRelease.textContent = fmtPose(state.presets.release);
  speed.max = String(state.max_speed_percent || 15);
  if (document.activeElement !== speed) {
    speed.value = String(state.speed_percent);
  }
  speedVal.textContent = speed.value;

  btnStart.disabled = recording;
  btnPause.disabled = !recording;
  btnEnd.disabled = !(recording || paused);
  btnReady.disabled = state.session_open || !state.enable_hand;
  const handReady = state.enable_hand && (state.session_open || Boolean(link.hand_url));
  btnGrasp.disabled = !handReady;
  btnRelease.disabled = !handReady;

  (state.arm.q_rad || []).forEach((v, i) => {
    const node = document.getElementById(`arm-${i}`);
    if (node) node.textContent = fmtRad(v);
  });
  (state.hand.percent || []).forEach((v, i) => {
    const node = document.getElementById(`hand-${i}`);
    const knob = document.getElementById(`knob-${i}`);
    if (node) node.textContent = fmtPct(v);
    if (knob) knob.style.left = `${v == null ? 0 : Math.max(0, Math.min(100, v))}%`;
  });
  state.hand.labels.forEach((_, i) => {
    const target = document.getElementById(`target-${i}`);
    if (!target) return;
    const goal = state.hand.target ? state.hand.target[i] : null;
    target.textContent = goal == null ? "" : `目标 ${fmtPct(goal)}`;
  });

  fileList.replaceChildren();
  (state.recent_files || []).forEach((name) => {
    const li = document.createElement("li");
    li.textContent = name;
    if (name === state.record.name || (state.record.state === "idle" && name === state.record.last_name)) {
      li.className = "current";
    }
    fileList.appendChild(li);
  });

  const problem = state.arm.error || state.hand.error;
  if (!busy) showError(problem || "");
}

async function refresh() {
  if (polling) return;
  polling = true;
  try {
    render(await api("/api/state"));
  } catch (err) {
    showError(err.message || err);
  } finally {
    polling = false;
  }
}

async function act(path, confirm, extra) {
  if (busy) return;
  busy = true;
  try {
    render(await api(path, { method: "POST", body: JSON.stringify({ confirm, ...extra }) }));
    showError("");
  } catch (err) {
    showError(err.message || err);
  } finally {
    busy = false;
  }
}

speed.addEventListener("input", () => {
  speedVal.textContent = speed.value;
});

btnStart.addEventListener("click", () => act("/api/record/start", "START"));
btnPause.addEventListener("click", () => act("/api/record/pause", "PAUSE"));
btnEnd.addEventListener("click", () => act("/api/record/end", "END"));
btnReady.addEventListener("click", () => act("/api/session/open", "READY"));
btnGrasp.addEventListener("click", () =>
  act("/api/hand/grasp", "GRASP", { speed_percent: Number(speed.value) })
);
btnRelease.addEventListener("click", () =>
  act("/api/hand/release", "RELEASE", { speed_percent: Number(speed.value) })
);

refresh();
setInterval(refresh, 100);
