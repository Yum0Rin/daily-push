# 更新日志（CHANGELOG）

> 本项目无正式版本号，按日期记录重要变更，**最新在上**。
> 更细的设计见 [docs/](docs/README.md)，当前能力与已知问题见 [docs/status.md](docs/status.md)。

## 2026-09-14

### 变更
- **本地改为「无常驻」架构**：不再有一个常驻的 `start.py`（Flask + 调度线程 + Node 代理）。
  - **采集**：登录时 `Startup\DailyPush.vbs` → `tools/run_daily.py` 一次性「采集 → 导出 → 推送」后退出；
    07:30 的定时采集交给云端 GitHub Actions，本地不再定时（移除本地调度线程 / `push_time` 生效）。
  - **网页**：按需启停。开始菜单「每日推送」→ `tools/open_dashboard.py` → `start.py --serve-only`
    （只起 Flask + 网易云代理，不采集、不定时）；设置页「停止本地服务」关闭，网易云代理一并退出。
  - 新增 `daily_push/pipeline.py`：`ensure_netease_api`/`stop_netease_api`（只关自己拉起的代理）+ `run_once`，
    登录任务 / 设置页「手动推送」/ `start.py` 共用。
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
- `tests/test_settings_api.py` 增加 push / shutdown 接口 CSRF 断言；新增 `tests/test_pipeline.py`；共 70 项。

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
