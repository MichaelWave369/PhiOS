# PhiOS v0.60 — ThinkTank Web hosted build-and-render pilot

## Status: HOSTED BUILD / BROWSER REHEARSAL ONLY

This rung exercises an **actual pinned ThinkTank React frontend** instead of merely rendering
its proposed PhiShell catalog tile. It does **not** install or launch a PhiOS application
inside the OS, create an App Platform receipt, grant browser permissions, or boot an ISO.

- Candidate: phios.thinktank-web from the existing v0.59 candidate manifest
- Repository: https://github.com/MichaelWave369/think-tank
- Source pin: 1e8084a684ccf400c37d05d8bfe992680a72e887
- Frontend build: npm run build, producing dist/index.html and dist/assets/
- Workflow: .github/workflows/thinktank-web-pilot.yml
- Verification: scripts/thinktank_web_pilot.py

## What actually executes

On a GitHub-hosted Ubuntu runner, the workflow:

1. Checks out the exact reviewed ThinkTank source SHA with read-only credentials.
2. Validates the existing PhiOS candidate manifest and refuses source drift.
3. Generates an **ephemeral** package-lock.json, because the pinned ThinkTank repository
   **does not contain a committed npm lockfile**. This is an observation, **not reproducible
   dependency provenance**.
4. Runs npm ci, upstream npm test, and the real upstream npm run build.
5. Runs npm audit --audit-level=high; advisories block the pilot rather than being hidden.
6. Rejects missing, escaping, symlinked, oversized, or externally hosted
   entrypoint assets. Hashes the complete static file set.
7. Serves only dist/ on a disposable 127.0.0.1 HTTP port. Starts headless Chrome
   with a temporary profile and disabled background networking; checks the
   actual React ThinkTank room mounts in the browser.
8. Uploads a **review-only JSON receipt**, **not** the distributable bundle,
   installed model, browser profile, temporary lockfile or runtime state.

Only the hosted runner's checkouts and disposable working directories are touched.
No permission to execute the ThinkTank provider bridge is granted. The workflow never
runs the provider-bridge command. Chrome has the runner's host networking, so DNS
suppression is **not proof of kernel-enforced network isolation**.

## Evidence boundaries

| Question | Status even when workflow passes |
| --- | --- |
| Actual ThinkTank React UI rendered in hosted browser? | **PASS** if observed |
| Exact source commit checked? | **PASS** if matched |
| Installed PhiOS application? | **NO** |
| Offline dependency closure and reproducible source lock? | **UNVERIFIED** |
| Transitive assets and dependency redistribution approved? | **UNVERIFIED** |
| App Platform v0.26–v0.57 install/desktop grant? | **NOT RUN** |
| Browser egress denied by kernel sandbox? | **UNVERIFIED** |
| ThinkTank provider bridge authorized or running? | **NO** |
| App-enabled ISO boot, persistence, update and rollback in QEMU? | **NOT RUN** |
| Independently verified production deployment? | **NO** |

A green hosted pilot does **not** change the v0.59 catalog's
HELD_FOR_OPERATOR_REVIEW candidate state or any false verification fields.

## Remaining gates toward first real PhiOS installation

1. **Commit a reviewed npm lockfile in ThinkTank upstream** and pin the candidate
   to the new commit. Use npm ci against that committed lock without generation.
   Review any dependency audit findings.
2. Inventory transitive dependencies and static asset licenses. Explicitly
   approve or refuse redistribution.
3. Execute the **existing** PhiOS intake -> source acquisition -> dependency staging ->
   bounded build -> artifact inspection -> package installation -> static-web adapter ->
   browser review -> desktop grant pipeline, preserving SHA-bound receipts.
   Do not invent a second installer.
4. Verify disconnected loopback startup and refusal of disabled provider-bridge
   operations, provenance tampering, and unauthorized network access in an isolated guest.
5. Boot an app-enabled PhiOS image in QEMU; verify desktop launch, state persistence,
   update, rollback and permission denial before external DONE.

**Ledger Above Ego. DONE Means Verified.**
