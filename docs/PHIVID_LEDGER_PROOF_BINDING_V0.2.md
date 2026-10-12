# PHIVid Ledger Proof Binding v0.2

PhiOS now enforces the PHIVid HMAC operator proof at the **ledger-admission service boundary**, not only in the command-line wrapper.

## Why

Before v0.2, the operator CLI verified the HMAC proof before calling `admit_phivid_evidence()`.

That protected the normal operator path, but code running inside PhiOS could call the lower-level admission function directly and bypass proof verification.

v0.2 closes that gap.

## Required inputs at the service boundary

Every new PHIVid ledger admission now requires:

- validated PHIVid evidence intake,
- policy `ELIGIBLE` receipt,
- AuthorityContext granting `evidence.phivid.ledger.admit`,
- exact AuthorityEpoch SHA-256,
- HMAC-bound `PHIVidOperatorApproval`,
- local operator HMAC key,
- matching operator identity,
- matching approval/confirmation timestamp,
- explicit operator confirmation.

The service itself verifies the HMAC and all bindings before any append.

## Persisted proof bindings

New ledger records use:

`phios.phivid_ledger_admission.v0.2`

and bind:

- AuthorityEpoch SHA-256,
- canonical operator-approval artifact SHA-256,
- operator approval payload SHA-256,
- operator approval HMAC SHA-256,
- `operator_approval_verified=true`.

The ledger record remains self-hashed.

## Backward compatibility

Existing `phios.phivid_ledger_admission.v0.1` records remain parseable.

v0.1 records do not gain retroactive proof fields. They remain historical records under the contract that existed when they were written.

## Authority boundary

A verified approval proves that the local operator key approved this exact admission tuple.

It still does not grant:

- operational authority,
- action authority,
- execution authority.

Those flags remain false in the persisted record.
