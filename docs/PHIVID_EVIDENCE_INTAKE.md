# PHIVid Evidence Intake

PhiOS can now validate the portable envelope emitted by PHIVid without admitting it to the Reality Ledger.

## Validation boundary

The intake parser verifies:

- exact `phivid.phios_evidence_envelope.v0.1` fields,
- `phivid.render.verified` event type,
- producer identity `PHIVid`,
- lowercase SHA-256 source receipt identity,
- explicit zero operational/action/execution authority,
- non-empty, sorted, unique evidence references,
- every nested object through PhiOS's own `EvidenceRef.from_dict()`,
- exactly one output EvidenceRef,
- output evidence kind `phivid.video.render`,
- canonical envelope SHA-256.

## No admission side effect

Successful validation returns `PHIVidEvidenceIntake` with:

- `ledger_admitted=False`,
- `operational_authority=False`,
- `action_authority=False`,
- `execution_authority=False`.

The parser performs no filesystem writes and never appends to the Reality Ledger.

This preserves the boundary:

```text
PHIVid evidence envelope
        |
        v
PhiOS contract validation
        |
        v
validated intake object
        |
        X  no automatic admission
        |
        v
future policy/admission decision
```

## Why PhiOS parses the nested references itself

PHIVid mirrors the EvidenceRef schema for interoperability, but PhiOS remains authoritative for its own evidence contract. A nested reference that has been modified after creation is rejected by `EvidenceRef.from_dict()` even if an attacker recomputes the outer envelope hash.
