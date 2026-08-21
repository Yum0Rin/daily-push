# 前端说明

前端为纯静态（无框架），`templates/index.html` + `static/app.js` + `static/style.css`。

## 双数据源

`app.js` 顶部读取 `window.__DAYS__`（`const DAYS = window.__DAYS__ || null`），据此决定走哪种模式：

- **本地模式**（Flask）：无 `__DAYS__`，`loadDay(date)` 请求 `/api/day/<date>`。
- **静态模式**（GitHub Pages）：`export_site.py` 已把全部历史数据内联成 `window.__DAYS__ = {...}`，
  `loadDay` 直接读内存，不发任何请求。这个单文件 `site/index.html` 也是导出/发布的核心产物。

新增数据字段时两边都要通：改 `storage` 输出后，`app.js` 的 `render()` 按 `data.netease / data.bilibili / data.mp` 消费。

## 页面结构

```
header: 品牌标题 + 主题切换 | 日期条（◀ datePicker ▶）
main:
  summary       # 顶部统计卡（歌曲/B站/公众号 条数，点击居中到对应卡片）
  card-music    # 🎵 网易云日推 Top N（带封面/播放外链）
  card-bili     # 📺 B站关注UP（最近视频：标题链接+UP名+时间，同公众号排版）
  card-mp       # 📰 微信公众号推文（作者+标题+时间，外链跳转，通知类弱化置底）
  emptyState    # 无数据提示（每日开机自动采集）
右下角：回到顶部按钮（🔝，滚动离开顶部时出现）
```

## 关键逻辑 (app.js)

- `render(data)`：依据 `data.mp` / `data.netease` / `data.bilibili`
  是否存在且非空来显示/隐藏卡片，并渲染 summary。
- `renderArticles`：逐条渲染公众号推文，`a.author` 显示公众号名，
  `a.notify` 为 true 时加「通知」标签并弱化样式（排序由后端完成）。
  **mp 为空时也保留公众号卡片**：云端静态站（`window.__DAYS__` 存在）显示
  「公众号推文仅在本机采集，云端不采集」权限说明；本地则显示「今日暂无新公众号推文」，
  避免卡片整个消失。
- `renderBili`：B站卡片复用公众号排版（标题链接 + `u.author` 下一行 + `u.created` 时间），
  初始化时给 `#ups` 加上 `articles` class 以复用样式。
- `renderMusic`：歌手/专辑下一行展示热评（`s.hot_comment`，双引号包裹）。
- summary 点击：手动计算 `scrollTo`（卡片顶部对齐到吸顶标题栏下方），保证卡片标题可见。
- 采集：无手动按钮，每日开机自动采集（另有 07:30 兜底定时），刷新页面即可看到。
- 主题：`data-theme=dark/light`，持久化到 `localStorage.theme`。
- 日期：`datePicker` + 前后切换；`loadDay` 请求 `/api/day/<date>`。
- 渲染时全部经 `esc()` 转义（防 XSS）。

## 样式注意

- `.articles li` / `.articles .ainfo` 是公众号与 B站共用排版（标题链接 + 作者下一行 + 时间）。
- 徽章：`.badge-updated / .badge-idle / .badge-err`（当前 B站卡已不用）。
- QQ / 微信卡片样式已无引用（采集保留，前端移除）。

## 变更记录

- 移除「日期标签」区块（由 datePicker 显示日期）。
- 移除 QQ 卡片（index.html `card-qq` / app.js `qqList`/`cardQQ` 及 summary 的 QQ 列）。
- 移除微信卡（index.html `card-wechat` / app.js `wechatList`/`cardWechat` 及 summary 的微信列）。
- 移除「立即采集」按钮与 `collect()`（每日定时自动采集）。
- 新增公众号卡片（`card-mp` / `mpList` / `renderArticles`）。
- 公众号卡片增强：逐条显示作者、通知类弱化（`li.notify` + `tag`）。
- B站卡片改为公众号排版（去掉「最新：」前缀与错误/空闲徽章）。

