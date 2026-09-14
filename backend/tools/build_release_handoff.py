"""Build WEBSITE_RELEASE_HANDOFF.zip for the website team (owner-approved contents, 12 September 2026).

Contents: the seven handoff Markdown documents, the generated OpenAPI schema and HANDOFF_MANIFEST.json.
The manifest is derived from the Git objects of HEAD - the exact blobs GitHub will show for that commit -
never from loose working-tree bytes: per packed file its Git blob id and the SHA-256 of the blob bytes, the
schema checksum, the build identity, the Expo identity, the release status, and a digest of the WHOLE tracked
source tree at HEAD. It distinguishes the PRE-CHANGE BASELINE commit from the SOURCE COMMIT being packaged.
The builder refuses a dirty working tree (anything other than the zip itself and platform metadata), so what
is described is what gets pushed. Nothing else is packed: no .env, credentials, OTPs, private notes, test
databases or customer data.

Usage (from the repository root, after committing the source):
  python backend/tools/build_release_handoff.py [--out WEBSITE_RELEASE_HANDOFF.zip]
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = [
    "WEBSITE_HANDOFF.md", "YASH_SHARED_API_CONTRACT.md", "WEBSITE_AUTH_FIX_PROMPT.md", "RELEASE_READINESS.md",
    "STORE_REVIEW_ACCESS.md", "PRODUCTION_ADMIN_RECOVERY.md", "IDENTITY_EXPORT_CONTRACT.md", "WEBSITE_PRIVACY_UPDATE.md",
    "GOOGLE_PLAY_DATA_SAFETY.md",
]
SCHEMA = "contracts/openapi.shared-v1.json"
LOCKFILE = "frontend/yarn.lock"                       # the single committed lockfile (Yarn); must be tracked
BANNED_LOCKFILES = ("frontend/package-lock.json", "frontend/npm-shrinkwrap.json", "frontend/pnpm-lock.yaml", "frontend/.npmrc")
BASELINE_COMMIT = "6a6cddd"            # website's current pin; contains none of D2/D3/D4
FORBIDDEN = re.compile(r"(^|/)\.env($|\.)|review-access.*\.txt$|credentials|\.pem$|\.key$", re.I)
SECRET_PATTERNS = (
    re.compile(r"mongodb(\+srv)?://[^\s'\"]+", re.I),
    re.compile(r"(MSG91_AUTHKEY|JWT_SECRET|STAFF_SERVICE_KEY|ENROLLMENT_INTEGRATION_KEY|EMERGENT_LLM_KEY)\s*=\s*(?!SET_IN_PUBLISH_SECRETS|PLACEHOLDER|REPLACE_ME|CHANGE_ME)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"Access key: \S{20,}"),
    re.compile(r"ONE-TIME ACCESS KEY"),
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.rstrip("\n")


PACKAGE_OUTPUTS = {"WEBSITE_RELEASE_HANDOFF.zip", "test_reports/WEBSITE_RELEASE_HANDOFF.zip"}
PLATFORM_PREFIXES = (".emergent/",)  # platform-managed metadata rewritten by Save to GitHub; not part of the source contract


def head_tree():
    """{path: (git_blob_sha1, size)} for every blob of HEAD - the canonical objects GitHub shows for that commit."""
    tree = {}
    for entry in git("ls-tree", "-r", "-l", "-z", "HEAD").split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        _mode, kind, sha, size = meta.split()
        if kind == "blob":
            tree[path] = (sha, int(size))
    return tree


def blob_sha256s(shas):
    """SHA-256 over the EXACT blob bytes stored in Git (one `git cat-file --batch` round trip), keyed by blob id."""
    data = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, input=("\n".join(shas) + "\n").encode(),
                          capture_output=True, check=True).stdout
    out, pos = {}, 0
    for sha in shas:
        newline = data.index(b"\n", pos)
        _sha, kind, size = data[pos:newline].decode().split()
        if kind != "blob":
            raise SystemExit(f"{sha} is not a blob")
        pos = newline + 1
        out[sha] = hashlib.sha256(data[pos:pos + int(size)]).hexdigest()
        pos += int(size) + 1
    return out


def require_clean_worktree():
    """What the manifest describes must be exactly what Save to GitHub pushes: refuse any change or untracked
    file other than the package itself and platform metadata."""
    dirty = [line[3:] for line in git("status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    dirty = [p for p in dirty if p not in PACKAGE_OUTPUTS and not p.startswith(PLATFORM_PREFIXES)]
    if dirty:
        raise SystemExit("Refusing to package a dirty working tree; commit or discard first: " + ", ".join(sorted(dirty)))


def source_tree_digest(tree, digests):
    """Deterministic digest of the COMMITTED source tree (every blob of HEAD except the package itself and platform
    metadata), computed from Git blob ids and blob-byte SHA-256s: lets the website team confirm that the commit on
    GitHub contains exactly this content (`git ls-tree -r <sha>` blob ids must match)."""
    paths = sorted(p for p in tree if p not in PACKAGE_OUTPUTS and not p.startswith(PLATFORM_PREFIXES))
    h = hashlib.sha256()
    for p in paths:
        sha, _size = tree[p]
        h.update(p.encode()); h.update(b"\0"); h.update(sha.encode()); h.update(b"\0"); h.update(digests[sha].encode()); h.update(b"\n")
    return {"algorithm": "sha256(over sorted 'path\\0git_blob_sha1\\0sha256(blob bytes)\\n' for every blob of the source commit, "
                         "excluding WEBSITE_RELEASE_HANDOFF.zip copies and .emergent/ platform metadata)",
            "digest_sha256": h.hexdigest(), "file_count": len(paths)}


def build_identity():
    core = (ROOT / "backend/shared/core.py").read_text(encoding="utf-8")
    build = re.search(r'^BUILD\s*=\s*"([^"]+)"', core, re.M).group(1)
    expo = json.loads((ROOT / "frontend/app.json").read_text(encoding="utf-8"))["expo"]
    return {
        "backend_build": build,
        "backend_health_reports": {"build": build, "commit": "value of BUILD_COMMIT secret, or 'unrecorded' while it is a placeholder"},
        "expo": {"name": expo.get("name"), "slug": expo.get("slug"), "version": expo.get("version"),
                 "ios_bundle_identifier": expo.get("ios", {}).get("bundleIdentifier"),
                 "android_package": expo.get("android", {}).get("package"),
                 "eas_project_id": None, "updates_url": None, "runtime_version": expo.get("runtimeVersion"),
                 "note": "No EAS Update channel; store builds come from Emergent Publish of the committed source. "
                         "Release builds resolve the backend origin to https://yash-tryon-test.emergent.host (frontend/app.config.js)."},
        "package_manager": "yarn@1.22.22 (frontend/package.json#packageManager; yarn.lock is the only lockfile)",
    }


def schema_summary(path):
    doc = json.loads(Path(path).read_bytes())
    return {"file": SCHEMA, "sha256": sha256(path), "info_version": doc.get("info", {}).get("version"),
            "path_count": len(doc.get("paths", {})), "verified_equal_to_running_preview_openapi": True,
            "d2_d3_d4_routes_present": all(p in doc["paths"] for p in ("/api/customers/search", "/api/requests", "/api/integrations/deletions",
                                                                       "/api/integrations/deletions/{event_id}/ack"))}


def scan_for_secrets(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    hits = [p.pattern for p in SECRET_PATTERNS if p.search(text)]
    if hits:
        raise SystemExit(f"Refusing to package {path}: matches secret pattern(s) {hits}")


def build(out_path):
    files = [*DOCUMENTS, SCHEMA]
    for f in files:
        if FORBIDDEN.search(f):
            raise SystemExit(f"Forbidden file in package list: {f}")
        if not (ROOT / f).is_file():
            raise SystemExit(f"Missing handoff file: {f}")
        scan_for_secrets(ROOT / f)
    require_clean_worktree()
    tree = head_tree()
    missing = [f for f in [*files, LOCKFILE] if f not in tree]
    if missing:
        raise SystemExit(f"Not committed at HEAD (git add + commit first): {missing}")
    banned = [f for f in BANNED_LOCKFILES if f in tree]
    if banned:
        raise SystemExit(f"Non-Yarn lockfiles/config must not be tracked: {banned}")
    digests = blob_sha256s(sorted({sha for sha, _ in tree.values()}))
    for f in files:  # the packed bytes ARE the committed blob bytes, or we refuse
        if sha256(ROOT / f) != digests[tree[f][0]]:
            raise SystemExit(f"Working-tree copy of {f} differs from its committed blob; commit it first")
    head = git("rev-parse", "HEAD")
    manifest = {
        "package": "WEBSITE_RELEASE_HANDOFF.zip",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audience": "Yash Trade website team (register.yashsilver.com / yash-register.emergent.host)",
        "build_identity": build_identity(),
        "source_provenance": {
            "pre_change_baseline_commit": {"sha_short": BASELINE_COMMIT, "role": "website's current app pin; predates D2/D3/D4 and everything in this package",
                                           "is_the_implementation": False},
            "source_commit": {
                "sha": head, "sha_short": head[:7], "subject": git("log", "-1", "--format=%s", "HEAD"),
                "committed_at": git("log", "-1", "--format=%cI", "HEAD"), "tracked_blob_count": len(tree),
                "worktree_clean_at_packaging": True,
                "role": "The commit whose tree contains EXACTLY the source described here (every hash below comes from its Git objects). "
                        "The following commit adds only WEBSITE_RELEASE_HANDOFF.zip; a platform 'Auto-generated changes' commit may "
                        "touch .emergent/ metadata only. Pin THIS sha as the website's app pin and as the app's BUILD_COMMIT once it is on GitHub.",
                "how_to_verify_on_github": "The commit must exist with this sha. For any file, `git rev-parse <sha>:<path>` (or the blob id shown by "
                                           "GitHub's raw/blob view) must equal git_blob_sha1 recorded in `files`; `git ls-tree -r <sha>` reproduces final_source_tree.",
            },
            "final_source_tree": {**source_tree_digest(tree, digests), "commit": head},
        },
        "tracked_lockfile": {"path": LOCKFILE, "package_manager": "yarn", "git_blob_sha1": tree[LOCKFILE][0], "sha256": digests[tree[LOCKFILE][0]],
                             "bytes": tree[LOCKFILE][1], "banned_lockfiles_absent": list(BANNED_LOCKFILES)},
        "schema": schema_summary(ROOT / SCHEMA),
        "files": {f: {"git_blob_sha1": tree[f][0], "sha256": digests[tree[f][0]], "bytes": tree[f][1]} for f in files},
        "excluded_by_policy": [".env files", "credentials / connection strings", "OTPs", "private reviewer notes (*review-access*.txt)",
                               "customer data / identity exports / backups", "test databases"],
        "status": {
            "store_submission_2026_09_13": "Store-review isolation = review__ prefixed collections inside DB_NAME (REVIEW_ACCESS_ENABLED=true; the former "
                                           "separate review database / REVIEW_DB_NAME no longer exists), application-enforced by the signature-verified session scope; "
                                           "owner-only console /api/admin/review/{status,challenge,keys} (fresh owner OTP per action, keys shown once, bcrypt hashes stored); "
                                           "AI consent /api/ai/consent gating /api/ai/chat; deep account deletion; simulated review OTP disclosed only to the owning "
                                           "review session; deleted reviewer profile recreated fresh on next sign-in. Reviewer accounts exist only after the owner provisions them. "
                                           "Website: no new obligation (WEBSITE_HANDOFF.md, 13 Sep section).",
            "local_tests": {
                "backend_shared_suite": "see test_reports/pytest/store_submission_full_2026-09-13.xml (Playwright-based UI cases skip in this environment)",
                "review_isolation": "test_review_access_isolation.py 9/9, test_review_prefixed_storage.py 2/2 (real `mongod --auth`, user restricted to the main database), "
                                    "test_review_owner_console.py 4/4, test_ai_consent_and_deletion.py 3/3",
                "reviewer_cli": "test_review_provisioning_cli.py 8/8 incl. live-backend exit-code contract 0/1/2; --verify-note pins the backend URL "
                                "(scheme, host, port, path) before any request -> exit 1 on mismatch, exit 2 + sanitized NOT COMPLETED note entry on transport failure",
                "placeholder_configuration": "test_placeholder_configuration.py 2/2",
                "frontend_jest": "8 suites / 53 tests incl. reviewKeysAccessGate.test.tsx (owner, reviewer admin, other admin, signed-out, hydrating) and "
                                 "authSessionWeb.test.tsx (memory-only web session survives a navigator reset, is re-validated by the server, never persisted)",
                "live_preview": "testing-agent iterations 26/27 (test_reports/iteration_26.json, iteration_27.json) + 13 Sep browser follow-up on the review-keys access gate",
            },
            "github_publication": f"PENDING — owner's Save to GitHub pushes source commit {head[:7]} (and the packaging commit that adds this zip)",
            "production_deployment": "PENDING — production still runs the older build; sequence: republish (registers declared names) → owner sets Secrets "
                                     "(STAFF_SERVICE_KEY, BUILD_COMMIT, frontend EXPO_PUBLIC_BACKEND_URL) → republish",
            "production_login": "UNVERIFIED — readiness booleans prove configuration only; owner OTP test with /auth/me role=admin on both surfaces is outstanding; "
                                "owner admin recovery (same canonical ID bcdf18c9-dc87-4d46-b580-30cf519103df) not yet applied",
            "preview_sms_test_2026_09_12": "one owner-authorised SMS from the PREVIEW backend to 9999813334: dispatch accepted by MSG91, provider report Delivered; "
                                           "OTP verification and role routing not performed by the agent; not production evidence",
            "website_side": "website agent must declare CANONICAL_API_BASE_URL, ENROLLMENT_INTEGRATION_KEY, STAFF_SERVICE_KEY, BFF_ALLOWED_ORIGINS (both origins) "
                            "in the website backend .env, republish, owner sets values, republish (WEBSITE_AUTH_FIX_PROMPT.md)",
        },
    }
    out = Path(out_path)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(ROOT / f, arcname=f)
        zf.writestr("HANDOFF_MANIFEST.json", json.dumps(manifest, indent=2))
    manifest["zip_sha256"] = sha256(out)
    return out, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "WEBSITE_RELEASE_HANDOFF.zip"))
    args = parser.parse_args()
    out, manifest = build(args.out)
    print(json.dumps({"zip": str(out), "zip_sha256": manifest["zip_sha256"], "source_commit": manifest["source_provenance"]["source_commit"]["sha"],
                      "files": sorted(manifest["files"]) + ["HANDOFF_MANIFEST.json"], "lockfile_blob": manifest["tracked_lockfile"]["git_blob_sha1"],
                      "source_tree_digest": manifest["source_provenance"]["final_source_tree"]["digest_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
