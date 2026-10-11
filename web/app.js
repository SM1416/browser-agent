"use strict";

/* ---------- helpers ---------- */
const $ = (id) => document.getElementById(id);

function vncUrl(interactive) {
  const params = new URLSearchParams({
    autoconnect: "true",
    reconnect: "true",
    resize: "scale",
    view_only: interactive ? "0" : "1",
    path: "vnc/websockify",
  });
  return "/vnc/vnc.html?" + params.toString();
}

function setVncInteractive(interactive) {
  $("vnc").src = vncUrl(interactive);
  $("takeover-btn").classList.toggle("hidden", interactive);
  $("handback-btn").classList.toggle("hidden", !interactive);
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...(opts || {}),
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  if (!res.ok) {
    const msg = (data && data.detail) || ("Request failed (" + res.status + ")");
    throw new Error(msg);
  }
  return data;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

/* ---------- state ---------- */
let ws = null;
let wsTimer = null;
let interactive = false;

const STATUS_LABEL = {
  idle: "idle",
  running: "running",
  paused: "paused",
  needs_human: "needs you",
  done: "done",
  error: "error",
  cancelled: "cancelled",
};

function setStatus(status) {
  const pill = $("status-pill");
  pill.textContent = STATUS_LABEL[status] || status || "idle";
  pill.className = "pill " + (status || "idle");
  const active = status === "running" || status === "paused" || status === "needs_human";
  $("start-btn").disabled = active;
  $("cancel-btn").disabled = !active;
  $("takeover-btn").disabled = !(status === "running" || status === "paused" || status === "needs_human");
  if (status !== "needs_human") hideBanner();
}

function showBanner(reason) {
  $("human-reason").textContent = reason || "The agent is stuck and needs you.";
  $("human-banner").classList.remove("hidden");
}

function hideBanner() {
  $("human-banner").classList.add("hidden");
}

function logStep(entry) {
  const list = $("log");
  const empty = list.querySelector(".muted");
  if (empty) empty.remove();
  const li = el("li");
  li.appendChild(el("span", "step-n", "Step " + entry.n));
  li.appendChild(el("div", null, entry.summary || ""));
  if (entry.url) li.appendChild(el("div", "step-url", entry.url));
  list.appendChild(li);
  list.scrollTop = list.scrollHeight;
}

function logMsg(text, cls) {
  const list = $("log");
  const empty = list.querySelector(".muted");
  if (empty) empty.remove();
  const li = el("li", cls || null, text);
  list.appendChild(li);
  list.scrollTop = list.scrollHeight;
}

/* ---------- websocket ---------- */
function connectWs() {
  if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(proto + "//" + location.host + "/api/ws");

  ws.onopen = () => {
    if (wsTimer) { clearInterval(wsTimer); wsTimer = null; }
  };

  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    onEvent(msg);
  };

  ws.onclose = () => {
    ws = null;
    if (!wsTimer) {
      wsTimer = setInterval(() => { if (document.visibilityState === "visible") connectWs(); }, 5000);
    }
  };

  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

function onEvent(msg) {
  switch (msg.type) {
    case "hello":
      if (msg.task) {
        setStatus(msg.task.status);
        (msg.task.steps || []).forEach(logStep);
        if (msg.task.status === "needs_human") {
          showBanner(msg.task.takeover_reason);
          if (!interactive) setVncInteractive(true), interactive = true;
        }
        if (msg.task.result) logMsg("✅ Result: " + msg.task.result, "done-msg");
      }
      break;
    case "task_started":
      setStatus("running");
      logMsg("▶ Task started: " + msg.instruction);
      break;
    case "step":
      setStatus(msg.status || "running");
      logStep(msg);
      break;
    case "needs_human":
      setStatus("needs_human");
      showBanner(msg.reason);
      logMsg("🙋 " + (msg.reason || "Agent needs your help."), "help-msg");
      break;
    case "task_paused":
      setStatus("paused");
      logMsg("⏸ Agent paused.");
      break;
    case "task_resumed":
      setStatus("running");
      logMsg("▶ Agent resumed.");
      break;
    case "task_finished":
      setStatus("done");
      logMsg("✅ Done: " + (msg.result || "finished"), "done-msg");
      break;
    case "task_error":
      setStatus("error");
      logMsg("❌ Error: " + (msg.error || "unknown"), "err-msg");
      break;
    case "task_cancelled":
      setStatus("cancelled");
      logMsg("⏹ Task cancelled.");
      break;
  }
}

/* ---------- actions ---------- */
async function doTakeover() {
  try {
    await api("/api/takeover", { method: "POST", body: JSON.stringify({ reason: "You took over the browser." }) });
  } catch (e) {
    // Takeover of the viewer is still useful even with no active task.
  }
  interactive = true;
  setVncInteractive(true);
  hideBanner();
}

async function doHandback() {
  try {
    await api("/api/resume", { method: "POST" });
  } catch (e) {
    logMsg("Couldn't resume agent: " + e.message, "err-msg");
  }
  interactive = false;
  setVncInteractive(false);
}

async function startTask() {
  const instruction = $("task-input").value.trim();
  if (!instruction) return;
  $("start-btn").disabled = true;
  try {
    await api("/api/task", { method: "POST", body: JSON.stringify({ instruction }) });
    $("task-input").value = "";
  } catch (e) {
    logMsg("Couldn't start task: " + e.message, "err-msg");
    $("start-btn").disabled = false;
  }
}

async function cancelTask() {
  try {
    await api("/api/task/cancel", { method: "POST" });
  } catch (e) {
    logMsg("Couldn't cancel: " + e.message, "err-msg");
  }
}

async function login() {
  const pw = $("password").value;
  $("login-error").textContent = "";
  $("login-btn").disabled = true;
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ password: pw }) });
    enterApp();
  } catch (e) {
    $("login-error").textContent = e.message;
  } finally {
    $("login-btn").disabled = false;
  }
}

async function logout() {
  try { await api("/api/logout", { method: "POST" }); } catch (e) {}
  location.reload();
}

function enterApp() {
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  interactive = false;
  setVncInteractive(false);
  connectWs();
}

/* ---------- boot ---------- */
async function boot() {
  $("login-btn").addEventListener("click", login);
  $("password").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
  $("logout-btn").addEventListener("click", logout);
  $("start-btn").addEventListener("click", startTask);
  $("cancel-btn").addEventListener("click", cancelTask);
  $("takeover-btn").addEventListener("click", doTakeover);
  $("banner-takeover-btn").addEventListener("click", doTakeover);
  $("handback-btn").addEventListener("click", doHandback);

  try {
    const me = await api("/api/me");
    if (me.logged_in) enterApp();
  } catch (e) {
    /* not logged in — stay on login view */
  }
}

document.addEventListener("DOMContentLoaded", boot);
