const pill = document.getElementById("link-pill");
const cameraMeta = document.getElementById("camera-meta");
const serviceMeta = document.getElementById("service-meta");
const armsRoot = document.getElementById("arms");

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
  const cam = (state.cameras || {}).head;
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
    setPill(true, "已连接 · 只读");
    renderService(state);
    renderCamera(state);
    renderArms(state);
  } catch (err) {
    setPill(false, `断开 · ${err.message || err}`);
  }
}

tick();
setInterval(tick, 250);
