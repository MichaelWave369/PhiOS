# PhiOS v0.63: disconnected Chromium reload, separate experimental offline profile

**Proposed proof, not production installation.** The v0.62 check proved browser
interactions and HTTP reload **while the localhost server remained available**.
This v0.63 rung tries a stronger, explicitly bounded experiment: reload both
web apps after the only static HTTP server is **closed** and Chromium's network
is set **offline**.

## How the separate derived packages are prepared

1. Compile immutable-source Vessie and ThinkTank and install the unmodified
   v0.61/v0.62 static staging packages with the pinned MIT-licensed Trellis.
2. Run the existing byte-for-byte staged verification first. Any changed file,
   forged receipt, bad profile lock, symlink, or source drift stops the process.
3. Create an isolated copy of each verified payload with a **new package
   identity**, `phios-vessie-web-offline` or
   `phios-thinktank-web-offline`. Do not modify upstream Git source,
   the normal staged package, the installed PhiOS system, or any ISO.
4. Add a first-party `phios-offline-bootstrap.js` to the derived HTML and
   generate `phios-offline-sw.js` with a manifest of every other static
   file's SHA-256. The service worker precaches each file **only after checking
   its digest** and serves only that allowlisted static shell from CacheStorage,
   with **no fallback to the network**.
5. Write an offline-profile receipt tying source commit, original payload
   checksum, derived checksum, manifest fingerprint and individual file hashes.
   Install the derived package in a **separate disposable Trellis home**,
   run Trellis `verify`, and independently rehash **all installed bytes**.
6. Open the derived shell in a fresh Chromium context with service workers
   enabled. Demand that it controls the page and has completed the pre-cache.
   **Close the HTTP server**, then call `browserContext.setOffline(true)` and
   reload. Require HTTP 200 with `response.fromServiceWorker() === true`,
   an identical initial React-root text digest, and one reviewed local-only
   interaction: GA108 filtering for Vessie, AUDIT selection for ThinkTank.
   Unexpected requests, uncaught errors, missing cached assets or WebSocket
   activity cause failure.

No provider request is ever allowed to run. ThinkTank's fixed eight localhost
health checks remain unserved; those attempts are separately observed where
the browser API exposes them. Neither app starts a model or executes a live
operator instruction.

## Strictly held claims

A PASS **does prove** a Chromium browser with an already-installed verified
service worker can reload and interact while its static HTTP server is stopped
and browser network emulation is offline. The derived package is an
**experimental shell profile**, not proof that the original unmodified
applications are offline-ready.

A PASS **does not prove** an air-gapped computer booted PhiOS, that apps cold
start after a browser/process reboot, that a service worker survives
cache eviction, that all views and workflows function, or that Ollama/providers
work offline. It does not authorize a desktop launcher, write production
AppRegistry state, grant one-use execution, ship binaries in an ISO, audit
transitive npm licenses, or declare external DONE.

Existing v0.61/v0.62 startup and interaction tests, package integrity and
tamper rejection remain required. Frontend npm dependency resolution still
lacks frozen reviewed lockfiles. Only source and stage contracts, including
separate SHA-256 receipts, are pinned; successful transitive npm builds are
**not reproducible** from source pins alone.

**Ledger Above Ego. DONE Means Verified.**
