# 架构与采集流程

> 本文件描述当前代码的运作方式。改过逻辑后记得同步这里。

## 整体架构：两条运行链路

```
┌─ 本地链路（无常驻）────────────────────────────────────────┐
│  登录时：tools/run_daily.py 一次性 collect → export → push  │
│          （跑完退出，关掉自己拉起的 :3000 代理）             │
│  按需：start.py --serve-only 只起 Flask @5000                  │
│        网易云代理**懒加载**：点检测/手动推送时才起，用完关   │
│        设置页「停止本地服务」→ Flask 关闭                    │
└─────────────────────────────────────────────────────────────┘

┌─ 云端链路（GitHub Actions）────────────────────────────────┐
│  cron 30 23 * * *（UTC，=北京 07:30，job 级 TZ=Asia/Shanghai）│
│  用 secrets 生成 config.json → 启动网易云 API                │
│  cloud_collect.py → collect_once(netease, bilibili)         │
│  export_site() → push 到 main（Pages）                       │
│  出错 → notify_email.py 发邮件                               │
│  cookie 类错误 → trigger_cookie_repair.py                    │
│    触发 cookie-repair.yml（回复邮件自动更新 Cookie）          │
└─────────────────────────────────────────────────────────────┘
```

两条链路共用 `collect_once()` 与 `export_site()`，区别仅在于：云端不采公众号（无微信解密环境）。

**时区**：`push_date` 固定用北京时间（`_beijing_today()`，UTC+8），
避免云端 runner（默认 UTC）把 07:30 北京时间的采集结果写到前一天——这是 2026-08-09
「网页永远没有 08-09」的根因。

## 配置分层与本地设置页

- `settings_store.py` 负责配置读写与分层：`默认 < settings.json（跟踪的策略） < config.json（gitignore 的密钥）`。
  `load_config()` 读取时会把 `settings.json` 里的密钥键剔除，策略覆盖 `config.json` 里的旧副本。
- 写策略/密钥都经白名单 schema 校验，采用「临时文件 + `os.replace`」原子写；写 `config.json` 前先备份 `.bak`。
- `app.py` 提供本地设置页 `/settings` 与 `/api/settings*`：`/api/*` 统一校验 Host/Origin，且 `/api/settings*`
  需要每次启动生成的 `X-CSRF-Token`（挡 CSRF 与 DNS rebinding），响应永不返回密钥明文（只回打码值）。
- 设置页**不参与** `export_site()` 导出：`export_site.py` 会把 `#settingsLink` 从导出 HTML 中剥离，
  `tests/test_export_isolation.py` 断言导出物不含设置入口/令牌。
- 云端 `tools/make_cloud_config.py` 现在也从 `settings.json` 读策略，因此「屏蔽名单」本地与云端同源
  （不再有硬编码副本）。

### 屏蔽名单全量生效链路

- **匹配规则**：B站按 `author` 子串；公众号**仅按 `author`（公众号名）子串**，**不匹配标题**（`sources/wechat_article.py:_is_excluded`），避免误伤。
- **以后**：采集时过滤；**历史 + 今天**：设置页「保存并应用到全部推送」触发异步任务
  `tools/purge_ignored.purge_and_publish()` → **先 `merge_remote_history()` 把远端独有日期并入本地**
  （否则这些日期的命中条目不会被清、还会被重新导出推回）→ 删本地库命中条目
  （`Storage.save(overwrite=True)` 才能真正清空字段）→ `export_site(merge_remote=False)` →
  `push_site()`（Pages）→ `git_publish.commit_and_push_settings()`（把 `settings.json` 推到 `code`，云端次日同源过滤）。
- **只提交 settings.json**：`git_publish.py` 只 `git add/commit -- settings.json`，不碰源码与密钥；
  无变化跳过；`GIT_TERMINAL_PROMPT=0` 防卡死；有超时；失败只返回错误不抛。
- **并发**：`daily_push/publish_lock.py` 提供**跨进程文件锁**，采集/清理/推送/导出全部串行化
  （含 `start.py` 的调度与后台重推线程）；Flask 路由非阻塞获取、抢不到返回 429。
  此前只有进程内 `_heavy_lock`，`start.py` 的线程与设置页清理会并发 `git reset --hard` / SQLite 写冲突。

> 完整的设置系统说明见 [settings.md](settings.md)。

## collect_once() 编排（collector.py）

1. `load_config()` 取配置，建 `Storage`。
2. 依次采集，每个来源独立 try/except，**失败返回 `{"error": ...}` 而不抛异常**：
   - 网易云 → `sources/netease.py`
   - B站 → `sources/bilibili.py`
   - 公众号 → `sources/wechat_article.py`（需本地解密环境，`wechat_available()` 检测）
3. **跨天去重（主）**：采集前从 DB 取历史已推 URL（`pushed_urls(field, exclude_date=today)`），
   传给采集器 `collect(exclude_urls=...)`，在套用 `max/reserve` **之前**过滤，
   保证 bilibili / mp 的每条内容只推一次，且与「采集时刻 / 行是否被回填」无关。
4. **跨天去重（兜底）**：`cutoffs.json` 只保留时间戳 > 历史最大 cutoff 的内容
   （bilibili 按 `created`，mp 按 `timestamp`），防 URL 不稳定时重复。
5. `storage.save(today, netease=..., bilibili=..., mp=...)` 写库。

## 存储层（storage.py）—— 按日合并语义

`pushes` 表按 `push_date`（主键）每天一行，列为 `netease, bilibili, mp`（历史列 `qq, wechat` 兼容保留）。

**关键合并逻辑**：`save()` 遍历各字段，当某来源本次返回 `None` 或 `{"error": ...}`
时，**保留数据库里当天的旧值**，避免「某来源失败 → 把当天该来源清空/覆盖成错误」。

数据库旧结构升级：无 `mp` 列时自动 `ALTER TABLE pushes ADD COLUMN mp`。
跨天去重：`pushed_urls(field, exclude_date)` 返回某字段历史上已推过的 URL 集合（主去重依据）。

## 跨天去重

**主机制（按 URL）**：采集时把历史已推 URL（`storage.pushed_urls(field, exclude_date=today)`）
作为 `exclude_urls` 传给采集器，在 `max/reserve` 切片前过滤，一条内容只推一次。
不依赖采集时刻，行被回填更新后依然准确（修复 09-13 公众号重复推送 09-12 内容）。

**兜底（cutoffs.json）**：
- 文件位于 `data/cutoffs.json`，键为日期、值为当天最后一次采集时间戳。
- 每天采集时：`threshold = max(所有历史日期的 cutoff)`，过滤掉时间戳 <= threshold 的内容；
  再把当天写入 cutoff，并只保留最近 3 天，避免文件膨胀。
- 仅当 URL 不稳定（同一内容 URL 变化）时才起作用。

## 采集执行方式

- 采集是**异步**的：`POST /api/collect` 用非阻塞锁 + 后台线程触发并立即返回，
  前端轮询 `/api/collect/status`。Flask `threaded=True`。
- 本地日常无常驻：登录启动项 `Startup\DailyPush.vbs` 跑一次 `tools/run_daily.py`（采完即退）；
  本地网页按需启停（开始菜单「每日推送」→ `tools/open_dashboard.py` → `start.py --serve-only`）。

## B站防风控 + WBI 签名（bilibili.py）

- 走「关注动态」接口 `feed/all?type=video`，一次拉取，不逐个访问 UP 空间。
- **WBI 签名**：从 `/x/web-interface/nav` 取 `img_url/sub_url` 的 key → 按 `_MIXIN_KEY_ENC_TAB`
  混淆出 mixin key → 拼上 `wts` 时间戳 → 对排序后的 query 做 md5 得 `w_rid`。
- **退避重试**：`_get()` 遇 HTTP 412 或返回 HTML（风控页）时，按递增间隔重试（最多 3 次）。

## 静态站导出与发布（export_site.py）

- **导出**：把 `index.html` 模板 + `style.css` + `app.js` + 全部历史数据（`window.__DAYS__`）
  内联成**单个自包含文件** `site/index.html`，离线可开、可扔 GitHub Pages。
- **合并远端历史**：导出前从已发布的 Pages `index.html` 抓出 `__DAYS__` 写回本地库，
  避免换机器 / 云端覆盖历史（尤其保护本地独有的 mp 数据）。
- **发布**：在 `site/` 内建一个指向远端分支的临时仓库，`reset --hard origin/<branch>`
  保留分支上其他文件（如 workflow），只提交并 push `index.html`，防止清空分支。

## 失败通知与 Cookie 自动修复

> **本地 → 云端 Cookie 同步（2026-09-12）**：本地设置页保存 Cookie 时可选勾「同步云端」，
> 经 `daily_push/cloud_secrets.py` 调本机 `gh secret set` 直写云端 Secrets（主动快路径）。
> 下面的「回复邮件自动更新」流程**保留为不在电脑前时的兜底**，两者写同一批 Secrets，不冲突。

**邮件通知**（`tools/notify_email.py`）—— 所有失败统一走邮件，不再桌面弹窗：
- SMTP 配置：本地读 `config.json.email` 段；云端读 Secrets `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/MAIL_TO`。
- 主题标明环节：`每日推送 · 本地采集失败 / 本地推送失败 / 云端采集失败 / 云端工作流提前失败`。
- 邮件里列出的错误来源即对应网易云 / B站 / 公众号。

**Cookie 自动修复**（报错邮件 → 回复 → 自动更新，云端 + 本地双通道，**仅 `api` 模式**）：
1. 采集报错若属 cookie/登录类（网易云 `MUSIC_U`、B站 `SESSDATA`），
   报错邮件主题追加 `ref=日期-来源` 标记（如 `ref=2026-08-09-netease`）。
2. 云端 `cookie-repair.yml`（`workflow_dispatch`，需 Secrets `REPO_TOKEN`）被触发后，
   每 10 分钟 IMAP 轮询收件箱，最多 6 小时。
3. 找到你回复的邮件 → `tools/cookie_reply.py` 剥离引用原文、按行解析新 cookie
   （netease 在前、bilibili 在后，一行一个、不带前缀）。
4. 验证：网易云 `/user/account`、B站 `/x/web-interface/nav`。
5. 通过 → `gh secret set` 更新 GitHub Secrets → 回「已更新并验证通过」邮件 → **停止轮询**；
   无效 → 回「Cookie 无效，请重新回复」邮件 → **停止轮询**；超时 → 回超时邮件 → 停止。
6. 本地 `start.py` 重试循环里同样读邮箱回复，直接写回 `config.json`
   （电脑关机时则下次开机自动补上，无需手动改）。

触发方：云端 `daily-collect.yml` 出错后由 `tools/trigger_cookie_repair.py` 触发；
本地 `start.py` 用本机 `gh`（需 `repo`+`workflow` 权限）触发。
`netease.mode=ncm-cli` 时网易云登录失效**不会**触发邮件轮询（只能手动 `ncm-cli login`）。

> **本地 netease.mode 当前为 `api`**：2026-08-10 起从 `ncm-cli` 切回。原因：本机 `ncm-cli`
> v0.1.6 命令树里没有 `recommend` 子命令，`ncm-cli recommend daily` 报
> `unknown command 'recommend'`，导致网易云采集持续失败。`api` 模式用 Cookie +
> :3000 NeteaseCloudMusicApi 已验证可用。`ncm-cli` 相关实现（`_NeteaseNcmCli`）保留作备用。

**网易云 ncm-cli 断网规则**：ncm-cli 远端同步失败时默认「使用本地缓存」返回过期数据，
`_NeteaseNcmCli._cli()` 检测到 `远端同步失败 / 使用本地缓存` 即抛出 `NeteaseError`，
拒绝用昨天/缓存的推荐冒充当天（断网时走 start.py 的耐心重试，网络恢复后补当天）。

## 本地运行模式（无常驻，2026-09-14 起）

**登录时一次性采集**：`Startup\DailyPush.vbs`（`pythonw`）→ `tools/run_daily.py`：
`pipeline.ensure_netease_api()` → `pipeline.run_once()`（采集→导出→推送）→
`pipeline.stop_netease_api()`（关掉**本进程拉起的** :3000 代理）→ 退出。
采集失败/推送失败发失败邮件。**07:30 的定时采集交给云端 GitHub Actions，本地不再定时。**

**按需网页**：开始菜单「每日推送」→ `tools/open_dashboard.py`：
探测 `:5000`，没起就 `pythonw start.py --serve-only`，端口就绪后再开浏览器。
**网易云代理懒加载**：打开页面不启代理；点「检测网易云 / 手动推送 / 清理发布」时才起，用完即关。
设置页「停止本地服务」→ `POST /api/settings/shutdown` → 关代理 + `os._exit(0)`。

## 共享流水线（pipeline.py）

`daily_push/pipeline.py` 被登录任务 / 设置页「检测」「手动推送」「清理发布」/ `start.py` 共用：
- **网易云代理懒加载（引用计数）**：`acquire()` 在网易云操作开始时按需拉起 `netease_server.js`（`:3000`）并 +1，
  `release()` 结束时 -1、归零才关闭——**不点网易云相关操作就不会起代理**；并发操作共用同一个代理。
- `ensure_netease_api()` / `stop_netease_api()`：常驻模式会话期间保留 / 服务关闭时强制关闭（只关本进程拉起的）。
- `run_once()`：一次 `collect_once → export_site → push_site`；任一来源出错则**不发布**，返回 summary。

## start.py 说明

- **`--serve-only`**：按需网页模式——只起 Flask，**不采集、不定时**（网易云代理懒加载；供开始菜单入口用）。
- 默认模式：启动时先采集一次并推送，再服务（手动 `python start.py` 时用）。
- **静默启动**：不再一上来就弹浏览器；默认模式**首次采集并成功推送后**才自动打开本地网页
  （`_first_push_event`）。`--serve-only` 不自动开（由入口脚本开）。
- 采集/推送经 `publish_lock` 跨进程锁串行化（与设置页清理任务互斥）。
- 失败处理（默认模式，统一邮件 + 耐心重试）：
  - 采集**连续失败 2 次**才发「本地 · 采集失败」邮件（首次瞬时抖动不发），每 5 分钟重试；
  - 推送失败 → 发「本地 · 推送失败」邮件，后台每 60 秒重试直到成功；
  - cookie 类错误 → 邮件主题带 `ref=`，用本机 gh 触发云端 `cookie-repair`，
    并在重试时读邮箱回复自愈写回 `config.json`。
- **静默运行**：自启改用 `pythonw.exe`（无控制台窗口）；无控制台时 `start.py` 自动把
  stdout/stderr 写到 `start_out.log`。
- **子进程不弹窗（2026-09-13）**：所有 `git` / `gh` / `ncm-cli` 子进程统一经
  `daily_push/proc.py`（Windows 加 `CREATE_NO_WINDOW`），`pythonw` 与测试运行时不再闪控制台窗口。
