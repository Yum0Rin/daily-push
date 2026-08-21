# 架构与采集流程

> 本文件描述当前代码的运作方式。改过逻辑后记得同步这里。

## 整体架构：两条运行链路

```
┌─ 本地链路（start.py）──────────────────────────────────────┐
│  ensure_netease_api() → 拉起 :3000 Node API                 │
│  run_collect()（daemon 线程） → collect_once()              │
│  Flask (app.py) @ 5000  +  每日 push_time 定时线程          │
│  采集完成后 export_site() + push_site() → 推 Pages           │
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

## collect_once() 编排（collector.py）

1. `load_config()` 取配置，建 `Storage`。
2. 依次采集，每个来源独立 try/except，**失败返回 `{"error": ...}` 而不抛异常**：
   - 网易云 → `sources/netease.py`
   - B站 → `sources/bilibili.py`
   - 公众号 → `sources/wechat_article.py`（需本地解密环境，`wechat_available()` 检测）
3. **跨天去重**（cutoffs.json）：只保留时间戳 > 历史最大 cutoff 的新内容
   （bilibili 按 `created`，mp 按 `timestamp`），保证一条内容只推一次。
4. `storage.save(today, netease=..., bilibili=..., mp=...)` 写库。

## 存储层（storage.py）—— 按日合并语义

`pushes` 表按 `push_date`（主键）每天一行，列为 `netease, bilibili, mp`（历史列 `qq, wechat` 兼容保留）。

**关键合并逻辑**：`save()` 遍历各字段，当某来源本次返回 `None` 或 `{"error": ...}`
时，**保留数据库里当天的旧值**，避免「某来源失败 → 把当天该来源清空/覆盖成错误」。

数据库旧结构升级：无 `mp` 列时自动 `ALTER TABLE pushes ADD COLUMN mp`。
跨天去重辅助：`pushed_urls(field)` 返回某字段历史上已推过的 URL 集合。

## 跨天去重（cutoffs.json）

- 文件位于 `data/cutoffs.json`，键为日期、值为当天最后一次采集时间戳。
- 每天采集时：`threshold = max(所有历史日期的 cutoff)`，过滤掉时间戳 <= threshold 的内容；
  再把当天写入 cutoff，并只保留最近 3 天，避免文件膨胀。

## 采集执行方式

- 采集是**异步**的：`POST /api/collect` 用非阻塞锁 + 后台线程触发并立即返回，
  前端轮询 `/api/collect/status`。Flask `threaded=True`。
- 本地日常不点按钮：开机自启（Startup 计划任务）自动采，另有 `push_time` 定时兜底。

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

## start.py 说明

- `--no-collect`：只启动服务，不做首次采集。
- `_port_open()` 端口检测去重，避免重复拉起网易云 API。
- 每日定时：`push_time`（默认 07:30）独立 daemon 线程，作为开机采集的兜底。
- 失败处理（统一邮件 + 耐心重试）：
  - 采集失败 → `_report_errors()` 发「本地 · 采集失败」邮件，每 5 分钟重试；
  - 推送失败 → 发「本地 · 推送失败」邮件，后台每 60 秒重试直到成功；
  - cookie 类错误 → 邮件主题带 `ref=`，用本机 gh 触发云端 `cookie-repair`，
    并在重试时读邮箱回复自愈写回 `config.json`。
