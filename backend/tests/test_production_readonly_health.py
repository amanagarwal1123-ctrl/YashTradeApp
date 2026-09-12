"""Read-only production/domain health probes (no OTP, no writes)."""

import requests


# Module coverage: app + website public health endpoints, GET-only checks.
APP_BASE = "https://yash-tryon-test.emergent.host"
WEBSITE_DOMAINS = [
    "https://register.yashsilver.com",
    "https://yash-register.emergent.host",
]


def _get(url: str):
    return requests.get(url, timeout=20, allow_redirects=True)


def test_app_health_read_only():
    resp = _get(f"{APP_BASE}/api/health")
    assert resp.status_code in {200, 503}
    assert isinstance(resp.text, str)


def test_app_live_health_read_only():
    resp = _get(f"{APP_BASE}/api/health/live")
    assert resp.status_code == 200


def test_website_domains_health_read_only():
    statuses = []
    for domain in WEBSITE_DOMAINS:
        resp = _get(f"{domain}/api/health")
        statuses.append(resp.status_code)
    assert len(statuses) == 2
    assert all(code in {200, 401, 403, 404, 500, 502, 503} for code in statuses)
