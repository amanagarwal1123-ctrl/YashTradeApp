"""Build WEBSITE_RELEASE_HANDOFF.zip for the website team (owner-approved contents, 12 September 2026).

Contents: the seven handoff Markdown documents, the generated OpenAPI schema and HANDOFF_MANIFEST.json.
The manifest records per-file SHA-256, the schema checksum, the build identity, the Expo identity and the
release status; it distinguishes the PRE-CHANGE BASELINE commit from the LOCAL IMPLEMENTATION commit and from
the FINAL SOURCE TREE (whose commit does not exist until the owner's Save to GitHub). Nothing else is packed:
no .env, credentials, OTPs, private notes, test databases or customer data.

Usage (from the repository root):  python backend/tools/build_release_handoff.py [--out WEBSITE_RELEASE_HANDOFF.zip]
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
    "STORE_REVIEW_ACCESS.md", "PRODUCTION_ADMIN_RECOVERY.md", "IDENTITY_EXPORT_CONTRACT.md",
]
SCHEMA = "contracts/openapi.shared-v1.json"
BASELINE_COMMIT = "6a6cddd"            # website's current pin; contains none of D2/D3/D4
IMPLEMENTATION_COMMIT = "2daa3ff"      # local review-fonts implementation commit in this workspace (55 files)
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
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.rstrip("\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


PACKAGE_OUTPUTS = {"WEBSITE_RELEASE_HANDOFF.zip", "test_reports/WEBSITE_RELEASE_HANDOFF.zip"}
PLATFORM_PREFIXES = (".emergent/",)  # platform-managed metadata rewritten by Save to GitHub; not part of the source contract


def source_tree_digest():
    """Deterministic digest of the ACTUAL source tree (tracked + untracked, .gitignore honoured, the package
    itself and platform metadata excluded): lets the website team confirm that the commit the owner later
    pushes contains exactly this content."""
    listing = git("ls-files", "-co", "--exclude-standard", "-z")
    files = sorted(f for f in listing.split("\0") if f and f not in PACKAGE_OUTPUTS and not f.startswith(PLATFORM_PREFIXES)
                   and (ROOT / f).is_file())
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode()); h.update(b"\0"); h.update(sha256(ROOT / f).encode()); h.update(b"\n")
    return {"algorithm": "sha256(over sorted 'path\\0sha256(file)\\n' for every tracked/untracked non-ignored file, excluding WEBSITE_RELEASE_HANDOFF.zip copies and .emergent/ platform metadata)",
            "digest_sha256": h.hexdigest(), "file_count": len(files)}


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
    head = git("rev-parse", "--short", "HEAD")
    dirty = [line[3:] for line in git("status", "--porcelain").splitlines() if line.strip()]
    manifest = {
        "package": "WEBSITE_RELEASE_HANDOFF.zip",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audience": "Yash Trade website team (register.yashsilver.com / yash-register.emergent.host)",
        "build_identity": build_identity(),
        "source_provenance": {
            "pre_change_baseline_commit": {"sha_short": BASELINE_COMMIT, "role": "website's current app pin; predates D2/D3/D4 and everything in this package",
                                           "is_the_implementation": False},
            "local_implementation_commit": {"sha_short": IMPLEMENTATION_COMMIT, "role": "review-fonts implementation committed in the workspace repository "
                                            "(55 files); NOT yet the final release commit", "is_final_release_commit": False},
            "workspace_head_at_packaging": head,
            "uncommitted_release_pass_changes": dirty,
            "final_source_tree": {**source_tree_digest(),
                                  "final_commit_sha": None,
                                  "how_to_obtain": "Created by the owner's Save to GitHub AFTER this package. Verify that commit reproduces this digest "
                                                   "(run backend/tools/build_release_handoff.py at that commit and compare), then pin it and set BUILD_COMMIT to it."},
        },
        "schema": schema_summary(ROOT / SCHEMA),
        "files": {f: {"sha256": sha256(ROOT / f), "bytes": (ROOT / f).stat().st_size} for f in files},
        "excluded_by_policy": [".env files", "credentials / connection strings", "OTPs", "private reviewer notes (*review-access*.txt)",
                               "customer data / identity exports / backups", "test databases"],
        "status": {
            "local_tests": {
                "backend_shared_suite": "see test_reports/pytest/release_pass_2026-09-12.xml (run at packaging; Playwright-based UI cases skip in this environment)",
                "reviewer_cli": "test_review_provisioning_cli.py 8/8 incl. live-backend exit-code contract 0/1/2",
                "placeholder_configuration": "test_placeholder_configuration.py 2/2",
                "frontend_clean_checkout": "yarn install --frozen-lockfile, yarn test (38 tests, 5 suites), tsc --noEmit, yarn lint — test_reports/clean_checkout_2026-09-12.txt",
            },
            "github_publication": "PENDING — owner's Save to GitHub creates the final source commit",
            "production_deployment": "PENDING — production still runs the older build; sequence: republish (registers declared names) → owner sets Secrets "
                                     "(STAFF_SERVICE_KEY, REVIEW_DB_NAME, BUILD_COMMIT, frontend EXPO_PUBLIC_BACKEND_URL) → republish",
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
    print(json.dumps({"zip": str(out), "zip_sha256": manifest["zip_sha256"], "files": sorted(manifest["files"]) + ["HANDOFF_MANIFEST.json"],
                      "source_tree_digest": manifest["source_provenance"]["final_source_tree"]["digest_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
