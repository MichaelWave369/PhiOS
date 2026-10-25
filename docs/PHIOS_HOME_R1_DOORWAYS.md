# PhiOS Home R1: Infinite Porch and Commons operator-opened doorways

**Status: first UI handoff candidate, not a live AI or Commons integration.**

From PhiShell **Home**, show two explicit links: local Porch control UI at `http://127.0.0.1:7331/`, and the documented public Infinite Commons browser destination. Both links require a human click, open a separate tab, use `noopener noreferrer`, and never submit credentials, call a backend, start a model, connect a peer, or install an app.

The local link only works if the operator separately installed and launched the actual Infinite Porch node on their machine. Porch maintains its own strict loopback-only control API and requires its own operator token; PhiOS does not load or pass that token. The public Commons destination needs user-chosen network access and does **not** confer PhiOS app permissions. No claimed LIVE status is inferred from a URL or an open tab.

## Existing boundaries intentionally preserved

- App Platform v0.25–0.58 governs actual installs, launches, updates, reviews and rollbacks. UI links are NOT AppManifest or launch grants.
- First-wave Vessie and ThinkTank proposals remain held for operator review.
- The 16-project foundation topology is source-review metadata, not a production service graph.
- No privileged API, OS service adapter, host process probe, local port scan, model inference, cookies, CORS, remote credential transport, wildcard iframe, or state persistence.
- No service readiness, physical-device qualification, offline capability or native PhiKernel boot claims.

## Tests

Run `cd phishell && npm ci && npm test && npm run build`. The React server-rendering unit tests verify both fixed URLs, explicit non-readiness labels, safe external-link attributes, and absence of form/iframe authority shortcuts. Test success proves only UI markup and bundling; it does not prove the real Porch UI is installed, authenticated, usable on hardware, or reachable offline.

## R2 acceptance prerequisite (not implemented)

The next rung is a **separately authorized, strictly read-only, same-origin PhiShell local transport adapter**, with positive identity binding and exact-versioned normalized Porch status (not just a port-open guess). It must be operator-initiated, fail closed on unexpected origin/response, never inspect or forward the Porch operator token, and never silently turn on model/peer sharing. Before production, validate on actual independently started Porch across the intended device/OS with negative controls for missing node, swapped identity, bad token, stale result, malformed JSON and shutdown.

**Ledger Above Ego.**
