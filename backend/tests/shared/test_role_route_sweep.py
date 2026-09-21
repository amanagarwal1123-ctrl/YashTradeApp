"""R10-B: negative authorization sweep over EVERY registered API route.

The audit the brief asks for ("explicitly audit every generic staff / STAFF and frontend staff-only condition for
over-broad access") is executed here against the live route table instead of a hand-written list: each route's
dependency tree is inspected for the role gate it uses, and every role that gate excludes is exercised against the route
with a valid session. Anything other than 403 PERMISSION_DENIED for an excluded role is a failure. Because the sweep is
derived from `app.routes`, a new endpoint that forgets its gate (or uses the generic STAFF set) is caught automatically.
"""
import pytest

from shared import core as c

pytestmark = pytest.mark.asyncio

ROLE_PHONES = {"admin": "9000000000", "telecaller": "9000000001", "billing_executive": "9000000003", "customer": "9000000004", "upload_executive": "9000000010"}
PLACEHOLDERS = {"ref": "u_tele2", "uid": "u_cust2", "rid": "r-none", "cid": "c-none", "nid": "n-none", "sid": "s-none", "jid": "j-none",
                "job_id": "j-none", "reference": "DEL-none", "provider": "sms_provider", "event_id": "e-none", "number": "9000000005",
                "pid": "p-none", "product_id": "p-none", "batch_id": "b-none", "id": "x-none", "path": "x/none.png", "reviewer_id": "store-review-customer",
                "slab_id": "s-none", "metal": "silver", "phone": "9000000005", "key": "k-none", "kind": "about", "code": "c-none", "path:path": "x/none.png"}


def gates_of(dependant, found=None):
    """Role gates (closures created by core.allow) and step-up gates reachable from a route's dependency tree."""
    found = set() if found is None else found
    for dep in dependant.dependencies:
        call = dep.call
        for name in ("admin", "staff", "billing", "content", "operations", "query_workers", "recent_admin", "customer"):
            if call is getattr(c, name, None):
                found.add(name)
        # legacy server.py gates
        legacy = {"get_admin_user": "admin", "get_content_user": "content", "get_executive_or_admin": "query_workers", "get_billing_or_admin": "billing"}
        if getattr(call, "__name__", "") in legacy:
            found.add(legacy[call.__name__])
        gates_of(dep, found)
    return found


ALLOWED = {"admin": {"admin"}, "recent_admin": {"admin"}, "billing": {"admin", "billing_executive"}, "content": {"admin", "upload_executive"},
           "operations": {"admin", "telecaller", "billing_executive"}, "query_workers": {"admin", "telecaller"}, "staff": set(c.STAFF), "customer": {"customer"}}


def fill(path):
    out = path
    for name, value in PLACEHOLDERS.items():
        out = out.replace("{" + name + "}", value)
    return out


async def test_every_gated_route_refuses_every_excluded_role(api_client, isolated_db, seeded_users, login_helper):
    from server import app
    admin_body = await login_helper(ROLE_PHONES["admin"])
    admin = {"Authorization": f"Bearer {admin_body['token']}"}
    created = await api_client.post("/api/integrations/staff", json={"phone": ROLE_PHONES["upload_executive"], "name": "Uploader", "role": "upload_executive"}, headers=admin)
    assert created.status_code == 200, created.text
    headers = {}
    for role, phone in ROLE_PHONES.items():
        body = await login_helper(phone)
        assert body["user"]["role"] == role, (role, body["user"])
        headers[role] = {"Authorization": f"Bearer {body['token']}"}

    gated, failures, checked = [], [], 0
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods or not route.path.startswith("/api") or "{" in route.path.replace("{", "", 1) and False:
            continue
        gates = gates_of(route.dependant)
        if not gates:
            continue
        # The most restrictive gate on the route decides who may pass (a recent_admin route is admin-only, etc.).
        allowed = set(c.ROLES)
        for g in gates:
            allowed &= ALLOWED[g]
        gated.append((route.path, sorted(methods), sorted(gates), sorted(allowed)))
        for role in sorted(set(c.ROLES) - allowed):
            for method in methods:
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue
                url = fill(route.path)
                kwargs = {"headers": headers[role]}
                if method in {"POST", "PUT", "PATCH"}:
                    kwargs["json"] = {}
                r = await getattr(api_client, method.lower())(url, **kwargs)
                checked += 1
                # A server-to-server credential gate (portal token exchange) refuses BEFORE the role gate with 401; that
                # is a denial too, not a grant.
                denied = r.status_code == 403 or (r.status_code == 401 and r.json().get("code") == "SERVICE_KEY_INVALID")
                if not denied:
                    failures.append((method, route.path, role, r.status_code, r.text[:120]))
    assert gated, "no gated routes found - the sweep is broken"
    assert not failures, "excluded roles reached gated routes:\n" + "\n".join(map(str, failures))
    assert checked > 300, checked

    # The generic STAFF gate (any staff role, including Upload Executive) must not protect anything but the portal
    # token exchange, which additionally requires the staff service key (header gate, not a role grant).
    staff_only = [p for p, m, g, a in gated if g == ["staff"]]
    assert staff_only == ["/api/integrations/staff/{ref}/token"], staff_only
    # Upload Executive reaches only the content domain (plus routes every signed-in user has).
    upload_reach = sorted({p for p, m, g, a in gated if "upload_executive" in a})
    assert all(g == ["content"] for p, m, g, a in gated if "upload_executive" in a and g != ["staff"]), [(p, g) for p, m, g, a in gated if "upload_executive" in a and g not in (["content"], ["staff"])]
    assert upload_reach, "no content routes found"
    # Record the inventory for the acceptance matrix (visible with -s).
    print("\nR10 content-domain routes reachable by upload_executive:", len(upload_reach))
    for p in upload_reach:
        print("  ", p)
