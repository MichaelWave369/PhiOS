# PHIVid HMAC Operator Approval Proof

The PHIVid ledger-admission path now separates **operator approval proof** from **effect confirmation**.

## Step 1: approve the exact admission payload

```bash
python -m phios.phivid_operator_approval \
  --envelope phivid-envelope.json \
  --admission-receipt phivid-admission.json \
  --authority-epoch authority-epoch.json \
  --operator-id operator:local \
  --approved-at 2026-10-05T04:15:00+00:00 \
  --out phivid-operator-approval.json
```

The approval HMAC binds:

- PHIVid evidence-envelope SHA-256,
- PHIVid policy admission-receipt SHA-256,
- AuthorityEpoch SHA-256,
- operator id,
- approval timestamp,
- required permission `evidence.phivid.ledger.admit`.

## Step 2: perform the governed admission

The ledger operator command now also requires:

- `--approval-proof phivid-operator-approval.json`
- the same operator id and confirmation timestamp,
- the matching local operator key,
- `--confirm-admit`.

The command re-verifies every input and refuses the write if the approval proof does not bind the exact envelope, admission receipt, AuthorityEpoch, operator, and timestamp.

## Key storage

The default local key is:

`~/.phios/authority/phivid-ledger-admission.key`

or `PHIOS_PHIVID_OPERATOR_KEY` when configured.

The key is created with owner-only permissions and rejected if group/other access is present.

## Security boundary

The HMAC proves possession of the local operator secret and exact-payload approval. It does not create authority, action permission, or execution permission.

This remains a same-user local trust boundary, not a defense against malware already controlling the operator account.
