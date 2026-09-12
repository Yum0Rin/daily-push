"""Apply the netease comment/favorite rule to already-collected history.

New collections store ``comment_count`` / ``favorite_count``; older entries don't,
so a ``stats_lookup`` (usually hitting the local NeteaseCloudMusicApi) fills the
gap on demand — throttled by ``interval`` to stay gentle on the API.
"""
import time


def apply_history(storage, max_comments, max_favorites=0, stats_lookup=None,
                  interval=0.3, shown_target=0):
    """Backfill counts on history, then drop songs over the comment/favorite limits.

    ``stats_lookup(song_id) -> (comment_count | None, favorite_count | None)`` is
    only called for entries missing a count.  A limit of 0/None means "no limit".
    ``shown_target`` un-hides reserve entries to refill after removals.
    Returns ``{"backfilled": int, "removed": [(date, name)]}``.
    """
    from .backfill import promote_reserve

    removed = []
    backfilled = 0
    for d in storage.list_dates():
        row = storage.get(d)
        if not row or not isinstance(row.get("netease"), list):
            continue
        kept = []
        changed = False
        for s in row["netease"]:
            if not isinstance(s, dict):
                kept.append(s)
                continue
            cc = s.get("comment_count")
            fc = s.get("favorite_count")
            if (cc is None or fc is None) and stats_lookup is not None:
                try:
                    nc, nf = stats_lookup(s.get("id"))
                except Exception:
                    nc, nf = None, None
                added = False
                if nc is not None and cc is None:
                    s["comment_count"] = cc = nc
                    added = True
                if nf is not None and fc is None:
                    s["favorite_count"] = fc = nf
                    added = True
                if added:
                    backfilled += 1
                    changed = True
                if interval:
                    time.sleep(interval)
            over_comments = max_comments and cc is not None and int(cc) > max_comments
            over_favorites = max_favorites and fc is not None and int(fc) > max_favorites
            if over_comments or over_favorites:
                removed.append((d, s.get("name", "")))
                changed = True
            else:
                kept.append(s)
        if changed:
            promote_reserve(kept, shown_target)
            storage.save(d, netease=kept or None,
                         bilibili=row.get("bilibili"),
                         mp=row.get("mp"), overwrite=True)
    return {"backfilled": backfilled, "removed": removed}
