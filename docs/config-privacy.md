# 配置与隐私字段

> ⚠️ **重要**：本文件只说明各字段的**用途**，**不包含真实值**。
> 真实凭证都在 `config.json` 里，该文件已被 `.gitignore` 排除，请勿提交到仓库。

## 各平台凭证来源

| 配置键 | 含义 | 获取方式 |
|--------|------|----------|
| `netease.cookie` | 网易云登录态 `MUSIC_U=...` | 浏览器登录网易云后复制 |
| `netease.base_url` | 网易云API地址 | 默认 `http://localhost:3000` |
| `bilibili.sessdata` | B站 Cookie 中 `SESSDATA` | 浏览器登录 B站后复制 |
| `qq.*` | QQ群采集配置（账号/重要群/上限） | 见 chat-mcp qq-mcp-server |
| `wechat.*` | 微信群+公众号配置（important_biz/max_articles 等） | 依赖微信本地解密 db |
| `xiaohongshu.cookie` | 小红书 `web_session=...` 预留 | 浏览器登录后复制（**当前未用，被风控**） |

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