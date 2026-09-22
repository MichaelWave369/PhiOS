# PhiOS Identity Continuity and Recovery v0.1

## Status

Research-hardening candidate.

Primary schemas:

```text
phios.identity_invariant_set.v0.1
phios.functional_equivalence_receipt.v0.1
phios.epoch_bound_identity.v0.1
phios.recovery_path_receipt.v0.1
```

Primary rules:

```text
SAME TOPOLOGY
!=
SAME IDENTITY

RECOVERED STATE
!=
RECOVERED AUTHORITY
```

This contract composes over Covenant CR-01 `IdentitySeal`.

It provides deterministic evidence for one narrow question:

> Can one exact actor identity continue across a topology/runtime recovery boundary
> without inferring identity from location, process continuity, or display name?

It does not create authority.

## IdentityInvariantSet

`IdentityInvariantSet` declares which existing `IdentitySeal` fields define continuity.

The available invariant vocabulary is exactly:

```text
subject_id
subject_kind
implementation_sha256
manifest_sha256
source_sha256
issuer_id
issuer_key_id
```

Every invariant set must include at least:

```text
subject_id
subject_kind
```

The strict CR-01 profile includes all seven fields.

Topology is structurally excluded:

```text
topology_is_identity_evidence = false
```

This prevents a host path, PID, container location, machine name, socket, or deployment
shape from becoming identity merely because it happened to remain unchanged.

## FunctionalEquivalenceReceipt

The equivalence evaluator compares two exact `IdentitySeal` records under one explicit
invariant set.

The receipt binds:

- invariant-set SHA-256;
- previous identity-seal SHA-256;
- candidate identity-seal SHA-256;
- the complete required-field set;
- matched fields;
- mismatched fields;
- explicit exclusion of topology evidence;
- zero trust/action/execution authority.

The matched and mismatched sets must partition the required invariant fields exactly.

That prevents a reconstructed receipt from simply omitting an inconvenient invariant.

Possible status:

```text
EQUIVALENT
CHANGED
```

`EQUIVALENT` means only:

> every declared invariant matched.

It does not mean:

- trusted identity;
- action authority;
- execution authority;
- correctness;
- health;
- semantic equivalence outside the declared invariant set.

## EpochBoundIdentity

One identity observation is bound to an explicit recovery epoch.

The contract contains:

```text
subject_id
subject_kind
epoch

identity_seal_sha256
invariant_set_sha256
topology_sha256
recovery_state_sha256

previous_epoch_identity_sha256 | null
recovery_checkpoint_sha256 | null
```

Epoch zero is the genesis observation and cannot claim prior recovery ancestry.

Every later epoch must carry:

```text
previous_epoch_identity_sha256
recovery_checkpoint_sha256
```

The previous-epoch hash creates an append-only continuity chain rather than trusting
process or machine continuity.

## Topology changes

Topology is recorded independently.

A recovery may therefore produce:

```text
previous_topology_sha256 != recovered_topology_sha256
topology_changed = true
```

and still preserve identity when the declared identity invariants match.

Conversely:

```text
same topology
+
changed identity invariant
=
identity changed
```

A process staying in the same container does not launder a changed implementation,
issuer, source, or manifest under the strict profile.

## Exact recovery-state boundary

v0.1 requires:

```text
previous.recovery_state_sha256
==
recovered.recovery_state_sha256
```

for successful recovery.

This is intentionally strict.

A migrated, transformed, partially restored, or semantically equivalent state is not
called exact recovery by this contract.

Such a future path would need its own transformation/equivalence receipt rather than
quietly weakening the meaning of recovery.

## RecoveryEvaluator

`RecoveryEvaluator` recomputes one recovery decision from the supplied exact contracts.

Recovery succeeds only when all of the following are true:

```text
previous identity-seal binding valid
recovered identity-seal binding valid
invariant-set binding valid
subject bindings valid
previous-epoch hash link valid
checkpoint binding valid
recovered epoch == previous epoch + 1
identity invariants equivalent
recovery-state digest unchanged
```

The first failed bounded condition is recorded as the reason.

## RecoveryPathReceipt

Possible status:

```text
RECOVERED
BLOCKED
```

The receipt binds:

- previous/recovered epoch-identity hashes;
- functional-equivalence receipt hash;
- checkpoint digest;
- previous/recovered epochs;
- previous/recovered topology digests;
- previous/recovered recovery-state digests;
- every recovery prerequisite as an explicit Boolean;
- topology-change status;
- deterministic reason.

Even a successful receipt fixes:

```text
authority_inherited = false
authority_revalidation_required = true
trusted_identity = false
action_authority = false
execution_authority = false
```

This is the crucial authority boundary.

A recovered actor may have continuity evidence and still need all ordinary PhiOS
authority to be re-established through the existing authority plane.

## Strict reconstruction

All four contracts support strict canonical serialization/reconstruction.

Unknown fields fail closed.

Digest mismatch fails closed.

Authority-like fields that are not part of the schema cannot be smuggled into the
record.

## Security properties

v0.1 is designed to prevent:

- topology-identity laundering;
- hostname/process/location identity inference;
- same-topology laundering of changed implementation identity;
- skipped recovery epochs;
- broken previous-epoch ancestry;
- checkpoint substitution;
- changed state being called exact recovery;
- recovery success restoring old authority;
- reconstructed equivalence receipts omitting declared invariants.

## Bounded claim

v0.1 proves only:

> under an explicit invariant set, an exact next recovery epoch can preserve identity
> across topology change when the exact recovery-state digest is unchanged and all
> continuity bindings hold.

It does not prove checkpoint authenticity, trusted identity, runtime correctness,
availability of the original substrate, or authority continuity.

## Design rule

```text
identity follows invariants
history follows hashes
topology remains descriptive
authority must be revalidated
```

Because apparently moving a thing to another box should not turn metaphysics into a
hostname comparison.
