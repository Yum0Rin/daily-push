"""一键打开本地网页：探测 :5000，没起就拉起 start.py，起来后再开浏览器。

供开始菜单快捷方式用 pythonw 运行（无控制台窗口）。
"""
import os
import socket
import sys
import time
import webbrowser

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from daily_push import proc  # noqa: E402


def _port_open(host, port, timeout=1.0):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def _config():
    try:
        from daily_push.config import load_config
        cfg = load_config()
    except Exception:
        cfg = {}
    return "127.0.0.1", int(cfg.get("port", 5000))


def _start_server():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    # 按需网页模式：只起 Flask + 网易云代理，不采集、不定时。
    proc.popen([exe, os.path.join(PROJECT_DIR, "start.py"), "--serve-only"],
               cwd=PROJECT_DIR)


def main():
    host, port = _config()
    if not _port_open(host, port):
        _start_server()
        for _ in range(60):  # 最多等 ~30s
            if _port_open(host, port):
                break
            time.sleep(0.5)
    webbrowser.open(f"http://{host}:{port}/")


if __name__ == "__main__":
    main()
