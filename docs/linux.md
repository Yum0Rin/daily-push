# Linux 部署（本地部分）

> 更新日期：2026-09-22

这是一份「把本地服务从 Windows 搬到 Linux」的说明。云端（GitHub Actions + Pages）两平台完全一致，差异只在**本地**：
自启方式、路径、以及微信公众号采集的有无。

## 与 Windows 的差异一览

| 能力 | Windows | Linux |
|------|---------|-------|
| 登录一次性采集 | 启动文件夹 `Startup\DailyPush.vbs`（pythonw） | systemd 用户服务 `daily-push-collect.service`（oneshot，绑 `graphical-session.target`） |
| 按需打开网页 | 开始菜单快捷方式 → `tools/open_dashboard.py` | 应用菜单 `daily-push.desktop` → `tools/open_dashboard.py` |
| 网易云 Node 代理 | 系统 `node` | `~/.local/node/bin/node`（代码里 `pipeline._node_exe()` 会自动找，不必进 PATH） |
| `gh` CLI | `C:\Program Files\GitHub CLI\gh.exe`（在 PATH） | `~/.local/bin/gh`（不在 PATH，`cloud_secrets._gh_exe()` 会自动找） |
| 公众号推文 | ✅ 读本地微信解密库 | ❌ 无微信解密环境，**静默跳过**（不算失败） |
| Node 依赖平台二进制 | 需重装 `npm install` | 需重装 `npm install` |

> **RTL：** 网页/采集/导出/推送是纯 Python + `requests`，跨平台；只有「自启胶水」和「公众号解密」是平台相关的。

## 目录与依赖

项目落在 `~/daily-push/`：

- Python：`.venv/`（`python3 -m venv .venv` + `pip install -r requirements.txt`）
- Node：`~/.local/node/bin`（v24）；在项目里 `npm install`（`NeteaseCloudMusicApi`）
- 密钥：`config.json`（从 Windows 直接拷，明文，不入库）
- 历史：`data/daily.db` 等（从 Windows 拷，不入库）

国内装依赖：pip 用清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`，npm 用 `--registry=https://registry.npmmirror.com`。

## 一键安装 / 卸载桌面集成

```bash
cd ~/daily-push
.venv/bin/python tools/install_linux.py           # 安装/更新 + 启用登录采集（幂等）
.venv/bin/python tools/install_linux.py --start   # 安装后立刻跑一次采集验证
.venv/bin/python tools/install_linux.py --uninstall
```

`install_linux.py` 写入两处（均可重复运行覆盖）：

- `~/.config/systemd/user/daily-push-collect.service`：登录会话起来后跑一次
  `tools/run_daily.py`（采集→导出→推送 Pages）即退出，**无常驻**；`ExecStartPre` 会先等 DNS（最多 60s）。
- `~/.local/share/applications/daily-push.desktop`：应用菜单「每日推送」，点开走
  `tools/open_dashboard.py`（探测 `:5000`，没起就先拉起 `start.py --serve-only`，起来再开浏览器）。

手动命令（与 Windows 相同）：

```bash
.venv/bin/python tools/run_daily.py        # 一次性采集并推送
.venv/bin/python -m daily_push             # 只采集不推送（不经 pipeline，网易云代理不会自动起）
.venv/bin/python start.py --serve-only     # 按需起本地网页（:5000）
.venv/bin/python -m unittest discover -s tests -t .   # 单元测试
```

> 只看网页时**不会**起网易云代理；只有「检测网易云 / 手动推送 / 清理发布」等网易云操作期间才懒加载 `:3000`。

## 平台适配改了哪些代码

为让同一份代码在 Linux 也跑得动（不改变 Windows 行为），改动集中在「找不到二进制 / 没有微信环境」两类：

- `daily_push/pipeline.py`：新增 `_node_exe()`，`shutil.which("node")` 找不到就退回 `~/.local/node/bin/node`。
- `daily_push/cloud_secrets.py`：新增 `_gh_exe()`，同样方式退回 `~/.local/bin/gh`；`gh_available()` 用同一解析。
- `daily_push/collector.py` + `sources/wechat_article.py`：新增 `decryption_available()`（检查 `WMCP_DIR` 与
  `wechat_cli_mcp` 是否可导入）。**非 Windows** 且无解密环境时，公众号源**静默跳过**（不写 `mp` 错误），
  这样一轮采集不会因「本机没有公众号」被判失败而中止推送；Windows 行为不变（缺环境仍报错）。
- `tools/install_linux.py`：新增，Linux 桌面集成安装器（systemd 用户服务 + `.desktop`）。
- `tests/test_cloud_secrets.py`：`gh` 路径断言改为 basename，并让 `test_no_gh` 同时屏蔽 fallback 路径，保持跨平台可过。

## git / gh 凭据（Linux）

- `~/.gitconfig`：已有 FastGithub 的 http/https 代理；补了 `user.name/email`。
- 推送认证：`gh auth setup-git` 写入 `credential.helper = !~/.local/bin/gh auth git-credential`（绝对路径，用户级）。
  `git fetch/push` 走 https + 代理即可，无需 SSH。
- 分支：本地 `code` 跟踪 `origin/code`；Pages 分支 `main` 由 `export_site.push_site()` 用独立 worktree 更新。

## 已知限制

- 微信公众号：Linux 无法登录微信（设备验证），`mp` 源不可用；云端本来也不采 mp，历史 mp 随站点合并保留。
  以后若在 Linux 打通微信解密，设 `WMCP_DIR` 指向解密模块并确保 `zstandard` 可用即可自动启用。
- `run_daily.py` 无重试（与 Windows 一致）；登录采集失败会发提示邮件，07:30 云端仍会兜底采集。
