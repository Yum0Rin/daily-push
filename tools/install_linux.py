"""把 daily-push 的本地部分装到 Linux 桌面（登录一次性采集 + 网页按需）。

Windows 侧用的是「启动文件夹 Startup\\DailyPush.vbs + 开始菜单快捷方式」；Linux 对应物：

* 登录一次性采集：systemd 用户服务 ``daily-push-collect.service``（oneshot，绑定
  ``graphical-session.target``，登录会话起来后跑一次 ``tools/run_daily.py`` 即退出，无常驻）。
* 网页按需启停：应用菜单里的 ``daily-push.desktop``，指向 ``tools/open_dashboard.py``
  （探测 :5000，没起就先拉起 ``start.py --serve-only``，起来再开浏览器）。

用法：
    python tools/install_linux.py            # 安装/更新（幂等）+ 启用登录采集
    python tools/install_linux.py --start    # 安装后立刻跑一次采集验证
    python tools/install_linux.py --uninstall
"""
import argparse
import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
VENV_PY = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
UNIT_DIR = os.path.join(HOME, ".config", "systemd", "user")
UNIT_NAME = "daily-push-collect.service"
UNIT_PATH = os.path.join(UNIT_DIR, UNIT_NAME)
APPS_DIR = os.path.join(HOME, ".local", "share", "applications")
DESKTOP_NAME = "daily-push.desktop"
DESKTOP_PATH = os.path.join(APPS_DIR, DESKTOP_NAME)
ICON = os.path.join(PROJECT_DIR, "assets", "daily-push.svg")

UNIT = f"""[Unit]
Description=daily-push 登录一次性采集并推送（无常驻）
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=oneshot
WorkingDirectory={PROJECT_DIR}
Environment=PATH={HOME}/.local/node/bin:{HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
# 等到 DNS 可用（最多 60s），避免会话刚起来就采集失败
ExecStartPre=/bin/sh -c 'timeout 60 sh -c "until getent hosts github.com >/dev/null 2>&1; do sleep 2; done" || true'
ExecStart={VENV_PY} {PROJECT_DIR}/tools/run_daily.py
TimeoutStartSec=1800

[Install]
WantedBy=graphical-session.target
"""

DESKTOP = f"""[Desktop Entry]
Type=Application
Name=每日推送
Comment=打开每日推送本地网页（必要时先启动服务）
Exec={VENV_PY} {PROJECT_DIR}/tools/open_dashboard.py
Path={PROJECT_DIR}
Icon={ICON}
Terminal=false
Categories=Utility;
StartupNotify=false
"""


def _systemctl(*args, check=False):
    return subprocess.run(["systemctl", "--user", *args], check=check)


def install(start_now=False):
    if not os.path.exists(VENV_PY):
        sys.exit(f"找不到虚拟环境：{VENV_PY}（先在项目里 python3 -m venv .venv 并装依赖）")
    os.makedirs(UNIT_DIR, exist_ok=True)
    os.makedirs(APPS_DIR, exist_ok=True)
    with open(UNIT_PATH, "w", encoding="utf-8") as f:
        f.write(UNIT)
    with open(DESKTOP_PATH, "w", encoding="utf-8") as f:
        f.write(DESKTOP)
    _systemctl("daemon-reload")
    _systemctl("enable", UNIT_NAME, check=True)
    if start_now:
        _systemctl("start", UNIT_NAME, check=True)
    print("已安装：")
    print("  systemd 用户服务:", UNIT_PATH)
    print("  桌面入口:", DESKTOP_PATH)
    print("  （应用菜单里搜「每日推送」即可打开本地网页）")
    if not start_now:
        print("登录会话起来后自动采集一次；现在想立刻验证：systemctl --user start " + UNIT_NAME)


def uninstall():
    _systemctl("disable", "--now", UNIT_NAME)
    for p in (UNIT_PATH, DESKTOP_PATH):
        try:
            os.remove(p)
            print("已删除:", p)
        except FileNotFoundError:
            pass
    _systemctl("daemon-reload")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", action="store_true", help="安装后立刻跑一次采集验证")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    if a.uninstall:
        uninstall()
    else:
        install(start_now=a.start)


if __name__ == "__main__":
    main()
