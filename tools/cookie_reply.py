"""回复邮件更新 Cookie 的共享逻辑（本地与云端通用）。

流程：
1. IMAP 读取「每日推送」报错邮件的回复（按主题里的 ref 标记精确匹配）。
2. 从回复正文剥离邮件客户端自动附带的引用原文，取第一段。
3. 多个来源按行顺序解析（netease 在前、bilibili 在后，不带前缀）。
4. 验证：网易云 /user/account；B站 /x/web-interface/nav。
5. 落地：本地写 config.json；云端用 gh secret set（见 cookie_repair_cloud.py）。

SMTP/IMAP 凭据：优先环境变量 SMTP_USER/SMTP_PASS（云端），否则 config.json 的 email 段。
QQ 邮箱：smtp.qq.com -> imap.qq.com:993，授权码 SMTP/IMAP 通用。
"""
import email
import imaplib
import json
import os
import re
import time

import requests
from email.header import decode_header


def _decode_subject(subj):
    parts = decode_header(subj or "")
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(text))
    return "".join(out)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def _config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _email_creds():
    """返回 (user, pass)。云端用 env，本地用 config email 段。"""
    cfg = _config().get("email") or {}
    user = os.environ.get("SMTP_USER") or cfg.get("smtp_user")
    pwd = os.environ.get("SMTP_PASS") or cfg.get("smtp_pass")
    return user, pwd


def _imap_host_port():
    """从 smtp 主机推导 imap；config 可覆盖 imap_host/imap_port。"""
    cfg = _config().get("email") or {}
    host = cfg.get("imap_host")
    port = cfg.get("imap_port")
    if not host:
        smtp = os.environ.get("SMTP_HOST") or cfg.get("smtp_host") or "smtp.qq.com"
        host = smtp.replace("smtp.", "imap.", 1) if smtp.startswith("smtp.") else "imap.qq.com"
    if not port:
        port = 993
    return host, int(port)


def _strip_quote(body):
    """去掉邮件客户端回复时附带的引用原文，只保留用户新写的内容。"""
    markers = [
        "---- 回复的原邮件 ----", "---- 转发的邮件 ----", "----- 原始邮件 -----",
        "写道：", "写道:", "wrote:", "On ", "───", "──────────",
    ]
    lines = body.splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith(">") or s.startswith("|"):
            continue
        if any(m in s for m in markers):
            break
        if s:
            out.append(s)
    return "\n".join(out).strip()


def _normalize_cookie(source, value):
    """归一化 Cookie 字符串，去掉用户可能带上的前缀/空白。"""
    v = value.strip()
    if not v:
        return None
    if source == "netease":
        if not v.lower().startswith("music_u="):
            m = re.search(r"(MUSIC_U=[A-Za-z0-9%]+)", v)
            v = m.group(1) if m else None
        if not v:
            return None
        # 只保留 MUSIC_U=... 这一段
        m = re.search(r"MUSIC_U=[A-Za-z0-9%]+", v)
        return m.group(0) if m else None
    if source == "bilibili":
        v = v.split()[0]
        if v.startswith("SESSDATA="):
            v = v[len("SESSDATA="):]
        if "SESSDATA=" in v:
            m = re.search(r"SESSDATA=([^;\s]+)", v)
            v = m.group(1) if m else v
        return v if re.match(r"^[A-Za-z0-9%_,\-.\*]+$", v) else None
    return v


def extract_cookies(text, sources):
    """按行顺序解析多个来源的 cookie：netease 第一行、bilibili 第二行。"""
    body = _strip_quote(text)
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    result = {}
    for i, src in enumerate(sources):
        if i < len(lines):
            v = _normalize_cookie(src, lines[i])
            if v:
                result[src] = v
    return result


def imap_find_reply(ref, since_days=3, sources=None):
    """IMAP 查找主题含 ref 的「Re:」回复，返回最新一封的正文；找不到返回 None。"""
    user, pwd = _email_creds()
    if not user or not pwd:
        return None
    host, port = _imap_host_port()
    since = time.strftime("%d-%b-%Y", time.gmtime(time.time() - since_days * 86400))
    try:
        m = imaplib.IMAP4_SSL(host, port, timeout=30)
        m.login(user, pwd)
        m.select("INBOX")
        typ, data = m.search(None, f'(SINCE {since})')
        ids = data[0].split()
        best = None
        for i in reversed(ids):
            typ, msg_data = m.fetch(i, "(RFC822.HEADER)")
            if typ != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            subj = _decode_subject(msg.get("Subject") or "")
            if "Re:" in subj and ref in subj:
                best = i
                break
        if best is None:
            m.logout()
            return None
        typ, msg_data = m.fetch(best, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        m.logout()
        parts = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        parts.append(part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="replace"))
                    except Exception:
                        pass
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
        return "\n".join(parts)
    except Exception as e:
        print(f"[cookie_reply] IMAP error: {e}")
        return None


def test_netease_cookie(cookie, base_url="http://localhost:3000"):
    """用新 cookie 调 /user/account 验证。返回 (ok, detail)。"""
    try:
        r = requests.get(base_url.rstrip("/") + "/user/account",
                         headers={"Cookie": cookie},
                         timeout=20)
        data = r.json()
        if data.get("code") == 200 and data.get("profile"):
            return True, f"网易云登录正常：{data['profile'].get('nickname')}"
        return False, f"网易云 cookie 无效（code={data.get('code')}）"
    except Exception as e:
        return False, f"网易云验证请求失败：{e}"


def test_bilibili_sessdata(sessdata):
    """用新 SESSDATA 调 nav 验证。返回 (ok, detail)。"""
    try:
        r = requests.get("https://api.bilibili.com/x/web-interface/nav",
                         cookies={"SESSDATA": sessdata},
                         headers={
                             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                             "Referer": "https://www.bilibili.com/",
                         }, timeout=20)
        data = r.json()
        if data.get("code") == 0:
            name = (data.get("data") or {}).get("uname") or "?"
            return True, f"B站登录正常：{name}"
        return False, f"B站 SESSDATA 无效（code={data.get('code')}）"
    except Exception as e:
        return False, f"B站验证请求失败：{e}"


def test_cookie(source, value, base_url="http://localhost:3000"):
    if source == "netease":
        return test_netease_cookie(value, base_url)
    if source == "bilibili":
        return test_bilibili_sessdata(value)
    return False, f"未知来源：{source}"


def apply_local_config(updates):
    """把新 cookie 写回本地 config.json。"""
    cfg = _config()
    netease = cfg.setdefault("netease", {})
    bilibili = cfg.setdefault("bilibili", {})
    changed = []
    if "netease" in updates:
        netease["cookie"] = updates["netease"]
        changed.append("netease.cookie")
    if "bilibili" in updates:
        bilibili["sessdata"] = updates["bilibili"]
        changed.append("bilibili.sessdata")
    if changed:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    return changed


def is_cookie_error(source, error):
    """判断某个来源的报错是否属于 cookie/登录失效类。"""
    if source not in ("netease", "bilibili"):
        return False
    text = str(error or "")
    keys = ["cookie", "Cookie", "登录", "未登录", "登录态", "过期", "login",
            "401", "code 301", "301", "账号", "SESSDATA", "MUSIC_U"]
    return any(k in text for k in keys)
