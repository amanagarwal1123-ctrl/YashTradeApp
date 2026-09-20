"""Byte-bounded process cache for PUBLIC media bytes and their display variants. Authorization/reference lookup
precedes EVERY cache access; private media is never cached here."""
import asyncio
import hashlib
import io
import time
from collections import OrderedDict

from PIL import Image, ImageOps

from . import core as c

_cache = OrderedDict()
MAX_BYTES = 16 * 1024 * 1024
TTL_SECONDS = 60
# Display widths the app may request (`?w=`): 400 for two-column feed / wishlist / cart cards, 800 for the full-width
# Home card on high-density phones. A bounded set keeps cache keys and CPU work bounded; masters are never rewritten.
VARIANT_WIDTHS = (400, 800)
VARIANT_QUALITY = 78


def etag_of(data):
    return '"' + hashlib.sha256(data).hexdigest()[:32] + '"'


def resize(data, kind, width):
    """JPEG display variant no wider than `width` (aspect preserved, EXIF orientation applied). Images that are already
    small enough, and non-image objects, are returned unchanged."""
    if not str(kind).startswith("image/") or kind == "image/gif":
        return data, kind
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width <= width:
                return data, kind
            if im.format == "JPEG":
                im.draft("RGB", (width * 2, width * 2))  # decode at reduced DCT scale: far cheaper than a full decode
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((width, width * 3), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, "JPEG", quality=VARIANT_QUALITY, optimize=True, progressive=True)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return data, kind


def _hit(key):
    entry = _cache.get(key)
    if entry and time.monotonic() - entry[0] < TTL_SECONDS:
        _cache.move_to_end(key)
        return entry[1], entry[2]
    if entry:
        del _cache[key]
    return None


def _store(key, data, kind):
    if len(data) > 2 * 1024 * 1024:
        return
    _cache[key] = (time.monotonic(), data, kind)
    while sum(len(v[1]) for v in _cache.values()) > MAX_BYTES:
        _cache.popitem(last=False)


async def cached_get(path, public, width=None):
    scope = c.scope()  # review bytes and production bytes never share a cache entry
    key = (scope, path, width)
    if public and (found := _hit(key)):
        return found
    if width is None:
        data, kind = await asyncio.to_thread(c.fetch_object, path)
    else:
        master, master_kind = await cached_get(path, public)
        data, kind = await asyncio.to_thread(resize, master, master_kind, width)
    if public:
        _store(key, data, kind)
    return data, kind