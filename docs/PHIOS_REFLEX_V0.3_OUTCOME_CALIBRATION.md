# PhiReflex v0.3 — Shadow Outcome Calibration

## Status

PhiReflex v0.3 evaluates previously recorded v0.2 shadow predictions against
**explicit observed labels** collected after a dispatch.

The central rule is:

```text
dispatch outcome
!=
ground truth for every Reflex prediction
```

A run succeeding does not automatically prove:

- the predicted role was correct;
- the predicted risk was correct;
- System Two was actually needed;
- verification was actually needed.

Those dimensions are scored only when an explicit observation exists.

## Why this rung exists

v0.1 created provider-neutral System-One decisions.

v0.2 attached those decisions to the real dispatch path in isolated shadow
mode.

v0.3 finally lets PhiOS ask:

> How well did the baseline and shadow provider match what we later observed?

without allowing that evaluation to rewrite history or influence the already
completed dispatch.

## Outcome observation

`ReflexOutcomeObservation` records:

- run ID;
- dispatch outcome;
- observer label;
- evidence SHA-256;
- optional observed role;
- optional observed risk;
- optional observed System-Two requirement;
- optional observed verification requirement.

The evidence hash identifies the evidence artifact used by the observer.

It is **not** a cryptographic claim that the observation is true.

## Supported dispatch outcomes

The operational run outcome is preserved as provenance:

```text
succeeded
failed
cancelled
partial
unknown
```

That value is not converted into role/risk/System-Two truth.

For example:

```text
dispatch_outcome = failed
```

does not imply:

```text
predicted risk = high was correct
```

unless an observer explicitly records the actual risk label.

## Partial labels are allowed

An observation may know some dimensions and not others.

Example:

```text
actual_role = builder
system2_needed = true
actual_risk = unknown
verification_needed = unknown
```

v0.3 scores only:

- role;
- System Two.

Risk and verification remain unscored.

This preserves missing information instead of replacing it with guesses.

## No-label behavior

If an outcome is recorded with no explicit prediction labels:

```text
dispatch_outcome = failed
actual_role = null
actual_risk = null
system2_needed = null
verification_needed = null
```

the receipt status is:

```text
unscored_no_observed_labels
```

There is no fabricated accuracy or calibration score.

## Brier scoring

v0.3 uses Brier-style squared probability error.

For binary predictions:

```text
Brier = (p - y)^2
```

where:

- `p` is the predicted probability;
- `y` is 1 for true and 0 for false.

For categorical role/risk distributions, v0.3 uses the mean squared error
across the declared label set.

Lower Brier values indicate probability mass closer to the observed label.

The receipt records separate scores for:

- role;
- risk;
- System Two;
- verification.

It also records a simple mean across only the dimensions that were actually
observed.

The score is descriptive evidence. It grants no routing authority.

## Baseline and shadow providers

The deterministic local baseline is always scored when labels exist.

If the v0.2 nested shadow provider status is `ok`, the shadow provider is
scored against the **same observation and same dimensions**.

If the shadow provider was unavailable or errored, the calibration receipt
records that provider status and leaves the shadow calibration empty.

v0.3 does not select a winner or change routing.

## Receipt validation

Before scoring, v0.3 validates the exact v0.2 dispatch shadow receipt.

It checks:

- dispatch-shadow schema;
- outer receipt SHA-256;
- task/context/plan digests;
- planner-influence flag remains false;
- context-contamination flag remains false;
- plan-contamination flag remains false;
- zero authority flags;
- nested v0.1 Reflex receipt schema;
- nested Reflex receipt SHA-256;
- nested zero-authority flags;
- valid provider probability distributions.

Tampered shadow history is rejected rather than calibrated.

## Persisted run integration

A live v0.2 dispatch stores its shadow observation under:

```text
shadow_observations.phireflex_v0_2
```

v0.3 can append calibration receipts to that same local run record under:

```text
reflex_calibration_receipts
```

and adds a local event:

```text
reflex_calibration_recorded
```

The original operational context, plan, and shadow receipt remain unchanged.

## CLI

Record explicit post-run observations:

```bash
phi agents reflex-evaluate run_123 \
  --outcome succeeded \
  --observer operator-review \
  --evidence-sha <sha256> \
  --role builder \
  --risk elevated \
  --system2-needed yes \
  --verification-needed yes
```

Every label after `--evidence-sha` is optional.

A valid outcome-only observation is also allowed:

```bash
phi agents reflex-evaluate run_123 \
  --outcome failed \
  --observer operator-review \
  --evidence-sha <sha256>
```

That produces an unscored receipt instead of pretending failure supplies
ground truth.

## Authority boundary

Every v0.3 calibration receipt retains:

```text
action_authority = false
execution_authority = false
```

v0.3 cannot:

- alter the original dispatch;
- rewrite the planner context;
- rewrite the operational plan;
- alter the shadow prediction;
- grant agent-dispatch authority;
- influence routing;
- promote Jev;
- modify CAPS or Spine permissions.

Calibration is evidence about past predictions, not permission for future
actions.

## Tests

v0.3 tests verify:

- only explicitly observed dimensions are scored;
- missing labels remain unscored;
- failed/succeeded outcomes do not become hidden labels;
- baseline and shadow providers use the same observed dimensions;
- categorical and binary Brier scores are deterministic;
- tampered v0.2 receipts are rejected;
- contaminated shadow history cannot be calibrated;
- invalid observed labels fail closed;
- calibration receipts are deterministic;
- persisted run records retain calibration receipts;
- a run without v0.2 shadow evidence cannot be calibrated;
- calibration recording emits a local run event;
- shell boolean labels reject ambiguous values.

## Next rung

The next useful step should aggregate many v0.3 receipts into a bounded
**calibration summary / promotion-readiness report**.

That report should still be advisory.

Only after sufficient sample size, coverage, and calibration evidence should a
separate governed contract even consider allowing PhiReflex signals to
influence dispatch routing.
