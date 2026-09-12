"""Fixed icon-font fallback asset for devices whose Expo Go update cache holds a corrupt copy.

Serves ONLY the exact, version-matched Ionicons.ttf bundled by @expo/vector-icons (MIT licence
retained beside the file). It is a last-resort source: the client validates status, byte length
and SHA-256 before loading and normal startup never depends on this route, authentication,
MongoDB readiness or SMS configuration.
"""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["Static fallback assets"])
FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
FONT_FILE = FONT_DIR / "Ionicons.ttf"
MANIFEST = json.loads((FONT_DIR / "ionicons.manifest.json").read_text())
FONT_SHA256 = hashlib.sha256(FONT_FILE.read_bytes()).hexdigest() if FONT_FILE.exists() else ""
FONT_BYTES = FONT_FILE.stat().st_size if FONT_FILE.exists() else 0
if FONT_SHA256 != MANIFEST["sha256"] or FONT_BYTES != MANIFEST["bytes"]:
    raise RuntimeError("static/fonts/Ionicons.ttf does not match ionicons.manifest.json; refusing to serve a mismatched font")
HEADERS = {"Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{FONT_SHA256}"',
           "X-Content-Type-Options": "nosniff", "X-Font-Sha256": FONT_SHA256, "Access-Control-Allow-Origin": "*"}


@router.get("/fonts/ionicons.ttf")
async def ionicons_font():
    return FileResponse(FONT_FILE, media_type="font/ttf", headers=HEADERS, filename="Ionicons.ttf",
                        content_disposition_type="inline")


@router.head("/fonts/ionicons.ttf", include_in_schema=False)
async def ionicons_font_head():
    return await ionicons_font()


@router.get("/fonts/ionicons.manifest.json")
async def ionicons_manifest():
    return {**MANIFEST, "path": "/api/fonts/ionicons.ttf"}
