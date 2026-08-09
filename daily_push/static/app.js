// Daily Push dashboard app.
const $ = (id) => document.getElementById(id);

const DAYS = window.__DAYS__ || null;

const els = {
  datePicker: $("datePicker"),
  summary: $("summary"),
  songs: $("songs"),
  ups: $("ups"),
  mpList: $("mpList"),
  cardMusic: $("card-music"),
  cardBili: $("card-bili"),
  cardMp: $("card-mp"),
  emptyState: $("emptyState"),
  collectBtn: $("collectBtn"),
  collectMsg: $("collectMsg"),
};

function localDateStr() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

let currentDate = DAYS
  ? (Object.keys(DAYS).sort().pop() || localDateStr())
  : localDateStr();

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function errMessage(kind, raw) {
  const r = String(raw || "");
  const credential = /cookie|sessdata|not configured|login|401|403|expired|失效|过期/i.test(r);
  const conn = /cannot reach|connect|refused|timeout|ECONN|网络|unable to determine/i.test(r);
  if (kind === "mp") {
    if (credential) return "微信公众号登录凭证可能已失效，请更新后重新采集。";
    if (conn) return "微信数据源暂时无法连接，请稍后再试。";
    return "公众号推文获取失败，请稍后重试。";
  }
  if (kind === "netease") {
    if (credential) return "网易云登录凭证可能已失效，请更新 Cookie 后重新采集。";
    if (conn) return "网易云服务暂时无法连接，请稍后再试。";
    return "网易云推荐获取失败，请稍后重试。";
  }
  if (kind === "bilibili") {
    if (credential) return "B站登录凭证可能已失效，请更新 sessdata 后重新采集。";
    if (conn) return "B站接口暂时无法连接，请稍后再试。";
    return "B站动态获取失败，请稍后重试。";
  }
  return "数据获取失败，请稍后重试。";
}

function errBlock(kind, raw) {
  return `<div class="module-err">
    <div class="module-err-title">⚠️ 该模块暂时无法加载</div>
    <div class="module-err-desc">${esc(errMessage(kind, raw))}</div>
    ${raw ? `<div class="module-err-raw">${esc(raw)}</div>` : ""}
  </div>`;
}

function fmtCreated(ts) {
  const sec = Number(ts);
  if (!sec) return "";
  const d = new Date(sec * 1000);
  const y = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  const nowY = new Date().getFullYear();
  return `${y === nowY ? "" : y + "-"}${mm}-${dd} ${hh}:${mi}`;
}

function renderMsg(m) {
  if (typeof m === "string") {
    return `<div class="msg-line">${esc(m)}</div>`;
  }
  const t = m.time, s = m.sender || "", x = m.text || "";
  return `<div class="msg-line">
    ${t ? `<span class="msg-time">${esc(t)}</span>` : ""}
    ${s ? `<span class="msg-sender">${esc(s)}</span>` : ""}
    <span class="msg-text">${esc(x)}</span>
  </div>`;
}

function renderGroups(el, groups) {
  if (!Array.isArray(groups) || groups.length === 0) return false;
  el.innerHTML = groups.map((g) => {
    const msgs = (g.messages || []).map(renderMsg).join("");
    return `<div class="group-block">
      <div class="gname">${esc(g.group || g.name || g.peer || "")}</div>
      ${msgs || `<pre>（昨日无文本消息）</pre>`}
    </div>`;
  }).join("");
  return true;
}

function renderMusic(data) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  els.cardMusic.style.display = (isErr || (Array.isArray(data) && data.length > 0)) ? "" : "none";
  if (isErr) {
    els.songs.innerHTML = errBlock("netease", data.error);
    return;
  }
  els.songs.innerHTML = Array.isArray(data)
    ? data.map((s) => `
        <li>
          <span class="rank"></span>
          ${s.pic ? `<img src="${esc(s.pic)}" onerror="this.style.display='none'">` : ""}
          <div class="meta">
            <div class="title">${esc(s.name)}</div>
            <div class="artist">${esc(s.artists)}${s.album ? " · " + esc(s.album) : ""}</div>
            ${s.hot_comment ? `<div class="comment">"${esc(s.hot_comment)}"</div>` : ""}
          </div>
          ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">▶ 播放</a>` : ""}
        </li>`).join("")
    : "";
}

function renderBili(data) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  els.cardBili.style.display = (isErr || (Array.isArray(data) && data.length > 0)) ? "" : "none";
  if (isErr) {
    els.ups.innerHTML = errBlock("bilibili", data.error);
    return;
  }
  if (!Array.isArray(data)) {
    els.ups.innerHTML = "";
    return;
  }
  els.ups.innerHTML = data.map((u) => `
    <li>
      <div class="ainfo">
        <a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.title)}</a>
        ${u.author ? `<span class="author">${esc(u.author)}</span>` : ""}
      </div>
      <div class="aside">
        ${u.created ? `<span class="time">${esc(fmtCreated(u.created))}</span>` : ""}
      </div>
    </li>`
  ).join("");
}

function renderArticles(data) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const empty = !Array.isArray(data) || data.length === 0;
  els.cardMp.style.display = (isErr || (Array.isArray(data) && data.length > 0) || (DAYS && empty)) ? "" : "none";
  if (isErr) {
    els.mpList.innerHTML = errBlock("mp", data.error);
    return;
  }
  if (empty) {
    // 云端（静态站）不采集公众号，mp 常为空 → 显示权限说明，避免整个卡片消失
    els.mpList.innerHTML = DAYS
      ? `<div class="module-note">📰 公众号推文仅在本机（微信解密环境）采集，云端不采集，故此处为空。</div>`
      : "";
    return;
  }
  els.mpList.innerHTML = data.map((a) => `
    <li${a.notify ? ' class="notify"' : ""}>
      <div class="ainfo">
        <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
        ${a.author ? `<span class="author">${esc(a.author)}</span>` : ""}
      </div>
      <div class="aside">
        ${a.notify ? `<span class="tag">通知</span>` : ""}
        ${a.time ? `<span class="time">${esc(a.time)}</span>` : ""}
      </div>
    </li>`
  ).join("");
}

function render(data) {
  renderMusic(data.netease);
  renderBili(data.bilibili);
  renderArticles(data.mp);

  const hasData = (x) => (Array.isArray(x) && x.length) ||
    (x && typeof x === "object" && !Array.isArray(x) && x.error);
  const any = hasData(data.netease) || hasData(data.bilibili) || hasData(data.mp);
  els.emptyState.style.display = any ? "none" : "";

  renderSummary(data);
}

function renderSummary(data) {
  const n = Array.isArray(data.netease) ? data.netease.length : 0;
  const mp = Array.isArray(data.mp) ? data.mp.length : 0;
  const bili = Array.isArray(data.bilibili) ? data.bilibili.length : 0;
  const stat = (target, label, val) => `
    <button class="stat" data-target="${target}"${val ? "" : " disabled"}>
      <div class="label">${label}</div><div class="value">${val}</div>
    </button>`;
  els.summary.innerHTML =
    stat("card-music", "🎵 推荐歌曲", n) +
    stat("card-bili", "👀 up动态", bili) +
    stat("card-mp", "📰 公众号推文", mp);
}

async function loadDay(date) {
  if (DAYS) {
    render(DAYS[date] || { netease: [], bilibili: [], mp: [] });
    return;
  }
  const d = await api("/api/day/" + date);
  if (d && typeof d === "object" && d.netease === undefined && d.bilibili === undefined
      && d.mp === undefined) {
    d.netease = null; d.bilibili = null; d.mp = null;
  }
  render(d);
}

function selectDate(ymd) {
  currentDate = ymd;
  els.datePicker.value = ymd;
  const btn = document.getElementById("dpButton");
  if (btn) btn.textContent = ymd;
  loadDay(ymd);
}

function buildDatePicker() {
  els.datePicker.style.display = "none";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "dpButton";
  btn.className = "ghost";
  btn.textContent = currentDate;
  els.datePicker.insertAdjacentElement("beforebegin", btn);

  const popup = document.createElement("div");
  popup.id = "dpPopup";
  popup.innerHTML =
    `<div class="dp-head">
      <button type="button" class="ghost" data-dp="-12">«</button>
      <button type="button" class="ghost" data-dp="-1">◀</button>
      <span class="dp-label"></span>
      <button type="button" class="ghost" data-dp="1">▶</button>
      <button type="button" class="ghost" data-dp="12">»</button>
    </div>
    <div class="dp-grid"></div>`;
  els.datePicker.insertAdjacentElement("beforebegin", popup);

  const m = (currentDate || "").match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  let view = m
    ? { y: +m[1], mo: +m[2] - 1 }
    : (() => { const d = new Date(); return { y: d.getFullYear(), mo: d.getMonth() }; })();

  const label = popup.querySelector(".dp-label");
  const grid = popup.querySelector(".dp-grid");
  const DOWS = ["一", "二", "三", "四", "五", "六", "日"];
  const todayStr = localDateStr();

  function render() {
    label.textContent = `${view.y} 年 ${view.mo + 1} 月`;
    const first = new Date(view.y, view.mo, 1);
    const lead = (first.getDay() + 6) % 7;
    const days = new Date(view.y, view.mo + 1, 0).getDate();
    const head = DOWS.map((d) => `<div class="dow">${d}</div>`).join("");
    let body = "";
    for (let i = 0; i < lead; i++) body += `<button type="button" class="out" tabindex="-1"></button>`;
    for (let d = 1; d <= days; d++) {
      const ymd = `${view.y}-${String(view.mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const wd = (first.getDay() + d - 1) % 7;
      const cls = [
        ymd === currentDate ? "selected" : "",
        ymd === todayStr ? "today" : "",
        wd === 0 || wd === 6 ? "weekend" : "",
      ].filter(Boolean).join(" ");
      body += `<button type="button" data-day="${d}" class="${cls}">${d}</button>`;
    }
    grid.innerHTML = head + body;
  }

  function toggle(open) {
    popup.classList.toggle("open", open);
    if (open) {
      render();
      const r = btn.getBoundingClientRect();
      const pw = popup.offsetWidth;
      let left = r.left + r.width / 2 - pw / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
      popup.style.left = left + "px";
      popup.style.top = (r.bottom + 8) + "px";
    }
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle(!popup.classList.contains("open"));
  });

  popup.addEventListener("click", (e) => {
    const dir = e.target.getAttribute && e.target.getAttribute("data-dp");
    if (dir) {
      view = { y: view.y, mo: view.mo + (+dir) };
      if (view.mo < 0) { view.mo = 11; view.y--; }
      if (view.mo > 11) { view.mo = 0; view.y++; }
      render();
      return;
    }
    const day = e.target.getAttribute && e.target.getAttribute("data-day");
    if (day) {
      const ymd = `${view.y}-${String(view.mo + 1).padStart(2, "0")}-${String(+day).padStart(2, "0")}`;
      selectDate(ymd);
      toggle(false);
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target !== btn && !popup.contains(e.target)) toggle(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") toggle(false);
  });
}

function shiftDate(days) {
  const ymd = (currentDate || "").match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  const dt = ymd ? new Date(+ymd[1], +ymd[2] - 1, +ymd[3]) : new Date();
  dt.setDate(dt.getDate() + days);
  const y = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  selectDate(`${y}-${mm}-${dd}`);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

async function init() {
  els.datePicker.value = currentDate;
  $("prevDay").addEventListener("click", () => shiftDate(-1));
  $("nextDay").addEventListener("click", () => shiftDate(1));
  buildDatePicker();

  if (els.collectBtn) {
    els.collectBtn.style.display = "none";
    els.collectMsg.style.display = "none";
  }

  const brandTitle = document.querySelector(".brand h1");
  if (brandTitle) brandTitle.textContent = "每日推送";

  els.emptyState.textContent = "该日暂无推送记录，每日开机自动采集。";

  const biliTitle = document.querySelector("#card-bili h2");
  if (biliTitle) biliTitle.textContent = "📺 B站 UP动态";

  els.ups.classList.add("articles");

  els.summary.addEventListener("click", (e) => {
    const btn = e.target.closest(".stat");
    if (!btn || btn.disabled) return;
    const card = $(btn.dataset.target);
    if (card && card.style.display !== "none") {
      const header = document.querySelector("header");
      const offset = (header ? header.offsetHeight : 0) + 12;
      const top = card.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
    }
  });

  const backTop = document.createElement("button");
  backTop.id = "backTop";
  backTop.className = "back-top";
  backTop.title = "回到顶部";
  backTop.setAttribute("aria-label", "回到顶部");
  backTop.textContent = "^";
  document.body.appendChild(backTop);
  window.addEventListener("scroll", () => {
    backTop.classList.toggle("show", window.scrollY > 0);
  }, { passive: true });
  backTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  const THEME_LOCATION = { lat: 39.9, lon: 116.4, tz: 8 };
  const THEME_AUTO = "auto";

  function sunTimes(date, lat, lon, tz) {
    const y = date.getFullYear(), m = date.getMonth() + 1, d = date.getDate();
    const N1 = Math.floor(275 * m / 9);
    const N2 = Math.floor((m + 9) / 12);
    const N3 = (1 + Math.floor((y - 4 * Math.floor(y / 4) + 2) / 3));
    const N = N1 - (N2 * N3) + d - 30;
    const lngHour = lon / 15;
    const zenith = 90.833;
    const d2r = Math.PI / 180;
    const solve = (kind) => {
      const t = N + ((kind === "rise" ? 6 : 18) - lngHour) / 24;
      const M = (0.9856 * t) - 3.289;
      const L = M + (1.916 * Math.sin(M * d2r)) + (0.020 * Math.sin(2 * M * d2r)) + 282.634;
      let RA = Math.atan(0.91764 * Math.tan(L * d2r)) / d2r;
      RA += Math.floor(L / 90) * 90 - Math.floor(RA / 90) * 90;
      RA = RA / 15;
      const sinDec = 0.39782 * Math.sin(L * d2r);
      const cosDec = Math.cos(Math.asin(sinDec));
      let cosH = (Math.cos(zenith * d2r) - sinDec * Math.sin(lat * d2r))
        / (cosDec * Math.cos(lat * d2r));
      cosH = Math.max(-1, Math.min(1, cosH));
      let H = Math.acos(cosH) / d2r;
      if (kind === "rise") H = 360 - H;
      H = H / 15;
      const local = (H + RA - 0.06571 * t - 6.622 - lngHour + tz) % 24;
      const h = Math.floor(local);
      const mi = Math.round((local - h) * 60);
      const dateMs = new Date(y, m - 1, d, h, mi).getTime();
      return new Date(dateMs);
    };
    return { rise: solve("rise"), set: solve("set") };
  }

  function autoTheme() {
    const now = new Date();
    const { rise, set } = sunTimes(now, THEME_LOCATION.lat, THEME_LOCATION.lon, THEME_LOCATION.tz);
    return now >= rise && now < set ? "light" : "dark";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeBtn.textContent = theme === "dark" ? "🌙" : "☀️";
  }

  const themeBtn = $("themeToggle");
  themeBtn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("theme", next);
  });
  const savedTheme = localStorage.getItem("theme");
  applyTheme(savedTheme === null || savedTheme === THEME_AUTO ? autoTheme() : savedTheme);

  await loadDay(currentDate);
}

init();