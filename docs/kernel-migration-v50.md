# PhiKernel Adapter Migration Runbook: `legacy` → `tiekat_v50`

This runbook defines a **controlled, operator-reviewed** migration campaign.

> Guardrail: rollout outputs are advisory-only and do not auto-switch adapters.

## 1) Preconditions

- PhiKernel is installed and reachable through `phik`.
- PhiOS rollout tooling is available (`phi eval-kernel`, `phi review-kernel-rollout`).
- Operator has confirmed migration window and rollback owner.

Quick checks:

```bash
phi status --json
phi eval-kernel --help
phi review-kernel-rollout --help
```

## 2) Start shadow rollout (legacy primary, v50 shadow)

```bash
export PHIOS_KERNEL_ENABLED=true
export PHIOS_KERNEL_ADAPTER=legacy
export PHIOS_KERNEL_SHADOW_ADAPTER=tiekat_v50
export PHIOS_KERNEL_COMPARE_MODE=true
```

Run initial canonical compare batch:

```bash
phi eval-kernel --compare legacy tiekat_v50 --report ./kernel_rollout_report.shadow.json --json
```

Optionally export a markdown review packet:

```bash
phi review-kernel-rollout --adapter legacy --markdown ./kernel_rollout_review.shadow.md --json
```

## 3) Readiness review loop

Review current readiness gate and reason codes:

```bash
phi review-kernel-rollout --adapter legacy --json
```

Filter by campaign window:

```bash
phi review-kernel-rollout --adapter legacy --since 2026-01-01T00:00:00+00:00 --until 2026-01-07T23:59:59+00:00 --json
```

Interpretation:

- `ready`: rollout window appears stable; promotion may be considered.
- `caution`: elevated divergence; collect more evidence before promotion.
- `hold`: unacceptable divergence or insufficient sample quality/volume.

## 4) Promotion sequence (manual)

Only after human sign-off:

```bash
export PHIOS_KERNEL_ENABLED=true
export PHIOS_KERNEL_ADAPTER=tiekat_v50
export PHIOS_KERNEL_SHADOW_ADAPTER=legacy
export PHIOS_KERNEL_COMPARE_MODE=true
```

Run post-promotion validation batch:

```bash
phi eval-kernel --compare tiekat_v50 legacy --report ./kernel_rollout_report.promoted.json --json
phi review-kernel-rollout --adapter tiekat_v50 --markdown ./kernel_rollout_review.promoted.md --json
```

## 5) Reverse-shadow validation sequence

Keep `tiekat_v50` primary and `legacy` shadow for a bounded period:

```bash
phi review-kernel-rollout --adapter legacy --context eval_case --json
phi status
```

If status remains acceptable, continue campaign; otherwise, rollback.

## 6) Rollback sequence (manual) back to `legacy`

```bash
export PHIOS_KERNEL_ENABLED=true
export PHIOS_KERNEL_ADAPTER=legacy
export PHIOS_KERNEL_SHADOW_ADAPTER=tiekat_v50
export PHIOS_KERNEL_COMPARE_MODE=true
```

Re-run evaluation and review after rollback:

```bash
phi eval-kernel --compare legacy tiekat_v50 --report ./kernel_rollout_report.rollback.json --json
phi review-kernel-rollout --adapter legacy --markdown ./kernel_rollout_review.rollback.md --json
```

## 7) Final campaign closeout

Archive artifacts:

- JSON compare reports (`kernel_rollout_report.*.json`)
- markdown review packets (`kernel_rollout_review.*.md`)
- operator decision notes (external change log/ticket)

Reminder:

- No auto-promotion in code.
- No proprietary internals in persisted/exported outputs.
- Operator approval remains authoritative.
