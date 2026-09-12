"""Fixed icon-font fallback asset: exact bytes, version-matched with the frontend manifest, no auth."""
import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio
FRONTEND_MANIFEST = json.loads(Path("/app/frontend/src/fonts/ionicons.manifest.json").read_text())


async def test_ionicons_fallback_serves_exact_version_matched_font_without_auth(api_client):
    res = await api_client.get("/api/fonts/ionicons.ttf")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("font/ttf")
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert res.headers["x-content-type-options"] == "nosniff"
    body = res.content
    assert len(body) == FRONTEND_MANIFEST["bytes"] == 389724
    assert hashlib.sha256(body).hexdigest() == FRONTEND_MANIFEST["sha256"] == res.headers["x-font-sha256"]
    assert hashlib.md5(body).hexdigest() == FRONTEND_MANIFEST["md5"] == "b4eb097d35f44ed943676fd56f6bdc51"
    assert body[:4] == b"\x00\x01\x00\x00"  # TrueType sfnt header, never HTML
    head = await api_client.head("/api/fonts/ionicons.ttf")
    assert head.status_code == 200 and head.headers["content-length"] == str(FRONTEND_MANIFEST["bytes"])
    manifest = await api_client.get("/api/fonts/ionicons.manifest.json")
    assert manifest.status_code == 200 and manifest.json()["sha256"] == FRONTEND_MANIFEST["sha256"]
    assert manifest.json()["source_version"] == FRONTEND_MANIFEST["source_version"]


async def test_font_route_is_fixed_and_not_a_file_proxy(api_client):
    for path in ("/api/fonts/MaterialIcons.ttf", "/api/fonts/../static/fonts/Ionicons.ttf", "/api/fonts/ionicons.ttf/extra", "/api/fonts/"):
        res = await api_client.get(path)
        assert res.status_code in (404, 405, 307), path
    licence = Path("/app/backend/static/fonts/LICENSE.ionicons.txt").read_text()
    assert "MIT" in licence and "Ionic" in licence
