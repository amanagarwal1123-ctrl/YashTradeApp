"""Store-review storage = `review__*` collections of the SAME database (application-enforced isolation).

Proves, against a dedicated `mongod --auth` instance whose application user may readWrite ONLY the main database
(production's real permission model), that the store-review environment initialises and serves reviewer sign-in
WITHOUT any second database or extra rights; and, in-process, that every cross-scope path (aggregation lookups,
reset, collection resolution) stays inside the prefixed collections. Nothing here touches preview or production."""
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

sys.path.insert(0, "/app/backend")
from shared import core as c  # noqa: E402
from shared import review_seed  # noqa: E402

BACKEND = Path("/app/backend")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def auth_mongod(tmp_path_factory):
    """A throw-away MongoDB with --auth: `appuser` may readWrite ONLY the main test database (real permissions)."""
    if not shutil.which("mongod"):
        pytest.skip("mongod binary unavailable; restricted-permission case cannot be exercised directly")
    port = _free_port()
    dbpath = tmp_path_factory.mktemp("mongo-auth")
    logpath = dbpath / "mongod.log"
    proc = subprocess.run(["mongod", "--auth", "--port", str(port), "--dbpath", str(dbpath), "--bind_ip", "127.0.0.1",
                           "--fork", "--logpath", str(logpath)], capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(f"could not start an auth-enabled mongod for the restricted-permission case ({proc.returncode})")
    main_db = f"prefixed_main_{uuid.uuid4().hex[:6]}"
    root_uri = None
    try:
        MongoClient(f"mongodb://127.0.0.1:{port}/", serverSelectionTimeoutMS=10000).admin.command(
            "createUser", "root", pwd="root-test-pw", roles=[{"role": "root", "db": "admin"}])
        root_uri = f"mongodb://root:root-test-pw@127.0.0.1:{port}/admin"
        MongoClient(root_uri, serverSelectionTimeoutMS=10000).admin.command(
            "createUser", "appuser", pwd="app-test-pw", roles=[{"role": "readWrite", "db": main_db}])
        yield {"port": port, "app_uri": f"mongodb://appuser:app-test-pw@127.0.0.1:{port}/admin", "root_uri": root_uri, "main": main_db}
    finally:
        if root_uri:
            try:
                MongoClient(root_uri, serverSelectionTimeoutMS=5000).admin.command("shutdown")
            except PyMongoError:
                pass
        time.sleep(1)


@pytest.fixture
def backend_process(auth_mongod):
    """The REAL backend process (uvicorn startup path) bound to the restricted user with review access ON."""
    port = _free_port()
    env = {**os.environ, "MONGO_URL": auth_mongod["app_uri"], "DB_NAME": auth_mongod["main"], "REVIEW_ACCESS_ENABLED": "true",
           "JWT_SECRET": "prefixed-jwt-secret-1234567890-abcdefghij", "STAFF_SERVICE_KEY": "prefixed-staff-key-1234567890-abcdefghij",
           "ENROLLMENT_INTEGRATION_KEY": "prefixed-enrol-key-1234567890-abcdefghij", "MSG91_AUTHKEY": "test-authkey",
           "MSG91_TEMPLATE_ID": "test-template", "OWNER_ADMIN_PHONE": "9000000000"}
    env.pop("REVIEW_DB_NAME", None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/api"
    try:
        for _ in range(80):
            try:
                if httpx.get(f"{base}/health/live", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert proc.poll() is None, "backend process exited during startup"
            time.sleep(0.5)
        else:
            pytest.fail("backend did not become live")
        yield {"base": base, "env": env}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_restricted_user_serves_reviewer_sign_in_from_prefixed_collections_without_a_second_database(auth_mongod, backend_process):
    base, env = backend_process["base"], backend_process["env"]
    health = httpx.get(f"{base}/health", timeout=10).json()
    review = health["flows"]["review"]
    assert review["ready"] is True and review["usable"] is True and review["enabled"] is True
    assert review["storage"] == "prefixed_collections" and review["isolation"] == "application_enforced" and review["accounts_enabled"] == 0
    assert health["configuration"]["REVIEW_ACCESS_ENABLED"] is True and health["configuration"]["REVIEW_STORAGE_USABLE"] is True
    # No account yet -> sign-in is refused as invalid credentials (not 503): the environment exists but is empty.
    empty = httpx.post(f"{base}/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": "x" * 43}, timeout=10)
    assert empty.status_code == 401 and empty.json()["code"] == "REVIEW_CREDENTIALS_INVALID"
    # The owner CLI provisions with the SAME restricted credentials (no second database, no extra rights) and
    # verifies every role end-to-end against the running backend: sign-in, role, sign-out, reuse rejected, repeat sign-in.
    note = Path("/tmp") / f"yash-prefixed-{uuid.uuid4().hex[:8]}" / "note.txt"
    try:
        proc = subprocess.run([sys.executable, str(BACKEND / "tools/provision_review_access.py"), "--expected-db", auth_mongod["main"],
                               "--provision", "--seed", "--status", "--environment", "preview", "--api-base-url", base, "--verify",
                               "--write-note", str(note)], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, proc.stderr[-500:]
        import json
        out = json.loads(proc.stdout)
        assert out["outcome"] == "ok" and out["all_accounts_verified"] is True and out["storage"] == "prefixed_collections"
        assert all(r["repeat_login"] is True and r["session_closed"] is True for r in out["verification"].values())
    finally:
        if note.exists():
            note.unlink()
            note.parent.rmdir()
    assert httpx.get(f"{base}/health", timeout=10).json()["flows"]["review"]["accounts_enabled"] == 6
    # Physical layout: ONLY the main database exists; every review collection is prefixed; unprefixed ones hold no review rows.
    root = MongoClient(auth_mongod["root_uri"])
    assert not any(n.startswith("prefixed_") and n != auth_mongod["main"] for n in root.list_database_names())
    names = root[auth_mongod["main"]].list_collection_names()
    review_names = {n for n in names if n.startswith(c.REVIEW_PREFIX)}
    assert {"review__users", "review__review_accounts", "review__products", "review__review_blobs", "review__review_access_log"} <= review_names
    main = root[auth_mongod["main"]]
    assert main.review_accounts.count_documents({}) == 0 and main.users.count_documents({"review_environment": True}) == 0
    assert main.products.count_documents({}) == 0 and main["review__products"].count_documents({}) == 12
    assert main["review__review_accounts"].count_documents({}) == 6
    assert all(row["secret_hash"].startswith("$2b$") for row in main["review__review_accounts"].find({}))
    # The owner record created by the bootstrap lives ONLY in the unprefixed users collection.
    assert main.users.count_documents({"phone_normalized": "9000000000", "role": "admin"}) == 1
    assert main["review__users"].count_documents({"phone_normalized": "9000000000"}) == 0


pytestmark_async = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_prefixed_view_resolves_only_review_collections_and_reset_never_touches_unprefixed_data(api_client, review_env, seeded_users):
    prod, view = review_env["primary"], review_env["db"]
    assert view.users.name == "review__users" and view["products"].name == "review__products" and view.name == prod.name
    with pytest.raises(AttributeError):
        view._database_handle  # private names are never proxied
    assert c.collection_name("users") == "users"
    with c.scoped(c.REVIEW):
        assert c.collection_name("users") == "review__users"
        await review_seed.seed_dataset()
        keys = await review_seed.provision_accounts()
    assert sorted(await view.list_collection_names()) and all(not n.startswith(c.REVIEW_PREFIX) for n in await view.list_collection_names())
    # A genuine production row in every collection the reset would clear; none of them may change.
    marker = {"id": "prod-marker", "note": "genuine"}
    for name in review_seed.DATA_COLLECTIONS:
        await prod[name].insert_one(dict(marker))
    with c.scoped(c.REVIEW):
        summary = await review_seed.seed_dataset(reset=True)
    assert summary["products"] == 12
    for name in review_seed.DATA_COLLECTIONS:
        assert await prod[name].count_documents({"id": "prod-marker"}) == 1, name
        await prod[name].delete_many({"id": "prod-marker"})
    # Aggregation $lookup (queries enrichment) joins review requests with review__users, never production users.
    await prod.users.insert_one({"id": "review-customer-0001", "phone": "9333333333", "phone_normalized": "9333333333", "name": "GENUINE PERSON",
                                 "role": "customer", "account_status": "active", "status": "active", "session_version": 0})
    admin = (await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": keys["store-review-admin"]})).json()
    listing = await api_client.get("/api/requests?status=all&limit=50", headers={"Authorization": f"Bearer {admin['token']}"})
    assert listing.status_code == 200, listing.text
    rows = listing.json()["requests"]
    assert rows and all("GENUINE PERSON" not in (r.get("customer_name") or "") for r in rows)
    assert any("synthetic" in (r.get("customer_name") or "") for r in rows)
    # Reviewer uploads persist in review__review_blobs (same database), never in production object storage.
    assert await prod["review__review_blobs"].count_documents({}) >= 12 and review_env["object_store"] == {}
