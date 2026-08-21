# AGENTS.md · 给 AI 助手的项目操作说明

本仓库是 daily-push（每日推送聚合器：网易云日推 + B站关注动态 + 公众号推文）。
下面是操作约定，请在处理相关请求时遵循。

## 「忽略某博主/公众号」流程

用户说「忽略 XX」时：

1. **编辑 `config.json`**（本文件已 gitignore，不会被提交）：
   - B站 UP 主：追加到 `bilibili.exclude` 数组（作者名子串匹配）
   - 公众号：追加关键词到 `wechat.exclude_keywords` 数组（author/title 子串匹配）
2. **清除历史**：运行
   ```
   python tools/purge_ignored.py
   ```
   该脚本会按忽略名单删除本地库所有历史日期中的对应条目，并自动
   重新导出静态站 + 推送 GitHub Pages。
   （只清除不推送加 `--no-push`）

> 注意：`config.json` 是敏感文件（Cookie），**绝不可提交**，已在 .gitignore 中。

## 分支与提交约定（重要）

- **本地分支就是 `code`**，跟踪 `origin/code`。改代码后直接 `git add -A && git commit && git push` 即可。
  **不要**新建/改名到 `master`，`git push` 也**不要**指定 `master`。
- 远程分支分工：
  - `code`：代码分支，云端每天定时采集 checkout 它（`daily-collect.yml`、`cookie-repair.yml`）
  - `main`：GitHub Pages 分支，云端每天自动提交 `index.html`，本地不要手动操作
  - 旧的 `master` 分支已删除（废弃，勿重建）
- 改前端后记得重新导出静态站让网页同步：`python -c "from daily_push.export_site import export_site, push_site; export_site(); push_site()"`
- 提交前检查 `git status`，`config.json` / `data/` / `site/` 已被 gitignore，不应出现在改动里。

## 常用命令

- 手动采集一次：`python -m daily_push`
- 本地采集依赖网易云 Node 代理 :3000（`npm install` + 启动 NeteaseCloudMusicApi）
- 重新导出并推送站点：`python tools/purge_ignored.py` 会自动做；
  单独做可参考 `daily_push/export_site.py` 的 `export_site()` / `push_site()`

## 平台关键点

- 网易云：`netease.mode=api`（Cookie + :3000 代理）；`ncm-cli` 因无 recommend 命令降为备用
- 公众号：仅本地采集（微信解密环境），云端不采 mp 但本地 mp 随站点合并保留
- B站：SESSDATA + WBI 签名，风控 412/HTML 会自动退避重试
