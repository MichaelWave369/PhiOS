# PhiOS v0.62: reviewed local UI interactions + HTTP reload

**Evidence scope:** two deliberately bounded, actual Chromium interaction sequences
against Vessie and ThinkTank built from the existing immutable source pins,
installed into disposable Trellis staging homes and rehashed before startup.

This rung extends [v0.61](PHIOS_TRELLIS_BROWSER_SMOKE_V0.61.md), rather than
asserting that a working production PhiOS desktop or air-gapped application exists.

## Test sequence, exactly as reviewed

- **Vessie:** navigate to the GA108 Atlas; filter the existing 108 identities
  down to zero with a nonsense query and restore all 108; navigate to Receipt
  Inspector; enter invalid JSON and verify a browser-local error is displayed;
  reload the HTTP page and verify the overview returns.
- **ThinkTank:** choose **AUDIT** in the browser-only collaboration mode strip;
  observe its selected visual state; reload and verify initial **COUNCIL**
  mode is restored. **No simulation run, FORCE SYNTHESIS, backend request or
  user grant** is part of this browser test.

Both are performed with Chromium against the actual Trellis-installed React
frontends, using the read-only loopback server from v0.61. No test touches
production AppRegistry or the installed PhiOS filesystem.

## Network boundary and evidence

- All non-static HTTP requests are denied. The eight fixed ThinkTank
  `127.0.0.1:3691` **GET status requests** are also denied and separately
  recorded as an unavailable local backend. All WebSocket attempts fail.
- Service workers are blocked and browser permissions are empty.
- After reviewed interactions, the browser performs a **fresh HTTP reload
  while the loopback HTTP server remains available**, then asserts that the
  expected initial UI returns with no missing static resources, uncaught JS
  errors or unreviewed network attempts.
- One diagnostic JSON per app records the exact reviewed step names,
  browser version, UI text digests and character counts, network attempts
  and explicit negative authority flags. Raw user-entered inputs, page
  contents and tokens are not recorded in evidence.

**Critical limitation:** This verifies a connected-to-local-server browser
reload, **not** reload after disconnecting Wi-Fi, losing the loopback server,
restarting PhiOS, replaying PWA cache, or attempting a true air-gapped app
boot. Those remain **NOT VERIFIED**.

The pinned frontend sources still lack reviewed npm lockfiles. The Vessie
derived build explicitly strips the one reviewed Google Fonts import as
documented in v0.61. License closure, full app workflows, provider
connections, model inference, desktop launch and operator-approved
installation remain held.

## Review boundary

A green v0.62 interaction check neither promotes nor installs applications.
Only the existing PhiOS App Platform, one-use operator approvals and
auditable receipts may eventually perform promotion. It does not supersede
separate full PhiOS qualification or QEMU image tests.

**Ledger Above Ego. DONE Means Verified.**
