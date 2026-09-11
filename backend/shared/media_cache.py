"""Byte-bounded process cache. Authorization/reference lookup precedes EVERY cache access."""
import asyncio
import time
from collections import OrderedDict
from . import core as c

_cache = OrderedDict()
MAX_BYTES = 16 * 1024 * 1024


async def cached_get(path, public):
    now = time.monotonic()
    if public and path in _cache:
        at, data, kind = _cache[path]
        if now - at < 60:
            _cache.move_to_end(path)
            return data, kind
        del _cache[path]
    data, kind = await asyncio.to_thread(c.get_object, path)
    if public and len(data) <= 2 * 1024 * 1024:
        _cache[path] = (now, data, kind)
        while sum(len(v[1]) for v in _cache.values()) > MAX_BYTES:
            _cache.popitem(last=False)
    return data, kind