# Release readiness — not a release approval

## Implemented and tested in workspace

Canonical revocable OTP/session service, staff scopes and role adapters, grant-backed enrollment, profile/phone changes, local deletion/tombstones and website deletion outbox; unified paginated queries and atomic events/metrics; billing rate/slab permissions; permanent image service/gallery selection; native-compatible reviewed PDF UI and durable-checkpoint service; versioned actual PDF sample/generator; private migration dry-run contract/tool.

Evidence: TypeScript build and Python compile;27 shared backend tests together;4 authenticated mobile-web routed-browser journeys; corrected upload-phase test. See reports and contracts. External providers are intercepted in tests; this is not a claim of delivered production SMS or real object-storage outage recovery.

## P0 release gates — unresolved
Latest combined result: **31 passed** in `test_reports/pytest/shared_final.xml`. Static build/test success does not close the release gates below.


- No production deployment performed; production observed old v7, exact artifact commit unavailable. New changes have not been verified as synced to GitHub.
- No website code changes, verified identity export, restorable backup or specific migration approval. Owner admin target is documented, not applied. Other conflicts remain unadjudicated.
- Separate STAFF_SERVICE_KEY missing locally; provision privately and rotate exposed/default integration/JWT keys on both systems. Coordinate old-client reauthentication and enrollment write contract cutover. Real OTP delivery on current target production is unverified.
- Play Console review access not provisioned. No fallback fixed OTP is introduced. Need isolated role identities/sample data that exercise the same features without accessing genuine customer/billing records; private external handoff only.
- Account deletion removes/anonymizes local records and prevents automatic resurrection, but provider-held data, legacy unowned chat, website caches/outbox and complete cross-system retention are not verified. Required-retention decisions need actual business/legal scope; do not use a blanket “business record” to retain personal profile fields.
- Full PDF negative/chaos matrix and physical native tests remain incomplete. Configured64MiB/200page limit is not proven on production resource budget. Managed-storage source/chunk purge and long-term orphan-media cleanup need provider-supported deletion confirmation.

## Privacy/Data Safety inventory to validate against actual release

| Data/use | Actual path to inspect | Review needed |
|---|---|---|
| Name, phone, shop, location, consent | Canonical Mongo + website cache/outbox | Purpose, retention, deletion acknowledgement, country/jurisdiction |
| Phone and OTP SMS transport | MSG91 Flow / delivery diagnostics | Processor terms, routing/log retention, deletion capability |
| AI prompts/answers/report reason | Existing LLM integration and chat/report storage | Provider retention, unsafe-content handling, user reporting, access ownership |
| Product/catalog photos & PDF source | Managed object storage + private previews/local temporary cache | Public vs private access, orphan/source retention, purge support |
| Camera/media/document files | Expo image/document picker and filesystem | Actual native permission declarations, on-device caching, user disclosure |
| Enquiries, staff activity, rewards/billing | Request ledger, lead/reward collections | Internal access, retention basis, pseudonymization, third-party logs |
| Sessions and diagnostics | SecureStore/native; website server cookies; SMS logs | Redaction, revocation, access/refresh expiry, backup retention |

Do not mark every Data Safety sharing answer “No” without reviewing the actual SDK/provider processors and Google's definitions/exemptions. Website privacy policy and store declarations must match the shipped binary and operational provider retention, not just this code diff. AI Try-On stays removed; separate AI assistant still exists and has authenticated history/report handling.

## Platform evidence limits

Static configuration follow-up: explicit CORS origin allowlist added (no wildcard); allowed website preflight and rejection of an untrusted origin both verified. Workspace Expo supervisor now uses `--tunnel`; tunnel-ready logs and a fresh mobile login screenshot verified. This container-level supervisor setting and ignored environment file must be checked independently on the target runtime; they are not proof of a production rollout.

A subsequent static-check report incorrectly claimed the supervisor file was absent and recommended committing secret-bearing `.env` files. Independent read-only verification confirmed the file and running services. Real `.env` files remain excluded from Git; only a names-only example is supplied. Startup cart deletion was removed to honor data-preservation requirements. Never “fix” a static-check false positive by publishing secrets.

Mobile web:390×844 screenshots and signed-in role flows via local Playwright+isolated ASGI. Native code uses SDK54-compatible DocumentPicker/FileHandle/SecureStore/Sharing, but no physical Android/iOS, emulator, Expo Go device or release build was run here. Gesture navigation, three-button navigation, home indicator, native file-provider permission lifetime, share/open handoff and OS process/background recovery remain device acceptance checks.