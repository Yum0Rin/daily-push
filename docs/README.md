# daily-push 每日推送聚合器

多平台每日信息聚合器：网易云日推、B站关注UP动态、QQ群消息、微信群消息、微信公众号推文。
通过 `start.py` 一键启动（自动拉起网易云API → 采集 → Flask 网页 → 开机自动采集 + 每日 08:30 兜底定时）。

## 目录结构

```
daily-push/
├── start.py                  # 一键启动入口
├── config.json               # 配置（含各平台 Cookie/密钥 —— 已 gitignore）
├── requirements.txt          # Python 依赖
├── package.json              # Node 依赖（NeteaseCloudMusicApi）
├── netease_server.js         # 网易云API封装
├── data/                     # SQLite 存储（已 gitignore）
├── daily_push/
│   ├── app.py                # Flask 网页 + 异步采集接口
│   ├── collector.py          # 聚合采集调度
│   ├── storage.py            # SQLite 存储层（按日合并语义）
│   ├── config.py             # 配置加载
│   ├── templates/index.html  # 前端页面
│   ├── static/app.js         # 前端逻辑
│   ├── static/style.css      # 前端样式
│   └── sources/
│       ├── netease.py        # 网易云日推
│       ├── bilibili.py       # B站关注UP（防风控批次+重试）
│       ├── qq.py             # QQ群消息
│       ├── wechat.py         # 微信群消息
│       ├── wechat_article.py # 公众号推文（标题+链接）
│       └── xiaohongshu.py    # 小红书（预留，见下方说明）
├── tools/
│   ├── xhs_console.txt       # 小红书浏览器Console采集脚本
│   └── xhs_capture.txt       # 小红书请求头捕获脚本
└── docs/                     # 本文档
```

## 快速开始

```bash
pip install -r requirements.txt
npm install            # 安装 NeteaseCloudMusicApi
python start.py        # 一键启动（或 python start.py --no-collect）
# 打开 http://127.0.0.1:5000
```

## 各模块详见

- [架构与采集流程](architecture.md)
- [数据源说明](sources/README.md)
- [前端说明](frontend.md)
- [配置与隐私字段](config-privacy.md)  ← 敏感信息处置说明，务必先读
- [当前状态与已知问题](status.md)