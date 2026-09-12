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
  python tools/provision_review_access.py --expected-review-db yash_review --verify-note /private/yash-review-access.txt \
      --environment production --api-base-url https://<backend-host>/api      # recovery: re-verify stored keys, no DB access
  python tools/provision_review_access.py --expected-review-db yash_review --reset-data
  python tools/provision_review_access.py --expected-review-db yash_review --rotate store-review-admin
  python tools/provision_review_access.py --expected-review-db yash_review --revoke store-review-customer

Exit codes: 0 = requested work done (and, when --verify/--verify-note was given, EVERY key proved: sign-in,
/auth/me role + review scope, sign-out, old session rejected); 1 = blocked before any change AND before any
network request (bad config, unsafe note path, mismatched environment, --verify-note whose note pins a different
backend URL - scheme, host, port and path must all equal --api-base-url); 2 = keys were issued/kept but verification
FAILED or was INCOMPLETE after a valid pre-flight (the private note records which, sanitized; recover with the same
--verify-note command). stdout JSON carries `outcome`; the account table is `status`.
"""
import argparse
import asyncio
import json
import os
import re
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


def _validate_target(api_base_url):
    """Only an explicit HTTPS origin whose path is exactly /api may receive reviewer keys (plain HTTP is
    allowed for loopback test servers only). Redirects are never followed."""
    from urllib.parse import urlsplit

    parts = urlsplit(api_base_url.strip())
    loopback = parts.hostname in {"localhost", "127.0.0.1", "::1", "testserver"}
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise ValueError("--api-base-url must be an https:// URL (http:// only for localhost test servers)")
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("--api-base-url must be a bare origin plus /api, without credentials, query or fragment")
    if parts.path.rstrip("/") != "/api":
        raise ValueError("--api-base-url must end in /api (the canonical backend base)")
    return f"{parts.scheme}://{parts.netloc}/api"


def _verify_issued(api_base_url, issued):
    """Sign in once with every key issued in THIS run against the deployed backend, confirm the role
    and review scope, log out and prove the old session is rejected. Never marks a failed step PASS.
    Returns per-account results without secrets; raises on transport failure so the caller can keep
    the already-persisted note and report an incomplete verification."""
    import httpx

    base = _validate_target(api_base_url)
    roles = {a["reviewer_id"]: role for role, a in review_seed.ACCOUNTS.items()}
    results = {}

    def code_of(response):
        return response.json().get("code") if response.headers.get("content-type", "").startswith("application/json") else None

    with httpx.Client(timeout=20, follow_redirects=False) as http:
        for reviewer_id, secret in issued.items():
            expected_role = roles.get(reviewer_id)
            login = http.post(f"{base}/auth/review/login", json={"reviewer_id": reviewer_id, "access_key": secret})
            if login.status_code != 200:
                results[reviewer_id] = {"ok": False, "step": "login", "http_status": login.status_code, "code": code_of(login)}
                continue
            body = login.json()
            headers = {"Authorization": f"Bearer {body['token']}"}
            me = http.get(f"{base}/auth/me", headers=headers)
            role = me.json().get("role") if me.status_code == 200 else None
            scope_ok = me.status_code == 200 and me.json().get("review_environment") is True and body.get("review_environment") is True
            role_ok = expected_role is not None and role == expected_role
            logout = http.post(f"{base}/auth/logout", headers=headers)
            logout_ok = logout.status_code == 200 and logout.json().get("logged_out") is True
            rejected = http.get(f"{base}/auth/me", headers=headers).status_code == 401
            session_closed = logout_ok and rejected
            failed_step = None if (scope_ok and role_ok and session_closed) else (
                "me" if not scope_ok else "role" if not role_ok else "logout" if not logout_ok else "session_reuse")
            results[reviewer_id] = {"ok": failed_step is None, "role": role, "review_environment": scope_ok, "session_closed": session_closed,
                                    **({"step": failed_step, "http_status": logout.status_code if failed_step == "logout" else me.status_code} if failed_step else {})}
    return results


def _restrict_windows_acl(path):
    """Owner-only ACL on Windows via icacls; verified by reading the ACL back. Raises when it cannot be enforced."""
    import subprocess
    user = os.environ.get("USERNAME") or os.getlogin()
    domain = os.environ.get("USERDOMAIN", "")
    principal = f"{domain}\\{user}" if domain else user
    mode = "(OI)(CI)(F)" if Path(path).is_dir() else "(R,W)"
    result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{principal}:{mode}"], capture_output=True, text=True)
    if result.returncode != 0:
        raise PermissionError(f"Could not restrict {path} to the current user (icacls failed)")
    listing = subprocess.run(["icacls", str(path)], capture_output=True, text=True).stdout
    others = [line for line in listing.splitlines()[1:] if line.strip() and user.lower() not in line.lower()
              and "successfully processed" not in line.lower()]
    if others:
        raise PermissionError(f"{path} still grants access to other principals; refusing to store keys there")


def _private(path, directory=False):
    """Best-effort owner-only permissions: POSIX mode bits, Windows ACL (enforced + verified)."""
    if os.name == "nt":
        _restrict_windows_acl(path)
        return
    Path(path).chmod(stat.S_IRWXU if directory else (stat.S_IRUSR | stat.S_IWUSR))


def _reserve_note(path):
    """Create the private note BEFORE any key is issued: validates the location, creates the parent
    directory privately, creates the file exclusively (never overwrites) with owner-only permissions
    and proves it is writable. A refused/unwritable destination therefore never loses a key."""
    target = Path(path).expanduser().resolve()
    repo_root = ROOT.parent.resolve()
    if target == repo_root or repo_root in target.parents:
        raise ValueError("Refusing to write reviewer credentials inside the repository; choose a private folder")
    if target.exists():
        raise FileExistsError("Note already exists; choose a new file name so an older note is never overwritten silently")
    if not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        _private(target.parent, directory=True)
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("YASH TRADE - STORE-REVIEW ACCESS (PRIVATE) - RESERVED, no keys issued yet\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        target.unlink(missing_ok=True)
        raise
    _private(target)
    return target


def _note_lines(environment, api_base_url, review_db, issued, unchanged, verification, verification_error=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "YASH TRADE - STORE-REVIEW ACCESS (PRIVATE - DO NOT COMMIT, SCREENSHOT OR PASTE INTO CHAT)",
        f"Environment: {environment.upper()}    Backend: {api_base_url or NOT_RECORDED}    Review database: {review_db}",
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
    lines += ["", "VERIFICATION AGAINST THE DEPLOYED BACKEND (sign-in, /auth/me role check, sign-out, old session rejected)"]
    if verification is None:
        if verification_error:
            lines += [f"  NOT COMPLETED - {verification_error}",
                      "  The keys above ARE issued and stored (hashed) on the server but are UNVERIFIED.",
                      "  Recovery: fix connectivity, then run the same tool with",
                      f"    --expected-review-db {review_db} --verify-note <this file> --api-base-url {api_base_url or '<https://backend-host>/api'} --environment {environment}",
                      "  which signs in with each key from this file and appends the results here. Never paste keys into chat."]
        else:
            lines.append(f"  NOT REQUESTED - run with --expected-review-db {review_db} --verify-note <this file> --api-base-url <https://backend-host>/api --environment {environment} to verify.")
    else:
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
    return lines


def _write_note(target, *args, **kwargs):
    """(Re)write the reserved private note in place; the file was created exclusively by _reserve_note."""
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_note_lines(*args, **kwargs)))
        handle.flush()
        os.fsync(handle.fileno())
    return str(target)


NOTE_KEY_LINE = re.compile(r"^\s*Reviewer ID: (\S+)\s+Role: .*?Access key: (\S+)\s*$", re.M)
NOTE_HEADER_LINE = re.compile(r"^Environment: (\S+)\s+Backend: (\S+|\(not recorded\))\s+Review database: (\S+)\s*$", re.M)
NOT_RECORDED = "(not recorded)"


def _target_identity(url):
    """(scheme, host, effective port, path) of an already-validated backend base URL: the parts that decide
    WHICH server receives reviewer keys. Default ports are made explicit so https://h/api == https://h:443/api."""
    from urllib.parse import urlsplit

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    return scheme, (parts.hostname or "").lower(), parts.port or {"https": 443, "http": 80}.get(scheme), parts.path.rstrip("/") or "/"


def _require_same_target(recorded, requested):
    """Pre-flight for --verify-note: the backend recorded in the note when the keys were issued and --api-base-url
    must be the SAME target (scheme, host, port and path all equal). Anything else - including a note that never
    recorded a backend - is refused BEFORE any request, so keys are never sent to another server."""
    if recorded == NOT_RECORDED:
        raise ValueError("The note does not record the backend its keys were issued for; refusing to verify against an unpinned "
                         "target. Issue a pinned note with --rotate <reviewer_id> --api-base-url <backend>/api --write-note <new file>")
    if _target_identity(recorded) != _target_identity(requested):
        raise ValueError(f"The note pins backend {recorded} but --api-base-url is {requested}; scheme, host, port and path must all "
                         "match. Refusing to send reviewer keys to a different server")


def _verify_note(path, api_base_url, environment, expected_review_db):
    """Recovery path: verify keys already stored in a private note (no database access, no mutation) and append
    the results to that note. PRE-FLIGHT (no network): the note's own header must name the same environment,
    review database AND backend URL as the request, so preview keys are never 'verified' against production, and
    keys are never sent anywhere but the server they were issued for. A transport failure AFTER a valid pre-flight
    is not a refusal: the note receives a sanitized NOT COMPLETED entry and the caller reports it as incomplete.
    Returns {"accounts": [...], "results": {...} | None, "error": None | "<ExceptionType>"}."""
    target = Path(path).expanduser().resolve()
    text = target.read_text(encoding="utf-8")
    header = NOTE_HEADER_LINE.search(text)
    if not header:
        raise ValueError("The note has no recognised header; only notes written by this tool can be verified")
    if header.group(1).lower() != environment:
        raise ValueError(f"The note was issued for {header.group(1)}, not {environment.upper()}; pass the matching --environment")
    if header.group(3) != expected_review_db:
        raise ValueError("The note's review database differs from --expected-review-db; refusing to mix environments")
    _require_same_target(header.group(2), api_base_url)
    keys = dict(NOTE_KEY_LINE.findall(text))
    if not keys:
        raise ValueError("The note contains no reviewer keys to verify")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = ["", f"VERIFICATION RE-RUN {ts} against {api_base_url} ({environment})"]
    results, error = None, None
    try:
        results = _verify_issued(api_base_url, keys)
    except Exception as exc:  # transport failure after a valid pre-flight: keys stay valid, outcome is INCOMPLETE
        error = type(exc).__name__
        block += [f"  NOT COMPLETED - {error} while contacting {api_base_url}; no key was verified, none was changed.",
                  "  Recovery: fix connectivity, then re-run the same --verify-note command."]
    else:
        block += [f"  {rid:<28} {'PASS' if r.get('ok') else 'FAIL'}  {json.dumps({k: v for k, v in r.items() if k != 'ok'})}" for rid, r in results.items()]
    with open(target, "a", encoding="utf-8") as handle:
        handle.write("\n".join(block) + "\n")
    return {"accounts": sorted(keys), "results": results, "error": error}


def _summary(issued, verification):
    verified = sorted(rid for rid, r in (verification or {}).items() if r.get("ok"))
    return {"issued_accounts": sorted(issued), "verified_accounts": verified,
            "unchanged_accounts": sorted(a["reviewer_id"] for a in review_seed.ACCOUNTS.values() if a["reviewer_id"] not in issued),
            "all_four_roles_verified": set(verified) == {a["reviewer_id"] for a in review_seed.ACCOUNTS.values()}}


async def run(args):
    if (args.write_note or args.verify or args.verify_note) and not args.environment:
        raise ValueError("--environment preview|production is required with --write-note/--verify/--verify-note")
    if (args.verify or args.verify_note) and not args.api_base_url:
        raise ValueError("--api-base-url is required with --verify/--verify-note")
    if args.api_base_url:
        args.api_base_url = _validate_target(args.api_base_url)
    if args.verify_note:
        if any((args.provision, args.seed, args.reset_data, args.rotate, args.revoke, args.write_note)):
            raise ValueError("--verify-note is a read-only recovery step; run it without provisioning flags")
        checked = _verify_note(args.verify_note, args.api_base_url, args.environment, args.expected_review_db)
        results = checked["results"]
        out = {"environment": args.environment, "review_db": args.expected_review_db,
               **_summary(dict.fromkeys(checked["accounts"]), results),
               "note_updated": str(Path(args.verify_note).expanduser().resolve())}
        if results is None:  # transport failure after a valid pre-flight -> exit 2 (incomplete), never "blocked"
            out.update(verification_error=checked["error"], verified_all=False)
        else:
            out.update(verification=results, verified_all=all(r.get("ok") for r in results.values()))
        return out
    mongo_url, primary, review = (os.environ.get(k, "").strip() for k in ("MONGO_URL", "DB_NAME", "REVIEW_DB_NAME"))
    if not mongo_url or not primary or not review:
        raise ValueError("MONGO_URL, DB_NAME and REVIEW_DB_NAME are required in the operator runtime")
    if c.is_placeholder(review) or c.is_placeholder(primary):
        raise ValueError("REVIEW_DB_NAME/DB_NAME still carry a bootstrap placeholder; set the real distinct review database name first")
    if review == primary:
        raise ValueError("REVIEW_DB_NAME must differ from DB_NAME")
    if review != args.expected_review_db:
        raise ValueError("REVIEW_DB_NAME does not match --expected-review-db")
    if args.environment == "production" and (args.provision or args.rotate) and not args.write_note:
        raise ValueError("Production key issuance/rotation requires --write-note <private file>; keys are never printed for production")
    note_target = _reserve_note(args.write_note) if args.write_note else None
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    sync_client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    issued = {}
    try:
        c.configure(client[primary], None, None, None, review_database=client[review], review_blobs=sync_client[review].review_blobs)
        await client[review].command("ping")
        out = {"review_db": review, "primary_db_untouched": True, "environment": args.environment or "unspecified"}
        with c.scoped(c.REVIEW):
            if not await c.initialize_review():
                state = c.review_status()
                raise PermissionError(f"The review database is not usable with these credentials ({state['reason']}: {state['detail']}); "
                                      "provision an authorised, separate review database first")
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
        unchanged = [a["reviewer_id"] for a in review_seed.ACCOUNTS.values() if a["reviewer_id"] not in issued]
        if issued and note_target:
            # Persist the keys privately BEFORE any fallible network verification.
            out["note_written"] = _write_note(note_target, args.environment, args.api_base_url, review, issued, unchanged, None)
        elif issued:
            for reviewer_id, secret in issued.items():
                print(f"ONE-TIME ACCESS KEY  {reviewer_id}: {secret}", file=sys.stderr)
        elif note_target:
            note_target.unlink()  # nothing issued: leave no empty reserved file behind
            out["note_written"] = None
            out["note_skipped_reason"] = "no key was issued in this run (accounts already exist; use --rotate to issue new keys)"
        verification = None
        if args.verify:
            if not issued:
                out["verification_skipped"] = "nothing was issued in this run; existing keys are never rotated just to verify them (use --verify-note)"
            else:
                try:
                    verification = _verify_issued(args.api_base_url, issued)
                except Exception as exc:  # transport failure: keys stay in the note, marked unverified
                    out["verification_error"] = f"{type(exc).__name__}"
                    if note_target:
                        _write_note(note_target, args.environment, args.api_base_url, review, issued, unchanged, None,
                                    verification_error=f"{type(exc).__name__} while contacting {args.api_base_url}")
                else:
                    out["verification"] = verification
                    if note_target:
                        _write_note(note_target, args.environment, args.api_base_url, review, issued, unchanged, verification)
            out["verified_all"] = bool(issued) and verification is not None and all(r.get("ok") for r in verification.values())
        out.update(_summary(issued, verification))
        return out
    finally:
        client.close()
        sync_client.close()
        if note_target and not issued and note_target.exists() and note_target.read_text(encoding="utf-8").startswith(
                "YASH TRADE - STORE-REVIEW ACCESS (PRIVATE) - RESERVED"):
            note_target.unlink()  # blocked before any key existed: leave no empty reserved note behind


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
    parser.add_argument("--api-base-url", default="", help="approved https backend base URL ending in /api, used by --verify/--verify-note and recorded in the note")
    parser.add_argument("--verify", action="store_true", help="sign in once with each key issued in this run against --api-base-url, sign out, prove reuse is rejected")
    parser.add_argument("--verify-note", default="", help="recovery: verify the keys stored in an existing private note (no mutation) and append the results to it")
    parser.add_argument("--write-note", default="", help="PRIVATE new file (outside the repository) that receives the keys instead of the terminal; required for production issuance")
    try:
        args = parser.parse_args()
        out = asyncio.run(run(args))
    except Exception as exc:
        # `outcome` is the run result; `status` (when present in a successful run) is the account status table.
        print(json.dumps({"outcome": "blocked", "error_type": type(exc).__name__, "detail": str(exc)[:200]}), file=sys.stderr)
        return 1
    if (args.verify or args.verify_note) and not out.get("verified_all"):
        # Verification was requested and did not prove every issued key: FAIL results -> verification_failed,
        # no results at all (transport failure / nothing issued) -> verification_incomplete. Never exit 0 here.
        out["outcome"] = "verification_failed" if out.get("verification") else "verification_incomplete"
        print(json.dumps(out, indent=2, default=str))
        return 2
    out["outcome"] = "ok"
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
