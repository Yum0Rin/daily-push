# 配置与隐私字段

> ⚠️ **重要**：本文件只说明各字段的**用途**，**不包含真实值**。
> 真实凭证都在 `config.json` 里，该文件已被 `.gitignore` 排除，请勿提交到仓库。

## 配置键参考

| 配置键 | 含义 | 说明 |
|--------|------|------|
| `netease.mode` | 网易云后端模式 | `api`（默认，NeteaseCloudMusicApi+Cookie）；`ncm-cli`（官方 CLI，备用） |
| `netease.cookie` | 网易云登录态 `MUSIC_U=...` | 浏览器登录网易云后复制 |
| `netease.base_url` | 网易云API地址 | 默认 `http://localhost:3000` |
| `bilibili.sessdata` | B站 Cookie 中 `SESSDATA` | 浏览器登录 B站后复制（动态接口需登录态 + WBI 签名） |
| `bilibili.exclude` | 按 UP 名排除的动态 | 默认一组固定排除名单 |
| `bilibili.recent_days` | 时间窗口天数 | 默认 1 |
| `bilibili.max_videos` | 最多条数 | 默认 10 |
| `bilibili.feed_pages` | 动态接口最多翻页数 | 默认 2 |
| `wechat.exclude_keywords` | 标题/账号命中即剔除 | 默认含演出余票监控、省教育厅等 |
| `wechat.notify_keywords` | 命中标记为「通知」类置底 | 默认覆盖取餐/优惠券/快递等 |
| `wechat.important_biz` | 只保留这些公众号 | 默认空=不过滤 |
| `wechat.max_articles` | 公众号最多条数 | 默认 10 |
| `wechat.article_days` | 时间窗口天数 | 默认 7 |
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