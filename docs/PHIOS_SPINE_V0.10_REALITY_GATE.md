# PhiOS Spine v0.10 - Reality Gate Verification Bridge

Spine v0.10 introduces the first deterministic Reality Gate verification bridge.

The purpose is not to make PhiOS declare truth. The purpose is to keep different kinds of claims from being silently collapsed into one another.

## Central distinction

```text
SOURCE CONTENT CLAIM
"The cited evidence contains PORT 24 DOWN."
        ↓
bounded lexical verification is possible

WORLD STATE CLAIM
"Physical port 24 is actually down."
        ↓
UNRESOLVED without an independent world verifier
```

An OCR output can support a statement about what the OCR text contains.

It cannot, by itself, establish the physical state of the system depicted or described.

## Authority

Reality verification requires:

`reality.verify`

Verification is read-only and does not confer action authority.

## Claim kinds

v0.10 supports two scopes.

### source_contains_text

The verifier reads explicitly cited UTF-8 evidence and checks whether a requested phrase is present after deterministic whitespace normalization.

Case-insensitive matching is the default. Case-sensitive matching is available explicitly.

A successful lexical match produces:

`SUPPORTED`

If all readable cited text evidence lacks the phrase:

`CONTRADICTED`

If none of the cited evidence can be read as bounded UTF-8 text:

`UNRESOLVED`

### world_state

World-state claims are always:

`UNRESOLVED`

in v0.10.

This is intentional. A screenshot, OCR transcript, note, or model output can describe the world without independently establishing the state of the world.

A future independent verifier may add bounded world-state adapters such as live device telemetry, signed service state, or other direct observations.

## RealityReceipt

The existing RealityReceipt contract is extended with:

- unresolved_claims
- verdict_summary
- verification_method
- promotion_status
- limitations

The receipt continues to record:

- claims_checked
- evidence_used
- unresolved_contradictions

## Status mapping

- all supported claims → ACCEPTED
- any contradicted claim → DISPUTED
- any unresolved claim with no contradiction → UNKNOWN
- invalid contract or missing permission → BLOCKED

These are verification states, not action decisions.

## No automatic promotion

Every v0.10 RealityReceipt records:

`promotion_status = not_promoted`

The bridge does not automatically:

- grant permissions
- execute actions
- promote memory
- convert OCR confidence into truth confidence
- infer world state from source text

## Example

Suppose OCR produced:

`PORT 24 DOWN`

The following source-content claim can be supported:

`The cited OCR text contains PORT 24 DOWN.`

The following world-state claim remains unresolved:

`Physical switch port 24 is currently down.`

That second claim needs evidence that observes the switch or network state independently.

## CLI

Source-content verification:

```bash
phi-spine \
  --allow reality.verify \
  verify-claim \
  --kind source_contains_text \
  --statement "The OCR text contains PORT 24 DOWN." \
  --evidence-ref evidence:sha256:<digest> \
  --expected-text "PORT 24 DOWN"
```

World-state boundary demonstration:

```bash
phi-spine \
  --allow reality.verify \
  verify-claim \
  --kind world_state \
  --statement "Physical switch port 24 is currently down." \
  --evidence-ref evidence:sha256:<ocr-text-digest>
```

The second result is UNKNOWN / UNRESOLVED by design.

## Still excluded

v0.10 does not add:

- semantic entailment models
- network/device telemetry
- external fact lookup
- automatic contradiction search
- action authorization
- memory promotion
- world-state truth scoring
