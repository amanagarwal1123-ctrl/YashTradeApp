"""Byte-bounded process cache. Authorization/reference lookup precedes EVERY cache access."""
import asyncio
import time
from collections import OrderedDict
from . import core as c

_cache = OrderedDict()
MAX_BYTES = 16 * 1024 * 1024


async def cached_get(path, public):
    now = time.monotonic()
    key = (c.scope(), path)  # review bytes and production bytes never share a cache entry
    if public and key in _cache:
        at, data, kind = _cache[key]
        if now - at < 60:
            _cache.move_to_end(key)
            return data, kind
        del _cache[key]
    data, kind = await asyncio.to_thread(c.fetch_object, path)
    if public and len(data) <= 2 * 1024 * 1024:
        _cache[key] = (now, data, kind)
        while sum(len(v[1]) for v in _cache.values()) > MAX_BYTES:
            _cache.popitem(last=False)
    return data, kind