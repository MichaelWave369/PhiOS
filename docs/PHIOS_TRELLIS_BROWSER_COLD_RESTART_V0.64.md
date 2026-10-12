# PhiOS v0.64: new Chromium process cold-starts a cached offline Trellis shell

**Status: proposed, read-only, CI-only proof for two previously reviewed app
candidates.** This is stricter than [v0.63](PHIOS_TRELLIS_DISCONNECTED_V0.63.md),
which proved a disconnected reload **in the same browser process**.

## What this verifies

CI starts from the same fixed Vessie and ThinkTank upstream revisions,
reviewed relative-path builds, the **separate** experimental Trellis
offline-profile artifacts, and independent package/byte verification.
No upstream code or production PhiOS files are modified.

For each reviewed offline-profile app, an original Node/Chromium test:

1. Starts a disposable localhost static server for only its verified package.
2. Launches Chromium **process A** with a fresh on-disk user profile. It
   loads the page, waits for service-worker control, and checks the previously
   digest-verified cache is populated.
3. **Closes process A entirely**, then **shuts down the HTTP server**.
4. Launches Chromium **process B** with the **persisted profile**, sets
   browser network emulation offline **before app navigation**, then opens
   the same URL. The document must return HTTP 200 **from the service worker**
   with matching React-root text digest and matching cached-file count.
   Vessie's GA108 filter or ThinkTank's AUDIT mode selection must work.
5. Runs a **negative control** using a distinct **never-warmed profile**
   while offline and with the server stopped. It must not load or mount.
6. Stores concise review receipts; deletes both disposable browser profiles.

An unexpected external request, WebSocket, uncaught JS exception, broken
asset, UI drift, unsafe interaction, or unprimed cold start fails closed.
ThinkTank's known local health probes remain blocked and logged, never
executed.

## Explicit limitations

**This is a browser-process restart and cached offline navigation test.**
It is **not** an air-gapped physical machine boot, a complete PhiOS desktop,
QEMU installed-app startup, power-loss recovery, cache-eviction resilience,
all app functions, or model/provider operation. Chromium launches in CI;
network emulation is switched off after browser launch and before its app
navigation, not before the operating system starts.

Frontend dependency resolution still lacks verified npm lockfiles and full
transitive license review. No app installation, execution grant, model access,
production ISO bundle, or external DONE authority is issued. Prior v0.60–0.63
checks and normal PhiOS qualification remain independent gates.

**Ledger Above Ego. DONE Means Verified.**
