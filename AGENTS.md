# AGENTS.md · 给 AI 助手的项目操作说明

本仓库是 daily-push（每日推送聚合器：网易云日推 + B站关注动态 + 公众号推文）。
下面是操作约定，请在处理相关请求时遵循。

## 「忽略某博主/公众号」流程

用户说「忽略 XX」时：

1. **编辑 `settings.json`**（本文件**纳入 git 跟踪**，策略键与云端同源）：
   - B站 UP 主：追加到 `bilibili.exclude` 数组（作者名子串匹配）
   - 公众号：追加关键词到 `wechat.exclude_keywords` 数组（**仅按 author/公众号名 子串匹配**，不匹配标题，避免误伤）
   > 也可直接在本地设置页 `http://127.0.0.1:5000/settings` 的「屏蔽名单」里增删，效果相同。
2. **清除历史**：运行
   ```
   python tools/purge_ignored.py
   ```
   该脚本会按忽略名单删除本地库所有历史日期中的对应条目，并自动
   重新导出静态站 + 推送 GitHub Pages。
   （只清除不推送加 `--no-push`）
3. **同步云端**：`settings.json` 需在 `code` 分支上，云端 `daily-collect` 才会同源忽略。
   - 用设置页保存时会**自动**提交并推送 `settings.json` 到 `code`；
   - 若手动改的，自己 `git add settings.json && git commit && git push`。

> **配置分层（重要）**：
> - `settings.json`：**非密钥**策略（屏蔽名单 / 阈值 / `push_time` 等），跟踪入库，本地与云端同源。
> - `config.json`：**密钥/机器相关**（各平台 Cookie、SMTP 授权码、`site.repo`、`port` 等），已 gitignore，**绝不可提交**。
> - `load_config()` 合并顺序 `默认 < settings.json < config.json`；`settings.json` 里出现密钥键会被忽略。
> - `settings_store.save_secrets()` 会生成 `config.json.bak`（含密钥），已被 `config.json.*` 规则忽略。

## 分支与提交约定（重要）

- **本地分支就是 `code`**，跟踪 `origin/code`。改代码后直接 `git add -A && git commit && git push` 即可。
  **不要**新建/改名到 `master`，`git push` 也**不要**指定 `master`。
- 远程分支分工：
  - `code`：代码分支，云端每天定时采集 checkout 它（`daily-collect.yml`、`cookie-repair.yml`）
  - `main`：GitHub Pages 分支，云端每天自动提交 `index.html`，本地不要手动操作
  - 旧的 `master` 分支已删除（废弃，勿重建）
- 改前端后记得重新导出静态站让网页同步：`python -c "from daily_push.export_site import export_site, push_site; export_site(); push_site()"`
- 提交前检查 `git status`，`config.json` / `data/` / `site/` 已被 gitignore，不应出现在改动里。
- **每次 commit / push 前必须同步更新受影响的文档**（`README.md`、`AGENTS.md`、`docs/*`），
  并在 `docs/status.md` 变更记录里登记日期；文档中写明**修改时间**。
- 本地个人笔记（gitignored，给 AI 自己看）见 `AGENTS.local.md`，**若存在请先读**。

## 常用命令

- 手动采集一次：`python -m daily_push`
- 本地采集依赖网易云 Node 代理 :3000（`npm install` + 启动 NeteaseCloudMusicApi）
- 重新导出并推送站点：`python tools/purge_ignored.py` 会自动做；
  单独做可参考 `daily_push/export_site.py` 的 `export_site()` / `push_site()`
- 跑单元测试：`python -m unittest discover -s tests -t .`

## 本地设置页（`/settings`）

`python start.py` 后访问 `http://127.0.0.1:5000/settings`（**仅本机**，仪表盘右上角 ⚙️ 进入）：

- **平台登录状态**：检测网易云 / B站；粘贴新 Cookie「保存并验证」（写 `config.json`）。
- **屏蔽名单**：增删 B站 UP / 公众号关键词。「保存并应用到全部推送」= 写 `settings.json`
  → 清理历史/今天命中条目 → 重发 Pages → 推送 `settings.json` 到 `code`。
- **采集参数**：`push_time` / `max_songs` / 窗口与条数等。
- **安全**：Host/Origin 校验 + 每次启动随机 `X-CSRF-Token`；密钥只回打码值；设置页不参与静态站导出。
- **生效时机**：屏蔽名单 / Cookie 下次采集即生效；`push_time`、`port` 等需重启进程。

> 云端要读到 `settings.json`，前提是 `code` 分支上是**含配置分层的新代码**，否则云端仍走旧逻辑。
> 详见 [docs/settings.md](docs/settings.md)。

## 平台关键点

- 网易云：`netease.mode=api`（Cookie + :3000 代理）；`ncm-cli` 因无 recommend 命令降为备用
- 公众号：仅本地采集（微信解密环境），云端不采 mp 但本地 mp 随站点合并保留
- B站：SESSDATA + WBI 签名，风控 412/HTML 会自动退避重试
