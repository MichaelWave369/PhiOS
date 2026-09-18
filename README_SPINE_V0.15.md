# PhiOS Spine v0.15 - Local HTTP JSON Contract Verifier

Spine v0.15 adds bounded semantic verification above the v0.14 live loopback HTTP adapter.

```text
explicit loopback HTTP JSON claim
      ↓
reality.verify
+
reality.local_http.read
+
reality.local_http.semantic.read
      ↓
bounded GET
      ↓
complete body within budget
      ↓
strict JSON parse
      ↓
exact JSON pointer
      ↓
expected JSON type
      ↓
redacted semantic evidence
      ↓
RealityReceipt
```

The response body is available only transiently for semantic inspection and is not serialized into the evidence record.

See `docs/PHIOS_SPINE_V0.15_LOCAL_HTTP_JSON_CONTRACT.md`.
