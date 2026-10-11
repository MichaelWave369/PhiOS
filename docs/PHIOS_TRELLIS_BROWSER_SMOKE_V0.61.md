# PhiOS v0.61: first Trellis-installed browser startup gate

**Status:** proposed read-only browser startup smoke for exactly two staged React frontends.
This does **not** authorize installation into PhiOS, a desktop launcher, local/cloud
model access, or any external DONE assertion.

## What CI now measures

The existing v0.60 path checks out fixed Vessie/ThinkTank source SHA pins,
compiles their frontends with relative `./assets` paths, builds MIT-licensed
Trellis from fixed commit `8c8f54f1539c688fd02247f82c9bd48d0b5444c1`,
and installs both packages only into two isolated runner temporary Trellis homes.
Before packaging, the separate, explicitly labeled **Vessie offline CSS profile**
removes **exactly one reviewed** Google Fonts `@import` from the *compiled
output only* and records its before/after SHA-256. The pinned upstream source
commit is unchanged. System font fallbacks render the UI without trying to
reach Google Fonts. A changed import, additional external CSS URL or absent
expected import fails closed. This is a **derived build profile**, not an
unmodified upstream compiled artifact, and not a redistribution/license approval.

The pre-existing bridge then checks **every installed byte** of those resulting
built assets against its payload hashes, receipts and profile locks.

After byte verification, v0.61 runs each **actual Trellis-installed**
`index.html` using a temporary HTTP server bound **only to 127.0.0.1** and
the GitHub-hosted Chromium/Chrome browser through a pinned CI-only
`playwright-core@1.56.1` driver. Browser service workers are disabled.
All non-loopback HTTP requests and all WebSockets are blocked. Each app must
mount a nonempty React root, load at least one compiled JS resource, and have
no uncaught page exceptions, local 4xx/5xx asset responses or attempted
external requests. The browser and HTTP server are stopped after each probe.

The CI job runs both applications even if one browser check fails, so a
failure for Vessie does not conceal ThinkTank evidence. The separate font
adaptation receipt is captured next to the browser reports.

Two small JSON reports are retained as CI **diagnostics only**. They include
status, browser version, visible-text digest (not page text), attempted egress,
asset errors and explicit denied authorizations. Browser results do not alter
the installed system, app manifest, Trellis package, ISO or AppRegistry.

The contract tests use Node's built-in runner to prove that unsupported app
names, symlinked home roots, hidden files and path traversal are refused.

## What PASS does *not* mean

- It does **not** mean full air-gapped device startup, offline reload, PWA
  caching, every application view, working provider APIs, local Ollama,
  model execution or a functional desktop launcher.
- This is a **hosted Chrome browser with loopback-only serving and network
  interception**; it is not a production PhiOS graphical session.
- The React source pins are immutable, but the upstream checkouts do not
  contain npm lockfiles. Frontend transitive dependency resolution and the
  temporary test-driver install are not reproducible from this evidence.
- Trellis MIT licensing is checked at its pinned revision; embedded software,
  third-party assets, package payloads and frontend dependency licenses
  still need separate review before redistribution.
- No one-use execution grant, v0.38 desktop approval, persistent install
  receipt, launch authorization or external DONE is issued.

A failing browser test is a real hold on **browser startup evidence**.
It does not invalidate independently passing source/packaging or ISO gates,
and an unrelated passing image test cannot override a failed browser check.

**Next:** independently pin/audit both frontend dependency graphs; add deliberate
air-gapped reload/interaction tests and, later, operator-authorized desktop
promotion using the existing PhiOS App Platform. Do not auto-promote on a
browser smoke PASS.

**Ledger Above Ego. DONE Means Verified.**
