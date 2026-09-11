"""Offline, reviewable identity reconciliation. Never connects to production by default.

Inputs are PRIVATELY transferred minimal exports, not passwords/tokens/full database dumps.
No production --apply is provided: generated changes require backup, owner review and a separate
transactional maintenance execution. This intentionally cannot silently merge live identities.
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

OWNER_PHONE = "9999813334"
ROLES = {"customer", "admin", "telecaller", "billing_executive"}
ACCOUNT_ALIASES = {"disabled": "inactive", "blocked": "inactive"}
QUERY_ALIASES = {"completed": "resolved", "done": "resolved", "assigned": "in_progress"}


def normalize(value):
    value = re.sub(r"[ ()-]", "", str(value))
    if value.startswith("+91"):
        value = value[3:]
    elif len(value) == 12 and value.startswith("91"):
        value = value[2:]
    if not re.fullmatch(r"[6-9][0-9]{9}", value):
        raise ValueError("Invalid normalized Indian phone")
    return value


def normalized_role(value):
    return "telecaller" if value == "executive" else value


def report(app_rows, website_rows, approved_mapping=None):
    app, web, issues, proposals = defaultdict(list), defaultdict(list), [], []
    for source, rows, target in [("app", app_rows, app), ("website", website_rows, web)]:
        for row in rows:
            forbidden = {"password", "password_hash", "otp", "token", "refresh_token", "integration_key", "authkey"} & set(row)
            if forbidden:
                raise ValueError("Export contains forbidden credential fields; remove them privately")
            try:
                target[normalize(row["phone"])].append(row)
            except (KeyError, ValueError):
                issues.append({"source": source, "record_id": row.get("record_id", row.get("id")), "kind": "invalid_phone"})
    mapping = approved_mapping or {}
    for phone in sorted(set(app) | set(web)):
        a, w = app[phone], web[phone]
        ids = [r.get("id", r.get("record_id")) for r in a]
        if len(a) != 1:
            issues.append({"phone": phone, "kind": "missing_app_identity" if not a else "duplicate_app_identity",
                           "app_ids": ids, "website_records": w, "action": "owner_adjudication_required"})
            continue
        row = a[0]
        current_role = normalized_role(row.get("role"))
        website_roles = sorted({normalized_role(r.get("role")) for r in w if r.get("role")})
        target = "admin" if phone == OWNER_PHONE else mapping.get(row["id"], {}).get("role")
        if current_role not in ROLES or any(r not in ROLES for r in website_roles):
            issues.append({"phone": phone, "app_id": row["id"], "kind": "unknown_role", "app_role": current_role, "website_roles": website_roles})
        if website_roles and set(website_roles) != {current_role} and not target:
            issues.append({"phone": phone, "app_id": row["id"], "kind": "role_conflict", "app_role": current_role,
                "website_roles": website_roles, "action": "explicit_admin_mapping_required"})
        linked = [r.get("canonical_user_id") for r in w if r.get("canonical_user_id")]
        if any(uid != row["id"] for uid in linked):
            issues.append({"phone": phone, "app_id": row["id"], "kind": "linkage_conflict", "website_canonical_ids": linked})
        if target and target not in ROLES:
            raise ValueError("Approved mapping contains an unknown target role")
        status = ACCOUNT_ALIASES.get(row.get("account_status", row.get("status", "active")), row.get("account_status", row.get("status", "active")))
        if status not in {"active", "inactive", "pending", "deleted"}:
            issues.append({"phone": phone, "app_id": row["id"], "kind": "account_state_conflict", "state": status})
        proposals.append({"canonical_user_id": row["id"], "phone": phone, "current_role": current_role,
            "target_role": target or current_role, "current_account_status": status, "target_account_status": status,
            "website_record_links": [{"collection": r.get("collection"), "record_id": r.get("record_id")} for r in w],
            "preserve_ids_and_business_history": True, "revoke_all_sessions": True,
            "authorization": "owner_intent_confirmed_specific_migration_not_yet_approved" if phone == OWNER_PHONE else
                "explicit_mapping" if target else "no_role_change", "apply_allowed": False})
    if OWNER_PHONE not in app:
        issues.append({"kind": "owner_not_found", "action": "do_not_create_default_admin"})
    payload = {"contract_version": 1, "dry_run": True, "website_export_supplied": bool(website_rows),
        "proposals": proposals, "conflicts": issues, "production_modified": False,
        "apply_preconditions": ["restorable backup and checksummed manifest", "owner approval referencing exact report hash",
            "adjudicated duplicate references", "at least one usable verified admin preserved", "maintenance window and rollback validation"]}
    payload["report_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def normalize_legacy_request(row):
    result = dict(row)
    result["status"] = QUERY_ALIASES.get(row.get("status"), row.get("status", "pending"))
    result.setdefault("version", 0)
    result.setdefault("events", [])
    result.setdefault("pending_since", row.get("created_at"))
    result["migration_provenance"] = {"version": 1, "original_status": row.get("status"), "resolution_credit_backfilled": False}
    if result["status"] == "resolved" and not result.get("resolved_at"):
        result["legacy_timing_unknown"] = True
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-export", required=True)
    parser.add_argument("--website-export")
    parser.add_argument("--approved-mapping")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    read = lambda p: json.loads(Path(p).read_text()) if p else []
    result = report(read(args.app_export), read(args.website_export), read(args.approved_mapping) or {})
    output = Path(args.output)
    if "/private/" not in str(output.resolve()):
        raise SystemExit("Reports contain personal information: output must be in a private directory outside the repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)); output.chmod(0o600)
    print(json.dumps({"dry_run": True, "proposals": len(result["proposals"]), "conflicts": len(result["conflicts"]), "report_sha256": result["report_sha256"]}))