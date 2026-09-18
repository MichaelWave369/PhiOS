# PhiOS Spine v0.6 - SOMA Acuity Recovery

Spine v0.6 adds deterministic recovery for preserved screen evidence:

```text
native frame -> tight crop -> native enlargement
```

The original frame is never overwritten. Every derived image receives its own SHA-256 evidence reference and explicit derivation chain.

Recovery requires the separate explicit grant:

`perception.screen.recover`

Native enlargement uses nearest-neighbor pixel replication, not generative super-resolution.

See `docs/PHIOS_SPINE_V0.6_ACUITY_RECOVERY.md`.
