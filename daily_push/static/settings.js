// Local settings page. Talks to /api/settings* with the per-run CSRF token.
const $ = (id) => document.getElementById(id);
const TOKEN = document.querySelector('meta[name="csrf-token"]').content;

const state = { policy: {}, secrets: {} };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts = {}) {
  const headers = { "X-CSRF-Token": TOKEN };
  if (opts.body) headers["Content-Type"] = "application/json";
  const r = await fetch(path, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = {};
  try { data = await r.json(); } catch (e) { /* ignore */ }
  if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
  return data;
}

let toastTimer = null;
function toast(msg, ok) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast " + (ok ? "ok" : "bad");
  el.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.display = "none"; }, 3200);
}

// --------------------------------------------------------------- auth cards
const SOURCES = [
  { key: "netease", label: "网易云", input: "粘贴 MUSIC_U=... 或整段 Cookie" },
  { key: "bilibili", label: "B站", input: "粘贴 SESSDATA 值或整段 Cookie" },
];

function renderAuth() {
  const grid = $("authGrid");
  grid.innerHTML = SOURCES.map((s) => {
    const info = state.secrets[s.key] || {};
    const configured = s.key === "netease" ? info.cookie_configured : info.sessdata_configured;
    const masked = s.key === "netease" ? info.cookie_masked : info.sessdata_masked;
    return `
      <div class="authcard" data-src="${s.key}">
        <div class="authhead">
          <span class="status-dot ${configured ? "" : "bad"}"></span>
          <strong>${esc(s.label)}</strong>
        </div>
        <div class="authmask">${configured ? "已配置：" + esc(masked) : "未配置"}</div>
        <input class="authinput" type="password" autocomplete="off" placeholder="${esc(s.input)}">
        <div class="authactions">
          <button class="ghost checkBtn">检测当前</button>
          <button class="saveBtn">保存并验证</button>
        </div>
        <div class="authresult"></div>
      </div>`;
  }).join("");

  grid.querySelectorAll(".authcard").forEach((card) => {
    const src = card.dataset.src;
    const input = card.querySelector(".authinput");
    const result = card.querySelector(".authresult");

    card.querySelector(".checkBtn").addEventListener("click", async () => {
      result.className = "authresult";
      result.textContent = "检测中…";
      try {
        const d = await api("/api/settings/check", { method: "POST", body: { sources: [src] } });
        const r = d.results[src] || {};
        setResult(card, r.ok, r.detail);
      } catch (e) { setResult(card, false, e.message); }
    });

    card.querySelector(".saveBtn").addEventListener("click", async () => {
      const value = input.value.trim();
      if (!value) { toast("请先粘贴新的凭证", false); return; }
      result.className = "authresult";
      result.textContent = "验证中…";
      try {
        const v = await api("/api/settings/verify", { method: "POST", body: { source: src, value } });
        if (!v.ok) { setResult(card, false, "验证未通过：" + v.detail); return; }
        await api("/api/settings/secrets", { method: "POST", body: { secrets: { [src]: value } } });
        input.value = "";
        setResult(card, true, "已保存并验证通过");
        toast("凭证已更新", true);
        await load();
      } catch (e) { setResult(card, false, e.message); }
    });
  });
}

function setResult(card, ok, detail) {
  const result = card.querySelector(".authresult");
  result.className = "authresult " + (ok ? "ok" : "bad");
  result.textContent = (ok ? "✅ " : "❌ ") + (detail || "");
  const dot = card.querySelector(".status-dot");
  dot.className = "status-dot " + (ok ? "ok" : "bad");
}

// ------------------------------------------------------------------- chips
function chipEditor(container, items, onChange) {
  container.innerHTML = "";
  const list = items.slice();
  const input = document.createElement("input");
  input.placeholder = "输入后回车添加";

  function render() {
    container.querySelectorAll(".chip").forEach((e) => e.remove());
    list.forEach((it, i) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `<span>${esc(it)}</span><button type="button" title="删除">×</button>`;
      chip.querySelector("button").addEventListener("click", () => {
        list.splice(i, 1); render(); onChange(list.slice());
      });
      container.insertBefore(chip, input);
    });
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const v = input.value.trim().replace(/,+$/, "");
      if (v && !list.includes(v)) { list.push(v); input.value = ""; render(); onChange(list.slice()); }
    } else if (e.key === "Backspace" && !input.value && list.length) {
      list.pop(); render(); onChange(list.slice());
    }
  });

  container.appendChild(input);
  render();
}

function policyNode(root) {
  return (state.policy && state.policy[root]) || {};
}

function renderChips() {
  chipEditor($("chipsBili"), policyNode("bilibili").exclude || [], (v) => {
    state.policy.bilibili = Object.assign({}, policyNode("bilibili"), { exclude: v });
  });
  chipEditor($("chipsMp"), policyNode("wechat").exclude_keywords || [], (v) => {
    state.policy.wechat = Object.assign({}, policyNode("wechat"), { exclude_keywords: v });
  });
}

// ------------------------------------------------------------------ params
const PARAMS = [
  { path: ["push_time"], label: "每日采集时间 (HH:MM)", type: "time" },
  { path: ["max_songs"], label: "网易云歌曲数", type: "number" },
  { path: ["bilibili", "recent_days"], label: "B站时间窗口（天）", type: "number" },
  { path: ["bilibili", "max_videos"], label: "B站最多条数", type: "number" },
  { path: ["bilibili", "feed_pages"], label: "B站翻页数", type: "number" },
  { path: ["wechat", "max_articles"], label: "公众号最多条数", type: "number" },
  { path: ["wechat", "mp_cutoff_hour"], label: "公众号窗口起点（时）", type: "number" },
];

function getPath(obj, path) {
  return path.reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function renderParams() {
  $("paramGrid").innerHTML = PARAMS.map((p, i) => {
    const v = getPath(state.policy, p.path);
    return `<div class="param">
      <label>${esc(p.label)}</label>
      <input data-param="${i}" type="${p.type}" value="${esc(v ?? "")}">
    </div>`;
  }).join("");
}

async function saveParams() {
  const policy = {};
  $("paramGrid").querySelectorAll("input[data-param]").forEach((el) => {
    const p = PARAMS[+el.dataset.param];
    let val = el.value.trim();
    if (p.type === "number") val = parseInt(val, 10);
    let node = policy;
    p.path.forEach((k, i) => {
      if (i === p.path.length - 1) node[k] = val;
      else node = node[k] = node[k] || {};
    });
  });
  try {
    const d = await api("/api/settings/policy", { method: "POST", body: { policy } });
    state.policy = d.policy || state.policy;
    toast("参数已保存", true);
  } catch (e) { toast(e.message, false); }
}

async function savePolicy() {
  const btn = $("savePolicy");
  const old = btn.textContent;
  const policy = {
    bilibili: { exclude: policyNode("bilibili").exclude || [] },
    wechat: { exclude_keywords: policyNode("wechat").exclude_keywords || [] },
  };
  btn.disabled = true;
  btn.textContent = "保存中…";
  try {
    const d = await api("/api/settings/policy", { method: "POST", body: { policy } });
    state.policy = d.policy || state.policy;
    btn.textContent = "清理历史并发布…";
    await api("/api/settings/purge", { method: "POST", body: {} });
    const s = await waitPurge();
    if (s.error) { toast("清理失败：" + s.error, false); return; }
    const r = s.result || {};
    const total = (r.removed_bilibili || 0) + (r.removed_mp || 0);
    const sp = r.settings_publish || {};
    if (r.push_error) {
      toast(`已清理 ${total} 条，但 Pages 推送失败：${r.push_error}`, false);
    } else if (sp.committed && !sp.pushed) {
      toast(`已清理 ${total} 条并发布 Pages；云端同步失败：${sp.detail}`, false);
    } else if (sp.pushed) {
      toast(`已保存：清理 ${total} 条，Pages 与云端均已同步`, true);
    } else {
      toast(`已保存，清理 ${total} 条并重新发布`, true);
    }
  } catch (e) {
    toast(e.message, false);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

async function waitPurge() {
  for (let i = 0; i < 180; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    const s = await api("/api/settings/purge/status");
    if (!s.running && s.done) return s;
  }
  throw new Error("清理超时");
}

// -------------------------------------------------------------------- init
function initTheme() {
  const btn = $("themeToggle");
  const apply = (t) => {
    document.documentElement.setAttribute("data-theme", t);
    btn.textContent = t === "dark" ? "🌙" : "☀️";
  };
  btn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    apply(next); localStorage.setItem("theme", next);
  });
  const saved = localStorage.getItem("theme");
  apply(saved === "light" ? "light" : "dark");
}

async function load() {
  const d = await api("/api/settings");
  state.policy = d.policy || {};
  state.secrets = d.secrets || {};
  renderAuth();
  renderChips();
  renderParams();
}

async function init() {
  initTheme();
  $("savePolicy").addEventListener("click", savePolicy);
  $("saveParams").addEventListener("click", saveParams);
  try {
    await load();
  } catch (e) {
    toast("加载设置失败：" + e.message, false);
  }
}

init();
