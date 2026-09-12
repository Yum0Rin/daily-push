# 配置与隐私字段

> ⚠️ **重要**：本文件只说明各字段的**用途**，**不包含真实值**。
> 真实凭证都在 `config.json` 里，该文件已被 `.gitignore` 排除，请勿提交到仓库。

## 配置分层

| 文件 | 内容 | 是否入库 |
|------|------|----------|
| `settings.json` | **非密钥策略**：屏蔽名单、阈值、`push_time` 等（本地与云端同源） | ✅ 跟踪 |
| `config.json` | **密钥 / 机器相关**：各平台 Cookie、SMTP 授权码、`site.repo`、`port` 等 | ❌ gitignore |
| `config.json.bak` | `save_secrets()` 自动备份（含密钥） | ❌ 被 `config.json.*` 忽略 |

`load_config()` 合并顺序：**默认值 < `settings.json` < `config.json`**。
`settings.json` 中若出现密钥键会被忽略（防止策略文件夹带凭证）。
本地设置页 `http://127.0.0.1:5000/settings` 可视化编辑上述两类文件：
- 策略 → 写 `settings.json`（「保存并应用到全部推送」会清理历史/今天、重发 Pages 并推送到 `code`）；
- Cookie → 写 `config.json`（仅本机）；勾「同步云端」可经 `gh secret set` 写入云端 Secrets
  （需本机 `gh` 已登录，或配置 `github.token`），否则走回复邮件 / 手动改 Secrets。
- 备份 / 还原 → 「💾 配置备份」可下载当前 `config.json`（**含密钥，仅本机保存**）或上传还原
  （覆盖前自动生成 `.bak`）。

## 配置键参考

| 配置键 | 含义 | 说明 |
|--------|------|------|
| `netease.mode` | 网易云后端模式 | `api`（默认，NeteaseCloudMusicApi+Cookie）；`ncm-cli`（官方 CLI，备用） |
| `netease.cookie` | 网易云登录态 `MUSIC_U=...` | 浏览器登录网易云后复制 |
| `netease.base_url` | 网易云API地址 | 默认 `http://localhost:3000` |
| `netease.max_comments` | 日推评论数阈值 | 评论数**大于**该值的歌跳过、顺延下一首；`0`=不限（默认 10000）。存于 `settings.json` |
| `bilibili.sessdata` | B站 Cookie 中 `SESSDATA` | 浏览器登录 B站后复制（动态接口需登录态 + WBI 签名） |
| `bilibili.exclude` | 按 UP 名**子串**排除的动态 | 存于 `settings.json`（跟踪入库） |
| `bilibili.recent_days` | 时间窗口天数 | 默认 1 |
| `bilibili.max_videos` | 最多条数 | 默认 10 |
| `bilibili.feed_pages` | 动态接口最多翻页数 | 默认 2 |
| `wechat.exclude_keywords` | 账号名命中即剔除 | **仅按 author/公众号名**子串匹配，不匹配标题（避免误伤） |
| `wechat.notify_keywords` | 命中标记为「通知」类置底 | 默认覆盖取餐/优惠券/快递等 |
| `wechat.important_biz` | 只保留这些公众号 | 默认空=不过滤 |
| `wechat.max_articles` | 公众号最多条数 | 默认 10 |
| `wechat.mp_cutoff_hour` | 公众号窗口起始边界（时） | 默认 18：窗口 = 最近一次该时刻之后 ~ 当前时刻，配合跨天去重不重复推送 |
| `email.smtp_host/port` | 本地发件 SMTP | 如 `smtp.qq.com:465`（授权码） |
| `email.smtp_user/pass` | 发件邮箱 + SMTP 授权码 | QQ 邮箱授权码 SMTP/IMAP 通用 |
| `email.mail_to` | 收件邮箱 | 失败通知 / cookie 修复结果都发到这里 |
| `email.imap_host/port` | IMAP 收信（可选，默认推导） | 默认 `smtp.`→`imap.`，端口 993 |
| `push_time` | 本地每日定时采集时间 HH:MM | 默认 `07:30` |
| `max_songs` | 网易云日推条数 | 默认 5 |
| `port` | Flask 本地端口 | 默认 5000 |
| `data_dir` | SQLite 数据目录 | 默认 `data` |
| `site.repo` | GitHub 仓库 `<user>/<repo>` | Pages 发布目标 |
| `site.branch` | Pages 分支 | 默认 `main` |
| `site.export_dir` | 静态站导出目录 | 默认 `site` |
| `github.token` | 本机 PAT（可选） | 本机未 `gh auth login` 时，用于 `gh secret set` 同步云端 Cookie（作为 `GH_TOKEN`） |

> 凭证类字段（Cookie / SESSDATA / SMTP 授权码）只出现在本机 `config.json`，已被 `.gitignore` 排除。
> 云端由 GitHub Actions 通过 Secrets 注入，见 `tools/make_cloud_config.py`。

### GitHub Secrets（云端使用）

| Secret | 用途 |
|--------|------|
| `NETEASE_COOKIE` / `BILIBILI_SESSDATA` | 云端采集登录态 |
| `SMTP_HOST/PORT/USER/PASS`、`MAIL_TO` | 云端失败邮件通知 |
| `REPO_TOKEN` | PAT（`repo`+`workflow` scope）：触发 `cookie-repair` + `gh secret set` 更新 cookie |

## 隐私相关的外部依赖

本项目的公众号/微信群采集依赖 **chat-mcp** 的 `wechat-mcp-server`：
- 目录：`C:\Users\39007\chat-mcp\wechat-mcp-server`
- 它负责微信本地消息库的**解密**（含解密密钥、sqlite key、解密缓存）。
- 这些密钥、解密后的 db 缓存、`all_keys.json` **均属于高度敏感信息**，
  与业务代码分离存放，不入库不同步。

相关敏感位置（均已被项目 .gitignore 及仓库隔离覆盖）：
- `data/daily.db`（含采集到的个人/群消息内容）
- 日志 `*.log`（可能含请求 URL / 路径细节）
- `config.json`（所有平台 Cookie / sessdata）
- `netease.out.log` 等运行日志

### 处置原则
1. `config.json`、`data/`、所有 `*.log` 一律 gitignore。
2. 仓库只提交代码 + `docs/` 文档（本文档不含真实凭证）。
3. 微信/mcp 相关的解密密钥、db 已天然位于项目之外（`chat-mcp/`），不会进仓库。