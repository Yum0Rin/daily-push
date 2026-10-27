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
  summary       # 顶部统计卡（歌曲/B站/B站推荐/小红书/抖音/公众号 条数，点击居中到对应卡片）
  card-music    # 🎵 网易云日推：3D 卡片流（景深左右切换，循环）+ 焦点歌曲信息条
  card-bilirec  # 🔥 B站首页推荐（未关注，播放量+点赞率；封面角标显示播放量）
  card-bili     # 📺 B站关注UP（最近视频：标题链接+UP名+时间，同公众号排版）
  card-xhs      # 📕 小红书推荐（3:4 竖图 + 点赞角标）
  card-douyin   # 🎬 抖音推荐（3:4 竖图 + 点赞角标，同小红书排版）
  card-mp       # 📰 微信公众号推文（作者+标题+时间，外链跳转，通知类弱化置底）
  emptyState    # 无数据提示（登录时自动采集一次）
右下角：回到顶部按钮（🔝，滚动离开顶部时出现）
```

> `card-bilirec` / `card-xhs` / `card-douyin` 都是 2026-10-27 加的模块：
> 当天**没有该字段就整块隐藏**（历史日期不会显示「0 条」）。

## 关键逻辑 (app.js)

- `render(data)`：依据 `data.douyin` / `data.xhs` / `data.bili_rec` / `data.mp` / `data.netease` / `data.bilibili`
  是否存在且非空来显示/隐藏卡片，并渲染 summary。
- `renderArticles`：逐条渲染公众号推文，`a.author` 显示公众号名，
  `a.notify` 为 true 时加「通知」标签并弱化样式（排序由后端完成）。
  **mp 为空时也保留公众号卡片**：云端静态站（`window.__DAYS__` 存在）显示
  「公众号推文仅在本机采集，云端不采集」权限说明；本地则显示「今日暂无新公众号推文」。
  但整日无任何记录（emptyState 显示「该日暂无推送记录」）时，`render()` 会强制隐藏
  公众号卡片，避免「暂无推送记录」与公众号说明两个提示重复矛盾。
- `renderBili`：B站卡片复用公众号排版（标题链接 + `u.author` 下一行 + `u.created` 时间），
  初始化时给 `#ups` 加上 `articles` class 以复用样式。
- `renderDouyin`：抖音推荐卡片，排版同 `renderXhs`（3:4 竖图 + 右下角 `♥ 点赞数`，
  用 `fmtViews` 显示「万/亿」），额外用 `referrerpolicy="no-referrer"` 规避封面防盗链。
- `renderMusic`：渲染 3D 卡片流（见下节「网易云卡片流」），信息（歌名/歌手·专辑/❤️💬/热评）
  放在卡片流下方的 `#cfCaption` 里，点卡片本身即跳转网易云播放页。
- **网易云卡片流**（2026-10-27 起）：`#cfMusic` 为容器，`.cf-viewport > .cf-stage > ol.cf-track > li.cf-item`。
  - 变换公式参考 GitHub [ikabeee/coverflow](https://github.com/ikabeee/coverflow)（vanilla + CSS-3D）：
    JS 只给每张卡写 `--side`（±1/0）与 `--distance`（离焦点几张），
    位移/后撤/`rotateY`/淡出/`z-index` 全在 CSS 里算（`style.css` 的 `.cf-*`），**不做尺寸测量**。
  - **循环**：`CF.cur` 按张数取模，首尾相接；邻居距离用 `cfOffset()` 取环形最短路径，
    所以「第 1 首往左」是最后一首，「最后一首往右」回到第 1 首，动画只挪一格。
  - 交互：◀ ▶ 按钮、`#cfMusic` 上的 ← → 方向键、横向拖拽/滑动（≥45px）、点两侧卡片切到那张、
    点正中卡片跳转外链；右上角 🎲（`#cfDice`）随机跳到另一首（`cfRandom()`，带旋转动画）。
  - 空/错误态不塞进 3D 舞台：隐藏 `#cfMusic`，改用 `#cfNote` 显示 `errBlock` / `module-note`。
- summary 点击：手动计算 `scrollTo`（卡片顶部对齐到吸顶标题栏下方），保证卡片标题可见。
- 采集：无手动按钮；登录时自动采集一次（`tools/run_daily.py`），07:30 由云端采集；刷新页面即可看到。
- 主题：`data-theme=dark/light`，持久化到 `localStorage.theme`。
- 日期：`datePicker` + 前后切换；`loadDay` 请求 `/api/day/<date>`。
- 渲染时全部经 `esc()` 转义（防 XSS）。

## 样式注意

- `.articles li` / `.articles .ainfo` 是公众号与 B站共用排版（标题链接 + 作者下一行 + 时间）。
- 网易云卡片流（`.cf`）全靠 CSS 变量调形：`--cf-cover`（卡片边长，`clamp(150px,38vw,250px)`）、
  `--cf-gap` / `--cf-step`（左右间距与层间步进）、`--cf-depth`（后撤深度）、`--cf-angle`（旋转角 58deg）、
  `--cf-stage-w`（720px 舞台最大宽度，骰子按它对齐右缘）。改形只动这几个变量。
- 边缘淡出用 `.cf-viewport` 的 `mask`（**不要**把它挪到带 `perspective` 的 `.cf-stage` 上，
  那会把 3D 子树拍平）；横向溢出由 `overflow:hidden` 兜住。
- 浅色主题下非焦点卡片的压暗层更淡（`[data-theme="light"] .cf-item:not(.is-active) .cf-card::after`），
  焦点卡阴影也单独调过，否则白底上会发灰。
- 徽章：`.badge-updated / .badge-idle / .badge-err`（当前 B站卡已不用）。
- QQ / 微信卡片样式已无引用（采集保留，前端移除）。

## 本地设置页（`templates/settings.html` + `static/settings.{css,js}`）

- 与仪表盘**同一套样式**（复用 `static/style.css`，追加 `settings.css`）；由 Flask 的 `/settings` 渲染。
- 仅本机可访问，**不参与静态站导出**：`export_site.py` 会把 `#settingsLink` 从导出 HTML 中剥离。
- 页面从 `<meta name="csrf-token">` 取本次启动的随机 token，所有 `/api/settings*` 请求带 `X-CSRF-Token`。
- 区块：运行状态、平台登录状态（检测 / 保存并验证 Cookie，值打码）、屏蔽名单（标签式增删 + 一键应用）、
  采集参数、配置备份；顶栏「← 返回推送页」。
- 「保存并应用到全部推送」会轮询 `/api/settings/purge/status`，完成后按结果提示 Pages / 云端同步情况。
- 仪表盘右上角新增 ⚙️ 入口；**静态站模式（`window.__DAYS__` 存在）下由 `app.js` 隐藏**，避免 Pages 404。

## 变更记录

### 2026-10-27

- **网易云日推改为 3D 卡片流**（景深左右切换）：纵向列表 → 卡片视图。封面为卡片主体，
  歌名/歌手·专辑/❤️💬/热评统一移到卡片流下方的信息条；**卡片上不显示序号**，信息条标题也不加序号。
  点正中卡片直接跳网易云播放页（原「▶ 在网易云打开」文字链已删，避免重复入口）。
- 卡片流**循环**：首尾相接，第 1 首往左 = 最后一首，最后一首往右回到第 1 首（`CF.cur` 取模 + 环形距离）。
- 卡片流右缘新增 🎲 随机按钮，点一下随机跳到另一首（带旋转动画）；另有 ◀ ▶ 按钮、
  ← → 方向键、横向拖拽/滑动、点两侧卡片切换。
- 空态/错误态改用 `#cfNote`，不再塞进 3D 舞台。旧版（纵向列表）快照见
  `历史版本/music-coverflow-v1-20261027/`。

### 2026-09-15

- 三源空态统一：有记录但某平台无新内容时，卡片保留并显示「今日暂无新…」；
  整日无记录只显示 `#emptyState`；平台失败显示 `errBlock`。此前仅公众号有空态，B站/网易云整卡隐藏。

### 2026-09-14

- 设置页顶栏「← 返回仪表盘」改为「← 返回推送页」。
- 「🩺 运行状态」卡新增「手动推送」按钮：调 `/api/settings/push` 立刻跑一遍定时流程
  （采集 → 导出 → 推送 Pages），轮询 `/api/settings/push/status`，完成后刷新运行状态；不改数据、不清理。
- 「🩺 运行状态」卡新增「停止本地服务」按钮：调 `/api/settings/shutdown` 关闭按需网页
  （网易云代理若在跑一并关）；本机无常驻进程，下次从开始菜单「每日推送」打开。

- 移除「日期标签」区块（由 datePicker 显示日期）。
- 移除 QQ 卡片（index.html `card-qq` / app.js `qqList`/`cardQQ` 及 summary 的 QQ 列）。
- 移除微信卡（index.html `card-wechat` / app.js `wechatList`/`cardWechat` 及 summary 的微信列）。
- 移除「立即采集」按钮与 `collect()`（每日定时自动采集）。
- 新增公众号卡片（`card-mp` / `mpList` / `renderArticles`）。
- 公众号卡片增强：逐条显示作者、通知类弱化（`li.notify` + `tag`）。
- B站卡片改为公众号排版（去掉「最新：」前缀与错误/空闲徽章）。

### 2026-09-12

- 新增本地设置页 `settings.html` / `settings.{css,js}`（同风格，仅本机，CSRF 鉴权）。
- 仪表盘新增 ⚙️ 设置入口；静态站模式下隐藏（`app.js`），并在导出时剥离（`export_site.py`）。
- 修复日期选择器 `«`/`»` 的跨年 bug：原来 ±12 个月只做一次 `if` 归一化，9 月会落到 12 月/1 月；
  改为取模 `view.y += Math.floor(mo/12); mo = ((mo%12)+12)%12`，现在 2026-09 → 2025-09 / 2027-09。
- 样式修复：`a.ghost`（返回仪表盘）按钮化；移除网易云登录卡的 `api` 小标签（B站无 mode，两卡对称）；
  toast 默认隐藏（此前空泡挂在顶部）；「仅本机可访问」改为右侧独立徽章。
- 设置页平台登录卡新增「同步云端」勾选：保存 Cookie 时可选 `gh secret set` 同步到云端 Secrets
  （`cloud-status` 不可用时自动禁用；邮件兜底流程保留）。
- 「B站翻页数」标签改为更直白的「B站动态翻页数（每页上限约20条）」。
- 设置页新增「🩺 运行状态」卡（上次采集/推送/清理发布/检测）与「💾 配置备份」卡（下载/上传还原）。
- 不直观的字段旁加 ⓘ 悬停说明（纯 CSS tooltip，无需 JS）；移除「屏蔽名单」卡里冗余的说明句
  与公众号关键词的 ⓘ（括号内已说明清楚）。
- 采集参数新增「网易云最大评论数」「网易云最大收藏数」（超过则跳过，0=不限）；
  「保存参数」右侧加 ⓘ 说明「调整会应用到全部推送」，原两个按钮合并为一个（保存即补全历史 + 过滤 + 重发）。
- 网易云歌曲卡在歌手下方显示 ❤️ 收藏数 / 💬 评论数（`favorite_count` / `comment_count`，万级简写为 `x.xw`）。
- B站与公众号共用 `.cardgrid` 网格：B站窄屏 2 列 / 宽屏 3 列；**公众号卡片更宽**（窄屏 1 列 / 宽屏 2 列）。
- 封面：B站 16:9；公众号按微信 **2.35:1 完整显示**（卡片更宽故不显小）；公众号标题**固定两行**
  （单行也占两行高，超出显示省略号）。
- 公众号封面防盗链：`mmbiz.qpic.cn` 对非微信 Referer 返回「不允许引用」占位图。
  页面 `<head>` 加 `<meta name="referrer" content="no-referrer">`（img 也带 `referrerpolicy="no-referrer"`），
  浏览器不发送 Referer → 微信返回真图（本地另有 `Referrer-Policy: no-referrer` 响应头，Pages 靠该 meta）。
- 无封面条目（非正式推文 / 失效视频）显示**占位封面** `.gthumb-ph`（渐变底 + 📰/📺），保留在列表里不删除。
- 网易云卡片：标题改「网易云日推」，并改为**内滚动卡片**（`.songs { max-height: min(440px, 78vh); overflow-y:auto }`，
  约显示前 5 首、不超过一屏），配合 `max_songs=0` 不限数量。
- B站封面取动态 `archive.cover`；公众号封面取 appmsg `thumburl` / `cover_16_9`（`mmbiz.qpic.cn`）。
- 网易云封面 URL 规范为 `https://`（修复被 CSP / 混内容拦截）；前端也对旧数据兜底替换。
- 三张卡片（音乐/B站/公众号）均过滤 `hidden` 隐藏缓冲项，summary 计数同样排除。

