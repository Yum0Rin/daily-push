# 更新日志（CHANGELOG）

> 本项目无正式版本号，按日期记录重要变更，**最新在上**。
> 更细的设计见 [docs/](docs/README.md)，当前能力与已知问题见 [docs/status.md](docs/status.md)。

## 2026-10-27

### 新增（同日第三批）：小红书「藏/赞比」筛选
- **小红书不提供浏览量**：推荐流与笔记详情接口都没有 `view/play` 字段（只有作者在创作中心能看到），
  所以做不了 B站 那种「点赞/播放」。改用详情接口的收藏数算 **藏/赞比** 作质量代理。
- `sources/xiaohongshu.py`：新增 `_detail()`（`POST /api/sns/web/v1/feed`，签名同推荐流），
  只对**已过点赞阈值**的候选查一次详情，按 `collected_count / liked_count` 过滤；
  详情失败按「比例未知」**放行**（不因一次请求失败丢内容）。
- 新策略 `xiaohongshu.min_collect_ratio`（默认 `0.04`，`0` = 关闭该过滤、也完全不发详情请求），
  设置页「采集参数」可改；`detail_interval` 默认 1.5s 节流。
- 卡片新增 `⭐ 收藏数`（悬停显示藏赞比百分比）；数据字段新增 `collects` / `collect_ratio`。
- 实测：18 条候选的藏/赞比 p25=0.040、中位 0.077、p75=0.129（跨度 25 倍，区分度够）；
  默认 0.04 约淘汰最低 20~25%，单次采集 10 条耗时由 ~12s 增至 ~28s（多 15~20 次详情请求）。
- 测试：`tests/test_xhs_filter.py` 新增 4 项（低于阈值丢弃 / 达标保留并回填 / 详情失败放行 / 阈值 0 不请求）。

### 调整（同日第四批）
- 小红书藏/赞比阈值由 0.04 提到 **0.1**，`max_pages` 6 → 8，实际取 **5~10 条**
  （实测一次 9 条，耗时约 65 秒 / 30~35 次详情请求）。
- **前端不再显示比值**：B站推荐改为「▶ 播放量 + ♥ 点赞数」，小红书改为「♥ 点赞 + ⭐ 收藏」，
  两个原始数据都展示，比值只用于后台筛选。

### 调整（同日第七批）：日期置灰 + B站推荐置顶
- 日期选择器：**没有推送记录的日期也标灰、不可点**（原先只挡 2026-08-07 之前的日期）。
  日期清单静态站取 `window.__DAYS__`、本地 Flask 取 `/api/dates`；拿不到清单时不做这层限制（不卡死页面）。
  左右箭头改为直接跳到「上一个/下一个有推送的日期」；今天还没采集时自动落到最近一个有数据的日期。
- 「🔥 B站推荐（未关注）」去掉括号 → 「🔥 B站推荐」，卡片移到「📺 B站 UP动态」**上面**，
  顶部统计项顺序同步（推荐歌曲 → B站推荐 → up动态 → 小红书 → 公众号）。
- 实测：库里 80 个日期中 2026-08-13 / 2026-08-30 缺失，截图确认这两天已置灰；未来日期同样置灰。

### 调整（同日第六批）：单模块 30 秒预算
- **每个模块加 `time_budget` 硬闸**：B站推荐 20s、小红书 30s；到点立刻收尾，
  已取到的条目照常返回，不会因为超时丢整批结果。
- **间隔不缩小**（小红书翻页 2.0s / 详情 1.5s，B站 1.2s）——防账号被标记异常；
  省时间靠「少翻页 + 少查详情」，不靠压间隔。
- 小红书 `max_pages` 8 → **4**：实测候选数远超详情吞吐，多翻页只是白耗时间；
  4 页 + 14~16 次详情正好落在 30s 内。
- 实测：B站 6 条 2~8 秒；小红书 6 条 22.6 秒（同一天再跑一次为 3 条 30 秒，
  说明阈值 0.1 下条数会随推荐流波动，`≤6` 是上限不是保证）。
- 测试 +1（预算耗尽后不再翻页，98 项）。

### 调整（同日第五批）
- **B站推荐 / 小红书推荐条数统一改为 6 条**（`bilibili.recommend.limit`、`xiaohongshu.limit`，
  本地 `config.json` 与云端默认值同步）。实测一次：B站 6 条 + 小红书 6 条，共 35.7 秒。
- 调研「赞/评」作为替代比例（**未启用**，仅记录数据）：17 条 5k+ 候选的
  `赞/评` 为 min 2.7 / p25 6.9 / 中位 40.7 / p75 75.3 / max 226，
  即**极度长尾**，且衡量的是「讨论密度」而非内容质量（高 = 看图点赞就走，低 = 求助/争议/答疑）。

### 新增
- **小红书推荐流接入**（`daily_push/sources/xiaohongshu.py`，恢复 8 月因风控暂停的源）。
  - 走 PC 网页 `POST /api/sns/web/v1/homefeed`（`category=homefeed_recommend`），20 条/页、`cursor_score` 翻页。
  - 签名用纯 Python 的 `xhshow` 生成 `x-s / x-t / x-s-common`（不再需要浏览器执行 JS）；
    8 月那次账号风控 `300011` 已解除，实测 `code 0`。
  - 登录态：优先 `config.json` 的 `xiaohongshu.cookie`，否则**只读**读本机 Firefox 的 `cookies.sqlite`
    （`mode=ro&immutable=1`）。Chrome 127+ Cookie 是 App-Bound 加密，进程外解不开，故不支持。
  - 筛选：点赞 ≥ `min_likes`（默认 5000），默认返回 `limit=10` 条；标题/作者命中广告关键词即丢弃。
  - 时间戳从笔记 ID 前 8 位十六进制解析（`created`），仅用于显示——推荐流会推老笔记，**不套时间窗口**。
  - 推送页新增「📕 小红书推荐」卡片：3:4 竖图 + 右下角点赞角标 + 作者 + 发布时间；汇总栏加一项。
- `export_site._merge_published()`：已存在的日期也补**缺失字段**（mp / xhs），
  避免云端每天导出一次就把本地采到的小红书/公众号数据从已发布页面上抹掉。

### 新增（同日第二批）
- **B站首页推荐模块**（`bilibili.BiliRecommendCollector` → `bili_rec` 字段）。
  - 接口 `x/web-interface/index/top/feed/rcmd`，**不需要 WBI**、需要 SESSDATA；20 条/页，`fresh_idx` 翻页。
  - 接口自带 `is_followed` 与 `stat.view/like`：只留**未关注** UP，且 `播放 > min_views`、`点赞率 > min_like_ratio`。
  - 默认 `min_views=50000`、`min_like_ratio=0.07`、`limit=10`、`max_pages=8`（策略在 `settings.json` 的
    `bilibili.recommend`，设置页「采集参数」可直接改）。
  - 额外过滤 `goto != av`、`rcmd_reason` 含广告/赞助、作者命中 `bilibili.exclude`；不套时间窗口，按 bvid 跨天去重。
  - 「关注 UP 动态」保持原样，两个模块互不影响。
- **小红书上云**（按 B 站同一套方法处理登录）：
  - `tools/make_cloud_config.py` 读 Secret `XHS_COOKIE`；`.github/workflows/daily-collect.yml` 传入；
    `cloud_collect.py` 改回 `xhs=True`。
  - `cloud_secrets.py` / `cookie_repair_cloud.py` 的 `SECRET_NAMES` 加 `xiaohongshu → XHS_COOKIE`；
    `trigger_cookie_repair.py` 把小红书纳入 cookie 类错误判定。
  - `cookie_reply.py`：新增 `_normalize_cookie("xiaohongshu")`（整段 Cookie 归一化）、
    `test_xiaohongshu_cookie()`（调推荐流验证签名+登录态）、`apply_local_config` 支持写回。
  - 设置页新增「小红书」登录卡片：粘贴**整段** Cookie（含 `a1` + `web_session`）→ 保存并验证 → 可勾「同步云端」。
  - `XhsCollector` 增加 `a1` 校验：只给 `web_session` 会明确报错（签名需要 a1）。
- **新模块按日期显示**：小红书 / B站推荐是今天才加的，前端对**没有该字段的历史日期整块隐藏**
  （卡片 + 汇总统计项都不渲染），避免「0 条」被误解为当天没内容。

### 变更（同日第二批）
- `storage.py`：新增 `bili_rec` 列；`collector.py` 同时采集 `bilibili` 与 `bili_rec`。
- `settings_store.py`：新增 `_ratio` 校验器（0~1），`bilibili.recommend` 策略项与默认值。
- `settings.js`：参数项支持 `float`（点赞率 0.07 不再被 `parseInt` 截断）；`SOURCES` 增加 `field` 字段。
- `purge_ignored` / `netease_history` / `cover_backfill` / `cloud_collect` 的 `overwrite=True` 调用补
  `bili_rec`，避免这些路径把新字段写成 None。

### 已知限制
- **广告判定是启发式**：推荐流返回的 `note_card` 只有 cover/type/title/user/interact_info，
  没有广告/赞助标记，只能靠标题+作者关键词过滤，会漏判和误杀。
- B站推荐是**个性化**流，没登录会退化成热门榜；阈值偏严时可能凑不满 10 条（返回实际条数）。
- 云端小红书依赖 `XHS_COOKIE`；未配置时报「登录态缺失」并触发 cookie-repair 邮件流程。

### 验证
- 小红书：实测 4 页 79 条中 ≥5k 赞 13 条；接入后单次采集 10 条全部 ≥5k。
- B站推荐：实测 5 页 89 条 → 未关注 79 → 播放≥10万 63 → 点赞率>10% 仅 7 条
  （10万+播放的点赞率中位数 4.0%）；改 5万/7% 后单次采集 10 条（4 页、约 3.8 秒）。
- 静态页导出后无头 Chrome 截图确认：今天 5 个统计项 + 4 个卡片正常；切到 2026-10-26 只剩 3 个统计项，
  两个新模块整块隐藏。
- 单元测试 84 项，1 项失败（`test_cloud_secrets` 的 `gh.EXE` vs `gh`，Windows 既有问题，与本次无关）。

### 变更
- `storage.py`：新增 `xhs` 列（老库自动 `ALTER TABLE` 迁移）。
- `collector.py`：`collect_once(..., xhs=True)`，跨天去重按已推 note id。
- `settings_store.py`：`xiaohongshu` 拆成策略（`min_likes/max_pages/ad_keywords/exclude_keywords`，
  写 `settings.json`）+ 密钥（`cookie/limit`，写 `config.json`）；`_SECRET_ROOTS` 移除整个
  `xiaohongshu` 根，改为只屏蔽 `cookie` 叶子。
- `requirements.txt`：新增 `xhshow>=0.2`。

### 已知限制
- **广告判定是启发式**：推荐流返回的 `note_card` 只有 cover/type/title/user/interact_info，
  没有广告/赞助标记，只能靠标题+作者关键词过滤，会漏判和误杀。

### 验证
- 实测 4 页 79 条中 ≥5k 赞 13 条；接入后单次采集 10 条全部 ≥5k。
- 静态页导出后无头 Chrome 截图确认：卡片、封面、点赞角标、汇总统计均正常。
- 单元测试 71 项，1 项失败（`test_cloud_secrets` 的 `gh.EXE` vs `gh`，Windows 既有问题，与本次无关）。

## 2026-09-22

### 新增
- **Linux 本地部署**：同一份代码可在 Linux 跑本地部分（采集→导出→推送 + 按需网页）。
  - `tools/install_linux.py`：幂等地把本地集成装到桌面——systemd 用户服务
    `daily-push-collect.service`（oneshot，绑 `graphical-session.target`，登录跑一次 `tools/run_daily.py` 后退出，
    无常驻；`ExecStartPre` 先等 DNS）+ 应用菜单入口 `daily-push.desktop`（走 `tools/open_dashboard.py`，
    按需拉起 `start.py --serve-only`）。支持 `--start` 立即验证、`--uninstall` 卸载。
  - `assets/daily-push.svg`：桌面入口图标。
- `docs/linux.md`：Linux 部署说明与平台差异对照。

### 变更
- **平台适配**（不改变 Windows 行为）：
  - `daily_push/pipeline.py` `_node_exe()`、`daily_push/cloud_secrets.py` `_gh_exe()`：`node` / `gh` 不在 PATH 时
    退回用户级路径 `~/.local/node/bin/node`、`~/.local/bin/gh`。
  - `daily_push/collector.py`：`wechat_available()` 改为同时检查微信解密模块是否可用；**非 Windows** 且无解密环境时
    公众号源**静默跳过**（不再写 `mp` 错误），避免整轮采集被误判失败而中止推送。`sources/wechat_article.py`
    新增 `decryption_available()`。
  - `tests/test_cloud_secrets.py`：`gh` 断言改为按 basename 匹配，并让 `test_no_gh` 同时屏蔽 fallback 路径（跨平台可过）。

### 验证
- 单元测试 71 项全通过；网易云（Node `:3000` 代理）采集 20 条、B站 7 条、mp 静默跳过；
  Flask `:5000`（`/`、`/settings`、`/api/status`）均 200；`export_site()` + `push_site()` 推送 Pages 成功；
  systemd 服务 `start` 一次跑通（`done push_date=2026-09-22 pushed=True`）。

## 2026-09-15

### 变更
- **三源空态显示统一**：有记录但某平台无新内容时，对应卡片保留并显示
  「🎵 今日暂无新推荐歌曲 / 📺 今日暂无新B站视频 / 📰 今日暂无新公众号推文」；
  整日无记录仍只显示「该日暂无推送记录，每日开机自动采集。」；平台采集失败仍显示错误块。
  （此前 B站/网易云为空时整卡隐藏，只有公众号有提示。）

## 2026-09-14

### 变更
- **本地改为「无常驻」架构**：不再有一个常驻的 `start.py`（Flask + 调度线程 + Node 代理）。
  - **采集**：登录时 `Startup\DailyPush.vbs` → `tools/run_daily.py` 一次性「采集 → 导出 → 推送」后退出；
    07:30 的定时采集交给云端 GitHub Actions，本地不再定时（移除本地调度线程 / `push_time` 生效）。
  - **网页**：按需启停。开始菜单「每日推送」→ `tools/open_dashboard.py` → `start.py --serve-only`
    （只起 Flask，不采集、不定时；网易云代理懒加载）；设置页「停止本地服务」关闭。
  - 新增 `daily_push/pipeline.py`：`ensure_netease_api`/`stop_netease_api`（只关自己拉起的代理）+ `run_once`，
    登录任务 / 设置页「手动推送」/ `start.py` 共用。
- **网易云代理懒加载**：`pipeline.acquire()/release()`（引用计数）——只有「检测网易云 / 手动推送 / 清理发布」
  时才拉起 `:3000` 代理，用完即关；打开网页只是看看**不会**起代理。并发操作共用同一个代理。
- 设置页顶栏「← 返回仪表盘」改为「← 返回推送页」。

### 新增
- 本地设置页「🩺 运行状态」卡新增「手动推送」：立刻手动跑一遍**定时任务的同一套流程**
  （采集 → 导出 → 推送 Pages），不改数据、不做屏蔽清理。
  接口 `POST /api/settings/push` + `GET /api/settings/push/status`。
- 设置页「停止本地服务」按钮 + `POST /api/settings/shutdown`：关 Flask + 网易云代理（仅按需进程）。
- 开始菜单快捷入口：`tools/open_dashboard.py` 探测 `:5000`，没起就 `pythonw start.py --serve-only`，
  起来后再开浏览器；`tools/create_shortcut.py` 生成「每日推送」快捷方式（可右键固定到开始屏幕）。
- `tools/run_daily.py`：登录时一次性采集并推送（跑完退出，关掉自己拉起的代理）。

### 测试
- `tests/test_settings_api.py` 增加 push / shutdown 接口 CSRF 断言；新增 `tests/test_pipeline.py`（含代理引用计数）；共 71 项。

## 2026-09-13

### 修复
- **跨天去重改用 URL（主）**：公众号 / B站采集前按「历史已推 URL」过滤（`Storage.pushed_urls`
  → `collect(exclude_urls=...)`），在 `max/reserve` 切片前生效，一条内容只推一次。
  修复 09-13 公众号重复推送 09-12 的 9 篇推文——旧逻辑以「采集墙钟时间」为 cutoff，
  行被回填更新后 cutoff 变陈旧而漏去重。`cutoffs.json` 降为时间兜底。
- 清理 09-13 已重复的公众号条目并重发 Pages。
- **子进程不再弹控制台窗口**：新增 `daily_push/proc.py`（`run`/`popen` 统一在 Windows 加
  `CREATE_NO_WINDOW`），`git` / `gh` / `ncm-cli` 调用全部改走它；`pythonw` 与跑测试时不再闪窗。
- `start_hidden.vbs`（本机绝对路径启动器）移出版本库并加入 `.gitignore`（保留本地文件）。

### 测试
- 新增 `tests/test_crossday_dedup.py`（微信 `_assemble` 去重 + B站 `collect` 去重），共 65 项。

## 2026-09-12

### 新增
- **本地设置页 `/settings`**：可视化编辑屏蔽名单、平台登录态（Cookie 更新 + 验证）、采集参数；
  仅本机、Host/Origin/CSRF 鉴权、密钥只回打码值、不参与静态站导出。
- **配置分层**：新增跟踪文件 `settings.json`（非密钥策略）与 `config.json`（密钥，gitignore）；
  `load_config` 合并 `默认 < settings.json < config.json`；原子写 + `.bak` 备份。
- **本地 → 云端 Cookie 同步**：设置页「同步云端」经本机 `gh secret set` 直写云端 Secrets（邮件流程保留兜底）。
- **屏蔽名单全量生效**：保存后清理历史/今天 → 重发 Pages → `git_publish` 只提交 `settings.json` 到 `code`。
- **跨进程文件锁** `publish_lock.py`：采集 / 清理 / 推送 / 导出串行化，避免并发 git / SQLite 冲突。
- **运行状态卡**（上次采集/推送/检测）、**配置备份/还原**、**安全响应头**、**ⓘ 悬停引导**。
- **网易云采集评论数 + 收藏数**（`/comment/music` 的 `total`、`/song/red/count`），可按阈值过滤
  （`netease.max_comments` 默认 10000、`netease.max_favorites` 默认 0=不限），并支持历史补全。
- **隐藏缓冲 `reserve`**（各源默认 3）：被忽略 / 过滤后从缓冲顺延补满。
- **封面**：B站取动态 `archive.cover`、公众号取 appmsg `thumburl`/`cover_16_9`；历史封面回填
  `python -m daily_push.cover_backfill [days] [interval]`（含失效视频清理、公众号补量）。
- **公众号历史补全**：从本地微信库把历史补到每日上限。
- **数量上限支持 0=不限**（`max_songs` / `max_videos` / `max_articles`），当前三源均设为不限。
- **静默启动**：自启改用 `pythonw.exe`（无控制台）、单实例；首次采集并成功推送后才自动打开网页；
  `push_time` 热更新。
- 单元测试（标准库 `unittest`，60 项）。

### 变更
- 公众号屏蔽改为**仅匹配作者（公众号名）子串**，不匹配标题（避免误伤）。
- 仪表盘：「网易云日推 Top 5」→「**网易云日推**」并改**内滚动卡片**；B站 / 公众号改**等高网格**
  （B站 3 列 / 公众号 2 列，窄屏自适应），公众号封面 2.35:1、标题固定两行。
- 本地采集**连续失败 2 次**才发失败邮件（避免瞬时抖动误报）。

### 修复
- purge 未清理**远端独有日期**；`Storage.save` 无法清空字段（新增 `overwrite`）。
- 仪表盘日期选择器 `«`/`»` 跨年 bug（2026-09 → 2025/2027-09）。
- 网易云封面 `http://` 被 CSP / 混内容拦截 → 统一 `https://`。
- 公众号封面防盗链：页面加 `no-referrer`，云端不再显示「不允许引用」占位图。
- `export_site` 合并远端会**复活已删日期** → 删除某天用 `merge_remote=False`。
- 自启多实例抢 :3000 导致采集超时误报 → 停用重复计划任务，只留一个 `pythonw` 实例。

## 2026-08-10
- 本地网易云从 `ncm-cli` 切回 `api`（Cookie + :3000 Node 代理）——`ncm-cli` v0.1.6 命令树无
  `recommend` 子命令，采集持续失败；`ncm-cli` 相关实现保留作备用。

## 2026-08-09
- **时区修复**：`push_date` 固定北京时间（UTC+8），解决云端 runner（UTC）导致「08-09 永不发布」。
- 失败通知统一改**邮件**（本地·采集/推送 + 云端），去掉桌面弹窗；采集每 5 分钟、推送每 60 秒耐心重试。
- **回复邮件自动更新 Cookie**：云端每 10 分钟轮询（最多 6h）→ 验证 → `gh secret set`；本地自愈写回 `config.json`。
- 公众号采集窗口改为「最近 18:00 之后 ~ 当前时刻」+ 动态发现全部 `biz_message_*.db`。
- 新增 `tools/purge_ignored.py`（按忽略名单清历史 + 重发）。
- `ncm-cli` 断网规则：拒绝「本地缓存回退」，不用过期数据冒充当天。

## 2026-08-07
- 初始能力：云端 GitHub Actions 定时采集 + GitHub Pages 发布 + 失败邮件；本地 Flask 仪表盘。
- B站改走「关注动态」接口（一次拉取最近视频，不逐个访问 UP 空间）；新增公众号推文采集。
- 移除 QQ 群 / 微信群消息采集；小红书因风控暂停。
