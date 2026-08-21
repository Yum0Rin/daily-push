# daily-push · 每日推送聚合器

多平台每日信息自动聚合：**网易云日推 Top5（含热评）** + **B站关注 UP 动态** + **微信公众号推文**。
采集结果写入 SQLite，本地通过 Flask 网页查看，并自动导出静态页推送到 GitHub Pages，手机随时可看。

---

## 一、技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 语言 | Python 3.10+ | 采集器 / 存储 / Web 服务全部用 Python |
| Web 框架 | Flask (`>=3.0`) | 本地仪表盘 + API |
| HTTP | requests (`>=2.31`) | 调网易云 / B站接口 |
| 存储 | SQLite (标准库 `sqlite3`) | 按「天」一行，存全部来源数据 |
| 前端 | 原生 HTML/CSS/JS（无框架） | 静态仪表盘，可脱离后端运行 |
| 网易云数据 | Node 包 `NeteaseCloudMusicApi` | 本地代理网易云官方接口（:3000） |
| 微信数据 | 复用 `chat-mcp/wechat-mcp-server` 的解密模块 | 解密本地微信库，取公众号推文 |
| 云端定时 | GitHub Actions（`schedule` cron） | 每天 23:30 UTC（=07:30 北京时间）自动采集并发布（云端按北京时间入库） |
| 静态托管 | GitHub Pages | 采集结果对外可访问（无需开电脑） |
| 计划任务 | 系统 `schedule` 语义自实现（daemon 线程） | 本地每日定时兜底采集 |

依赖文件：`requirements.txt`（Python）、`package.json`（Node）。

---

## 二、目录结构

```
daily-push/
├── start.py                     # 一键启动入口
├── config.json                  # 各平台 Cookie / 登录态（已 gitignore，勿提交）
├── config.example.json          # 配置模板（只含占位符）
├── requirements.txt             # Python 依赖
├── package.json / package-lock.json   # Node 依赖（NeteaseCloudMusicApi）
├── netease_server.js            # 网易云 API 启动脚本
├── data/                        # SQLite 库 + cutoffs.json（已 gitignore）
├── site/                        # 导出后的静态站 index.html（已 gitignore）
├── daily_push/                  # 主包
│   ├── __main__.py              # CLI：python -m daily_push 手动采集
│   ├── config.py                # 配置加载（含默认值补齐）
│   ├── storage.py               # SQLite 存储层（按日合并语义）
│   ├── collector.py             # 聚合采集器（编排所有数据源）
│   ├── app.py                   # Flask Web 应用 + 异步采集 API
│   ├── export_site.py           # 导出自包含静态页 + git push 到 Pages
│   ├── templates/index.html     # 前端页面结构
│   ├── static/app.js            # 前端逻辑
│   ├── static/style.css         # 前端样式
│   └── sources/
│       ├── netease.py           # 网易云日推采集器
│       ├── bilibili.py          # B站关注动态采集器
│       └── wechat_article.py    # 公众号推文采集器
├── tools/
│   ├── make_cloud_config.py     # 云端用 secrets 生成 config.json
│   ├── cloud_collect.py         # GitHub Actions 云端采集入口
│   ├── notify_email.py          # 失败邮件通知（本地/云端通用 SMTP）
│   ├── cookie_reply.py          # 回复邮件更新 Cookie：IMAP/解析/验证/写回
│   ├── cookie_repair_cloud.py   # 云端每 10 分钟轮询回复并更新 Secrets
│   ├── trigger_cookie_repair.py # 判定 cookie 类错误并触发 cookie-repair
│   ├── xhs_console.txt          # 小红书签名调研备忘（未启用）
│   └── xhs_capture.txt          # 小红书请求头捕获脚本（未启用）
├── .github/workflows/daily-collect.yml  # 云端每日采集 + 发布 + 出错通知 workflow
├── .github/workflows/cookie-repair.yml  # 回复邮件自动更新 Cookie 的轮询 workflow
└── docs/                        # 更细化的设计说明文档
```

---

## 三、模块概览

> 每个模块一句话讲清楚职责；**内部设计与约定详见 [docs/](docs/README.md)**。

| 模块 | 一句话职责 |
|------|-----------|
| `start.py` | 本地一键启动：拉起网易云 API → 首次采集 → Flask 网页 → 每日定时兜底；失败发邮件并按 5 分钟耐心重试 |
| `daily_push/config.py` | 读取 `config.json` 并补齐默认值 |
| `daily_push/storage.py` | SQLite 存储：按 `push_date` 一行，**按日合并**（采集失败不覆盖当天旧值） |
| `daily_push/collector.py` | 聚合编排：按序采集各来源 → 跨天去重 → 写库；`push_date` 固定北京时间（UTC+8） |
| `sources/netease.py` | 网易云日推 Top N（含 top1 热评）；`mode=api`（本地现用，NeteaseCloudMusicApi+Cookie）或 `ncm-cli`（官方接口备用，当前版本无 recommend 命令） |
| `sources/bilibili.py` | B站关注动态（WBI 签名 + 412/HTML 防风控退避重试） |
| `sources/wechat_article.py` | 公众号推文标题+链接+作者，读微信本地解密库 |
| `daily_push/app.py` | Flask 仪表盘 + `/api/*` 数据接口 + 异步采集接口（失败也发邮件） |
| `daily_push/export_site.py` | 导出单文件静态站 → git push 到 GitHub Pages |
| `daily_push/__main__.py` | CLI：`python -m daily_push` 手动采集一次 |
| `templates/index.html` + `static/*` | 无框架前端仪表盘，本地 API / 内联 `__DAYS__` 双数据源 |
| `tools/notify_email.py` | 失败邮件通知：本地读 `config.json` email 段，云端读 Secrets `SMTP_*` |
| `tools/cookie_reply.py` | 回复邮件更新 Cookie：IMAP 读取 → 剥离引用 → 解析 → 验证 → 写回本地 |
| `tools/cookie_repair_cloud.py` | 云端每 10 分钟轮询回复（最多 6h），验证后 `gh secret set` 更新 Secrets |
| `tools/trigger_cookie_repair.py` | 判定 cookie 类错误并触发 `cookie-repair` 工作流 |
| `tools/` | 云端采集辅助：secrets 生成 config、云端采集入口 |
| `.github/workflows/daily-collect.yml` | 云端每日采集 + 发布 Pages + 出错发邮件 + 触发 cookie-repair |
| `.github/workflows/cookie-repair.yml` | 回复邮件自动更新 Cookie：轮询 → 验证 → 更新 Secrets → 结果邮件 |

各模块的详细设计、数据源输出结构、前端实现细节、配置键参考与隐私处置，分别见
[docs/architecture.md](docs/architecture.md)、[docs/sources/README.md](docs/sources/README.md)、
[docs/frontend.md](docs/frontend.md)、[docs/config-privacy.md](docs/config-privacy.md)。

---

## 四、数据流

```
每天 (开机 / 07:30 定时 / GitHub Actions)
        │
        ▼
collect_once() ──┬─ sources/netease.py        （需要本地 :3000 Node API + Cookie）
                 ├─ sources/bilibili.py       （需要 SESSDATA + WBI 签名）
                 └─ sources/wechat_article.py （仅本地，需要微信解密环境 zstandard）
        │
        ├─ 跨天去重（cutoffs.json，只推新内容）
        │
        ▼
storage.save(push_date, ...)  ──►  data/daily.db（按日合并，失败不覆盖旧值）
        │
        ▼
export_site()  ──►  site/index.html（单文件自包含）
        │
        ▼
push_site()  ──►  GitHub Pages（手机可访问）

本地查看：Flask 仪表盘  http://127.0.0.1:5000  （或直接打开 Pages 链接）
```

---

## 五、快速开始

```bash
pip install -r requirements.txt   # Python 依赖
npm install                        # Node：NeteaseCloudMusicApi
python start.py                    # 一键启动（或 python start.py --no-collect）
# 打开 http://127.0.0.1:5000
```

手动只采一次：`python -m daily_push`。

> 详见 [docs/](docs/README.md)，尤其 [配置与隐私](docs/config-privacy.md)：`config.json`、`data/`、`*.log` 均已 gitignore，请勿提交 Cookie 等敏感信息。

---

## 六、当前能力与限制

- ✅ 网易云日推 Top5（含热评）、B站关注动态、公众号推文，本地网页 + 云端 Pages 双通道。
- ✅ 失败统一邮件通知（本地·采集/推送、云端），标明失败来源。
- ✅ Cookie 失效自动修复：回复报错邮件贴新 Cookie，云端每 10 分钟轮询并更新 Secrets，本地自愈写回 config.json。
- ✅ 网络/登录失败自动耐心重试：采集每 5 分钟、推送每 60 秒，恢复后自动补上。
- ⛔ 小红书已暂停（接口被风控 `300011`，签名已摸清但账号被标记，见 `docs/sources/README.md`）。
- 网易云只提供官网歌曲页链接（`orpheus://` 客户端协议本机无法唤起）。
- 公众号采集依赖本机微信解密环境，云端不采集 mp（但本地 mp 会在推送时随站点合并保留）。

详见 `docs/status.md`。
