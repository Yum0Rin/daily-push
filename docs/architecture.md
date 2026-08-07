# 架构与采集流程

## 整体流程

```
start.py
  ├── ensure_netease_api()  → 保证 :3000 NeteaseCloudMusicApi 存活
  ├── 采集线程 collect_once()（异步 daemon）
  └── Flask (app.py) @ 5000  +  每日定时采集线程

collect_once():
  - 网易云日推      → sources/netease.py
  - B站关注UP动态   → sources/bilibili.py
  - QQ群消息       → sources/qq.py（采集保留，前端已移除）
  - 微信群消息     → sources/wechat.py
  - 公众号推文     → sources/wechat_article.py  (mp 字段)
  - 小红书         → sources/xiaohongshu.py (预留/未接通)
  统一结果写 storage.save(push_date, ...)  → data/daily.db
```

## 存储层（storage.py）—— 按日合并语义

`pushes` 表按 `push_date`（主键）每天一行，含列：`netease,bilibili,qq,wechat,mp`。

**关键合并逻辑**：`save()` 遍历各字段，当某来源本次返回 `None` 或 `{"error": ...}`
时，**保留数据库里当天的旧值**，避免「某来源失败 → 把当天该来源清空/覆盖成错误」。
这是修复「网易云和QQ刚正常后就消失」问题的核心。

数据库旧结构升级：自动 `ALTER TABLE pushes ADD COLUMN mp`（无 mp 列时）。

## 采集执行方式

- 采集是**异步**的：`POST /api/collect` 启动后台线程立即返回，前端轮询 `/api/collect/status`。
- Flask 使用 `threaded=True`。

## B站防风控策略（bilibili.py）

- 采集分两轮：全部UP → 重试失败的UP。
- 每轮每个批次 2 个，批间 `sleep 2s`。
- `_get` 遇 HTTP 412 / HTML 响应时降级为 `risk-control (HTTP 412)`，重试 3 次。

## start.py 说明

- `--no-collect`：只启动服务，不做首次采集。
- 端口冲突检测 `_port_open()` 去重，避免重复拉起网易云API。
- 每日定时：`push_time`（默认 07:30），独立 daemon 线程，作为开机采集的兜底。