# PhiOS R0.7: PhiARK operator-approved local gateway

**Scope:** Linux-only, bounded developer integration for an **already running** private PhiARK Unix socket. This is not governed app installation, PhiOS launch authority, a permanent daemon, or a release-ready multi-user gateway.

## Why

PhiARK #8 supplies a private Unix-domain socket without opening an application TCP listener. PhiOS R0.6 can observe local PhiARK bytes but cannot launch it safely: its current generic Bubblewrap runtime only denies all networking or inherits broad host networking. The R0.7 bridge is deliberately a **separate, human-started host-side process**. It forwards only read-only, recognized PhiARK paths from host loopback to a private Unix socket, with no general proxy facility.

## Preflight and operator action

First, on a trusted Linux machine with Node.js 20+, launch **already-reviewed PhiARK source** manually using its R0.6 instructions, private data root, and PHIARK_SOCKET_PATH. Never use a stranger's repository or an unreviewed download.

Then:

~~~sh
phi-phiark-gateway plan --data-root "$HOME/.local/share/phiark-vault" --port 3692
~~~

Review the non-authoritative plan including its exact private socket inode/device and SHA-256. To deliberately start the **separate local browser gateway**, with exact plan digest, run:

~~~sh
phi-phiark-gateway serve --data-root "$HOME/.local/share/phiark-vault" --port 3692 --approve-plan-sha <reviewed-plan-sha256>
~~~

The foreground terminal prints an operator-only one-time browser activation URL with its capability token in the URL fragment. Do not share or paste that link into chats/logs. The fragment is not submitted in HTTP URL requests; the local activation page exchanges it for a HttpOnly, SameSite=Strict, one-hour session cookie. Close the terminal with Ctrl+C to stop the gateway. An HTTP request without a valid session receives 403.

## Bounded behavior

- Only Linux, only 127.0.0.1, only explicit nonprivileged port.
- Private root (0700, owner), owner-only Unix socket (0600), no symlink path components, exact inode/device bound to reviewed plan. Fail closed if changed.
- Preflight GET /api/status through **only** the Unix socket; validates shape but does NOT attest process identity or source SHA.
- One-time random activation capability and independent session token, strict Host/Origin/Referer/Sec-Fetch-Site policy, no CORS, no remote fonts/scripts.
- Only GET/HEAD for /, /app.js, /style.css, /api/status, /api/items, /api/search, /api/kiwix and documents by SHA-256 ID. No arbitrary proxy destination; no upstream POST, updates, shell or filesystem writes.
- Private document bytes still undergo PhiARK's own R0.5 full hash-verification prior to delivery. PhiOS does not independently reverify each streamed byte.
- Bound upstream response size, disabled access logging, no persisted browser tokens.

## Explicitly still missing

- PhiOS exact-commit acquisition and artifact receipt; verified Node 20+ toolchain; data mount and environment mapping through Bubblewrap.
- Approved integrated app launch/stop; desktop catalog installed/running/blocked evidence; signed release handoff and rollback.
- Physical demonstration that the PhiARK service is **inside a network-denied sandbox**, with no unintended outbound traffic.
- Independent security review of this diagnostic gateway, especially multi-user local threats. A private socket is not strong isolation from other same-user processes.
- True WAN-disconnected cold-start after PhiOS service restart, successful local search/read/hash checks and corruption refusal.
- Kiwix archive/reader and downstream license governance. No archive is preinstalled by this change.

**Release gate:** Do not mark PhiOS issue #321 complete or grant broad runtime.network.inherit on the strength of this bridge.

Related: https://github.com/MichaelWave369/PhiOS/issues/321 and https://github.com/MichaelWave369/PhiARK/pull/8
