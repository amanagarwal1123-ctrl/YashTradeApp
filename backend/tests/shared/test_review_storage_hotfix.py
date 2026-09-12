"""Hotfix regression: optional store-review storage must never crash startup or reach production data.

Production's MongoDB user is authorised for the main database ONLY. Cases:
  1. placeholder REVIEW_DB_NAME -> no review access, normal startup (also covered in test_placeholder_configuration.py);
  2. configured review database that REJECTS index creation with a genuine MongoDB authorisation error (code 13):
     normal startup, reviewer access unavailable with reason, existing reviewer sessions fail closed without touching
     the main database, background workers never poll that database again;
  3. authorised SEPARATE review database: initialisation and isolation still work;
  4. main-database failure stays a genuine startup failure (not hidden by the optional-feature handler);
  5. review database == main database stays prohibited.

Case 2 is exercised DIRECTLY against a dedicated `mongod --auth` instance started by this module with a user holding
readWrite on the main test database only (not injected), and additionally with an injected OperationFailure in-process
for worker-loop assertions. Nothing here touches the preview or production databases."""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from shared import core as c  # noqa: E402

BACKEND = Path("/app/backend")
pytestmark = pytest.mark.asyncio


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
    main_db, review_db = f"hotfix_main_{uuid.uuid4().hex[:6]}", f"hotfix_review_{uuid.uuid4().hex[:6]}"
    root_uri = None
    try:
        MongoClient(f"mongodb://127.0.0.1:{port}/", serverSelectionTimeoutMS=10000).admin.command(
            "createUser", "root", pwd="root-test-pw", roles=[{"role": "root", "db": "admin"}])  # localhost exception
        root_uri = f"mongodb://root:root-test-pw@127.0.0.1:{port}/admin"
        MongoClient(root_uri, serverSelectionTimeoutMS=10000).admin.command(
            "createUser", "appuser", pwd="app-test-pw", roles=[{"role": "readWrite", "db": main_db}])
        yield {"port": port, "app_uri": f"mongodb://appuser:app-test-pw@127.0.0.1:{port}/admin", "root_uri": root_uri,
               "main": main_db, "review": review_db, "log": logpath}
    finally:
        if root_uri:
            try:
                MongoClient(root_uri, serverSelectionTimeoutMS=5000).admin.command("shutdown")
            except PyMongoError:
                pass
        time.sleep(1)


def _unauthorized_log_lines(logpath, dbname):
    text = Path(logpath).read_text(encoding="utf-8", errors="replace")
    return [line for line in text.splitlines() if "Unauthorized" in line and f"not authorized on {dbname}" in line]


def test_restricted_user_review_database_cannot_be_initialised_directly(auth_mongod):
    """Baseline for the real permission model: ping is allowed, createIndexes on the review database is code 13."""
    client = MongoClient(auth_mongod["app_uri"], serverSelectionTimeoutMS=10000)
    client[auth_mongod["main"]].users.create_index("phone_normalized", unique=True, sparse=True)
    client[auth_mongod["review"]].command("ping")  # ping does not prove usability
    with pytest.raises(OperationFailure) as exc:
        client[auth_mongod["review"]].users.create_index("phone_normalized", unique=True, sparse=True)
    assert exc.value.code == 13
    names = MongoClient(auth_mongod["root_uri"]).list_database_names()
    assert auth_mongod["main"] in names and auth_mongod["review"] not in names


@pytest.fixture
def backend_process(auth_mongod):
    """The REAL backend process (uvicorn startup path) bound to the restricted user, with a configured review DB."""
    port = _free_port()
    env = {**os.environ, "MONGO_URL": auth_mongod["app_uri"], "DB_NAME": auth_mongod["main"], "REVIEW_DB_NAME": auth_mongod["review"],
           "JWT_SECRET": "hotfix-jwt-secret-1234567890-abcdefghij", "STAFF_SERVICE_KEY": "hotfix-staff-key-1234567890-abcdefghij",
           "ENROLLMENT_INTEGRATION_KEY": "hotfix-enrol-key-1234567890-abcdefghij", "MSG91_AUTHKEY": "test-authkey", "MSG91_TEMPLATE_ID": "test-template"}
    log = open(Path(auth_mongod["log"]).parent / f"backend-{port}.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "info"],
                            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}/api"
    try:
        for _ in range(80):
            try:
                if httpx.get(f"{base}/health/live", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            assert proc.poll() is None, "backend process exited during startup (the crash this hotfix removes)"
            time.sleep(0.5)
        else:
            pytest.fail("backend did not become live")
        yield {"base": base, "env": env, "log": log.name, "proc": proc}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def test_unauthorised_review_database_does_not_crash_startup_and_fails_closed(auth_mongod, backend_process):
    base = backend_process["base"]
    # 1) Startup survived; readiness is truthful: main flows ready, review reported unusable WITH a reason.
    health = httpx.get(f"{base}/health", timeout=10)
    body = health.json()
    assert health.status_code == 200 and body["ready"] is True, body["flows"]
    assert body["flows"]["review"]["ready"] is False and body["flows"]["review"]["issues"] == ["REVIEW_DB_UNAUTHORIZED"]
    assert body["flows"]["review"]["configured"] is True and body["flows"]["review"]["usable"] is False
    assert body["configuration"]["REVIEW_DB_NAME"] is True and body["configuration"]["REVIEW_DB_USABLE"] is False
    assert body["flows"]["mobile"]["ready"] and body["flows"]["staff"]["ready"] and body["flows"]["enrollment"]["ready"]
    # 2) Reviewer sign-in fails closed; an existing reviewer session token fails closed too - neither returns production data.
    login = httpx.post(f"{base}/auth/review/login", json={"reviewer_id": "store-review-admin", "access_key": "k" * 40}, timeout=10)
    assert login.status_code == 503 and login.json()["code"] == "REVIEW_UNAVAILABLE"
    claims = {"sub": "review-admin-0001", "user_id": "review-admin-0001", "role": "admin", "sv": 0, "sid": "sid-1", "scope": c.REVIEW,
              "iss": "yash-canonical", "aud": "yash-clients", "iat": int(time.time()), "exp": int(time.time()) + 600}
    stale = jwt.encode(claims, backend_process["env"]["JWT_SECRET"], algorithm="HS256")
    me = httpx.get(f"{base}/auth/me", headers={"Authorization": f"Bearer {stale}"}, timeout=10)
    assert me.status_code == 503 and me.json()["code"] == "REVIEW_UNAVAILABLE"
    refresh = httpx.post(f"{base}/auth/refresh", json={"refresh_token": "review." + "r" * 64}, timeout=10)
    assert refresh.status_code == 503 and refresh.json()["code"] == "REVIEW_UNAVAILABLE"
    # 3) Ordinary customer flow keeps working against the main database (unknown number -> 404, no SMS involved).
    otp = httpx.post(f"{base}/auth/send-otp", json={"phone": "9000000001", "channel": "mobile", "purpose": "login"}, timeout=10)
    assert otp.status_code == 404 and otp.json()["code"] == "USER_NOT_FOUND"
    # 4) The review database was never created and the main database holds no review artefacts.
    root = MongoClient(auth_mongod["root_uri"])
    assert auth_mongod["review"] not in root.list_database_names()
    assert not any(name.startswith("review") for name in root[auth_mongod["main"]].list_collection_names())
    # 5) Workers do not keep hammering the unauthorised database: the authorisation failures recorded by mongod stop
    #    growing after startup (worker loops run every 2 s / 60 s while we wait).
    before = len(_unauthorized_log_lines(auth_mongod["log"], auth_mongod["review"]))
    assert before >= 1  # the single startup attempt that used to crash the process
    time.sleep(5)
    after = len(_unauthorized_log_lines(auth_mongod["log"], auth_mongod["review"]))
    assert after == before, f"background workers still access the unauthorised review database ({after - before} new attempts)"
    # 6) Sanitized warning in the backend log; no connection string, password or provider payload.
    text = Path(backend_process["log"]).read_text(encoding="utf-8", errors="replace")
    assert "Store-review storage DISABLED" in text and "not authorized" in text
    assert "app-test-pw" not in text and "mongodb://" not in text


def test_review_database_equal_to_main_database_is_refused_at_startup(auth_mongod):
    """Sharing the production database with reviewers is still a hard refusal (process exits, never serves)."""
    port = _free_port()
    env = {**os.environ, "MONGO_URL": auth_mongod["app_uri"], "DB_NAME": auth_mongod["main"], "REVIEW_DB_NAME": auth_mongod["main"]}
    proc = subprocess.run([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port)],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0 and "REVIEW_DB_NAME must differ from DB_NAME" in proc.stderr
    with pytest.raises(RuntimeError):
        c.configure(MongoClient(auth_mongod["app_uri"])[auth_mongod["main"]], None, None, None,
                    review_database=MongoClient(auth_mongod["app_uri"])[auth_mongod["main"]])


class _CountingDatabase:
    """Motor database proxy: counts every collection access; create_index raises the injected failure."""

    def __init__(self, inner, failure=None):
        self._inner, self._failure, self.accesses = inner, failure, 0

    @property
    def name(self):
        return self._inner.name

    async def command(self, *args, **kwargs):
        self.accesses += 1
        return await self._inner.command(*args, **kwargs)

    def __getattr__(self, name):
        self.accesses += 1
        collection = getattr(self._inner, name)
        if self._failure is None:
            return collection

        class Failing:
            def __getattr__(self_inner, attr):
                if attr == "create_index":
                    async def create_index(*a, **k):
                        raise self._failure
                    return create_index
                return getattr(collection, attr)
        return Failing()

    def __getitem__(self, name):
        return self.__getattr__(name)


async def test_injected_authorisation_failure_marks_review_unavailable_and_excludes_workers(isolated_db, monkeypatch):
    """In-process variant with an injected code-13 OperationFailure: state, scopes and worker behaviour."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from shared import people, pdf_jobs

    client = AsyncIOMotorClient(os.environ["MONGO_URL"], maxPoolSize=5)
    name = f"shared_review_denied_{uuid.uuid4().hex[:8]}"
    denied = _CountingDatabase(client[name], OperationFailure("not authorized on db to execute command", code=13))
    c.configure(isolated_db["db"], c.dispatch_sms, c.put_object, c.get_object, review_database=denied)
    monkeypatch.setattr(c, "db", c._DatabaseProxy(), raising=False)  # production wiring: scope-aware proxy
    monkeypatch.setattr(server, "db", c.db, raising=False)
    try:
        assert c.review_configured() is True and c.review_available() is False  # configured != usable
        assert await c.initialize_review() is False
        assert c.review_status()["reason"] == "REVIEW_DB_UNAUTHORIZED" and c.review_available() is False
        assert c.scopes() == [None]
        settled = denied.accesses
        with c.scoped(c.REVIEW):
            with pytest.raises(Exception) as exc:
                await c.db.users.find_one({})
            assert exc.value.detail["code"] == "REVIEW_UNAVAILABLE"
        # Both worker loops run for a few cycles: only the production scope is served, the review handle is idle.
        tasks = [asyncio.create_task(pdf_jobs.worker_loop()), asyncio.create_task(people.deletion_retry_loop())]
        await asyncio.sleep(4.5)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with pytest.raises(asyncio.CancelledError):
                await task
        assert denied.accesses == settled
        assert name not in await client.list_database_names()
    finally:
        client.close()


async def test_authorised_separate_review_database_still_initialises_and_isolates(review_env, api_client):
    """Case 3: the normal fixture proves the separate review copy is usable; scope and isolation unchanged."""
    assert c.review_configured() and c.review_available() and c.review_status()["reason"] is None
    assert c.scopes() == [None, c.REVIEW]
    health = (await api_client.get("/api/health")).json()
    assert health["flows"]["review"]["ready"] is True and health["configuration"]["REVIEW_DB_USABLE"] is True
    unknown = await api_client.post("/api/auth/review/login", json={"reviewer_id": "store-review-nobody", "access_key": "x" * 40})
    assert unknown.status_code == 401 and unknown.json()["code"] == "REVIEW_CREDENTIALS_INVALID"
    assert await review_env["primary"].review_access_log.count_documents({}) == 0
    assert await review_env["db"].review_access_log.count_documents({}) == 1


async def test_main_database_failure_is_not_absorbed_by_the_review_handler(isolated_db, monkeypatch):
    """Case 4: a failing PRIMARY database still aborts startup; initialize_review() never masks it."""
    broken = _CountingDatabase(isolated_db["db"], OperationFailure("not authorized on main to execute command", code=13))
    c.configure(broken, c.dispatch_sms, c.put_object, c.get_object)
    monkeypatch.setattr(c, "db", c._DatabaseProxy(), raising=False)  # production wiring: scope-aware proxy
    monkeypatch.setattr(server, "db", c.db, raising=False)
    monkeypatch.setattr(server, "init_storage", lambda: None, raising=False)
    with pytest.raises(OperationFailure):
        await server.startup()  # the real primary startup handler
    with pytest.raises(OperationFailure):
        await c.ensure_indexes()
    assert await c.initialize_review() is False and c.review_status()["reason"] == "REVIEW_DB_NAME"


def test_placeholder_review_name_means_no_review_database_handle_at_all(monkeypatch):
    """Case 1 (unit level): the placeholder never produces a handle, so nothing can be initialised or polled."""
    monkeypatch.setenv("REVIEW_DB_NAME", "SET_IN_PUBLISH_SECRETS")
    assert c.setting("REVIEW_DB_NAME") == "" and c.is_placeholder("SET_IN_PUBLISH_SECRETS")
    monkeypatch.setenv("REVIEW_DB_NAME", "jewellers_app_review")
    assert c.setting("REVIEW_DB_NAME") == "jewellers_app_review"
