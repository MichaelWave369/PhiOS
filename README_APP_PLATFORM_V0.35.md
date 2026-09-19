# PhiOS App Platform v0.35

PhiOS App Platform v0.35 adds the **Static-Web Runtime Adapter Contract**.

v0.34 can launch direct Node and Python installed files. v0.35 adds a separately reviewed path for
receipted built web output such as Vite `dist/` and React Scripts `build/`.

The adapter is intentionally **server-only**.

```text
serve static files
≠ launch a browser
≠ execute application JavaScript in the server
≠ grant browser permissions
```

## Pipeline

```text
v0.33 install receipt
        ↓
reverify complete installed tree
        ↓
verify installed package-plan metadata
        ↓
inspect receipted artifact topology
        ↓
unique known static output?
        ↓
static-web adapter plan
        ↓
review exact plan SHA + loopback port
        ↓
explicit approval
        ↓
reverify install + static subtree
        ↓
trusted Python static server
inside Bubblewrap
        ↓
127.0.0.1:PORT
        ↓
bounded foreground serve window
        ↓
static-web serve receipt
```

## Deterministic output mapping

v0.35 currently recognizes only:

```text
dist/index.html   → static root dist/   → vite_dist_index
build/index.html  → static root build/  → react_build_index
```

The evidence comes from the installed v0.33 package artifact list.

PhiOS does not derive a built runtime target from `package.json`.

If both roots are present, mapping is ambiguous and fails closed.

If neither root is present, the plan remains inspectable but not serveable.

## Network boundary

The trusted static server binds exactly:

```text
127.0.0.1:REVIEWED_PORT
```

The server sandbox inherits host networking because the host browser must be able to reach that
loopback listener.

That is recorded honestly as host-network inheritance.

It is **not** described as a network namespace or network allowlist.

## Browser boundary

v0.35 does not launch a browser.

The plan and receipt both record:

```text
browser_launch_authority = false
application_code_executed_by_server = false
```

Manifest runtime permissions are recorded for review but deferred. They are not granted to the
trusted static-file server.

## Commands

Create a plan:

```bash
phi-app plan-static-web install-receipt.json \
  --loopback-port 8787 \
  --serve-seconds 300 \
  > static-web-plan.json
```

Review:

```bash
phi-app review-static-web static-web-plan.json
```

Serve only after approving the exact plan:

```bash
phi-app serve-static-web \
  static-web-plan.json \
  install-receipt.json \
  --approve-static-web-plan-sha EXACT_STATIC_WEB_PLAN_SHA256
```

The serve session is bounded. Reaching the reviewed timeout produces a normal
`serve_window_complete` receipt.

See `docs/PHIOS_APP_PLATFORM_V0.35_STATIC_WEB_ADAPTER.md`.
