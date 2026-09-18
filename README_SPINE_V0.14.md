# PhiOS Spine v0.14 - Live Loopback HTTP Observation

Spine v0.14 activates the bounded local HTTP response contract through an explicit standard-library loopback adapter.

```text
explicit local HTTP claim
      ↓
reality.verify
+
reality.local_http.read
      ↓
strict loopback resolution
      ↓
bounded GET, no redirects
      ↓
status + safe headers + bounded body digest
      ↓
content-addressed observation evidence
      ↓
RealityReceipt
```

The Reality Gate core remains transport-agnostic and fail-closed by default.

See `docs/PHIOS_SPINE_V0.14_LOCAL_HTTP_ADAPTER.md`.
