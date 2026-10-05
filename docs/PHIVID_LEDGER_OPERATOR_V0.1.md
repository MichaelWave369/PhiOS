# PHIVid Local Operator Ledger Admission

PhiOS now exposes the PHIVid ledger-write boundary through a local operator CLI.

## Command

```bash
python -m phios.phivid_ledger_operator \
  --envelope phivid-envelope.json \
  --admission-receipt phivid-admission.json \
  --authority-epoch authority-epoch.json \
  --ledger ~/.phios/reality-ledger.jsonl \
  --operator-id operator:local \
  --confirmed-at 2026-10-04T23:15:00+00:00 \
  --confirm-admit
```

## Authority

The command does not accept an arbitrary list of permissions.

It loads PhiOS's canonical `AuthorityEpoch`, verifies its self-hash, requires the operator id to match the epoch principal, and derives an `AuthorityContext` from the epoch's frozen ceiling and reconstructed grants.

The resulting context must allow:

`evidence.phivid.ledger.admit`

## Temporal freshness

Operator confirmation may not predate the AuthorityEpoch observation.

If the epoch declares a `next_known_transition_at`, the command refuses to use that epoch at or after the transition. The operator must reconstruct a fresh authority state first.

## Explicit effect boundary

The command requires `--confirm-admit`.

Before the flag is present, no admission file is written.

Successful admission appends one immutable PHIVid evidence admission record through the already-qualified ledger service. The record documents the persistence effect while retaining zero operational, action, and execution authority.

## Trust scope

This is a local operator-channel boundary. It is not designed to defend against arbitrary malware already executing as the same operating-system user. Stronger host identity or hardware-backed authorization can be layered above this contract later.
