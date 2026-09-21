# Independent Review: Yash Trade App

Reviewed commit: `2093300ae7549281f6bacb1851f13bb082b7be7e`
Commit timestamp: 20 September 2026, 12:27 UTC
Review date: 20 September 2026
Scope: Focused source audit and isolated reproductions against the GitHub snapshot. This is not a full R00-R17 sign-off or native-device certification.

## Result

Do not mark this snapshot release-ready. Five defects were reproduced by executing saved application code with isolated dependencies. Four additional actionable issues were identified by source-path inspection. The working app project and production systems were not modified.

The implementing chat may already have newer uncommitted fixes. Reconcile each finding against its current working tree; retain a regression test even if a finding has already been fixed. Do not reset or replace newer work with this snapshot.

## Reproduced Findings

### F01 [P1] An old refresh response can overwrite a newer account or restore cleared credentials

Requirement: R01-B, R00-C.

Source: [frontend/src/api.ts:48](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/frontend/src/api.ts#L48), with the later request guard at line 83.

`refreshSession()` writes access and refresh credentials without checking whether the session changed while its HTTP request was pending. The request-level epoch check happens AFTER those writes. Rejecting the original caller with SessionChangedError therefore does not prevent credential restoration or overwrite.

Reproduction:
1. Start account A's refresh and hold its response.
2. Clear/replace the session using the application's exported session/token setters, as during logout or another login. This race matters whenever that transition finishes while the old refresh remains pending, including failed/offline logout paths.
3. Deliver the old successful refresh response.
4. The caller throws SessionChangedError, but memory and secure storage nevertheless contain account A's newly issued credentials. Both logout and account-B replacement cases reproduced.

Fix: Bind refresh work and its credential persistence to the initiating session generation and refresh credential. Reject obsolete success AND failure results before mutating current credentials or invoking current-session logout. Serialize persistence/session transitions so asynchronous storage writes cannot cross an account change. Add tests covering refresh versus logout, new login, revocation, and late failures, not just ordinary parallel requests within one account.

Evidence: `audit_repros_2093300.cjs`, two successful issue reproductions using the actual transpiled api.ts and isolated HTTP/SecureStore doubles. This is not an end-to-end device logout test.

### F02 [P1] Queued notifications ignore logout, reassignment, disabling, and opt-out before dispatch

Requirement: R09-B/D, R15-B.

Source: [backend/shared/notifications.py:446](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/notifications.py#L446).

Outbox messages freeze the token and intended user during fan-out. `process_job()` sends those messages directly without checking the current device association, account state/role, or marketing preference. Deleting/unlinking the push_devices row or changing its owner therefore does not stop an already queued, not-yet-dispatched message.

Reproduction: Queue a message for A, represent its token as disabled and now belonging to B, then execute the saved process_job function with a recording transport. A's message is still passed to the transport and the job is marked sent.

Fix: Revalidate token-to-user ownership, enabled/invalid state, account usability, current role eligibility, and marketing preference immediately before each send/retry. Exclude ineligible messages and account for them explicitly. Cover logout, account switch, staff role change, disable/delete, and opt-out after queueing. Notifications already accepted by an external provider cannot generally be recalled; distinguish those from unsent outbox messages.

Evidence: `test_reproduces_notification_sent_to_unlinked_reassigned_device` in the isolated Python harness. No real push was sent.

### F03 [P1] A partial completion failure permanently loses the staff-report record

Requirement: R12-B, R13-A.

Source: [backend/shared/queries.py:545](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/queries.py#L545). Retry short-circuits also occur at lines 446 and 484.

The request is marked resolved and its idempotency key stored before the separate completion-ledger write. If that write fails, the query has left the pending list but has no completion-report record. Same-key retries return early; a new-key Mark Complete returns already_completed. Neither repairs the missing ledger entry.

Reproduction: Inject a failure at record_completion after the request update, restore the ledger dependency, and retry with both the original and a new idempotency key. The request remains resolved and no ledger record is written.

Fix: Make request lifecycle and completion attribution atomic, or use a durable, recoverable operation/outbox whose retries reconcile the missing record. Also scope reopen/supersession updates to the intended completion sequence so a delayed reopen write cannot supersede a later completion. Add partial-write/crash-recovery tests, not only double-click tests.

Evidence: `test_reproduces_completion_ledger_failure_not_repaired_by_retry`.

### F04 [P1] A post-03:00 edit lets yesterday's claimant evade the daily release

Requirement: R13-B/C.

Source: [backend/shared/queue_reset.py:54](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/queue_reset.py#L54), and request mutations in queries.py.

The reset candidate predicate excludes ANY request updated after the boundary, not just a request legitimately claimed in the new cycle. With the worker polling every 30 seconds, yesterday's claimant can submit a note/head update at 03:00:01 before the next reset pass. That updates updated_at and makes the old assignment ineligible. The cycle can then be marked completed with that assignment retained all day. The same gap exists during catch-up after downtime.

Reproduction: An old in_progress request claimed before the boundary is eligible with updated_at=02:59:59 IST, but becomes ineligible when only updated_at changes to 03:00:01 IST. The owner and claimed_at remain from yesterday.

Fix: Enforce the logical reset cycle in claim/work mutations as well as the worker. Distinguish an authorized post-boundary claim from activity under an expired previous-cycle assignment. Do not simply remove every race-protection predicate; protect completed requests and genuinely new claims while ensuring stale owners cannot extend their assignment by editing.

Evidence: `test_reproduces_old_claim_surviving_daily_reset_after_one_post_boundary_edit`. This executes the saved candidate predicate with controlled timestamps; multi-worker Mongo testing is still required for the final fix.

### F05 [P2] Older unseen catalog products can never appear in discovery

Requirement: R03.

Source: [backend/shared/discovery.py:63](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/discovery.py#L63).

Every new discovery session first selects the newest 4,000 eligible product IDs and only then separates seen from unseen. Products outside that fixed newest window can never enter a session, even if unseen. The stored truncated flag is not returned to the client.

Reproduction: Create 4,001 eligible products, mark the newest 4,000 seen, leave the oldest unseen, then execute the saved start/page functions. The response says unseen=0 and exhausted=true; the unseen older product is excluded from the session order.

Fix: Select unseen candidates across the complete eligible catalog using a scalable cursor/indexed approach or a rotating bounded candidate strategy with complete coverage. A bounded session size is acceptable; a permanently fixed catalog cutoff is not. Test beyond 4,000 and 5,000 products/impressions and preserve stable pagination and visibility rules.

Evidence: `test_reproduces_older_unseen_product_permanently_outside_discovery`.

## Additional Source Findings

These findings are grounded in the saved code paths but were not reproduced with full runtime or fault-injection tests during this audit.

### F06 [P1] Notification enqueue failure permanently drops a new-query alert

Requirement: R12-A, R09-D.

Source: [backend/shared/queries.py:239](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/queries.py#L239) and [notify_created at line 244](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/queries.py#L244).

After creating the request, notify_created catches an enqueue/fan-out failure, logs it, and returns success. There is no durable pending-notification marker on the query for a worker to reconcile. A retry of the same request does not call notify_created because the document is no longer newly inserted. The outbox worker cannot retry an event that never reached the outbox.

Fix: Persist a recoverable notification intent with request creation and process it idempotently. Test failure before the first outbox insert and partway through fan-out, including every query creation path. Keep customer request creation reliable without silently losing its alert. Audit campaign transition-to-sending followed by fan-out failure for the analogous stuck-send problem.

### F07 [P2] Account erasure does not cover the new completion ledger's customer details

Requirement: R15-B, R17-A.

Source: [completion-ledger personal fields at queries.py:561](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/queries.py#L561), [PERSONAL_COLLECTIONS at people.py:618](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/people.py#L618), and [cleanup_deletion at line 666](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/backend/shared/people.py#L666).

New completion rows store customer_name and shop_name. Cleanup anonymizes the request document but neither includes request_completions in its personal-data audit nor anonymizes those new ledger fields. The cleanup report can therefore omit surviving customer-identifying data.

Fix: Inventory every newly introduced personal-data store, including completion rows and notification outbox payloads. Preserve legitimate operational counts and attribution while anonymizing customer-identifying fields according to the documented retention policy. Explicitly report any justified retention; do not claim zero remaining personal records by checking only an outdated collection list. Add a completed-query-then-customer-deletion test.

### F08 [P2] In-app call and WhatsApp actions bypass the query claim workflow

Requirement: R11-B, R12-B.

Source: [frontend/src/components/staff/RequestDetail.tsx:94](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/frontend/src/components/staff/RequestDetail.tsx#L94).

Call/WhatsApp buttons are disabled only when the number is missing. They stay active for an unclaimed query and for one held by a different telecaller. They directly open the external app without a claim/revalidation step, even while the screen says another telecaller is working on the query.

Fix: For telecaller work actions, require a successful atomic claim first or revalidate existing ownership, and disable the actions when another telecaller owns the query. Keep deliberately authorized admin/billing exceptions explicit. Do not claim the app can prevent someone independently dialing a visible phone number outside the app.

### F09 [P2] Root-back handling is bound to mounting instead of navigation focus

Requirement: R01-A.

Source: [frontend/src/navigation.ts:42](https://github.com/amanagarwal1123-ctrl/YashTradeApp/blob/2093300ae7549281f6bacb1851f13bb082b7be7e/frontend/src/navigation.ts#L42).

useRootBackHandler registers a global Android listener in useEffect and always consumes the event. A root screen can remain mounted underneath another route, so its listener is not limited to the root actually being active. This risks swallowing Back from subsequent screens instead of returning to the previous page.

Fix: Scope registration to the focused root route/navigator and handle nested-tab/root detection explicitly. Verify hardware Back from product, image viewer, notifications, staff requests, keyboard, and modal states. Do not globally disable normal Back to prevent logout. React Navigation specifically advises focus-scoped subscriptions rather than mount/unmount effects for this pattern: [official custom Back guidance](https://reactnavigation.org/docs/custom-android-back-button-handling/).

Evidence level: Source/lifecycle finding, not a native-device reproduction.

## Readiness Gaps in This Commit

- APP_STORE_SUBMISSION.md is still absent from the fetched commit.
- IMPLEMENTATION_ACCEPTANCE_MATRIX.md contains stale states such as missing screens that now exist, and old baseline test results. It cannot substantiate current completion.
- frontend/package.json includes new notifications/keyboard dependencies, but the tracked frontend/yarn.lock has no entries for expo-device, expo-notifications, expo-rich-notifications, or react-native-keyboard-controller. Reconcile the lockfile and prove a clean frozen-lockfile install/build. That install was not executed in this audit; this is an observed manifest/lock mismatch, not a claimed build log.
- Native Android/iOS keyboard, pinch, OTP suggestions, notification delivery, iOS extension compilation/signing, and device screenshots remain outside this audit's evidence.
- Website code/deployment was not verified by this app-repository audit. A website handoff is not implementation.
- Full repository pytest, Jest, tsc, lint, and independent browser E2E were not rerun here. The saved snapshot does not have a matching installed dependency set or a local Mongo service in this review environment. The app chat's reported counts are not independent results from this audit.

## What Passed in the Focused Check

The saved MCX conversion helpers correctly converted 100000 INR/kg silver to 100 INR/g and 75000 INR/10g gold to 7500 INR/g, and round-tripped those values. This does not verify live stored-rate migration, every UI display, or every old-client scenario.

There is real implementation progress in the snapshot: shared query workspace components, upload-role permission gates, a cross-platform gesture component, shared keyboard handling, discovery consumption, push workers, and separate account actions are present. Their presence does not remove the findings above or complete native verification.

## Reproduction Artifacts and Results

Local audit files are outside the implementation snapshot:

- audit_repros_2093300.cjs: transpiles the actual saved api.ts using available Babel tooling and executes it with isolated native-storage/HTTP doubles. Both late-refresh cases reproduced.
- audit_repros_2093300.py: executes selected saved Python function bodies with dependency-injection wiring removed, isolated in-memory collections, a recording transport, and an injected ledger failure. Four issue reproductions and the MCX conversion control completed successfully.

These reproductions intentionally assert the defective behavior to demonstrate it. Their successful execution means the defects were observed, NOT that the app passes its acceptance tests. Convert them into regression tests that assert corrected behavior in the real project, including real isolated Mongo integration tests for database/concurrency semantics.

Commands used in the review workspace:

```text
node audit_repros_2093300.cjs
python audit_repros_2093300.py
```

No live SMS, real-device push, production account mutation, production reset, database migration, deployment, or store submission was performed.

## Instruction for the Implementing Chat

Reconcile F01-F09 with the current working tree and fix all still-applicable findings as part of the ongoing R00-R17 job. Do not restart, overwrite newer work, or drop the original scope. Add focused regression/fault-injection tests, run the full required checks, and include the two-telecaller customer-query journey in independent E2E testing. Record addressed commit/test evidence for every finding and distinguish source changes from actual native/website verification.

Return final GitHub commit IDs, updated acceptance and release documents, and any genuinely blocked gates. Do not describe this review as approval to release.
