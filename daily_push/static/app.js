// Daily Push dashboard app.
const $ = (id) => document.getElementById(id);

const DAYS = window.__DAYS__ || null;

const els = {
  datePicker: $("datePicker"),
  summary: $("summary"),
  songs: $("songs"),
  ups: $("ups"),
  biliRecList: $("biliRecList"),
  xhsList: $("xhsList"),
  douyinList: $("douyinList"),
  mpList: $("mpList"),
  cardMusic: $("card-music"),
  cardBili: $("card-bili"),
  cardBiliRec: $("card-bilirec"),
  cardXhs: $("card-xhs"),
  cardDouyin: $("card-douyin"),
  cardMp: $("card-mp"),
  cfMusic: $("cfMusic"),
  cfNote: $("cfNote"),
  cfCaption: $("cfCaption"),
  cfCounter: $("cfCounter"),
  cfPrev: $("cfPrev"),
  cfNext: $("cfNext"),
  cfDice: $("cfDice"),
  emptyState: $("emptyState"),
  collectBtn: $("collectBtn"),
  collectMsg: $("collectMsg"),
};

// 站点 2026-08-07 才上线：这之前的日期没有任何数据，日期选择器里标灰且不可点
const MIN_DATE = "2026-08-07";

// 有推送记录的日期集合：静态站直接用内联的 DAYS，本地 Flask 走 /api/dates。
// 没产生过推送的日期同样标灰不可点（避免点进去看到空页面）。
let AVAILABLE = DAYS ? new Set(Object.keys(DAYS)) : null;

async function loadAvailableDates() {
  if (AVAILABLE) return AVAILABLE;
  try {
    const d = await api("/api/dates");
    AVAILABLE = new Set((d && d.dates) || []);
  } catch (e) {
    AVAILABLE = null;  // 拿不到就不做这层限制，别把整页卡死
  }
  return AVAILABLE;
}

const dayHasData = (ymd) => (AVAILABLE && AVAILABLE.size ? AVAILABLE.has(ymd) : true);

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
  if (kind === "xhs") {
    if (/300011|异常|风控|verify|461/i.test(r)) return "小红书账号被风控（300011），请先在浏览器正常刷一会儿再试。";
    if (credential) return "小红书登录态已失效，请在浏览器重新登录后再采集。";
    if (conn) return "小红书接口暂时无法连接，请稍后再试。";
    return "小红书推荐获取失败，请稍后重试。";
  }
  if (kind === "douyin") {
    if (/登录态缺失|sessionid/i.test(r)) return "抖音登录态缺失，请在 Firefox 登录抖音后再采集。";
    if (credential) return "抖音登录态已失效，请在浏览器重新登录后再采集。";
    if (conn) return "抖音接口暂时无法连接，请稍后再试。";
    return "抖音推荐获取失败，请稍后重试。";
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

function fmtCount(n, icon) {
  if (n === null || n === undefined || n === "") return "";
  const v = Number(n);
  if (!isFinite(v)) return "";
  const txt = v >= 10000 ? (v / 10000).toFixed(1).replace(/\.0$/, "") + "w" : String(v);
  return `<span class="cstat">${icon} ${txt}</span>`;
}

/* ---- 网易云卡片视图（3D 景深左右切换） --------------------------------
   变换公式参考 GitHub ikabeee/coverflow（vanilla，CSS-3D）：
   每张卡片只暴露两个变量给 CSS —— --side(±1/0 左右侧) 与 --distance(离焦点的张数)，
   剩下的位移 / 后撤 / 旋转 / 淡出全部由 CSS 算，JS 端不需要测量尺寸。
   ---------------------------------------------------------------------- */
const CF = { list: [], items: [], cur: 0, drag: { x: null, moved: false } };

function renderMusic(data, hasDay) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const list = Array.isArray(data) ? data.filter((s) => !s.hidden) : [];
  els.cardMusic.style.display = hasDay ? "" : "none";
  if (!hasDay) return;
  if (isErr || list.length === 0) {
    els.cfMusic.style.display = "none";
    els.cfNote.style.display = "";
    els.cfNote.innerHTML = isErr
      ? errBlock("netease", data.error)
      : `<div class="module-note">🎵 今日暂无新推荐歌曲。</div>`;
    return;
  }
  els.cfMusic.style.display = "";
  els.cfNote.style.display = "none";
  els.songs.innerHTML = list.map((s, i) => {
    const pic = (s.pic || "").replace(/^http:/, "https:");
    const tag = s.url ? "a" : "div";
    const attrs = s.url
      ? `href="${esc(s.url)}" target="_blank" rel="noopener"` : "";
    return `
      <li class="cf-item">
        <${tag} class="cf-card" ${attrs} tabindex="-1">
          ${pic
            ? `<img class="cf-art" src="${esc(pic)}" alt="" draggable="false" loading="lazy" onerror="this.remove()">`
            : `<span class="cf-ph">🎵</span>`}
        </${tag}>
      </li>`;
  }).join("");
  cfSetup(list);
}

function cfSetup(list) {
  CF.list = list;
  CF.cur = 0;
  CF.items = Array.prototype.slice.call(els.songs.children);
  cfApply();
}

function cfGo(delta) {
  cfSelect(CF.cur + delta);
}

// 循环：索引按张数取模，第一张往左就是最后一张
function cfSelect(index) {
  const n = CF.list.length;
  if (n < 2) return;
  const next = ((index % n) + n) % n;
  if (next === CF.cur) return;
  CF.cur = next;
  cfApply();
}

function cfRandom() {
  const n = CF.list.length;
  if (n < 2) return;
  let next = CF.cur;
  while (next === CF.cur) next = Math.floor(Math.random() * n);
  cfSelect(next);
  els.cfDice.classList.remove("spin");
  void els.cfDice.offsetWidth;
  els.cfDice.classList.add("spin");
}

// 邻居关系也按环形算：越过两端的那几张绕回来贴在另一侧
function cfOffset(i, n) {
  let off = i - CF.cur;
  if (off > n / 2) off -= n;
  else if (off < -n / 2) off += n;
  return off;
}

function cfApply() {
  const n = CF.list.length;
  CF.items.forEach((el, i) => {
    const off = cfOffset(i, n);
    el.style.setProperty("--side", Math.sign(off));
    el.style.setProperty("--distance", Math.abs(off));
    el.style.zIndex = String(n - Math.abs(off));
    el.classList.toggle("is-active", off === 0);
    const card = el.firstElementChild;
    if (card && card.tagName === "A") card.tabIndex = off === 0 ? 0 : -1;
  });
  els.cfCounter.textContent = `${CF.cur + 1} / ${n}`;
  els.cfPrev.disabled = els.cfNext.disabled = els.cfDice.disabled = n < 2;
  cfRenderCaption();
}

function cfRenderCaption() {
  const s = CF.list[CF.cur];
  if (!s) {
    els.cfCaption.innerHTML = "";
    return;
  }
  const stats = (s.favorite_count != null || s.comment_count != null)
    ? `<div class="cf-stats">${fmtCount(s.favorite_count, "❤️")}${fmtCount(s.comment_count, "💬")}</div>`
    : "";
  els.cfCaption.innerHTML = `
    <div class="cf-ttl">${esc(s.name)}</div>
    <div class="cf-sub">${esc(s.artists || "")}${s.album ? " · " + esc(s.album) : ""}</div>
    ${stats}
    ${s.hot_comment ? `<div class="cf-quote">“${esc(s.hot_comment)}”</div>` : ""}`;
  els.cfCaption.classList.remove("pulse");
  void els.cfCaption.offsetWidth;
  els.cfCaption.classList.add("pulse");
}

function cfBind() {
  const root = els.cfMusic;
  if (!root) return;
  els.cfPrev.addEventListener("click", () => cfGo(-1));
  els.cfNext.addEventListener("click", () => cfGo(1));
  els.cfDice.addEventListener("click", cfRandom);
  root.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") cfGo(-1);
    else if (e.key === "ArrowRight") cfGo(1);
    else return;
    e.preventDefault();
  });
  root.addEventListener("click", (e) => {
    const item = e.target.closest(".cf-item");
    if (!item) return;
    const i = CF.items.indexOf(item);
    if (i < 0) return;
    if (i === CF.cur) {
      if (CF.drag.moved) e.preventDefault();  // 拖拽回弹不算点击
      return;
    }
    e.preventDefault();  // 点两侧卡片 = 切到那张，不跳转
    cfSelect(i);
  });
  // 触屏 / 鼠标横向拖拽
  const vp = root.querySelector(".cf-viewport");
  vp.addEventListener("pointerdown", (e) => {
    CF.drag = { x: e.clientX, moved: false };
  });
  vp.addEventListener("pointermove", (e) => {
    if (CF.drag.x === null) return;
    if (Math.abs(e.clientX - CF.drag.x) > 12) CF.drag.moved = true;
  });
  const end = (e) => {
    if (CF.drag.x === null) return;
    const dx = e.clientX - CF.drag.x;
    CF.drag.x = null;
    if (Math.abs(dx) >= 45) cfGo(dx < 0 ? 1 : -1);
  };
  vp.addEventListener("pointerup", end);
  vp.addEventListener("pointercancel", () => { CF.drag = { x: null, moved: false }; });
}

function renderBili(data, hasDay) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const list = Array.isArray(data) ? data.filter((u) => !u.hidden) : [];
  els.cardBili.style.display = hasDay ? "" : "none";
  if (!hasDay) return;
  if (isErr) {
    els.ups.innerHTML = errBlock("bilibili", data.error);
    return;
  }
  if (list.length === 0) {
    els.ups.innerHTML = `<div class="module-note">📺 今日暂无新B站视频。</div>`;
    return;
  }
  els.ups.innerHTML = list.map((u) => {
    const pic = (u.pic || "").replace(/^http:/, "https:");
    return `
      <li class="gcard">
        <a class="gthumb" href="${esc(u.url)}" target="_blank" rel="noopener">
          ${pic ? `<img src="${esc(pic)}" loading="lazy" onerror="this.remove()">` : `<span class="gthumb-ph">📺</span>`}
        </a>
        <div class="ginfo">
          <a class="gtitle" href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.title)}</a>
          <div class="gmeta">
            ${u.author ? `<span class="author">${esc(u.author)}</span>` : ""}
            ${u.created ? `<span class="time">${esc(fmtCreated(u.created))}</span>` : ""}
          </div>
        </div>
      </li>`;
  }).join("");
}

function renderXhs(data, hasDay) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const list = Array.isArray(data) ? data.filter((n) => !n.hidden) : [];
  // 小红书模块是 2026-10-27 才加的：历史日期没有这个字段就整块不显示
  const hasData = data !== undefined && data !== null;
  els.cardXhs.style.display = hasDay && hasData ? "" : "none";
  if (!hasDay || !hasData) return;
  if (isErr) {
    els.xhsList.innerHTML = errBlock("xhs", data.error);
    return;
  }
  if (list.length === 0) {
    els.xhsList.innerHTML = DAYS
      ? `<div class="module-note">📕 小红书仅在本机采集（依赖本机登录态），云端不采集，故此处为空。</div>`
      : `<div class="module-note">📕 今日暂无 5k 赞以上的推荐。</div>`;
    return;
  }
  els.xhsList.innerHTML = list.map((n) => {
    const pic = (n.pic || "").replace(/^http:/, "https:");
    const likes = n.likes_text || String(n.likes || "");
    return `
      <li class="gcard">
        <a class="gthumb" href="${esc(n.url)}" target="_blank" rel="noopener">
          ${pic ? `<img src="${esc(pic)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : `<span class="gthumb-ph">📕</span>`}
          <span class="xhs-likes">♥ ${esc(likes)}</span>
        </a>
        <div class="ginfo">
          <a class="gtitle" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title || "（无标题）")}</a>
          <div class="gmeta">
            <span class="author">${esc(n.author)}</span>
            ${n.created ? `<span class="time">${esc(fmtCreated(n.created))}</span>` : ""}
          </div>
        </div>
      </li>`;
  }).join("");
}

function renderDouyin(data, hasDay) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const list = Array.isArray(data) ? data.filter((n) => !n.hidden) : [];
  // 抖音模块是 2026-10-27 才加的：历史日期没有这个字段就整块不显示
  const hasData = data !== undefined && data !== null;
  els.cardDouyin.style.display = hasDay && hasData ? "" : "none";
  if (!hasDay || !hasData) return;
  if (isErr) {
    els.douyinList.innerHTML = errBlock("douyin", data.error);
    return;
  }
  if (list.length === 0) {
    els.douyinList.innerHTML =
      `<div class="module-note">🎬 今日暂无符合条件的推荐（2 万赞以上 + 藏赞比达标）。</div>`;
    return;
  }
  els.douyinList.innerHTML = list.map((n) => {
    const pic = (n.pic || "").replace(/^http:/, "https:");
    return `
      <li class="gcard">
        <a class="gthumb" href="${esc(n.url)}" target="_blank" rel="noopener">
          ${pic ? `<img src="${esc(pic)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : `<span class="gthumb-ph">🎬</span>`}
          <span class="xhs-likes">♥ ${esc(fmtViews(n.digg))}</span>
        </a>
        <div class="ginfo">
          <a class="gtitle" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title || "（无文案）")}</a>
          <div class="gmeta">
            ${n.author ? `<span class="author">${esc(n.author)}</span>` : ""}
            ${n.created ? `<span class="time">${esc(fmtCreated(n.created))}</span>` : ""}
          </div>
        </div>
      </li>`;
  }).join("");
}

function fmtViews(n) {
  const v = Number(n) || 0;
  if (v >= 100000000) return (v / 100000000).toFixed(1).replace(/\.0$/, "") + "亿";
  if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, "") + "万";
  return String(v);
}

function renderBiliRec(data, hasDay) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const list = Array.isArray(data) ? data.filter((u) => !u.hidden) : [];
  // 模块是 2026-10-27 才加的：该日没有这个字段（历史日期）就整块不显示，
  // 否则别人会看到「B站推荐 0」而以为当天没内容。
  const hasData = data !== undefined && data !== null;
  els.cardBiliRec.style.display = hasDay && hasData ? "" : "none";
  if (!hasDay || !hasData) return;
  if (isErr) {
    els.biliRecList.innerHTML = errBlock("bilibili", data.error);
    return;
  }
  if (list.length === 0) {
    els.biliRecList.innerHTML =
      `<div class="module-note">🔥 今日暂无符合条件的推荐（未关注 + 播放量、点赞数达标）。</div>`;
    return;
  }
  els.biliRecList.innerHTML = list.map((u) => {
    const pic = (u.pic || "").replace(/^http:/, "https:");
    return `
      <li class="gcard">
        <a class="gthumb" href="${esc(u.url)}" target="_blank" rel="noopener">
          ${pic ? `<img src="${esc(pic)}" loading="lazy" onerror="this.remove()">` : `<span class="gthumb-ph">🔥</span>`}
          <span class="rec-views">▶ ${esc(fmtViews(u.views))}</span>
        </a>
        <div class="ginfo">
          <a class="gtitle" href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.title)}</a>
          <div class="gmeta">
            ${u.author ? `<span class="author">${esc(u.author)}</span>` : ""}
            <span class="time">♥ ${esc(fmtViews(u.likes))}</span>
          </div>
        </div>
      </li>`;
  }).join("");
}

function renderArticles(data, hasDay) {
  const isErr = data && typeof data === "object" && !Array.isArray(data) && data.error;
  const list = Array.isArray(data) ? data.filter((a) => !a.hidden) : [];
  els.cardMp.style.display = hasDay ? "" : "none";
  if (!hasDay) return;
  if (isErr) {
    els.mpList.innerHTML = errBlock("mp", data.error);
    return;
  }
  if (list.length === 0) {
    // mp 为空时也保留卡片：云端（静态站）显示「仅本机采集」说明；
    // 本地则提示「今日暂无新推文」，避免公众号模块在网页上整个消失
    els.mpList.innerHTML = DAYS
      ? `<div class="module-note">📰 公众号推文仅在本机（微信解密环境）采集，云端不采集，故此处为空。</div>`
      : `<div class="module-note">📰 今日暂无新公众号推文。</div>`;
    return;
  }
  els.mpList.innerHTML = list.map((a) => {
    const pic = (a.pic || "").replace(/^http:/, "https:");
    return `
      <li class="gcard${a.notify ? " notify" : ""}">
        <a class="gthumb" href="${esc(a.url)}" target="_blank" rel="noopener">
          ${pic ? `<img src="${esc(pic)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : `<span class="gthumb-ph">📰</span>`}
        </a>
        <div class="ginfo">
          <a class="gtitle" href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
          <div class="gmeta">
            ${a.author ? `<span class="author">${esc(a.author)}</span>` : ""}
            <span class="time">${a.notify ? "通知 · " : ""}${esc(a.time || "")}</span>
          </div>
        </div>
      </li>`;
  }).join("");
}

function render(data) {
  const hasDay = !!data;
  renderMusic(data && data.netease, hasDay);
  renderBili(data && data.bilibili, hasDay);
  renderBiliRec(data && data.bili_rec, hasDay);
  renderXhs(data && data.xhs, hasDay);
  renderDouyin(data && data.douyin, hasDay);
  renderArticles(data && data.mp, hasDay);

  // 整日无记录（未采集）→ 只显示「该日暂无推送记录」；
  // 有记录但某平台为空 → 各卡片显示「今日暂无新…」；采集失败 → 卡片显示错误块。
  els.emptyState.style.display = hasDay ? "none" : "";
  renderSummary(data || {});
}

function renderSummary(data) {
  const shown = (x) => (Array.isArray(x) ? x.filter((i) => !i.hidden).length : 0);
  // 当天没有这个字段（模块上线前的历史日期）就不显示对应统计项
  const present = (x) => x !== undefined && x !== null;
  const n = shown(data.netease);
  const mp = shown(data.mp);
  const bili = shown(data.bilibili);
  const rec = shown(data.bili_rec);
  const xhs = shown(data.xhs);
  const douyin = shown(data.douyin);
  const stat = (target, label, val) => `
    <button class="stat" data-target="${target}"${val ? "" : " disabled"}>
      <div class="label">${label}</div><div class="value">${val}</div>
    </button>`;
  els.summary.innerHTML =
    stat("card-music", "🎵 推荐歌曲", n) +
    (present(data.bili_rec) ? stat("card-bilirec", "🔥 B站推荐", rec) : "") +
    stat("card-bili", "👀 up动态", bili) +
    (present(data.xhs) ? stat("card-xhs", "📕 小红书", xhs) : "") +
    (present(data.douyin) ? stat("card-douyin", "🎬 抖音", douyin) : "") +
    stat("card-mp", "📰 公众号推文", mp);
}

async function loadDay(date) {
  if (DAYS) {
    render(DAYS[date] || null);
    return;
  }
  const d = await api("/api/day/" + date);
  const hasRow = d && typeof d === "object"
    && (d.netease !== undefined || d.bilibili !== undefined || d.mp !== undefined
        || d.xhs !== undefined || d.bili_rec !== undefined || d.douyin !== undefined);
  render(hasRow ? d : null);
}

function selectDate(ymd) {
  if (ymd && ymd < MIN_DATE) return;
  if (ymd && !dayHasData(ymd)) return;  // 该日没有推送记录
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
      const beforeLaunch = ymd < MIN_DATE;
      const noPush = !dayHasData(ymd);
      const locked = beforeLaunch || noPush;
      const cls = [
        ymd === currentDate ? "selected" : "",
        ymd === todayStr ? "today" : "",
        wd === 0 || wd === 6 ? "weekend" : "",
        beforeLaunch ? "before-launch" : "",
        noPush ? "no-push" : "",
      ].filter(Boolean).join(" ");
      body += `<button type="button" data-day="${d}" class="${cls}"${locked ? " disabled" : ""}>${d}</button>`;
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
      const mo = view.mo + (+dir);
      view = { y: view.y + Math.floor(mo / 12), mo: ((mo % 12) + 12) % 12 };
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
  // 有日期清单时直接跳到「上一个/下一个有推送的日期」，跳过没推送的空档
  if (AVAILABLE && AVAILABLE.size) {
    const list = [...AVAILABLE].sort();
    const pick = days > 0
      ? list.find((d) => d > currentDate)
      : [...list].reverse().find((d) => d < currentDate);
    if (pick) selectDate(pick);
    return;
  }
  const ymd = (currentDate || "").match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  const dt = ymd ? new Date(+ymd[1], +ymd[2] - 1, +ymd[3]) : new Date();
  dt.setDate(dt.getDate() + days);
  const y = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  const next = `${y}-${mm}-${dd}`;
  if (next < MIN_DATE) return;  // 站点上线前没有数据
  selectDate(next);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

async function init() {
  await loadAvailableDates();
  // 今天还没采集时，直接落到最近一个有推送的日期，别停在空页
  if (AVAILABLE && AVAILABLE.size && !AVAILABLE.has(currentDate)) {
    currentDate = [...AVAILABLE].sort().pop();
  }
  els.datePicker.value = currentDate;
  $("prevDay").addEventListener("click", () => shiftDate(-1));
  $("nextDay").addEventListener("click", () => shiftDate(1));
  buildDatePicker();
  cfBind();

  if (els.collectBtn) {
    els.collectBtn.style.display = "none";
    els.collectMsg.style.display = "none";
  }

  const brandTitle = document.querySelector(".brand h1");
  if (brandTitle) brandTitle.textContent = "每日推送";

  const settingsLink = $("settingsLink");
  if (settingsLink && DAYS) settingsLink.style.display = "none";

  els.emptyState.textContent = "该日暂无推送记录，每日开机自动采集。";

  const biliTitle = document.querySelector("#card-bili h2");
  if (biliTitle) biliTitle.textContent = "📺 B站 UP动态";

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