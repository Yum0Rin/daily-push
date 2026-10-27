"""小红书「推荐流」采集（homefeed_recommend）。

流程：签名（xhshow）→ 翻页拉推荐流 → 按点赞阈值过滤 → 广告启发式过滤 → 取前 N 条。

登录态来源（按顺序）：
1. ``config.json`` 的 ``xiaohongshu.cookie``（含 ``web_session=`` 的完整 Cookie 串）；
2. 本机 Firefox 配置目录里已登录的小红书 Cookie（只读打开，不复制不外传）。

注意：推荐流返回的 ``note_card`` 只有 cover/type/display_title/user/interact_info，
**没有广告标记**，所以「非推广/广告」只能靠标题+作者关键词启发式，会漏判/误杀。

小红书**不对外提供浏览量**（推荐流与笔记详情接口都没有 view/play 字段，只有作者
自己在创作中心能看到），所以做不了 B站 那种「点赞/播放」比例。替代方案是按笔记
详情里的收藏数算「藏/赞比」：收藏相对点赞越高，说明内容越有留存价值（干货型），
纯情绪/娱乐内容这个比值很低。取收藏需要逐条调详情接口（一条候选一次请求），
因此只在候选已过点赞阈值后才查，并且 ``min_collect_ratio=0`` 时完全关闭。
"""
import glob
import os
import re
import sqlite3
import time

import requests

API_HOST = "https://edith.xiaohongshu.com"
FEED_URI = "/api/sns/web/v1/homefeed"
DETAIL_URI = "/api/sns/web/v1/feed"
NOTE_URL = "https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_feed"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) "
       "Gecko/20100101 Firefox/145.0")

# 默认广告/推广关键词：命中标题或作者名即丢弃。可在 settings.json 的
# xiaohongshu.ad_keywords 覆盖（传空数组则关闭该过滤）。
DEFAULT_AD_KEYWORDS = [
    "广告", "推广", "赞助", "带货", "品牌合作", "合作推广",
    "优惠券", "领券", "团购", "橱窗", "旗舰店", "专卖店",
    "点击链接", "拍立淘", "私信咨询", "限时折扣",
]

_NOTE_ID_RE = re.compile(r"/explore/([0-9a-fA-F]{16,})")


class XhsError(Exception):
    pass


def _parse_likes(raw):
    """'1.1万' / '549' / '2.3千' -> int。"""
    s = str(raw or "").strip()
    mult = 1
    if s.endswith("万"):
        mult, s = 10000, s[:-1]
    elif s.endswith("千"):
        mult, s = 1000, s[:-1]
    elif s.lower().endswith("w"):
        mult, s = 10000, s[:-1]
    try:
        return int(round(float(s) * mult))
    except (TypeError, ValueError):
        return 0


def _parse_cookie_string(text):
    out = {}
    for part in str(text or "").split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k:
            out[k] = v.strip()
    return out


def _cookies_from_firefox():
    """从本机 Firefox 配置里读小红书 Cookie（只读，不复制文件）。

    返回第一个含未过期 ``web_session`` 的配置里的 Cookie；没有则返回 {}。
    """
    base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
    now = time.time()
    for db in glob.glob(os.path.join(base, "*", "cookies.sqlite")):
        uri = "file:" + db.replace("\\", "/") + "?mode=ro&immutable=1"
        try:
            con = sqlite3.connect(uri, uri=True, timeout=3)
            rows = con.execute(
                "SELECT name, value, expiry FROM moz_cookies WHERE host LIKE ?",
                ("%xiaohongshu%",)).fetchall()
            con.close()
        except sqlite3.Error:
            continue
        jar = {n: v for n, v, exp in rows if exp == 0 or exp > now}
        if jar.get("web_session"):
            return jar
    return {}


def probe_login(cookie_str):
    """用给定 Cookie 打一次推荐流，验证登录态是否可用。返回 ``(ok, detail)``。

    设置页「检测/保存并验证」与邮件 cookie-repair 共用，保证两边判定一致。
    """
    try:
        from xhshow import Xhshow
    except ImportError:
        return False, "缺少依赖 xhshow（pip install xhshow）"
    text = str(cookie_str or "").strip()
    jar = _parse_cookie_string(text) if "=" in text else {"web_session": text}
    if not jar.get("web_session"):
        return False, "Cookie 里没有 web_session"
    if not jar.get("a1"):
        return False, "Cookie 里没有 a1（签名需要 a1，请粘贴整段 Cookie）"
    payload = {
        "cursor_score": "", "num": 10, "refresh_type": 1, "note_index": 0,
        "unread_begin_note_id": "", "unread_end_note_id": "", "unread_note_count": 0,
        "category": "homefeed_recommend", "search_key": "", "need_num": 10,
        "image_scenes": ["FD_PRV_WEBP", "FD_WM_WEBP"],
    }
    headers = {
        "User-Agent": _UA,
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.xiaohongshu.com",
        "Referer": "https://www.xiaohongshu.com/explore",
    }
    try:
        headers.update(Xhshow().sign_headers_post(FEED_URI, jar, payload=payload))
        r = requests.post(API_HOST + FEED_URI, json=payload, headers=headers,
                          cookies=jar, timeout=20)
        data = r.json()
    except Exception as e:
        return False, f"小红书验证请求失败：{e}"
    code = data.get("code")
    if code == 0:
        n = len(((data.get("data") or {}).get("items")) or [])
        return True, f"小红书登录正常（推荐流返回 {n} 条）"
    if code == -101:
        return False, "小红书未登录：Cookie 无效或已过期"
    if code == 300011:
        return False, "小红书账号被风控（300011），请先在浏览器正常使用一段时间"
    return False, f"小红书验证失败（code={code}：{data.get('msg')}）"


class XhsCollector:
    def __init__(self, cfg):
        try:
            from xhshow import Xhshow
        except ImportError as e:  # pragma: no cover - 依赖缺失时给出可读提示
            raise XhsError(f"缺少依赖 xhshow（pip install xhshow）：{e}")
        x = cfg.get("xiaohongshu") or {}
        self.cookie_str = str(x.get("cookie") or "").strip()
        self.limit = int(x.get("limit") or 10)
        self.min_likes = int(x.get("min_likes") or 5000)
        self.min_collect_ratio = float(x.get("min_collect_ratio") or 0)
        self.max_pages = int(x.get("max_pages") or 6)
        self.interval = float(x.get("request_interval") or 2.0)
        self.detail_interval = float(x.get("detail_interval") or 1.5)
        self.time_budget = float(x.get("time_budget") or 30)
        self.ad_keywords = [str(k) for k in (x.get("ad_keywords")
                                             if x.get("ad_keywords") is not None
                                             else DEFAULT_AD_KEYWORDS) if str(k).strip()]
        self.exclude = [str(k) for k in (x.get("exclude_keywords") or []) if str(k).strip()]
        self._signer = Xhshow()
        self._cookies = None
        self.session = requests.Session()

    # ---- auth ----
    def cookies(self):
        if self._cookies is not None:
            return self._cookies
        if "web_session=" in self.cookie_str:
            jar = _parse_cookie_string(self.cookie_str)
            if not jar.get("a1"):
                raise XhsError("小红书 Cookie 缺少 a1（签名需要），请粘贴浏览器里的整段 Cookie")
        else:
            jar = _cookies_from_firefox()
        if not jar.get("web_session"):
            raise XhsError(
                "小红书登录态缺失：config.json 的 xiaohongshu.cookie 未配置，"
                "且本机 Firefox 里没有已登录的小红书 Cookie")
        self._cookies = jar
        return jar

    # ---- request ----
    def _headers(self, payload):
        headers = {
            "User-Agent": _UA,
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/explore",
        }
        headers.update(self._signer.sign_headers_post(FEED_URI, self.cookies(),
                                                      payload=payload))
        return headers

    def _page(self, cursor):
        payload = {
            "cursor_score": cursor, "num": 20, "refresh_type": 1, "note_index": 0,
            "unread_begin_note_id": "", "unread_end_note_id": "", "unread_note_count": 0,
            "category": "homefeed_recommend", "search_key": "", "need_num": 20,
            "image_scenes": ["FD_PRV_WEBP", "FD_WM_WEBP"],
        }
        last = None
        for attempt in (1, 2):
            try:
                r = self.session.post(API_HOST + FEED_URI, json=payload,
                                      headers=self._headers(payload),
                                      cookies=self.cookies(), timeout=20)
            except Exception as e:
                last = XhsError(f"请求失败：{e}")
                time.sleep(3 * attempt)
                continue
            if r.status_code != 200:
                last = XhsError(f"HTTP {r.status_code}")
                time.sleep(3 * attempt)
                continue
            try:
                data = r.json()
            except ValueError:
                last = XhsError("返回非 JSON（可能被风控）")
                time.sleep(3 * attempt)
                continue
            if data.get("code") != 0:
                raise XhsError(f"接口返回 {data.get('code')}：{data.get('msg')}")
            body = data.get("data") or {}
            return body.get("items") or [], body.get("cursor_score") or ""
        raise last or XhsError("请求失败")

    def _detail(self, note_id, xsec_token):
        """取笔记详情里的 ``interact_info``（收藏/评论/转发数）。

        失败返回 ``None``：调用方按「比例未知」放行，不因单条请求失败就丢内容。
        """
        payload = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": "1"},
            "xsec_source": "pc_feed",
            "xsec_token": xsec_token or "",
        }
        headers = {
            "User-Agent": _UA,
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.xiaohongshu.com",
            "Referer": "https://www.xiaohongshu.com/explore",
        }
        try:
            headers.update(self._signer.sign_headers_post(DETAIL_URI, self.cookies(),
                                                          payload=payload))
            r = self.session.post(API_HOST + DETAIL_URI, json=payload, headers=headers,
                                  cookies=self.cookies(), timeout=20)
            if r.status_code != 200:
                return None
            data = r.json()
        except Exception:
            return None
        if data.get("code") != 0:
            return None
        items = (data.get("data") or {}).get("items") or []
        if not items:
            return None
        return ((items[0] or {}).get("note_card") or {}).get("interact_info") or None

    # ---- filtering ----
    def _is_dropped(self, title, author):
        text = f"{title} {author}"
        for k in self.exclude:
            if k in text:
                return True
        return any(k.lower() in text.lower() for k in self.ad_keywords)

    @staticmethod
    def _cover(card):
        cover = card.get("cover") or {}
        url = cover.get("url") or ""
        if not url:
            for info in cover.get("info_list") or []:
                if info.get("image_scene") == "FD_PRV_WEBP" and info.get("url"):
                    url = info["url"]
                    break
            if not url:
                for info in cover.get("info_list") or []:
                    if info.get("url"):
                        url = info["url"]
                        break
        return url.replace("http://", "https://", 1) if url.startswith("http://") else url

    @staticmethod
    def _created(note_id):
        """笔记 ID 前 8 位十六进制 = 发布时间戳。"""
        try:
            ts = int(str(note_id)[:8], 16)
        except ValueError:
            return 0
        # 合理区间校验（2001-09 ~ 2033-05），避免误解析
        return ts if 10 ** 9 < ts < 2 * 10 ** 9 else 0

    def _pause(self, seconds, deadline):
        """按剩余预算 sleep：快超时就不再等满间隔。"""
        remain = deadline - time.time()
        if remain > 0:
            time.sleep(min(seconds, remain))

    def collect(self, exclude_urls=None):
        self.cookies()
        pushed = {m.group(1) for u in (exclude_urls or set())
                  for m in [_NOTE_ID_RE.search(str(u))] if m}
        deadline = time.time() + self.time_budget
        cursor, out, seen, stop = "", [], set(), False
        for page in range(max(1, self.max_pages)):
            if time.time() >= deadline:
                break
            items, cursor = self._page(cursor)
            for it in items:
                card = it.get("note_card") or {}
                nid = str(it.get("id") or "")
                if not nid or nid in seen or nid in pushed:
                    continue
                seen.add(nid)
                title = (card.get("display_title") or "").strip()
                author = ((card.get("user") or {}).get("nickname") or "").strip()
                likes = _parse_likes((card.get("interact_info") or {}).get("liked_count"))
                likes_text = str((card.get("interact_info") or {}).get("liked_count") or "")
                if likes < self.min_likes or self._is_dropped(title, author):
                    continue
                collects, ratio = 0, None
                if self.min_collect_ratio > 0:
                    if time.time() >= deadline:
                        stop = True
                        break
                    info = self._detail(nid, it.get("xsec_token") or "")
                    self._pause(self.detail_interval, deadline)
                    if info:
                        detail_likes = _parse_likes(info.get("liked_count"))
                        if detail_likes:
                            likes, likes_text = detail_likes, str(info.get("liked_count"))
                        collects = _parse_likes(info.get("collected_count"))
                        ratio = collects / likes if likes else 0.0
                        if ratio < self.min_collect_ratio:
                            continue
                out.append({
                    "id": nid,
                    "title": title,
                    "url": NOTE_URL.format(note_id=nid, token=it.get("xsec_token") or ""),
                    "author": author,
                    "likes": likes,
                    "likes_text": likes_text,
                    "collects": collects,
                    "collect_ratio": round(ratio, 4) if ratio is not None else None,
                    "kind": card.get("type") or "normal",
                    "pic": self._cover(card),
                    "created": self._created(nid),
                })
                if len(out) >= self.limit:
                    stop = True
                    break
            if stop or not cursor:
                break
            if page + 1 < self.max_pages:
                self._pause(self.interval, deadline)
        return out
