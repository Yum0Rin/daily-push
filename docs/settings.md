# 本地设置页与配置分层

> 更新日期：2026-09-12
> 相关文件：`daily_push/settings_store.py`、`daily_push/git_publish.py`、`daily_push/app.py`、
> `daily_push/templates/settings.html`、`daily_push/static/settings.{css,js}`、
> `tools/purge_ignored.py`、`tools/make_cloud_config.py`、`settings.json`

## 1. 为什么需要它

原先所有配置（含策略与密钥）都堆在 gitignore 的 `config.json` 里，导致两个问题：

1. **策略无法可视化、容易改错**：屏蔽名单、阈值要手改 JSON。
2. **本地与云端不一致**：云端 `tools/make_cloud_config.py` 从 `config.example.json` 生成配置，
   `bilibili.exclude` 甚至是**硬编码**在脚本里的，本地改屏蔽名单云端完全看不到。

本方案把配置拆成两层，并提供一个**仅本机可访问**的可视化设置页。

## 2. 配置分层

| 文件 | 内容 | 是否入库 |
|------|------|----------|
| `settings.json` | **非密钥策略**：屏蔽名单、阈值、`push_time` 等 | ✅ 纳入 git 跟踪 |
| `config.json` | **密钥 / 机器相关**：各平台 Cookie、SMTP 授权码、`site.repo`、`port`、`data_dir` 等 | ❌ gitignore |
| `config.json.bak` | `save_secrets()` 写入前的自动备份（**含密钥**） | ❌ 被 `config.json.*` 忽略 |

合并顺序（`daily_push/settings_store.py:load_config`）：

```
内置默认值  <  settings.json（策略）  <  config.json（密钥）
```

- `settings.json` 中的**密钥形状键会被剔除**（`_strip_secrets`），策略文件不可能夹带凭证。
- 因此策略以 `settings.json` 为准，`config.json` 里的旧策略副本会被覆盖。
- `load_config()` 每次调用都重新读盘，所以**屏蔽名单 / Cookie 改完下次采集即生效**；
  `push_time` 等被 `start.py` 启动时读取的项需重启进程（见 §7）。

### 可编辑 schema（服务端白名单）

写入前按显式 schema 校验，拒绝未知键与错误类型（`settings_store.py` 的 `POLICY_SPEC` / `SECRET_SPEC`）：

- 策略：`push_time`(HH:MM)、`max_songs`、
  `netease.{max_comments,max_favorites,reserve}`、
  `bilibili.{exclude,recent_days,max_videos,feed_pages,reserve}`、
  `wechat.{exclude_keywords,notify_keywords,important_biz,max_articles,mp_cutoff_hour,reserve}`。
- 密钥：`netease.{mode,cookie,base_url}`、`bilibili.sessdata`、`email.*`、`site.*`、
  `xiaohongshu.*`、`port`、`data_dir`。

### 写入安全

- **原子写**：同目录临时文件 + `os.replace()`，绝不做截断式覆盖。
- **备份**：写 `config.json` 前先复制 `config.json.bak`。
- **保留未知键**：读→合并→写，不丢未纳管的键。
- **串行化**：进程内 `threading.RLock`。

## 3. 本地设置页（`/settings`）

`start.py` 启动后访问 `http://127.0.0.1:5000/settings`（仪表盘右上角 ⚙️ 也可进入；静态站模式下该入口隐藏）。

功能：

| 区块 | 能力 |
|------|------|
| 🔐 平台登录状态 | 网易云 / B站 是否已配置（值打码）、一键「检测当前」、粘贴新 Cookie「保存并验证」 |
| 🚫 屏蔽名单 | B站 UP 名、公众号关键词的标签式增删；「保存并应用到全部推送」 |
| ⚙️ 采集参数 | `push_time`、`max_songs`、`netease.max_comments/max_favorites/reserve`、`recent_days`、`max_videos`、`feed_pages`、`max_articles`、`mp_cutoff_hour`、各源 `reserve`；「保存参数」右侧 ⓘ 说明调整会应用到全部 |
| 🩺 运行状态 | 上次采集 / 上次推送 / 上次清理发布 / 上次各平台检测时间 |
| 💾 配置备份 | 下载当前 `config.json`（含密钥，仅本机）/ 上传还原（覆盖前自动 `.bak`） |

接口（全部要求本机 Host + 每次启动随机生成的 `X-CSRF-Token`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 返回策略 + 打码后的密钥状态（**永不返回明文**） |
| POST | `/api/settings/policy` | 保存策略到 `settings.json` |
| POST | `/api/settings/secrets` | 保存 Cookie 到 `config.json`（先规范化） |
| POST | `/api/settings/verify` | 用**未保存**的值调平台接口验证（网易云 `/user/account`、B站 `nav`） |
| POST | `/api/settings/check` | 用**已保存**的值检测 |
| GET | `/api/settings/cloud-status` | 云端同步可用性（gh 是否登录、repo 是否配置） |
| POST | `/api/settings/sync-cloud` | 把已保存的 Cookie 写入云端 Secrets（`gh secret set`，值走 stdin） |
| GET | `/api/settings/config-backup` | 下载当前 `config.json`（含密钥，仅本机） |
| POST | `/api/settings/config-restore` | 上传备份还原 `config.json`（覆盖前自动 `.bak`） |
| POST | `/api/settings/purge` | 异步任务：清理历史 + 重新导出 + 推送 Pages + 推送 `settings.json` |
| GET | `/api/settings/purge/status` | 上述任务状态 |

### 安全模型（`app.py:_guard_api`）

浏览器允许任意网站向 `127.0.0.1` 发跨站请求，仅绑 localhost 不足以防护，故：

1. **Host 校验**：只允许 `127.0.0.1` / `localhost` / `::1`（挡 DNS rebinding）。
2. **Origin/Referer 校验**：非本机来源拒绝（挡 CSRF）。
3. **CSRF Token**：`/api/settings*` 必须带本次进程启动生成的随机 token，用 `compare_digest` 比对。
4. **密钥只回打码值**（`mask()`，如 `MUSI••••••9c53`），响应里绝不含明文。
5. **导出隔离**：设置页不参与 `export_site()`；`export_site.py` 会把 `#settingsLink` 从导出 HTML 中剥离，
   `tests/test_export_isolation.py` 断言导出物不含设置入口 / 令牌。

## 4. 屏蔽名单：对「历史 + 今天 + 以后」全生效

- **匹配规则**：
  - B站：按 `author`（UP 名）**子串**匹配 `bilibili.exclude`。
  - 公众号：**仅按 `author`（公众号名）子串**匹配 `wechat.exclude_keywords`，**不匹配标题**（避免误伤）。
- **以后**：采集时过滤（`sources/wechat_article.py:_is_excluded`、`sources/bilibili.py`）。
- **历史 + 今天**：点「保存并应用到全部推送」后，异步任务执行
  `tools/purge_ignored.purge_and_publish()`：
  1. 遍历本地库所有日期，删除命中条目；
  2. `export_site()` 重新导出静态站；
  3. `push_site()` 推送到 GitHub Pages；
  4. `git_publish.commit_and_push_settings()` 把 `settings.json` 提交并推送到 `code` 分支。

### 云端一致性

云端 `daily-collect` checkout `code` 分支，`tools/make_cloud_config.py` 现在从 `settings.json`
读取策略（不再硬编码名单）。所以**只要 `settings.json` 已推到 `code`，云端以后的采集也会过滤**。

> ⚠️ 前提：`code` 分支上必须是**包含本方案的新代码**。若 `code` 上还是旧代码，
> 云端不会读 `settings.json`。因此首次上线需把本方案代码提交并 push 到 `code`。

### 只提交 settings.json

`daily_push/git_publish.py` 的原则：**只 `git add/commit -- settings.json`**，
不碰源码、不碰 `config.json`（本就 gitignore）。无变化则跳过提交；
`GIT_TERMINAL_PROMPT=0` 避免凭证提示卡死；有超时保护；失败只返回错误不抛出。

### 手动 CLI 流程（等价于设置页按钮）

```bash
# 1) 编辑 settings.json：bilibili.exclude / wechat.exclude_keywords
# 2) 清历史 + 重发 Pages（加 --no-push 只清不发）
python tools/purge_ignored.py
# 3) 让云端生效：把 settings.json 推到 code
git add settings.json && git commit -m "chore: 更新 settings.json" && git push origin HEAD:code
```

> 设置页「保存并应用到全部推送」会自动完成上面 3 步（并额外经 `git_publish` 提交推送）。

### 评论/收藏过滤应用到历史

「采集参数」卡的「保存参数」按钮（右侧 ⓘ 说明「调整会应用到全部」）保存后即执行同一个清理发布任务：
`apply_history()` 对历史中**缺失**评论数/收藏数的条目**逐首补全**（`/comment/music` 取 `total`、
`/song/red/count` 取 `data.count`，请求间隔 `netease.request_interval`，默认 0.3s 防风控），
再按 `netease.max_comments` / `netease.max_favorites` 删除超阈值歌曲，然后重发 Pages + 推送 `settings.json`。
删除后会从**隐藏缓冲**（`hidden`）里顺延补满（到 `max_songs`）；B站 / 公众号的忽略删除同理（补到 `max_videos` / `max_articles`）。
「保存并应用到全部推送」（屏蔽名单）也会顺带执行这一步。

## 5. 本地 → 云端 Cookie 同步（`gh secret set`）

设置页每个登录卡片有「同步云端」勾选：保存并验证 Cookie 后，勾选则调用
`daily_push/cloud_secrets.py`，通过本机 `gh secret set` 把值写入 GitHub Actions Secrets
（`NETEASE_COOKIE` / `BILIBILI_SESSDATA`），本地 `config.json` 与云端一次到位。

- **鉴权**：用本机 `gh`。已 `gh auth login` 则直接可用；否则可在 `config.json` 配 `github.token`（作为 `GH_TOKEN`）。
- **预检**：`GET /api/settings/cloud-status` 返回 `{available, authed, repo, token_configured, detail}`；
  不可用时勾选框自动禁用并提示原因。
- **写入**：`POST /api/settings/sync-cloud {sources:[...]}`，服务端读取已保存的值再推；
  Secret 经 **stdin** 传入（不出现在命令行参数里）。
- **邮件兜底保留**：人不在电脑前时，云端 `cookie-repair` 回复邮件流程仍可用（见 [architecture.md](architecture.md)）。
  两套写的是同一批 Secrets，不冲突。

> GitHub Secrets 只写不可读，因此只能**本地 → 云端**单向同步；云端改完由本地 `start.py` 读回复邮件自愈。

## 6. 并发控制

采集 / 清理 / 导出 / 推送都会写 SQLite 并操作 `site/` 的 git 仓库，绝不能并发。
`daily_push/publish_lock.py` 提供**跨进程文件锁**（Windows `msvcrt` / POSIX `fcntl`，
进程退出自动释放、不会残留死锁）：

- `start.py` 的采集、后台推送重试，以及 `app.py` 的采集/清理任务都 `acquire` 同一把锁；
- Flask 路由用非阻塞获取，抢不到直接返回 `429`；`start.py` 用带超时的阻塞获取。
- 这解决了此前 `start.py` 的调度/重推线程与设置页清理任务并发 `git reset --hard` / SQLite 写冲突的问题。

## 7. 运行状态、配置备份与安全响应头

- **运行状态**：`daily_push/run_status.py` 把「上次采集 / 上次推送 / 上次清理发布 / 上次各平台检测」
  记到 `<data_dir>/status.json`，设置页顶部「🩺 运行状态」卡展示。
- **配置备份 / 还原**：设置页「💾 配置备份」可下载当前 `config.json`（含密钥，仅本机），
  或上传备份还原（`restore_config()` 覆盖前自动生成 `.bak`）。
- **安全响应头**：所有响应加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、
  `Referrer-Policy: no-referrer` 与一条 CSP（保留 `'unsafe-inline'` 以兼容现有内联事件处理）。
- **界面引导**：不直观的字段旁有 ⓘ 圆圈，鼠标悬停显示说明（纯 CSS tooltip，无需 JS）。
- **历史回填 CLI**：`python -m daily_push.cover_backfill [days] [interval]` —— 网易云封面 `https` 化、
  B站补封面并删除失效/私密视频、公众号补封面并补到 `max_articles`；逐条 `sleep` 控频。

## 8. 测试

零新依赖，使用标准库 `unittest`：

```
python -m unittest discover -s tests -t .
```

覆盖：

| 文件 | 覆盖点 |
|------|--------|
| `tests/test_settings_store.py` | 分层合并、策略覆盖旧 config、settings 中的密钥被忽略、schema 拒绝非法键、原子写 + 备份保留未知键、打码 |
| `tests/test_settings_api.py` | `/settings` 渲染、无 token 403、密钥不明文、策略保存、非法键 400、坏 Origin/Host 403 |
| `tests/test_export_isolation.py` | 导出 HTML 不含设置入口 / token |
| `tests/test_wechat_filter.py` | 公众号屏蔽仅匹配作者、标题不参与 |
| `tests/test_git_publish.py` | 只提交 settings.json（其他脏文件不进 commit）、无变化跳过 |
| `tests/test_cloud_secrets.py` | `gh secret set` 用 stdin 传值、token 走 `GH_TOKEN`、缺 repo/失败的错误处理 |

## 9. 已知限制

- `port`、`netease.mode` 等由 `create_app` / `start.py` 启动时读取的项，改完需重启进程才生效；
  `push_time` 已支持**热更新**（调度线程每轮重读）；屏蔽名单 / Cookie 因每次采集重读，无需重启。
- 网页更新的是**本地** `config.json`；云端 Cookie 需勾选「同步云端」（本机 `gh` 已登录）才会同步，
  否则云端仍走「回复邮件自动更新」或手动改 Secrets。
- 设置页仅本机可用；PC 关机时无法访问（Cookie 靠邮件兜底，屏蔽名单等下次开机再改）。

## 变更记录

- **2026-09-12**：新增配置分层（`settings.json` 跟踪 + `config.json` 密钥）、本地设置页 `/settings`
  与 `/api/settings*`（Host/Origin/CSRF 鉴权、密钥打码、原子写与备份）、
  屏蔽名单「保存并应用到全部推送」（purge 历史 + 重发 Pages + 推送 `settings.json` 到 `code`）、
  公众号屏蔽改为仅匹配作者、`git_publish` 只提交 `settings.json`、导出隔离、
  **本地 → 云端 Cookie 同步（`cloud_secrets.py` + 设置页「同步云端」，邮件流程保留兜底）**、
  「B站动态翻页数（每页上限约20条）」标签，共 31 项单元测试。
- **2026-09-12（二）**：跨进程文件锁 `publish_lock`（采集/清理/推送串行化）；修复 purge 未清理
  **远端独有日期** + `Storage.save(overwrite=True)` 清空字段；B站屏蔽空串防御；
  云端 `gh secret set` 改 stdin；`start.py` 静默启动、**首次成功推送后才开网页**、`push_time` 热更新；
  设置页新增运行状态卡、配置备份/还原、安全响应头、ⓘ 悬停引导；测试增至 44 项。
- **2026-09-12（三）**：网易云采集**评论数 + 收藏数**（`comment_count` / `favorite_count`，
  后者走 `/song/red/count`），请求间隔默认 0.3s 防风控；新增 `netease.max_favorites`（默认 0=不限）；
  历史条目经「保存参数」（右侧 ⓘ）**补全**这两个数并按 `max_comments` / `max_favorites` 过滤；
  仪表盘显示 ❤️/💬；测试增至 50 项。
- **2026-09-12（四）**：网易云封面规范为 `https://`（修复被 CSP / 混内容拦截）；
  B站动态采集封面（`archive.cover`）；各源新增**隐藏缓冲** `reserve`（默认 3），
  被忽略 / 过滤后从缓冲**顺延补满**；`AGENTS.md` 增加「爬取必须控频」约定；测试增至 54 项。
- **2026-09-12（五）**：展示细节——B站 3 列 / 公众号 2 列等高网格（公众号封面按微信 **2.35:1 完整显示**、
  标题固定两行、无封面用 `.gthumb-ph` 占位且非正式推文保留）；`mmbiz` 防盗链用页面 `no-referrer` 解决；
  公众号历史补到 **12/天**；测试 60 项。
