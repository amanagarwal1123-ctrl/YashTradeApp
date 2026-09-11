# Private identity linkage export — version 1

Follow-up status (11 September2026): no verified website export has been supplied. No production role changes, account merges, backup/restore or reconciliation have run. This absence did NOT block compatibility, catalog, crop/authoring, lifecycle accounting or synthetic tests. Baseline30796997d3484594c6c5f53965e1c71dd5ed1c86 is publicly verified; follow-up sync/release provenance is separate (RELEASE_READINESS.md).
Owner target: phone **9999813334**, role **admin**, retaining its existing canonical app user ID and history. This is a proposal until the specific backed-up report is approved. No other website role is authoritative.

## Minimum website export

Privately transfer a UTF-8 JSON array, one record per identity-bearing record in `staff_users` and the customer/enrollment collection. Export only:

| Field | Meaning |
|---|---|
| `collection` | Source collection name (staff/customer linkage only) |
| `record_id` | Stable website record ID, string |
| `canonical_user_id` | Existing app ID if known, otherwise null; do not invent |
| `phone` | Existing stored phone; include original format for conflict diagnosis |
| `phone_verified` | Boolean or null when unknown; not authorization |
| `verified_at` | Existing UTC verification time or null; do not infer |
| `role` | Existing local role or null; report evidence only |
| `account_status` | Existing active/inactive/disabled/deleted account flag or null |
| `created_at`, `updated_at` | Existing UTC timestamps or null; never used to choose the winning role |

If `status` is overloaded, also provide its documented semantic meaning (account vs lead vs onboarding), NOT an entire record. Provide a count-only manifest of collection counts and reference fields containing those IDs, such as `enrollments.canonical_user_id`, `sessions.user_id`, `outbox.subject_id`; export referenced IDs only if a conflict requires them. Names, addresses and shop details are unnecessary for the initial identity conflict report. Request a narrowly scoped private supplement only for a named unresolved collision.

**Never export passwords, password hashes, OTPs, tokens, cookies, SMS keys, integration keys, chat/customer notes, financial records, or a database dump.** Do not paste PII into public GitHub files, screenshots or public issues. Use a private encrypted transfer, restrict recipients, and delete the temporary export after approval/reconciliation under an agreed retention schedule.

## App export

Same minimum identity fields, with `id` as canonical ID and `session_version` for revocation review. A backup is separate and private; it is not the linkage export. No live export or backup has been taken by this implementation.

## Offline dry-run

`python backend/tools/reconcile_identities.py --app-export /private/app.json --website-export /private/web.json --output /private/reconciliation/report.json`

Tool produces proposed stable-ID links, conflicts, role proposals, and a deterministic report hash. It never connects to or writes a live database. Synthetic fixture: `backend/fixtures/identity-contract.json`. It rejects credential-bearing input and does not infer roles for other conflicts.

## Approval-gated execution contract

1. Obtain a restorable full backup privately, collection counts and SHA-256 manifest; test restore.
2. Generate the report from consistent snapshots and inspect duplicates, account state and every reference.
3. Owner approves that report hash and explicit per-canonical-ID mapping. Approval of a target phone in conversation is not approval to blindly merge records.
4. In a controlled maintenance transaction, keep canonical app IDs; rewrite reviewed duplicate references; normalize phone/role/account state; increment session versions; invalidate website sessions and canonical refresh families.
5. Verify unique normalized phones and at least one usable genuine admin, then enable the final unique constraint after resolving conflicts. Startup's sparse normalized-phone index does not claim legacy data has been fully reconciled.
6. Validate both verified client logins and business-history counts before release. Roll back data from the approved backup only under the same maintenance controls; never restore old sessions or exposed secrets.

**No live apply command is included intentionally.** Duplicate-reference merging and production execution remain blocked on the real export, backup and specific approval. The dry-run tool is safe to run now; it is not proof of completed production migration.

## Exact minimal read-only instructions for the later website stage

1. In the authorized website environment, use an existing read-only database credential, not a new elevated integration key. Confirm the actual identity collection names (staff_users plus the identity-bearing enrollment/customer collection); do not export sessions/drafts/outbox contents. Obtain a consistent snapshot/read timestamp. These steps do not authorize writes.
2. Project ONLY the fields in the table above. Map source `_id` to string `record_id`, preserve any existing canonical_user_id exactly, and output unknown fields as null. Preserve raw phone for conflict diagnosis. Do not infer missing verification/status/role values from dates or local login success.
3. Save the UTF-8 array privately as `/private/web-identity.json`, mode0600, outside the repository. Generate a second manifest with source collection names, row count per collection, snapshot time, SHA-256 of the encrypted-transfer plaintext payload and the NAMES of reference fields only. No phones/names/IDs in the manifest. Enumerate collection relationships separately, e.g. outbox.subject_id and enrollment.canonical_user_id.
4. Produce the app-side minimal export separately with existing canonical `id`/session_version; never use phone as a replacement ID. Record duplicates/missing mappings rather than choosing a winner. Run the offline reconcile_identities command above into `/private/reconciliation/` and share that report only with authorized reviewers.
5. Agree encrypted transfer recipients, expiry, backup retention and destruction acknowledgement BEFORE transfer. Keep payload, hashes tying PII sets, full backup and private conflict report out of Git/public evidence. Publish only aggregate counts and approval state.
6. The existing owner target remains9999813334 retaining its canonical ID/history. **Do not create9711881372 as a password admin.** All other role conflicts remain unresolved until explicit report-hash/per-ID mapping approval. Export receipt alone is not merge/promotion approval.

Backup gate: production owner supplies/takes an authorized full consistent backup, checksum/count manifest and verifies restoration to an isolated restore target. No backup/export may be fabricated from synthetic fixtures. Reconciliation execution remains separately gated even after code review and website readiness. Canonical self-service phone change is NOT a substitute for approved identity reconciliation or an admin-targeted phone workflow.