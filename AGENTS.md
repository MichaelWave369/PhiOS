# PhiOS Agent Guardrails

This repository is public/open-source. Treat PhiKernel and TIEKAT implementation internals as private.

## Kernel migration rollout rules

- **Do not auto-promote adapters.**
  - Never change adapter selection automatically from rollout metrics.
  - Promotion and rollback must remain explicit operator actions.
- **Keep recommendations advisory-only.**
  - Readiness (`ready` / `caution` / `hold`) is guidance, not proof.
- **Preserve public/private boundary.**
  - Consume only PhiKernel's stable normalized runtime contract.
  - Do not import, copy, or infer proprietary PhiKernel/TIEKAT internals into PhiOS.
- **Keep compare mode operator-controlled.**
  - Compare/shadow behavior is opt-in via environment and explicit commands.
  - Default-safe behavior must remain unchanged.
- **No proprietary leakage in logs/reports/docs.**
  - Persist/export only normalized contract fields and additive PhiOS metadata.

## Workflow expectations

- Prefer minimally invasive changes and deterministic tests.
- Verify with focused tests and typing checks when touching rollout/runtime layers.
- Keep operator-facing docs and commands synchronized with implementation.
