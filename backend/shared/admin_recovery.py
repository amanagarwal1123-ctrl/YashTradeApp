"""Operator-only, single-account role repair. NEVER imported into an HTTP/startup flow.

The caller already needs Mongo write access. No passwords, token minting, account creation,
or phone allowlist is introduced. The role, session version and audit event change atomically.
"""
import hashlib
import re

from bson import json_util
from pymongo.errors import DuplicateKeyError

from . import core as c


def fingerprint(value):
    return hashlib.sha256(json_util.dumps(value, sort_keys=True).encode()).hexdigest()


async def target(database, number, user_id):
    normalized = c.phone(number)
    pattern = r"^(?:\+?91[ ()-]*)?" + r"[ ()-]*".join(normalized) + r"$"
    rows = await database.users.find({"$or": [{"phone_normalized": normalized},
        {"phone": {"$regex": pattern}}]}, {"_id": 0}).limit(3).to_list(3)
    if len(rows) != 1:
        c.fail(409, "RECOVERY_IDENTITY_CONFLICT", "Expected exactly one existing identity; no account was created")
    user = rows[0]
    if user.get("id") != user_id or await database.users.count_documents({"id": user_id}) != 1:
        c.fail(409, "RECOVERY_ID_MISMATCH", "Confirm the exact canonical user ID")
    if c.phone(user.get("phone", "")) != normalized or user.get("phone_normalized", normalized) != normalized:
        c.fail(409, "RECOVERY_PHONE_CONFLICT", "Phone fields disagree; manual reconciliation required")
    c.usable(user)
    tombstone = await database.deleted_identities.find_one({"$or": [
        {"user_id": user_id}, {"phone_hash": c.keyed(normalized)}]}, {"_id": 0})
    if user.get("deleted_at") or user.get("is_deleted") or tombstone:
        c.fail(409, "RECOVERY_DELETED_IDENTITY", "Deleted identities cannot be recovered by role repair")
    if user["role"] not in {"customer", "admin"}:
        c.fail(409, "RECOVERY_ROLE_CONFLICT", "This repair only converts an existing customer to admin")
    version = user.get("session_version", 0)
    if type(version) is not int or version < 0 or not isinstance(user.get("identity_events", []), list):
        c.fail(409, "RECOVERY_SCHEMA_CONFLICT", "Review identity version/history before repair")
    return user


def validate_request(database, expected_db, operation_id, operator, reason):
    if not expected_db or database.name != expected_db:
        c.fail(409, "RECOVERY_DATABASE_MISMATCH", "Database does not match the operator's explicit target")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", operation_id):
        c.fail(422, "RECOVERY_OPERATION_REQUIRED", "Use an 8-100 character unique operation ID")
    if not 3 <= len(operator.strip()) <= 120 or not 10 <= len(reason.strip()) <= 500:
        c.fail(422, "RECOVERY_REASON_REQUIRED", "Record the authorizing operator and specific reason")


def report_for(database, user, operation_id, operator, reason):
    report = {"database": database.name, "operation_id": operation_id, "user_id": user["id"],
              "phone_suffix": c.phone(user["phone"])[-4:], "from_role": user["role"], "to_role": "admin",
              "account_status": c.account_status(user), "session_version": user.get("session_version", 0),
              "operator": operator, "reason": reason, "snapshot_sha256": fingerprint(user),
              "preserve_id_and_business_history": True}
    return {**report, "report_sha256": fingerprint(report)}


async def recover(database, *, phone, user_id, expected_db, operation_id, operator, reason,
                  apply=False, approved_report_sha256="", backup_ref="", maintenance_confirmed=False):
    validate_request(database, expected_db, operation_id, operator, reason)
    user = await target(database, phone, user_id)
    report = report_for(database, user, operation_id, operator, reason)
    if not apply:
        return {"dry_run": True, "changed": False, "already_admin": user["role"] == "admin", **report}
    if not maintenance_confirmed or not backup_ref.strip() or not approved_report_sha256:
        c.fail(422, "RECOVERY_APPROVAL_REQUIRED", "Apply requires reviewed hash, restorable backup reference and maintenance confirmation")
    op_key = "admin-recovery:" + operation_id
    old_op = await database.admin_recovery_operations.find_one({"_id": op_key}, {"_id": 0})
    if old_op and any(old_op.get(key) != value for key, value in {
        "user_id": user_id, "database": expected_db, "operator": operator, "reason": reason,
        "report_sha256": approved_report_sha256, "backup_ref": backup_ref}.items()):
        c.fail(409, "RECOVERY_OPERATION_CONFLICT", "Operation ID belongs to a different approved repair")
    applied = any(e.get("type") == "operator_admin_recovery" and e.get("operation_id") == operation_id
                  for e in user.get("identity_events", []) if isinstance(e, dict))
    if user["role"] == "admin":
        if not old_op or not applied:
            c.fail(409, "RECOVERY_ALREADY_ADMIN", "Account already admin; no repair or session change performed")
        if old_op.get("state") == "completed":
            return {"changed": False, "replayed": True, "user_id": user_id, "role": "admin"}
        return await complete(database, user_id, op_key, replayed=True)
    if applied:
        c.fail(409, "RECOVERY_PREVIOUSLY_APPLIED", "A later role change exists; this repair cannot promote it again")
    if report["report_sha256"] != approved_report_sha256:
        c.fail(409, "RECOVERY_STALE_REPORT", "Identity changed or approval does not match; review a new dry-run")
    if not old_op:
        intent = {"_id": op_key, **report, "backup_ref": backup_ref, "state": "prepared", "prepared_at": c.stamp()}
        try:
            await database.admin_recovery_operations.insert_one(dict(intent))
        except DuplicateKeyError:
            c.fail(409, "RECOVERY_IN_PROGRESS", "Another operator started this repair; inspect and retry")
    # Compare every observed field; update only the explicit role/session fields, never replace/upsert.
    expected = [{key: {"$eq": value}} for key, value in user.items()]
    for key in ("session_version", "phone_normalized", "account_status", "status", "disabled", "deleted_at", "is_deleted"):
        if key not in user:
            expected.append({key: {"$exists": False}})
    ts = c.stamp()
    event = {"type": "operator_admin_recovery", "operation_id": operation_id, "at": ts,
             "actor_id": "operator:" + operator, "reason": reason, "old_role": "customer", "new_role": "admin"}
    result = await database.users.update_one({"$and": expected}, {
        "$set": {"role": "admin", "updated_at": ts}, "$inc": {"session_version": 1},
        "$push": {"identity_events": event}})
    if result.modified_count != 1:
        c.fail(409, "RECOVERY_CONCURRENT_CHANGE", "Identity changed during repair; no overwrite performed")
    return await complete(database, user_id, op_key)


async def complete(database, user_id, op_key, replayed=False):
    # sv increment already revokes old access AND refresh tokens even if this bookkeeping crashes.
    # Revoke ONLY families with pre-repair refresh tokens. Never touch new-version sessions,
    # including when an operator resumes bookkeeping after a crash and a fresh owner login.
    operation = await database.admin_recovery_operations.find_one({"_id": op_key}, {"_id": 0})
    if not operation or operation.get("user_id") != user_id:
        c.fail(409, "RECOVERY_AUDIT_MISSING", "Approved recovery audit is missing; stop and review")
    ids = set()
    cursor = database.refresh_tokens.find({"user_id": user_id, "sv": {"$lte": operation["session_version"]}},
                                          {"_id": 0, "sid": 1}).batch_size(200)
    async for token in cursor:
        if token.get("sid"):
            ids.add(token["sid"])
        if len(ids) >= 200:
            await database.session_families.update_many({"user_id": user_id, "id": {"$in": list(ids)}},
                                                       {"$set": {"revoked": True}})
            ids.clear()
    if ids:
        await database.session_families.update_many({"user_id": user_id, "id": {"$in": list(ids)}},
                                                   {"$set": {"revoked": True}})
    await database.admin_recovery_operations.update_one({"_id": op_key},
        {"$set": {"state": "completed", "completed_at": c.stamp()}})
    return {"changed": not replayed, "replayed": replayed, "user_id": user_id,
            "role": "admin", "reauthentication_required": True}