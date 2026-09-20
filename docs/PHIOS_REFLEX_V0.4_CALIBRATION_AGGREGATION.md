# PhiReflex v0.4 — Calibration Aggregation and Review Readiness

## Status

PhiReflex v0.4 aggregates many validated v0.3 calibration receipts into one
deterministic advisory report.

The central rule is:

```text
review eligible
!=
promoted
```

and:

```text
calibration evidence
!=
routing authority
```

v0.4 can summarize evidence and determine whether an explicit review policy has
enough support to justify human/governed review. It cannot install, promote,
select, or authorize a provider.

## Why this rung exists

v0.1 created provider-neutral System-One decisions.

v0.2 attached those decisions to real dispatches in strict shadow mode.

v0.3 scored individual predictions only against explicit observed labels.

v0.4 asks the next question:

> Across many independent dispatch runs, is there enough calibrated evidence to
> justify reviewing a provider for possible future routing influence?

The answer remains advisory.

## Input evidence

v0.4 consumes only v0.3 receipts with schema:

```text
phios.reflex_calibration_receipt.v0.3
```

Every receipt is validated before aggregation, including:

- schema;
- status;
- receipt SHA-256;
- run ID;
- exact dispatch-shadow/context/plan digests;
- baseline calibration structure;
- optional shadow calibration structure;
- shadow status;
- zero action authority;
- zero execution authority.

Tampered evidence is rejected.

## One run, one sample

A single dispatch run may accumulate multiple post-run reviews.

v0.4 does **not** treat those as independent samples.

For each run:

- exact duplicate calibration receipts are deduplicated;
- one unique receipt is accepted;
- two or more distinct calibration receipts make that run ambiguous;
- ambiguous runs are excluded from scoring.

This prevents repeated reviews of one run from inflating sample size.

The report records:

- unique runs seen;
- included runs;
- ambiguous run IDs;
- exact duplicates ignored.

## Provider aggregates

For each provider aggregate, v0.4 records:

- provider identity;
- model identities observed;
- available runs;
- scored runs;
- scored dimension observations;
- per-dimension sample counts;
- per-dimension mean Brier score;
- observed-dimension coverage;
- overall mean Brier score.

The dimensions remain:

```text
role
risk
system2
verification
```

Missing labels remain missing and do not enter the denominator as fake scores.

## Fair candidate comparison

The candidate provider is compared to the baseline only on the same runs where
that candidate actually produced a shadow decision.

For example, when the candidate is Jev:

```text
Jev available on run A
Jev available on run B
Jev unavailable on run C
```

the paired baseline used for the Jev quality delta contains only runs A and B.

The comparison is:

```text
candidate mean Brier
-
paired baseline mean Brier
```

Negative values mean the candidate had lower Brier error over those paired
observations.

This avoids comparing candidate performance against a baseline sample drawn
from different runs.

## Shadow availability

The report separately records:

- shadow-ok runs;
- shadow-unavailable runs;
- shadow-error runs;
- shadow availability rate.

The current v0.2 dispatch integration configures Jev as the shadow provider, so
the default v0.4 Jev policy treats this shadow availability rate as operational
Jev availability evidence.

Future multi-shadow-provider routing should make provider-specific
unavailability identity explicit before reusing this assumption.

## Default Jev review policy

`default_jev_readiness_policy()` currently requires:

```text
minimum unique calibrated runs       20
minimum Jev scored runs              12
minimum observed-dimension coverage  0.50
minimum shadow availability rate     0.80
maximum Jev mean Brier               0.20
maximum regression vs paired baseline 0.02
```

These are explicit v0.4 policy defaults, not universal scientific thresholds.

They can be replaced by a caller-supplied `PromotionReadinessPolicy`.

Every policy has a deterministic SHA-256.

## Readiness statuses

### INSUFFICIENT_EVIDENCE

Returned when evidence coverage is not sufficient for review.

Examples:

- too few unique runs;
- too few candidate-scored runs;
- inadequate label coverage;
- inadequate shadow availability;
- ambiguous runs caused sample loss.

### NOT_REVIEW_ELIGIBLE

Returned when evidence quantity/coverage is sufficient but the configured
quality thresholds are not met.

Examples:

- candidate mean Brier exceeds the policy maximum;
- candidate performance regresses beyond the allowed paired-baseline margin.

### REVIEW_ELIGIBLE

Returned only when all configured evidence and quality thresholds pass.

This means:

> evidence is sufficient for a separate governed review.

It does **not** mean:

> promote this provider.

## Authority boundary

Every v0.4 readiness receipt explicitly carries:

```text
routing_influence_authority = false
promotion_authority = false
action_authority = false
execution_authority = false
```

Therefore even:

```text
status = REVIEW_ELIGIBLE
```

cannot:

- enable Jev routing;
- alter Crane Fly / dispatch behavior;
- replace the deterministic baseline;
- grant tools;
- change CAPS policy;
- change Spine permissions;
- promote a provider;
- execute anything.

A future influence contract must be a distinct governed layer.

## Persisted-run report

PhiOS can scan locally persisted agent runs and aggregate all discovered v0.3
receipts:

```bash
phi agents reflex-report
```

The default command evaluates Jev using the conservative default policy.

Policy values can be overridden explicitly:

```bash
phi agents reflex-report \
  --candidate jev \
  --policy-id lab-review-001 \
  --min-runs 30 \
  --min-scored 20 \
  --min-coverage 0.75 \
  --min-availability 0.90 \
  --max-brier 0.15 \
  --max-regression 0.01
```

The command returns:

- runs scanned;
- runs with calibration;
- calibration receipts found;
- deterministic v0.4 readiness receipt.

## Empty-data behavior

A fresh PhiOS installation with no v0.3 evidence returns:

```text
INSUFFICIENT_EVIDENCE
```

It does not fail and does not infer readiness.

## Tests

v0.4 tests verify:

- a well-calibrated candidate can become `REVIEW_ELIGIBLE`;
- review eligibility never grants promotion or routing authority;
- insufficient sample size remains insufficient;
- adequate evidence with poor quality becomes `NOT_REVIEW_ELIGIBLE`;
- partial labels reduce coverage instead of creating fake observations;
- exact duplicate receipts count once;
- conflicting receipts for one run are excluded;
- tampered v0.3 receipts are rejected;
- report ordering is deterministic;
- persisted-run aggregation works;
- empty repositories remain insufficient;
- conflicting persisted observations remain excluded;
- shell policy overrides are parsed explicitly;
- malformed numeric policy input is rejected.

## Next rung

v0.5 should **not** immediately turn `REVIEW_ELIGIBLE` into routing influence.

The next safe rung is a governed review/adoption boundary for Reflex influence,
similar to the reasoning stack's distinction between recommendation and plan
adoption.

That future contract should require explicit human/authority approval for a
specific:

- provider;
- model/version;
- calibrated policy receipt;
- permitted routing dimensions;
- maximum influence scope;
- rollback condition.

Only then should PhiReflex move from observation into bounded routing influence.
