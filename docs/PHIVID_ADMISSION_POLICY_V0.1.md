# PHIVid Policy-Bound Admission Receipt

This rung evaluates already-validated PHIVid evidence for eligibility to enter a later Reality Ledger admission workflow.

It does **not** append to the ledger.

## Strict local policy

The default policy accepts only:

- `phivid.video.source`
- `phivid.video.render`

with exactness class:

- `byte_exact`

and the currently qualified warning:

- `render_used_cpu_encoder`

Unknown source kinds, exactness classes, or warnings fail closed as `HOLD`.

By default, EvidenceRefs that already contain an admissibility receipt binding are also held to avoid accidental re-admission.

## Receipt

The deterministic receipt binds:

- PHIVid envelope SHA-256,
- original PHIVid render-receipt SHA-256,
- policy-profile SHA-256,
- plan id,
- rendered output EvidenceRef,
- decision and reason,
- explicit evaluation timestamp,
- ledger eligibility.

It also records:

- `ledger_write_performed=false`
- `admission_effect_performed=false`
- zero operational authority
- zero action authority
- zero execution authority

## Meaning of ELIGIBLE

`ELIGIBLE` means only that the evidence satisfied this policy profile and may proceed to a **future, separate** ledger-admission step.

It is not equivalent to:

- ledger persistence,
- truth certification,
- action permission,
- execution permission,
- operator approval.

That separation keeps evidence evaluation from quietly becoming an authority mint, a surprisingly popular hobby in agent systems.
