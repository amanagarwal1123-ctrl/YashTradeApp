"""Provision/rotate/revoke isolated store-review accounts and their synthetic dataset.

Operator-only (the owner runs it). Requires the runtime's MONGO_URL, DB_NAME and REVIEW_DB_NAME
(must differ from DB_NAME) as ENVIRONMENT VARIABLES — never as command-line arguments, so the
connection string stays out of shell history. Only bcrypt hashes are stored. Plaintext access keys
are delivered exactly once: either printed to the operator terminal (default) or written to a
PRIVATE note file with --write-note (then nothing is printed). Never redirect the output into the
repository, tickets, chat or screenshots.

Examples (run from backend/):
  python tools/provision_review_access.py --expected-review-db yash_review --status
  python tools/provision_review_access.py --expected-review-db yash_review --provision --seed \
      --environment production --api-base-url https://<backend-host>/api --verify \
      --write-note /private/yash-review-access.txt
  python tools/provision_review_access.py --expected-review-db yash_review --reset-data
  python tools/provision_review_access.py --expected-review-db yash_review --rotate store-review-admin
  python tools/provision_review_access.py --expected-review-db yash_review --revoke store-review-customer
"""
import argparse
import asyncio
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from shared import core as c  # noqa: E402
from shared import review_seed  # noqa: E402

ROLE_LABELS = {"customer": "Customer (retail jeweller)", "admin": "Admin (owner console)",
               "telecaller": "Telecaller (follow-up desk)", "billing_executive": "Billing executive"}


def _verify_issued(api_base_url, issued):
    """Sign in once with every key issued in THIS run against the deployed backend, confirm the role
    and review scope, then log that session out. Returns per-account results without secrets."""
    import httpx

    base = api_base_url.rstrip("/")
    roles = {a["reviewer_id"]: role for role, a in review_seed.ACCOUNTS.items()}
    results = {}
    with httpx.Client(timeout=20) as http:
        for reviewer_id, secret in issued.items():
            expected_role = roles.get(reviewer_id)
            login = http.post(f"{base}/auth/review/login", json={"reviewer_id": reviewer_id, "access_key": secret})
            if login.status_code != 200:
                results[reviewer_id] = {"ok": False, "step": "login", "http_status": login.status_code,
                                        "code": (login.json().get("code") if login.headers.get("content-type", "").startswith("application/json") else None)}
                continue
            body = login.json()
            headers = {"Authorization": f"Bearer {body['token']}"}
            me = http.get(f"{base}/auth/me", headers=headers)
            ok = (me.status_code == 200 and me.json().get("review_environment") is True and body.get("review_environment") is True
                  and (expected_role is None or me.json().get("role") == expected_role))
            http.post(f"{base}/auth/logout", headers=headers)
            results[reviewer_id] = {"ok": ok, "role": me.json().get("role") if me.status_code == 200 else None,
                                    "review_environment": me.json().get("review_environment") if me.status_code == 200 else None,
                                    "session_closed": True}
    return results


def _note_target(path):
    """Validate the private note location BEFORE any key is issued, so a refused path never loses a key."""
    target = Path(path).expanduser().resolve()
    repo_root = ROOT.parent.resolve()
    if target == repo_root or repo_root in target.parents:
        raise ValueError("Refusing to write reviewer credentials inside the repository; choose a private folder")
    if target.exists():
        raise FileExistsError("Note already exists; choose a new file name so an older note is never overwritten silently")
    return target


def _write_note(target, environment, api_base_url, review_db, issued, unchanged, verification):
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "YASH TRADE - STORE-REVIEW ACCESS (PRIVATE - DO NOT COMMIT, SCREENSHOT OR PASTE INTO CHAT)",
        f"Environment: {environment.upper()}    Backend: {api_base_url or '(not recorded)'}    Review database: {review_db}",
        f"Generated: {ts}    Accounts issued in this run: {len(issued)}",
        "",
        "These credentials only work for the isolated store-review environment: synthetic records,",
        "simulated SMS/calls/messages, no access to genuine customer data. They are reusable until rotated or revoked.",
        "",
        "HOW A REVIEWER SIGNS IN",
        "  1. Open the Yash Trade app. On the login screen tap 'Store reviewer access' (small link under the footer).",
        "  2. Enter the Reviewer ID and the Access key exactly as written below, then tap SIGN IN.",
        "  3. A gold 'STORE-REVIEW ENVIRONMENT' banner confirms the session. No SMS or OTP is required.",
        "",
        "ACCOUNTS",
    ]
    for reviewer_id, secret in issued.items():
        role = next((r for r, a in review_seed.ACCOUNTS.items() if a["reviewer_id"] == reviewer_id), "unknown")
        lines.append(f"  Reviewer ID: {reviewer_id:<26} Role: {ROLE_LABELS.get(role, role):<30} Access key: {secret}")
    if unchanged:
        lines += ["", "  Existing accounts whose key was NOT changed in this run (use --rotate <reviewer_id> to issue a new key):",
                  *[f"    - {rid}" for rid in unchanged]]
    if verification is not None:
        lines += ["", "VERIFICATION AGAINST THE DEPLOYED BACKEND (sign-in, /auth/me role check, sign-out)"]
        for rid, result in verification.items():
            lines.append(f"  {rid:<28} {'PASS' if result.get('ok') else 'FAIL'}  {json.dumps({k: v for k, v in result.items() if k != 'ok'})}")
    lines += [
        "",
        "TEXT FOR THE STORE REVIEW FORMS (App Store Connect > App Review Information / Play Console > App access)",
        "  Sign-in type: username + password style (Reviewer ID + Access key). No SMS, OTP or phone number is needed.",
        "  Steps: Login screen > 'Store reviewer access' > enter Reviewer ID and Access key > SIGN IN.",
        "  Customer role shows catalogue, rates, requests, rewards and AI assistant on sample data.",
        "  Admin/Telecaller/Billing roles open the staff panel with sample customers and enquiries.",
        "  The environment is isolated from live customers; SMS/calls are simulated and clearly labelled.",
        "",
        "ROTATE / REVOKE (from backend/, with MONGO_URL, DB_NAME, REVIEW_DB_NAME set in the environment)",
        f"  python tools/provision_review_access.py --expected-review-db {review_db} --rotate <reviewer_id> --environment {environment} --write-note <new-private-file>",
        f"  python tools/provision_review_access.py --expected-review-db {review_db} --revoke <reviewer_id>",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    try:
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return str(target)


async def run(args):
    mongo_url, primary, review = (os.environ.get(k, "").strip() for k in ("MONGO_URL", "DB_NAME", "REVIEW_DB_NAME"))
    if not mongo_url or not primary or not review:
        raise ValueError("MONGO_URL, DB_NAME and REVIEW_DB_NAME are required in the operator runtime")
    if review == primary:
        raise ValueError("REVIEW_DB_NAME must differ from DB_NAME")
    if review != args.expected_review_db:
        raise ValueError("REVIEW_DB_NAME does not match --expected-review-db")
    if (args.write_note or args.verify) and not args.environment:
        raise ValueError("--environment preview|production is required with --write-note/--verify")
    if args.verify and not args.api_base_url:
        raise ValueError("--api-base-url is required with --verify")
    note_target = _note_target(args.write_note) if args.write_note else None
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    sync_client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        c.configure(client[primary], None, None, None, review_database=client[review], review_blobs=sync_client[review].review_blobs)
        await client[review].command("ping")
        out = {"review_db": review, "primary_db_untouched": True, "environment": args.environment or "unspecified"}
        issued = {}
        with c.scoped(c.REVIEW):
            await c.ensure_indexes()
            if args.reset_data:
                out["dataset"] = await review_seed.seed_dataset(reset=True)
            elif args.seed:
                out["dataset"] = await review_seed.seed_dataset()
            if args.provision:
                issued.update(await review_seed.provision_accounts())
                out["new_accounts"] = sorted(issued)
            if args.rotate:
                issued[args.rotate] = await review_seed.rotate(args.rotate)
                out["rotated"] = args.rotate
            if args.revoke:
                out["revoked"] = await review_seed.revoke(args.revoke)
            out["status"] = await review_seed.status()
        verification = None
        if args.verify:
            verification = _verify_issued(args.api_base_url, issued)
            out["verification"] = verification
            out["verified_all"] = bool(issued) and all(r.get("ok") for r in verification.values())
        if issued:
            unchanged = [a["reviewer_id"] for a in review_seed.ACCOUNTS.values() if a["reviewer_id"] not in issued]
            if note_target:
                out["note_written"] = _write_note(note_target, args.environment, args.api_base_url, review, issued, unchanged, verification)
            else:
                for reviewer_id, secret in issued.items():
                    print(f"ONE-TIME ACCESS KEY  {reviewer_id}: {secret}", file=sys.stderr)
        elif note_target:
            out["note_written"] = None
            out["note_skipped_reason"] = "no key was issued in this run (accounts already exist; use --rotate to issue new keys)"
        return out
    finally:
        client.close()
        sync_client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expected-review-db", required=True)
    parser.add_argument("--provision", action="store_true", help="create the four missing reviewer accounts")
    parser.add_argument("--seed", action="store_true", help="add missing synthetic records (idempotent)")
    parser.add_argument("--reset-data", action="store_true", help="wipe and reseed synthetic data; accounts and hashes kept")
    parser.add_argument("--rotate", default="", help="issue a new access key for one reviewer_id")
    parser.add_argument("--revoke", default="", help="disable one reviewer_id and revoke its sessions")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--environment", choices=("preview", "production"), default="",
                        help="label recorded in the note/verification so preview and production accounts are never confused")
    parser.add_argument("--api-base-url", default="", help="deployed backend base URL ending in /api, used by --verify and recorded in the note")
    parser.add_argument("--verify", action="store_true", help="sign in once with each key issued in this run against --api-base-url, then sign out")
    parser.add_argument("--write-note", default="", help="PRIVATE file (outside the repository) that receives the keys instead of the terminal")
    try:
        print(json.dumps(asyncio.run(run(parser.parse_args())), indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__, "detail": str(exc)[:200]}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
