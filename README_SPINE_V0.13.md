# PhiOS Spine v0.13 - Local HTTP Response Verification Contract

Spine v0.13 freezes the bounded Reality Gate contract for loopback HTTP response observations.

The verification core can evaluate injected HTTP observations, but the default transport provider fails closed. Live HTTP I/O remains a separate adapter responsibility.

```text
explicit loopback HTTP claim
      ↓
strict URL contract
      ↓
provider seam
      ↓
content-addressed observation evidence
      ↓
RealityReceipt
```

See `docs/PHIOS_SPINE_V0.13_LOCAL_HTTP_VERIFIER.md`.
