"""聚合采集器：跑全部数据源并写库。"""
import datetime
import json
import os
import time

from .config import load_config
from .storage import Storage

CUTOFFS_FILE = "cutoffs.json"


def _cutoffs_path(storage_dir):
    return os.path.join(storage_dir, CUTOFFS_FILE)


def _load_cutoffs(storage_dir):
    try:
        with open(_cutoffs_path(storage_dir), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_cutoffs(storage_dir, cutoffs):
    try:
        with open(_cutoffs_path(storage_dir), "w", encoding="utf-8") as f:
            json.dump(cutoffs, f, ensure_ascii=False)
    except Exception:
        pass


def collect_once(config_path=None, netease=True, bilibili=True):
    cfg = load_config(config_path)
    data_dir = cfg.get("data_dir", "data")
    storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), data_dir)
    storage = Storage(storage_dir)

    today = datetime.date.today()
    result = {"push_date": today.isoformat()}

    # Netease
    if netease:
        from .sources.netease import NeteaseCollector, NeteaseError
        try:
            result["netease"] = NeteaseCollector(cfg).collect()
        except NeteaseError as e:
            result["netease"] = {"error": str(e)}

    # Bilibili
    if bilibili:
        from .sources.bilibili import BiliCollector, BiliError
        try:
            result["bilibili"] = BiliCollector(cfg).collect()
        except BiliError as e:
            result["bilibili"] = {"error": str(e)}

    # WeChat official account articles (title + url)
    if wechat_available():
        try:
            from .sources.wechat_article import WeChatArticleCollector
            result["mp"] = WeChatArticleCollector(cfg).collect()
        except Exception as e:
            result["mp"] = {"error": str(e)}
    else:
        result["mp"] = {"error": "当前环境无法获取微信公众号数据（缺少微信解密环境）"}

    # 跨天去重：记录每天最后一次采集时间；次日只推「该时间之后」的新内容
    cutoffs = _load_cutoffs(storage_dir)
    today_str = today.isoformat()
    past = [int(v) for k, v in cutoffs.items() if k < today_str]
    threshold = max(past) if past else 0
    for field, tkey in (("bilibili", "created"), ("mp", "timestamp")):
        val = result.get(field)
        if isinstance(val, list):
            result[field] = [x for x in val if int(x.get(tkey) or 0) > threshold]
    cutoffs[today_str] = int(time.time())
    for k in sorted(cutoffs)[:-3]:
        cutoffs.pop(k, None)
    _save_cutoffs(storage_dir, cutoffs)

    storage.save(today.isoformat(),
                 netease=result.get("netease"),
                 bilibili=result.get("bilibili"),
                 mp=result.get("mp"))
    storage.close()
    return result


collect = collect_once  # alias


def wechat_available():
    try:
        import zstandard  # noqa
    except ImportError:
        return False
    return True