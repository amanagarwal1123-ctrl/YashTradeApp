"""Owner admin recovery + readiness verification for isolated canonical flows.

# Module coverage: operator recovery dry-run/apply/replay safeguards + health/readiness auth checks + CLI guard rails.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from shared import admin_recovery as ar
from shared import core as c


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def _strong(value: str) -> str:
    return (value + "-" + ("x" * 64))[:40]


async def _owner_reference_snapshot(db):
    """Reference-only snapshot to prove no upsert/replace/side-effects for owner-linked data."""
    return {
        "owner": await db.users.find_one({"id": "u_admin"}, {"_id": 0}),
        "same_phone_users": await db.users.find(
            {"phone_normalized": "9000000000"}, {"_id": 0, "id": 1, "phone": 1}
        ).to_list(20),
        "reward_transactions": await db.reward_transactions.find({"user_id": "u_admin"}, {"_id": 0}).to_list(50),
        "requests_by_customer": await db.requests.find({"customer_id": "u_admin"}, {"_id": 0}).to_list(50),
        "requests_by_user": await db.requests.find({"user_id": "u_admin"}, {"_id": 0}).to_list(50),
        "deletion_requests": await db.deletion_requests.find({"user_id": "u_admin"}, {"_id": 0}).to_list(50),
    }


@pytest.mark.asyncio
async def test_recovery_dry_run_no_write_and_customer_start(isolated_db, seeded_users):
    db = isolated_db["db"]
    await db.users.update_one(
        {"id": "u_admin"},
        {
            "$set": {
                "role": "customer",
                "session_version": 4,
                "reward_points": 99,
                "identity_events": [{"type": "seed", "at": datetime.now(timezone.utc).isoformat()}],
            }
        },
    )

    before = await db.users.find_one({"id": "u_admin"}, {"_id": 0})
    report = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="dryrun-owner-001",
        operator="operator-qa",
        reason="TEST owner recovery dry-run",
        apply=False,
    )
    after = await db.users.find_one({"id": "u_admin"}, {"_id": 0})

    assert report["dry_run"] is True
    assert report["changed"] is False
    assert report["from_role"] == "customer"
    assert report["to_role"] == "admin"
    assert before == after
    assert await db.admin_recovery_operations.count_documents({}) == 0


@pytest.mark.asyncio
async def test_recovery_apply_revokes_old_tokens_and_allows_fresh_admin_mobile_and_portal(
    api_client, isolated_db, seeded_users, login_helper
):
    db = isolated_db["db"]
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": "u_admin"},
        {
            "$set": {
                "role": "customer",
                "identity_events": [],
                "reward_points": 123,
                "profile_version": 2,
                "phone_verified": True,
                "shop_name": "HQ Preserved",
                "location": "Delhi",
            }
        },
    )
    await db.reward_transactions.insert_one(
        {
            "id": "txn-owner-preserve-1",
            "user_id": "u_admin",
            "type": "credit",
            "points": 10,
            "reason": "pre-existing",
            "created_at": now,
            "updated_at": now,
        }
    )
    await db.requests.insert_one(
        {
            "id": "req-owner-preserve-1",
            "user_id": "u_admin",
            "customer_id": "u_admin",
            "status": "pending",
            "request_type": "call",
            "created_at": now,
            "updated_at": now,
            "events": [],
            "version": 1,
        }
    )

    before_snapshot = await _owner_reference_snapshot(db)
    before_user_count = await db.users.count_documents({})

    old_login = await login_helper("9000000000", channel="mobile")
    old_access = old_login["token"]
    old_refresh = old_login["refresh_token"]

    dry = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="apply-owner-001",
        operator="operator-qa",
        reason="TEST owner recovery apply",
        apply=False,
    )
    assert dry["report_sha256"]

    result = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="apply-owner-001",
        operator="operator-qa",
        reason="TEST owner recovery apply",
        apply=True,
        approved_report_sha256=dry["report_sha256"],
        backup_ref="backup-test-001",
        maintenance_confirmed=True,
    )
    assert result["changed"] is True

    updated = await db.users.find_one({"id": "u_admin"}, {"_id": 0})
    assert updated["id"] == "u_admin"
    assert updated["role"] == "admin"
    assert updated["reward_points"] == 123
    assert updated["shop_name"] == "HQ Preserved"
    assert updated["location"] == "Delhi"
    assert await db.users.count_documents({}) == before_user_count

    after_snapshot = await _owner_reference_snapshot(db)
    assert after_snapshot["same_phone_users"] == before_snapshot["same_phone_users"]
    assert after_snapshot["reward_transactions"] == before_snapshot["reward_transactions"]
    assert after_snapshot["requests_by_customer"] == before_snapshot["requests_by_customer"]
    assert after_snapshot["requests_by_user"] == before_snapshot["requests_by_user"]
    assert after_snapshot["deletion_requests"] == before_snapshot["deletion_requests"]
    assert after_snapshot["owner"]["shop_name"] == before_snapshot["owner"]["shop_name"]
    assert after_snapshot["owner"]["reward_points"] == before_snapshot["owner"]["reward_points"]

    old_me = await api_client.get("/api/auth/me", headers=_auth_headers(old_access))
    assert old_me.status_code == 401

    old_refresh_used = await api_client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert old_refresh_used.status_code == 401

    await db.otp_challenges.update_many(
        {"phone": "9000000000", "purpose": "login"},
        {"$set": {"created_at": c.now() - c.timedelta(seconds=61)}},
    )

    mobile_new = await login_helper("9000000000", channel="mobile")
    await db.otp_challenges.update_many(
        {"phone": "9000000000", "purpose": "login"},
        {"$set": {"created_at": c.now() - c.timedelta(seconds=61)}},
    )
    portal_new = await login_helper(
        "9000000000",
        channel="portal",
        headers={"X-Staff-Service-Key": os.environ.get("STAFF_SERVICE_KEY", "")},
    )
    assert mobile_new["user"]["id"] == portal_new["user"]["id"] == "u_admin"
    assert mobile_new["user"]["role"] == portal_new["user"]["role"] == "admin"

    me = await api_client.get("/api/auth/me", headers=_auth_headers(portal_new["token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "admin"

    staff_access = await api_client.get("/api/requests?view=all", headers=_auth_headers(portal_new["token"]))
    assert staff_access.status_code == 200

    customer_login = await login_helper("9000000004", channel="mobile")
    customer_denied = await api_client.get("/api/requests?view=all", headers=_auth_headers(customer_login["token"]))
    assert customer_denied.status_code == 403


@pytest.mark.asyncio
async def test_recovery_missing_approval_and_identity_negatives(isolated_db, seeded_users):
    db = isolated_db["db"]
    await db.users.update_one({"id": "u_admin"}, {"$set": {"role": "customer", "identity_events": []}})

    dry = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="neg-owner-001",
        operator="operator-qa",
        reason="TEST negatives",
        apply=False,
    )

    with pytest.raises(Exception) as missing_approval:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="neg-owner-001",
            operator="operator-qa",
            reason="TEST negatives",
            apply=True,
            approved_report_sha256=dry["report_sha256"],
            backup_ref="",
            maintenance_confirmed=False,
        )
    assert missing_approval.value.status_code == 422

    with pytest.raises(Exception) as wrong_db:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db="wrong-db",
            operation_id="neg-owner-002",
            operator="operator-qa",
            reason="TEST wrong db",
            apply=False,
        )
    assert wrong_db.value.status_code == 409

    # Duplicate legacy phone row without phone_normalized (regex path collision)
    now = datetime.now(timezone.utc).isoformat()
    await db.users.insert_one(
        {
            "id": "u_dup_phone",
            "phone": "+91 90000 00000",
            "role": "customer",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "identity_events": [],
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "Dup",
            "location": "Delhi",
        }
    )
    with pytest.raises(Exception) as duplicate:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="neg-owner-003",
            operator="operator-qa",
            reason="TEST duplicate",
            apply=False,
        )
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "RECOVERY_IDENTITY_CONFLICT"


@pytest.mark.asyncio
async def test_recovery_stale_hash_and_repromote_block_after_demotion(isolated_db, seeded_users):
    db = isolated_db["db"]
    await db.users.update_one({"id": "u_admin"}, {"$set": {"role": "customer", "identity_events": []}})

    dry = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="stale-owner-001",
        operator="operator-qa",
        reason="TEST stale",
        apply=False,
    )
    await db.users.update_one({"id": "u_admin"}, {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})

    with pytest.raises(Exception) as stale:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="stale-owner-001",
            operator="operator-qa",
            reason="TEST stale",
            apply=True,
            approved_report_sha256=dry["report_sha256"],
            backup_ref="backup-test-002",
            maintenance_confirmed=True,
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "RECOVERY_STALE_REPORT"

    # Apply once using a clean operation, then demote manually and ensure same op cannot re-promote.
    dry2 = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="reuse-owner-001",
        operator="operator-qa",
        reason="TEST first apply",
        apply=False,
    )
    await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="reuse-owner-001",
        operator="operator-qa",
        reason="TEST first apply",
        apply=True,
        approved_report_sha256=dry2["report_sha256"],
        backup_ref="backup-test-003",
        maintenance_confirmed=True,
    )
    await db.users.update_one({"id": "u_admin"}, {"$set": {"role": "customer", "updated_at": datetime.now(timezone.utc).isoformat()}})
    with pytest.raises(Exception) as reused:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="reuse-owner-001",
            operator="operator-qa",
            reason="TEST first apply",
            apply=True,
            approved_report_sha256=dry2["report_sha256"],
            backup_ref="backup-test-003",
            maintenance_confirmed=True,
        )
    assert reused.value.status_code == 409
    assert reused.value.detail["code"] == "RECOVERY_PREVIOUSLY_APPLIED"


@pytest.mark.asyncio
async def test_recovery_replay_after_partial_failure_should_keep_new_sessions_valid(
    api_client, isolated_db, seeded_users, login_helper, monkeypatch
):
    db = isolated_db["db"]
    await db.users.update_one({"id": "u_admin"}, {"$set": {"role": "customer", "identity_events": []}})
    old_login = await login_helper("9000000000", channel="mobile")

    dry = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="replay-owner-001",
        operator="operator-qa",
        reason="TEST replay",
        apply=False,
    )

    original_complete = ar.complete

    async def break_after_user_update(*args, **kwargs):
        raise RuntimeError("simulated crash after user write")

    monkeypatch.setattr(ar, "complete", break_after_user_update)
    with pytest.raises(RuntimeError):
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="replay-owner-001",
            operator="operator-qa",
            reason="TEST replay",
            apply=True,
            approved_report_sha256=dry["report_sha256"],
            backup_ref="backup-test-004",
            maintenance_confirmed=True,
        )

    revoked_old = await api_client.get("/api/auth/me", headers=_auth_headers(old_login["token"]))
    assert revoked_old.status_code == 401

    await db.otp_challenges.update_many(
        {"phone": "9000000000", "purpose": "login"},
        {"$set": {"created_at": c.now() - c.timedelta(seconds=61)}},
    )

    fresh_login = await login_helper(
        "9000000000", channel="portal", headers={"X-Staff-Service-Key": os.environ.get("STAFF_SERVICE_KEY", "")}
    )
    monkeypatch.setattr(ar, "complete", original_complete)

    replay = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="replay-owner-001",
        operator="operator-qa",
        reason="TEST replay",
        apply=True,
        approved_report_sha256=dry["report_sha256"],
        backup_ref="backup-test-004",
        maintenance_confirmed=True,
    )
    assert replay["replayed"] is True

    # Spec expectation: completed replay should not revoke newly issued sessions.
    fresh_me = await api_client.get("/api/auth/me", headers=_auth_headers(fresh_login["token"]))
    assert fresh_me.status_code == 200


@pytest.mark.asyncio
async def test_health_live_and_ready_truthfulness(api_client, isolated_db, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _strong("jwt-secret"))
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", _strong("enrollment"))
    monkeypatch.setenv("STAFF_SERVICE_KEY", "")
    monkeypatch.setenv("MSG91_AUTHKEY", "msg91-key")
    monkeypatch.setenv("MSG91_TEMPLATE_ID", "tpl-1")
    monkeypatch.setenv("MONGO_URL", "mongodb://example")
    monkeypatch.setenv("DB_NAME", isolated_db["db"].name)

    live = await api_client.get("/api/health/live")
    assert live.status_code == 200
    assert live.headers.get("cache-control") == "no-store"

    ready = await api_client.get("/api/health")
    assert ready.status_code == 503
    body = ready.json()
    assert body["flows"]["mobile"]["ready"] is True
    assert body["flows"]["staff"]["ready"] is False


@pytest.mark.asyncio
async def test_protected_readiness_separate_credentials_invalid_vs_missing_and_no_writes(
    api_client, isolated_db, monkeypatch
):
    db = isolated_db["db"]
    monkeypatch.setenv("JWT_SECRET", _strong("jwt-secret"))
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", "  " + _strong("enrollment") + "  ")
    monkeypatch.setenv("STAFF_SERVICE_KEY", _strong("staff-service"))
    monkeypatch.setenv("MSG91_AUTHKEY", "msg91-key")
    monkeypatch.setenv("MSG91_TEMPLATE_ID", "tpl-2")
    monkeypatch.setenv("MONGO_URL", "mongodb://example")
    monkeypatch.setenv("DB_NAME", db.name)

    before = {
        "otp_challenges": await db.otp_challenges.count_documents({}),
        "auth_grants": await db.auth_grants.count_documents({}),
        "session_families": await db.session_families.count_documents({}),
    }

    bad_staff = await api_client.get("/api/integrations/staff/readiness", headers={"X-Staff-Service-Key": "wrong-key"})
    assert bad_staff.status_code == 401
    assert bad_staff.headers.get("cache-control") == "no-store"

    ok_staff = await api_client.get(
        "/api/integrations/staff/readiness",
        headers={"X-Staff-Service-Key": _strong("staff-service")},
    )
    assert ok_staff.status_code == 200
    assert ok_staff.json()["credential_verified"] is True

    ok_enroll = await api_client.get(
        "/api/integrations/enrollment/readiness",
        headers={"X-Integration-Key": _strong("enrollment")},
    )
    assert ok_enroll.status_code == 200
    assert ok_enroll.json()["credential_verified"] is True

    monkeypatch.setenv("STAFF_SERVICE_KEY", "")
    missing_staff = await api_client.get(
        "/api/integrations/staff/readiness",
        headers={"X-Staff-Service-Key": _strong("staff-service")},
    )
    assert missing_staff.status_code == 503

    after = {
        "otp_challenges": await db.otp_challenges.count_documents({}),
        "auth_grants": await db.auth_grants.count_documents({}),
        "session_families": await db.session_families.count_documents({}),
    }
    assert before == after


@pytest.mark.asyncio
async def test_readiness_same_key_even_with_whitespace_is_rejected(api_client, isolated_db, monkeypatch):
    same = _strong("same-key")
    monkeypatch.setenv("JWT_SECRET", _strong("jwt-secret"))
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", f"  {same}  ")
    monkeypatch.setenv("STAFF_SERVICE_KEY", same)
    monkeypatch.setenv("MSG91_AUTHKEY", "msg91-key")
    monkeypatch.setenv("MSG91_TEMPLATE_ID", "tpl-3")
    monkeypatch.setenv("MONGO_URL", "mongodb://example")
    monkeypatch.setenv("DB_NAME", isolated_db["db"].name)

    health = await api_client.get("/api/health")
    assert health.status_code == 503
    assert health.json()["configuration"]["STAFF_SERVICE_KEY"] is False

    staff = await api_client.get("/api/integrations/staff/readiness", headers={"X-Staff-Service-Key": same})
    assert staff.status_code == 503


@pytest.mark.asyncio
async def test_readiness_database_unavailable_returns_503_but_live_stays_200(api_client, monkeypatch):
    class BrokenDB:
        async def command(self, *_args, **_kwargs):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr(c, "db", BrokenDB())
    monkeypatch.setenv("JWT_SECRET", _strong("jwt-secret"))
    monkeypatch.setenv("ENROLLMENT_INTEGRATION_KEY", _strong("enrollment"))
    monkeypatch.setenv("STAFF_SERVICE_KEY", _strong("staff"))
    monkeypatch.setenv("MSG91_AUTHKEY", "msg91-key")
    monkeypatch.setenv("MSG91_TEMPLATE_ID", "tpl-4")
    monkeypatch.setenv("MONGO_URL", "mongodb://example")
    monkeypatch.setenv("DB_NAME", "x")

    live = await api_client.get("/api/health/live")
    assert live.status_code == 200

    ready = await api_client.get("/api/health/ready")
    assert ready.status_code == 503
    assert ready.json()["database_ready"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_name,mutator,expected_code",
    [
        (
            "missing_identity",
            lambda db: db.users.delete_one({"id": "u_admin"}),
            "RECOVERY_IDENTITY_CONFLICT",
        ),
        (
            "normalized_raw_mismatch",
            lambda db: db.users.update_one(
                {"id": "u_admin"}, {"$set": {"phone": "9000000099", "phone_normalized": "9000000000"}}
            ),
            "RECOVERY_PHONE_CONFLICT",
        ),
        (
            "unsupported_role",
            lambda db: db.users.update_one({"id": "u_admin"}, {"$set": {"role": "telecaller"}}),
            "RECOVERY_ROLE_CONFLICT",
        ),
        (
            "inactive_account",
            lambda db: db.users.update_one(
                {"id": "u_admin"}, {"$set": {"account_status": "inactive", "status": "inactive"}}
            ),
            "ACCOUNT_INACTIVE",
        ),
        (
            "pending_account",
            lambda db: db.users.update_one(
                {"id": "u_admin"}, {"$set": {"account_status": "pending", "status": "pending"}}
            ),
            "ACCOUNT_INACTIVE",
        ),
        (
            "deleted_flags",
            lambda db: db.users.update_one(
                {"id": "u_admin"}, {"$set": {"deleted_at": datetime.now(timezone.utc).isoformat(), "is_deleted": True}}
            ),
            "RECOVERY_DELETED_IDENTITY",
        ),
        (
            "schema_conflict_bad_session_history",
            lambda db: db.users.update_one(
                {"id": "u_admin"}, {"$set": {"session_version": "bad", "identity_events": {"bad": True}}}
            ),
            "RECOVERY_SCHEMA_CONFLICT",
        ),
    ],
)
async def test_recovery_negative_matrix_blocks_with_http_exception_and_no_reference_mutation(
    isolated_db, seeded_users, case_name, mutator, expected_code
):
    db = isolated_db["db"]
    await db.users.update_one(
        {"id": "u_admin"},
        {
            "$set": {
                "role": "customer",
                "session_version": 0,
                "identity_events": [],
                "account_status": "active",
                "status": "active",
                "phone": "9000000000",
                "phone_normalized": "9000000000",
            },
            "$unset": {"deleted_at": "", "is_deleted": ""},
        },
    )
    await mutator(db)

    before = await _owner_reference_snapshot(db)
    before_user_count = await db.users.count_documents({})
    with pytest.raises(HTTPException) as blocked:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id=f"neg-matrix-{case_name}",
            operator="operator-qa",
            reason="TEST negative matrix",
            apply=False,
        )
    assert blocked.value.detail["code"] == expected_code
    assert await db.users.count_documents({}) == before_user_count
    after = await _owner_reference_snapshot(db)
    assert after == before


@pytest.mark.asyncio
async def test_recovery_wrong_canonical_duplicate_id_operation_collision_and_cas_guard(isolated_db, seeded_users):
    db = isolated_db["db"]
    await db.users.update_one({"id": "u_admin"}, {"$set": {"role": "customer", "identity_events": []}})

    with pytest.raises(HTTPException) as wrong_id:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="not-u-admin",
            expected_db=db.name,
            operation_id="neg-wrong-id-001",
            operator="operator-qa",
            reason="TEST wrong canonical",
            apply=False,
        )
    assert wrong_id.value.detail["code"] == "RECOVERY_ID_MISMATCH"

    now = datetime.now(timezone.utc).isoformat()
    await db.users.insert_one(
        {
            "id": "u_admin",
            "phone": "9100000000",
            "phone_normalized": "9100000000",
            "name": "Duplicate Canonical",
            "role": "customer",
            "account_status": "active",
            "status": "active",
            "session_version": 0,
            "identity_events": [],
            "created_at": now,
            "updated_at": now,
            "onboarding_status": "completed",
            "phone_verified": True,
            "shop_name": "Dup Canonical",
            "location": "Delhi",
        }
    )
    with pytest.raises(HTTPException) as duplicate_id:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="neg-dup-id-001",
            operator="operator-qa",
            reason="TEST duplicate canonical id",
            apply=False,
        )
    assert duplicate_id.value.detail["code"] == "RECOVERY_ID_MISMATCH"
    await db.users.delete_many({"phone_normalized": "9100000000"})

    dry = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="neg-collision-001",
        operator="operator-qa",
        reason="TEST operation collision",
        apply=False,
    )
    await db.admin_recovery_operations.insert_one(
        {
            "_id": "admin-recovery:neg-collision-001",
            "database": db.name,
            "operation_id": "neg-collision-001",
            "user_id": "u_admin",
            "operator": "other-op",
            "reason": "different",
            "report_sha256": dry["report_sha256"],
            "backup_ref": "b1",
            "session_version": 0,
            "state": "prepared",
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    with pytest.raises(HTTPException) as conflict:
        await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="neg-collision-001",
            operator="operator-qa",
            reason="TEST operation collision",
            apply=True,
            approved_report_sha256=dry["report_sha256"],
            backup_ref="backup-test-collision",
            maintenance_confirmed=True,
        )
    assert conflict.value.detail["code"] == "RECOVERY_OPERATION_CONFLICT"

    dry2 = await ar.recover(
        db,
        phone="9000000000",
        user_id="u_admin",
        expected_db=db.name,
        operation_id="neg-cas-001",
        operator="operator-qa",
        reason="TEST cas concurrent",
        apply=False,
    )

    async def _apply_once():
        return await ar.recover(
            db,
            phone="9000000000",
            user_id="u_admin",
            expected_db=db.name,
            operation_id="neg-cas-001",
            operator="operator-qa",
            reason="TEST cas concurrent",
            apply=True,
            approved_report_sha256=dry2["report_sha256"],
            backup_ref="backup-test-cas",
            maintenance_confirmed=True,
        )

    race_results = await asyncio.gather(_apply_once(), _apply_once(), return_exceptions=True)
    assert any(isinstance(item, dict) and item.get("role") == "admin" for item in race_results)
    cas_errors = [item for item in race_results if isinstance(item, HTTPException)]
    assert cas_errors
    assert any(err.detail["code"] in {"RECOVERY_CONCURRENT_CHANGE", "RECOVERY_ALREADY_ADMIN"} for err in cas_errors)


@pytest.mark.asyncio
async def test_openapi_readiness_503_schema_matches_runtime_shape(api_client):
    from server import app

    schema = app.openapi()
    assert len(schema.get("paths", {})) >= 120
    health_503 = schema["paths"]["/api/health"]["get"]["responses"]["503"]["content"]["application/json"]["schema"]
    assert health_503.get("$ref") == "#/components/schemas/AuthReadiness"

    ready = await api_client.get("/api/health")
    assert ready.status_code in {200, 503}
    body = ready.json()
    assert set(["status", "ready", "flows", "configuration", "database_ready"]).issubset(body.keys())


@pytest.mark.asyncio
async def test_recovery_cli_help_and_isolated_subprocess_dry_run_apply(isolated_db, seeded_users):
    db = isolated_db["db"]
    await db.users.update_one({"id": "u_admin"}, {"$set": {"role": "customer", "identity_events": []}})

    help_run = subprocess.run(
        ["python", "/app/backend/tools/recover_owner_admin.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_run.returncode == 0
    assert "--operation-id" in help_run.stdout

    env = dict(os.environ)
    env["MONGO_URL"] = os.environ["MONGO_URL"]
    env["DB_NAME"] = db.name

    base_cmd = [
        "python",
        "/app/backend/tools/recover_owner_admin.py",
        "--phone",
        "9000000000",
        "--user-id",
        "u_admin",
        "--expected-db",
        db.name,
        "--operation-id",
        "cli-owner-001",
        "--operator",
        "operator-qa",
        "--reason",
        "TEST CLI owner recovery",
    ]

    dry = subprocess.run(base_cmd, capture_output=True, text=True, check=False, env=env)
    assert dry.returncode == 0, dry.stderr
    dry_payload = json.loads(dry.stdout)
    assert dry_payload["dry_run"] is True

    apply = subprocess.run(
        [
            *base_cmd,
            "--apply",
            "--approved-report-sha256",
            dry_payload["report_sha256"],
            "--backup-ref",
            "backup-cli-001",
            "--maintenance-confirmed",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert apply.returncode == 0, apply.stderr
    apply_payload = json.loads(apply.stdout)
    assert apply_payload["role"] == "admin"