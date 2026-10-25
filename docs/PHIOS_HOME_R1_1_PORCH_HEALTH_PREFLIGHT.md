# PhiOS Home R1.1: operator-initiated Infinite Porch health preflight

**Scope:** an optional, click-initiated local health preflight on the already-existing PhiShell Home screen. It is **not** authenticated pairing, model discovery, an installed Porch service, an AI provider connection, or native OS validation.

## Exact behavior

- From the existing `InfiniteHomeDock`, the operator may select **CHECK LOCAL PORCH HEALTH**.
- The browser makes one **same-origin** GET to PhiShell's fixed local transport endpoint `/api/v1/porch-health-preflight` with a non-secret preflight header. This is not a credential.
- Only when requested does the local PhiShell Node server make one bounded GET to the fixed literal `http://127.0.0.1:7331/health` using a 1.5-second abort timer, no login token, no redirects, and an application/json response limit of 1024 bytes.
- Porch 0.1.2's public `/health` response has exactly `status:READY`, `protocol_version:1`, and an explicit candidate version. It is intentionally **unauthenticated**.
- A correct-shaped response is displayed only as **PORCH-LIKE RESPONSE / IDENTITY NOT VERIFIED**. Malformed, unavailable, cross-origin and unsupported responses fail closed. The result is never a model, peer, account, network or operating-system authority grant.
- No automatic requests on mount, startup, refresh, or website navigation. If the browser is showing a purely static Pages build instead of the local PhiShell transport, the check reports unavailable.
- Existing manual Porch/Commons links remain as they were. Never copy or share `state/api.token` with PhiOS: Porch remains responsible for authenticating its own UI.

## Why health cannot be treated as proof

A different process bound to port 7331 can trivially imitate the public response. Therefore matching these three fields does **not** prove who is responding, that the executable is a reviewed commit, that any Porch identity is trusted, that Ollama or remote peers work, or that production security review happened.

Authenticated identity binding needs a separate explicit operator-run handshake against a signed key whose fingerprint is checked through an independent trusted channel, with carefully scoped token isolation. Do not infer trust or enable sharing from this preflight.

## Verification

```shell
cd phishell
npm ci
npm test
npm run build
```

The added Node tests cover the exact single fixed-target GET, strict health-response envelope, no authorization header, negative cases for wrong fields, oversized/redirect/error responses, lack of mutation authority, and local transport refusal for cross-origin/missing manual header/unexpected query or method.

This PR is only a **preflight rung** after Foundation #319 and doorways #320. Actual hardware/Porch service identity tests are not satisfied by source CI. Future ΦOS Home R2 work must bring separately approved authenticated status, negative controls, model endpoint qualification, and explicit operator grants without ever sharing Porch credentials with the web shell.

**Ledger Above Ego.**
