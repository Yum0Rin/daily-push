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
│  cron 30 23 * * *（UTC，≈北京 07:30）触发                    │
│  用 secrets 生成 config.json → 启动网易云 API                │
│  cloud_collect.py → collect_once(netease, bilibili)         │
│  export_site() → push 到 main（Pages）                       │
└─────────────────────────────────────────────────────────────┘
```

两条链路共用 `collect_once()` 与 `export_site()`，区别仅在于：云端不采公众号（无微信解密环境）。

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

## start.py 说明

- `--no-collect`：只启动服务，不做首次采集。
- `_port_open()` 端口检测去重，避免重复拉起网易云 API。
- 每日定时：`push_time`（默认 07:30）独立 daemon 线程，作为开机采集的兜底。
- 出错提醒：采集失败写桌面 `collect_error.txt` 并弹出（每天一次，标记文件去重）。
