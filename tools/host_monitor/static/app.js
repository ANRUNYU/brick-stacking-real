const pill = document.getElementById("link-pill");
const cameraMeta = document.getElementById("camera-meta");
const serviceMeta = document.getElementById("service-meta");
const armsRoot = document.getElementById("arms");
const overlay = document.getElementById("cam-overlay");
const btnRelease = document.getElementById("btn-release");
const btnAcquire = document.getElementById("btn-acquire");
const headStream = document.getElementById("head-stream");
const controlMeta = document.getElementById("control-meta");
const controlMsg = document.getElementById("control-msg");
const ctlJoint = document.getElementById("ctl-joint");
const ctlStep = document.getElementById("ctl-step");
const ctlDir = document.getElementById("ctl-dir");
const btnReady = document.getElementById("btn-ready");
const btnPrepare = document.getElementById("btn-prepare");
const btnEnable = document.getElementById("btn-enable");
const btnMove = document.getElementById("btn-move");
const btnJRelease = document.getElementById("btn-jrelease");
const btnClose = document.getElementById("btn-close");

let lastControl = null;
let controlBusy = false;

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
  const ctl = state.control || {};
  const rows = [
    ["mode", meta.mode || "?"],
    ["camera", meta.camera_held ? "HELD" : "RELEASED"],
    ["serial", meta.serial || (meta.camera_selected && meta.camera_selected.serial) || "—"],
    ["arms", meta.arms || "—"],
    ["motion", String(!!(meta.motion_enabled || ctl.motion_process_enabled))],
    ["session", ctl.session_open ? "OPEN" : "closed"],
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
    armsRoot.innerHTML = `<p class="hint">当前未启用臂状态采集（或控制会话已暂停轮询）</p>`;
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

function renderControl(state) {
  lastControl = state.control || {};
  const c = lastControl;
  const plan = c.plan || null;
  const rows = [
    ["enabled", String(!!c.motion_process_enabled)],
    ["session", c.session_open ? "OPEN" : "closed"],
    ["busy", String(!!c.busy)],
    ["active", c.active_joint == null ? "—" : `J${c.active_joint}`],
  ];
  if (plan) {
    rows.push(
      ["kind", plan.kind],
      ["start°", fmt(plan.start_deg, 2)],
      ["target°", fmt(plan.target_deg, 2)],
      ["step°", fmt(plan.step_deg, 2)],
      ["en/mv", `${plan.enabled}/${plan.moved}`],
    );
  }
  if (c.last_error) rows.push(["error", c.last_error]);
  if (c.notice) rows.push(["notice", c.notice]);
  controlMeta.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");

  const motion = !!c.motion_process_enabled;
  const open = !!c.session_open;
  const busy = !!c.busy || controlBusy;
  btnReady.disabled = !motion || open || busy;
  btnClose.disabled = !motion || !open || busy;
  btnPrepare.disabled = !motion || !open || busy;
  btnEnable.disabled = !motion || !open || busy || !plan || plan.enabled;
  btnMove.disabled = !motion || !open || busy || !plan || !plan.enabled || plan.moved;
  btnJRelease.disabled = !motion || !open || busy || !plan;
  if (plan && ctlJoint.value !== String(plan.joint)) {
    // keep user selection unless a plan is active
  }
  if (!motion) {
    controlMsg.textContent = "进程未加 --enable-motion，控制按钮禁用";
  } else if (!controlMsg.textContent || controlMsg.dataset.sticky !== "1") {
    controlMsg.textContent = c.notice || "";
  }
}

async function tick() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const state = await res.json();
    const held = !!(state.meta && state.meta.camera_held);
    const ctl = state.control || {};
    setPill(
      true,
      held
        ? (ctl.session_open ? "已连接 · 相机占用 · 控制会话开" : "已连接 · 相机占用中")
        : (ctl.session_open ? "已连接 · 相机释放 · 控制会话开" : "已连接 · 相机已释放"),
    );
    renderService(state);
    renderCamera(state);
    renderArms(state);
    renderControl(state);
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
    if (!res.ok || body.ok === false) throw new Error(body.notice || body.error || `HTTP ${res.status}`);
    if (path.endsWith("/acquire")) {
      headStream.src = `/stream/head?t=${Date.now()}`;
    }
    await tick();
  } catch (err) {
    setPill(false, `相机操作失败 · ${err.message || err}`);
    await tick();
  }
}

async function postJson(path, payload) {
  controlBusy = true;
  controlMsg.dataset.sticky = "1";
  controlMsg.textContent = `请求 ${path} …`;
  renderControl({ control: lastControl || {} });
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const body = await res.json();
    if (!res.ok || body.ok === false) {
      throw new Error(body.error || body.notice || `HTTP ${res.status}`);
    }
    controlMsg.textContent = body.notice || "OK";
    lastControl = body;
    renderControl({ control: body });
    await tick();
    return body;
  } catch (err) {
    controlMsg.textContent = `失败：${err.message || err}`;
    await tick();
    throw err;
  } finally {
    controlBusy = false;
    controlMsg.dataset.sticky = "0";
    await tick();
  }
}

btnRelease.addEventListener("click", () => cameraAction("/api/camera/release"));
btnAcquire.addEventListener("click", () => cameraAction("/api/camera/acquire"));
btnReady.addEventListener("click", () => {
  if (!window.confirm("确认打开控制会话？将暂停只读关节轮询并占用 can2。请确认周围安全。")) return;
  postJson("/api/control/session/open", { confirm: "READY" });
});
btnPrepare.addEventListener("click", () => postJson("/api/control/joint/prepare", {
  joint: Number(ctlJoint.value),
  step_deg: Number(ctlStep.value),
  direction: Number(ctlDir.value),
}));
btnEnable.addEventListener("click", () => {
  if (!window.confirm(`确认 ENABLE J${ctlJoint.value}？`)) return;
  postJson("/api/control/joint/enable", { joint: Number(ctlJoint.value), confirm: "ENABLE" });
});
btnMove.addEventListener("click", () => {
  if (!window.confirm(`确认 MOVE J${ctlJoint.value}？将按计划小步移动。`)) return;
  postJson("/api/control/joint/move", { joint: Number(ctlJoint.value), confirm: "MOVE" });
});
btnJRelease.addEventListener("click", () => postJson("/api/control/joint/release", {
  joint: Number(ctlJoint.value),
  confirm: "RELEASE",
}));
btnClose.addEventListener("click", () => postJson("/api/control/session/close", {}));

ctlJoint.addEventListener("change", () => {
  const j = Number(ctlJoint.value);
  const defaults = (lastControl && lastControl.defaults && lastControl.defaults.step_deg) || {};
  if (defaults[j] != null) ctlStep.value = defaults[j];
});

tick();
setInterval(tick, 250);
