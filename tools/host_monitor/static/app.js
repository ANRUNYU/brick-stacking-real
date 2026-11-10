const pill = document.getElementById("link-pill");
const cameraMeta = document.getElementById("camera-meta");
const serviceMeta = document.getElementById("service-meta");
const armsRoot = document.getElementById("arms");
const overlay = document.getElementById("cam-overlay");
const btnRelease = document.getElementById("btn-release");
const btnAcquire = document.getElementById("btn-acquire");
const headStream = document.getElementById("head-stream");

function fmt(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

function setPill(ok, text) {
  pill.textContent = text;
  pill.classList.toggle("ok", ok);
  pill.classList.toggle("bad", !ok);
}

function renderService(state) {
  const meta = state.meta || {};
  const rows = [
    ["mode", meta.mode || "?"],
    ["camera", meta.camera_held ? "HELD" : "RELEASED"],
    ["serial", meta.serial || (meta.camera_selected && meta.camera_selected.serial) || "—"],
    ["arms", meta.arms || "—"],
    ["motion", "false"],
    ["host_t", fmt(state.host_monotonic_s, 2) + " s"],
  ];
  if (meta.camera_error) rows.push(["cam_err", meta.camera_error]);
  if (meta.notice) rows.push(["notice", meta.notice]);
  serviceMeta.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

function renderCamera(state) {
  const meta = state.meta || {};
  const held = !!meta.camera_held;
  overlay.classList.toggle("hidden", held);
  btnRelease.disabled = !held;
  btnAcquire.disabled = held;

  const cam = (state.cameras || {}).head;
  if (!held) {
    cameraMeta.textContent = "已释放 · 可供其它视觉进程独占";
    return;
  }
  if (!cam) {
    cameraMeta.textContent = "无头部相机状态";
    return;
  }
  if (cam.error) {
    cameraMeta.textContent = `错误：${cam.error}`;
    return;
  }
  cameraMeta.textContent = `${cam.width}×${cam.height} · ${cam.source} · jpeg ${cam.jpeg_bytes} B · t=${fmt(cam.stamp_s, 2)}`;
}

function jointBar(qRad) {
  if (qRad === null || qRad === undefined) return 0;
  const span = Math.PI;
  return Math.max(0, Math.min(100, ((qRad + span) / (2 * span)) * 100));
}

function renderArms(state) {
  const arms = state.arms || {};
  const roles = Object.keys(arms);
  if (!roles.length) {
    armsRoot.innerHTML = `<p class="hint">当前未启用臂状态采集</p>`;
    return;
  }
  armsRoot.innerHTML = roles.map((role) => {
    const a = arms[role];
    const joints = (a.joint_names || []).map((name, i) => {
      const q = (a.q_rad || [])[i];
      const deg = (a.q_deg || [])[i];
      return `<div class="joint">
        <span>${name}</span>
        <div class="bar"><span style="width:${jointBar(q)}%"></span></div>
        <span class="val">${fmt(q)} / ${fmt(deg, 1)}°</span>
      </div>`;
    }).join("");
    return `<div class="arm-block">
      <h3>${role} · ${a.channel} · ${a.validity}${a.error ? " · ERR" : ""}</h3>
      ${a.reason ? `<p class="hint">${a.reason}</p>` : ""}
      ${joints}
    </div>`;
  }).join("");
}

async function tick() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const state = await res.json();
    const held = !!(state.meta && state.meta.camera_held);
    setPill(true, held ? "已连接 · 相机占用中" : "已连接 · 相机已释放");
    renderService(state);
    renderCamera(state);
    renderArms(state);
  } catch (err) {
    setPill(false, `断开 · ${err.message || err}`);
  }
}

async function cameraAction(path) {
  btnRelease.disabled = true;
  btnAcquire.disabled = true;
  try {
    const res = await fetch(path, { method: "POST" });
    const body = await res.json();
    if (!res.ok || body.ok === false) throw new Error(body.notice || `HTTP ${res.status}`);
    // Bust MJPEG cache when re-acquiring.
    if (path.endsWith("/acquire")) {
      headStream.src = `/stream/head?t=${Date.now()}`;
    }
    await tick();
  } catch (err) {
    setPill(false, `相机操作失败 · ${err.message || err}`);
    await tick();
  }
}

btnRelease.addEventListener("click", () => cameraAction("/api/camera/release"));
btnAcquire.addEventListener("click", () => cameraAction("/api/camera/acquire"));

tick();
setInterval(tick, 250);
