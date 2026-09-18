# PhiOS Spine v0.3 — North Gate / SOMA Perception

Spine v0.3 implements the first executable **Perception Gate** path from the PhiOS Mandala architecture.

The scope is intentionally narrow: deterministic text perception with native-source preservation and typed receipts.

## Transaction

```text
external text input
        ↓
MandalaPacket(PERCEPTION)
        ↓
GateReceipt
        ↓
native evidence store
        ↓
optional deterministic recovery transforms
        ↓
PerceptionReceipt
        ↓
eligible for later Deliberation / Memory gates
```

## Invariants

1. Native evidence is preserved byte-for-byte in a content-addressed local store.
2. Transformations are explicit and recorded.
3. Transformations do not increase epistemic or execution authority.
4. Observation is not truth.
5. Unsupported transformations quarantine the derived observation instead of inventing output.
6. Empty input is DEGRADED, not silently repaired.
7. Perception does not mutate the Phi Core authority envelope.

## Native evidence

Evidence is stored at:

```text
<state-root>/evidence/native/<sha256>.txt
```

The receipt uses a stable reference:

```text
evidence:sha256:<digest>
```

v0.3 does not read arbitrary filesystem paths. The caller supplies the text to the gate. File, screen, browser, camera, and device adapters can be added later behind their own bounded acquisition contracts.

## Deterministic transforms

Supported in v0.3:

- `strip_utf8_bom`
- `normalize_newlines`

These are recovery operations, not generative enhancement.

If a transform actually changes the observation, acuity becomes `recovered`. If no recovery is needed, acuity remains `native`.

Unsupported transforms produce:

```text
status = QUARANTINED
acuity = unavailable
native evidence = preserved
derived observation = absent
```

## MA-002 progress

This release implements the first concrete MA-002 behavior:

> external observations retain native provenance or are explicitly marked unavailable/degraded.

It does not yet implement image capture, OCR, screen reacquisition, browser evidence, sensor input, or model interpretation.

## CLI

```bash
phi-spine perceive \
  --source-id operator \
  --text $'hello\r\nworld' \
  --transform normalize_newlines
```

The CLI prints packet, native evidence metadata, and the PerceptionReceipt. It does not echo the perceived text unless requested by code through the Python API.

## Future North Gate work

Later SOMA phases can add:

- bounded file acquisition;
- screen-region capture;
- native reacquisition;
- acuity recovery ladders;
- browser/source adapters;
- image/video evidence;
- interpretation separated from native observation;
- Reality Gate promotion.

Those additions must preserve the v0.3 rule that enhancement does not add authority.
