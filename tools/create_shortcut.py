"""在开始菜单创建「每日推送」快捷方式：一键（必要时先启动服务）打开本地网页。

用法：python tools/create_shortcut.py

快捷方式指向 tools/open_dashboard.py（用 pythonw 无控制台运行）：
先探测 :5000，没起就拉起 start.py，起来后再打开浏览器——所以即使后台进程崩了，
双击也能自动补起，而不是打开一个连不上的页面。
"""
import argparse
import base64
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from daily_push import proc  # noqa: E402

START_MENU = os.path.join(os.environ.get("APPDATA", ""),
                          "Microsoft", "Windows", "Start Menu", "Programs")
ICON = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                    "System32", "SHELL32.dll")


def _pythonw():
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return cand if os.path.exists(cand) else sys.executable


def create(name="每日推送"):
    os.makedirs(START_MENU, exist_ok=True)
    lnk = os.path.join(START_MENU, name + ".lnk")
    launcher = os.path.join(PROJECT_DIR, "tools", "open_dashboard.py")
    ps = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{lnk}');"
        f"$s.TargetPath = '{_pythonw()}';"
        f"$s.Arguments = '\"{launcher}\"';"
        f"$s.WorkingDirectory = '{PROJECT_DIR}';"
        f"$s.IconLocation = '{ICON},13';"
        "$s.Description = '每日推送 - 打开本地网页（必要时先启动服务）';"
        "$s.Save()"
    )
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    proc.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
             check=True, capture_output=True)
    return lnk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="每日推送")
    a = ap.parse_args()
    print("已创建快捷方式:", create(a.name))


if __name__ == "__main__":
    main()
