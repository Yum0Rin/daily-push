"""抖音「推荐流」采集（PC 端 tab/feed，等同网页「推荐」页）。

接口 ``GET /aweme/v1/web/tab/feed/`` —— 实测**不需要 a_bogus 签名**，
只要带上本机已登录的 Cookie（含 httpOnly 的 ``sessionid``）就能拿到 ``aweme_list``。
（对比：小红书必须用 xhshow 生成 ``x-s/x-t/x-s-common``。）

登录态来源（按顺序）：
1. ``config.json`` 的 ``douyin.cookie``（整段 Cookie 串）；
2. 本机 Firefox 配置目录里已登录的抖音 Cookie（只读打开 cookies.sqlite，不复制不外传）。

口径（2026-10-27 由用户定）：
- ``statistics.digg_count >= min_digg``（默认 2 万）；
- ``statistics.collect_count / digg_count >= min_collect_ratio``（默认 0.08，``0`` = 关闭）；
- **标签屏蔽**：``video_tag[].tag_name`` 或话题 ``text_extra[].hashtag_name``
  命中 ``blocked_tags``（默认 游戏 / 娱 / 热点 / vibe / 英语 / 抽象 / 推荐 /
  唠嗑 / 零基础 / 抖音 / 华语乐坛 / 讲解 / 作文 / AI）即丢弃；
  标签/话题匹配忽略大小写（`AI` 会连带命中 #aigc / #aivideo）；标题匹配对纯英文词**区分大小写**，
  所以 `AI` 只命中大写的「AI」，不会误伤 again / said 这类单词。
- **AI 内容**：接口不下发 AIGC 标记（实测 ``aigc_info`` / ``is_aigc`` / ``AI生成`` 都不存在，
  仅 ``music.extra.aigc_clip`` 这个与成片无关的音乐片段字段），只能按文案+话题关键词启发式
  过滤（``ai_keywords``），会漏判——抖音官方「内容由AI生成」标签不在推荐流响应里；
- 广告 / 生活服务（``is_ads`` / ``is_life_item``）直接丢弃；
- 最多返回 ``limit`` 条（默认 6）。

注意：推荐流的 ``statistics.play_count`` **恒为 0**（网页端不下发播放量），
所以做不了 B站那种「点赞/播放」比例，只能用「藏/赞比」。
封面 URL 带 ``x-expires`` 签名会过期（约 30 天），历史页的图会失效。
"""
import glob
import os
import re
import sqlite3
import time

import requests

API_HOST = "https://www.douyin.com"
FEED_URI = "/aweme/v1/web/tab/feed/"
VIDEO_URL = "https://www.douyin.com/video/{aweme_id}"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) "
       "Gecko/20100101 Firefox/158.0")

# 接口必需的公共参数（缺了会被网关回 404 Unsupported path(Janus)）
_BASE_QUERY = (
    "device_platform=webapp&aid=6383&channel=channel_pc_web&pc_client_type=1"
    "&version_code=170400&version_name=17.4.0&cookie_enabled=true&platform=PC"
    "&browser_language=zh-CN&browser_platform=Win32&browser_name=Firefox"
    "&browser_version=158.0&engine_name=Gecko&os_name=Windows&os_version=10"
)

# 默认屏蔽标签词：命中 video_tag 或话题名即丢弃（子串、忽略大小写）
DEFAULT_BLOCKED_TAGS = ["游戏", "娱", "热点", "vibe", "英语", "抽象",
                        "推荐", "唠嗑", "零基础", "抖音", "华语乐坛",
                        "讲解", "作文", "AI"]

# AI 内容启发式关键词（接口无 AIGC 标记，只能查文案/话题）
DEFAULT_AI_KEYWORDS = [
    "ai生成", "aigc", "ai绘画", "ai视频", "ai动画", "ai配音", "ai换脸",
    "ai数字人", "ai创作", "ai作画", "由ai生成",
]

_AWEME_ID_RE = re.compile(r"/video/(\d{8,})")


def _lower(value, default):
    """取配置里的词表；``None``/缺省 → 用默认表；``[]`` → 关闭该项。"""
    raw = default if value is None else value
    return [str(k) for k in raw if str(k).strip()]


def _blocked_hit(words, tags, title):
    """屏蔽词判定：标签/话题**忽略大小写**；标题里对纯英文词**区分大小写**
    （``AI`` 能命中「AI绘画」，但不会误伤 again / said 这种词）。"""
    lowered = [t.lower() for t in tags]
    if any(w.lower() in t for w in words for t in lowered):
        return True
    for w in words:
        if w.isascii():
            if w in title:          # 保留大小写
                return True
        elif w in title:
            return True
    return False


def is_blocked_entry(entry, blocked_tags=None, ai_keywords=None, exclude_keywords=None):
    """按「标签屏蔽 / AI 关键词 / 屏蔽词」判断一条**已入库的成品条目**是否该丢。

    采集时（``DouyinCollector._dropped``）和「保存并应用屏蔽名单」清理历史
    （``tools/purge_ignored.py``）共用同一套规则，避免两边口径漂移。
    """
    tags = [str(t) for t in (entry.get("tags") or []) if str(t).strip()]
    title = str(entry.get("title") or "")
    author = str(entry.get("author") or "")
    blocked = _lower(blocked_tags, DEFAULT_BLOCKED_TAGS)
    ai = [w.lower() for w in _lower(ai_keywords, DEFAULT_AI_KEYWORDS)]
    exclude = [str(k) for k in (exclude_keywords or []) if str(k).strip()]
    if _blocked_hit(blocked, tags, title):
        return True
    text = f"{title} {author} {' '.join(tags)}".lower()
    if any(k in text for k in ai):
        return True
    plain = f"{title} {author}"
    return any(k in plain for k in exclude)


class DouyinError(Exception):
    pass


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
    """从本机 Firefox 配置里读抖音 Cookie（只读，不复制文件）。

    返回第一个含未过期 ``sessionid`` / ``sessionid_ss`` 的配置里的 Cookie；没有则 {}。
    """
    base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
    now = time.time()
    for db in glob.glob(os.path.join(base, "*", "cookies.sqlite")):
        uri = "file:" + db.replace("\\", "/") + "?mode=ro&immutable=1"
        try:
            con = sqlite3.connect(uri, uri=True, timeout=3)
            rows = con.execute(
                "SELECT name, value, expiry FROM moz_cookies WHERE host LIKE ?",
                ("%douyin%",)).fetchall()
            con.close()
        except sqlite3.Error:
            continue
        jar = {n: v for n, v, exp in rows if exp == 0 or exp > now}
        if jar.get("sessionid") or jar.get("sessionid_ss"):
            return jar
    return {}


def _feed_url(refresh_index):
    return f"{API_HOST}{FEED_URI}?{_BASE_QUERY}&count=20&refresh_index={int(refresh_index)}"


def probe_login(cookie_str):
    """用给定 Cookie 打一次推荐流，验证登录态是否可用。返回 ``(ok, detail)``。

    设置页「检测/保存并验证」与邮件 cookie-repair 共用，保证两边判定一致。
    """
    text = str(cookie_str or "").strip()
    jar = _parse_cookie_string(text) if "=" in text else {}
    if not (jar.get("sessionid") or jar.get("sessionid_ss")):
        return False, "Cookie 里没有 sessionid（请粘贴抖音浏览器里的整段 Cookie）"
    try:
        r = requests.get(_feed_url(1), cookies=jar, timeout=20,
                         headers={"User-Agent": _UA,
                                  "Referer": "https://www.douyin.com/?recommend=1",
                                  "Accept": "application/json"})
    except Exception as e:
        return False, f"抖音验证请求失败：{e}"
    if r.status_code != 200:
        return False, f"抖音验证失败（HTTP {r.status_code}）"
    try:
        data = r.json()
    except ValueError:
        return False, "抖音返回非 JSON（登录态可能失效或被风控）"
    if data.get("status_code") != 0:
        return False, f"抖音验证失败（status_code={data.get('status_code')}）"
    n = len(data.get("aweme_list") or [])
    if not n:
        return False, "抖音登录态无效：推荐流返回 0 条"
    return True, f"抖音登录正常（推荐流返回 {n} 条）"


class DouyinCollector:
    def __init__(self, cfg):
        c = cfg.get("douyin") or {}
        self.cookie_str = str(c.get("cookie") or "").strip()

        def num(key, default, cast=float):
            """``0`` 是合法值（如关掉间隔/关闭藏赞比），不能用 ``or`` 兜底。"""
            raw = c.get(key)
            return default if raw is None else cast(raw)

        self.limit = num("limit", 6, int)
        self.min_digg = num("min_digg", 20000, int)
        self.min_collect_ratio = num("min_collect_ratio", 0.08)
        self.max_pages = num("max_pages", 6, int)
        self.interval = num("request_interval", 1.5)
        self.time_budget = num("time_budget", 30)
        self.blocked_tags = _lower(c.get("blocked_tags"), DEFAULT_BLOCKED_TAGS)
        self.ai_keywords = _lower(c.get("ai_keywords"), DEFAULT_AI_KEYWORDS)
        self.exclude = [str(k) for k in (c.get("exclude_keywords") or []) if str(k).strip()]
        self._cookies = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _UA,
            "Referer": "https://www.douyin.com/?recommend=1",
            "Accept": "application/json",
        })

    # ---- auth ----
    def cookies(self):
        if self._cookies is not None:
            return self._cookies
        if self.cookie_str:
            jar = _parse_cookie_string(self.cookie_str)
            if not (jar.get("sessionid") or jar.get("sessionid_ss")):
                raise DouyinError("抖音 Cookie 缺少 sessionid，请粘贴浏览器里的整段 Cookie")
        else:
            jar = _cookies_from_firefox()
        if not jar or not (jar.get("sessionid") or jar.get("sessionid_ss")):
            raise DouyinError(
                "抖音登录态缺失：config.json 的 douyin.cookie 未配置，"
                "且本机 Firefox 里没有已登录的抖音 Cookie")
        self._cookies = jar
        return jar

    # ---- request ----
    def _page(self, refresh_index):
        last = None
        for attempt in (1, 2):
            try:
                r = self.session.get(_feed_url(refresh_index), cookies=self.cookies(),
                                     timeout=20)
            except Exception as e:
                last = DouyinError(f"请求失败：{e}")
                time.sleep(3 * attempt)
                continue
            if r.status_code != 200:
                last = DouyinError(f"HTTP {r.status_code}")
                time.sleep(3 * attempt)
                continue
            try:
                data = r.json()
            except ValueError:
                last = DouyinError("返回非 JSON（可能被风控）")
                time.sleep(3 * attempt)
                continue
            if data.get("status_code") != 0:
                raise DouyinError(f"接口返回 status_code={data.get('status_code')}")
            return data.get("aweme_list") or []
        raise last or DouyinError("请求失败")

    # ---- helpers ----
    @staticmethod
    def _cover(item):
        """封面：video.cover → origin_cover → 图文 images[0]。统一 https。"""
        video = item.get("video") or {}
        for key in ("cover", "origin_cover", "dynamic_cover"):
            node = video.get(key) or {}
            for url in node.get("url_list") or []:
                if url:
                    return url.replace("http://", "https://", 1)
        for img in item.get("images") or []:
            for url in img.get("url_list") or []:
                if url:
                    return url.replace("http://", "https://", 1)
        return ""

    @staticmethod
    def _tags(item):
        """标签名 + 话题名（用于屏蔽词与 AI 词匹配）。"""
        tags = [str(t.get("tag_name") or "") for t in (item.get("video_tag") or [])]
        tags += [str(h.get("hashtag_name") or "") for h in (item.get("text_extra") or [])]
        return [t for t in tags if t]

    @staticmethod
    def _title(item):
        text = str(item.get("item_title") or item.get("desc") or "").strip()
        if not text:
            text = str(item.get("desc") or "").strip()
        return re.sub(r"\s+", " ", text)

    def _dropped(self, item):
        """True = 该条按口径丢弃（标签屏蔽 / AI / 屏蔽词）。"""
        return is_blocked_entry(
            {"title": self._title(item),
             "author": str(((item.get("author") or {}).get("nickname")) or ""),
             "tags": self._tags(item)},
            self.blocked_tags, self.ai_keywords, self.exclude)

    def _pause(self, deadline):
        remain = deadline - time.time()
        if remain > 0:
            time.sleep(min(self.interval, remain))

    def collect(self, exclude_urls=None):
        self.cookies()
        pushed = {m.group(1) for u in (exclude_urls or set())
                  for m in [_AWEME_ID_RE.search(str(u))] if m}
        deadline = time.time() + self.time_budget
        out, seen = [], set()
        for page in range(1, max(1, self.max_pages) + 1):
            if time.time() >= deadline:
                break
            for item in self._page(page):
                aid = str(item.get("aweme_id") or "")
                if not aid or aid in seen or aid in pushed:
                    continue
                seen.add(aid)
                if item.get("is_ads") or item.get("is_life_item"):
                    continue
                if self._dropped(item):
                    continue
                stat = item.get("statistics") or {}
                digg = int(stat.get("digg_count") or 0)
                if digg < self.min_digg:
                    continue
                collects = int(stat.get("collect_count") or 0)
                ratio = collects / digg if digg else 0.0
                if self.min_collect_ratio > 0 and ratio < self.min_collect_ratio:
                    continue
                author = item.get("author") or {}
                out.append({
                    "id": aid,
                    "title": self._title(item) or "（无文案）",
                    "url": VIDEO_URL.format(aweme_id=aid),
                    "author": str(author.get("nickname") or ""),
                    "sec_uid": str(author.get("sec_uid") or ""),
                    "digg": digg,
                    "collect": collects,
                    "comment": int(stat.get("comment_count") or 0),
                    "share": int(stat.get("share_count") or 0),
                    "collect_ratio": round(ratio, 4),
                    "duration": int(((item.get("video") or {}).get("duration") or 0) // 1000),
                    "created": int(item.get("create_time") or 0),
                    "pic": self._cover(item),
                    "tags": self._tags(item)[:6],
                })
                if len(out) >= self.limit:
                    return out
            if page < self.max_pages:
                if time.time() >= deadline:
                    break
                self._pause(deadline)
        return out
