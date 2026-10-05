# Operator-Confirmed PHIVid Ledger Admission

This rung is the first PHIVid evidence step that intentionally writes to the PhiOS Reality Ledger.

## Preconditions

Admission requires all of the following:

1. a PHIVid evidence envelope already validated by PhiOS,
2. a policy-bound admission receipt with decision `ELIGIBLE`,
3. an existing PhiOS `AuthorityContext` that allows:
   - `evidence.phivid.ledger.admit`
4. explicit operator confirmation,
5. operator identity and a timezone-bearing confirmation timestamp,
6. no existing admission record for the same envelope digest.

Failure at any gate performs no ledger write.

## Existing authority system

The ledger boundary does not create a parallel authority mechanism.

It uses PhiOS's canonical `AuthorityContext.allows()` check. In a deployed system, that context can be reconstructed from the existing AuthorityEpoch / authoritative grant pipeline.

The admission record binds the exact AuthorityContext digest used for the decision.

## Ledger effect

Successful admission appends one immutable record to:

`phivid-evidence-admissions.jsonl`

The record binds:

- PHIVid admission-receipt SHA-256,
- PHIVid evidence-envelope SHA-256,
- original PHIVid render-receipt SHA-256,
- admission-policy profile SHA-256,
- plan id,
- rendered output EvidenceRef,
- operator id,
- operator confirmation timestamp,
- authority-context SHA-256,
- required permission.

It records:

- `operator_confirmed=true`
- `ledger_write_performed=true`
- `evidence_admitted=true`

while retaining:

- `operational_authority=false`
- `action_authority=false`
- `execution_authority=false`

## Meaning

Ledger admission means PhiOS has accepted the evidence record into its append-only history under the stated policy and operator authority.

It does not make the evidence an instruction, grant permission to act, or authorize execution.
