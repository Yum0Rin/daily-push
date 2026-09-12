"""Promote hidden reserve items to fill the shown slots after removals.

Collectors fetch a few extra items per source and mark them ``hidden`` (a reserve
buffer).  When a shown item is later removed (ignore list / comment filter), the
earliest hidden entries are un-hidden so the day keeps a full list.
"""


def promote_reserve(items, target):
    """Un-hide reserve items so up to ``target`` items are shown.

    ``items`` is expected in display order with reserve (hidden) entries after the
    shown ones; the earliest hidden entries are promoted first.  Mutates + returns
    the list.
    """
    if not isinstance(items, list):
        return items
    shown = sum(1 for x in items if isinstance(x, dict) and not x.get("hidden"))
    need = target - shown
    if need <= 0:
        return items
    for x in items:
        if need <= 0:
            break
        if isinstance(x, dict) and x.get("hidden"):
            x.pop("hidden", None)
            need -= 1
    return items
