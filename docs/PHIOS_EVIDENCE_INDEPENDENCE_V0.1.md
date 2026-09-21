# PhiOS Evidence Independence v0.1

## Status

Research-hardening candidate.

Primary schemas / receipts:

```text
phios.independence_policy.v0.1
IndependenceReceipt
DisagreementDecompositionReceipt
```

Primary rule:

```text
THREE AGENTS AGREE
!=
THREE INDEPENDENT PIECES OF EVIDENCE
```

This contract exists to stop multi-model deliberation from laundering correlated or
shared evidence into fake corroboration.

## What independence means here

v0.1 does not infer independence from:

- different model names;
- different prompts;
- different prose;
- different roles;
- unanimous answers;
- repeated runs;
- majority vote.

Instead, each path declares the evidence structure PhiOS can inspect and pairwise
independence must be supported explicitly.

Shared deliberation context is recorded as a correlation signal. It does not by itself
force dependency when separately acquired root evidence is independently attested, but
it also does not count as evidence of independence.

## EvidencePathDeclaration

Each path binds:

```text
path_id
claim_id
actor_id
stance
output_sha256

evidence_refs[]
root_source_refs[]
parent_path_ids[]
transformation_lineage_sha256s[]

context_sha256
method
```

The stance vocabulary is intentionally small:

```text
SUPPORTS
CONTRADICTS
UNCERTAIN
```

Stance is not authority and does not imply truth.

## Pairwise independence

Pairwise relations are:

```text
INDEPENDENT
DEPENDENT
UNKNOWN
```

### Forced dependency

A pair is dependent when PhiOS can see any of the following:

- same actor;
- shared direct evidence reference;
- shared root-source reference;
- shared transformation-lineage receipt;
- direct path derivation.

An explicit `INDEPENDENT` assertion cannot override those facts.

### Demonstrated independence

An `INDEPENDENT` assertion requires:

- explicit `basis_refs`;
- explicit root-source refs for both paths;
- no forced dependency.

This means independence is still a claim backed by evidence, not a property inferred
from multiplicity.

### Unknown

When independence has not been demonstrated and dependency is not known, the relation is
`UNKNOWN`.

Unknown does not receive independence credit.

## Conservative evidence groups

PhiOS forms conservative dependency groups.

Any pair that is not explicitly demonstrated independent is collapsed for group-count
purposes.

Therefore:

```text
three model outputs
same source
same evidence

raw participant count = 3
demonstrated independent group count = 1
```

Likewise, two paths with unknown relationship do not become two independent votes just
because no dependency was found.

This is intentionally asymmetric:

```text
absence of dependency evidence
!=
evidence of independence
```

## IndependenceReceipt

The receipt records:

```text
claim_id
evidence_paths[]
pairwise_relations[]

independence_status
independent_pair_count
dependent_pair_count
unknown_pair_count

demonstrated_independent_group_count
dependency_groups[]

agreement_without_independence
assessment_sha256

operational_authority = false
action_authority      = false
execution_authority   = false
```

Assessment status is:

```text
SINGLE_PATH
INDEPENDENT
DEPENDENT
MIXED
UNRESOLVED
```

An unresolved assessment is a valid diagnostic result and is Mandala `DEGRADED`, not
silently accepted as independence.

## DisagreementDecompositionReceipt

Agreement and disagreement are reported separately from independence.

The receipt records:

```text
stance_counts
independent_stance_group_counts
contested_group_count
dependency_groups

disagreement_status
independence_qualified_agreement

consensus_authority = false
promotion_status = not_promoted

operational_authority = false
action_authority      = false
execution_authority   = false
```

The receipt is parent-linked to the exact `IndependenceReceipt`.

## Unanimous does not mean independently corroborated

Consider three models:

```text
Model A → SUPPORTS
Model B → SUPPORTS
Model C → SUPPORTS
```

If all three used the same source:

```text
disagreement_status = UNANIMOUS_PARTICIPANTS
demonstrated_independent_group_count = 1
independence_qualified_agreement = false
```

If three separately grounded paths have explicit pairwise independence evidence:

```text
disagreement_status = UNANIMOUS_PARTICIPANTS
demonstrated_independent_group_count = 3
independence_qualified_agreement = true
```

Even then:

```text
consensus_authority = false
promotion_status = not_promoted
```

Independent agreement is stronger evidence structure, not permission.

## Disagreement remains visible

If independently grounded paths disagree:

```text
Path A → SUPPORTS
Path B → CONTRADICTS
Path C → UNCERTAIN
```

PhiOS preserves all three positions.

The contract does not:

- elect a winner;
- average away uncertainty;
- convert majority into truth;
- grant authority to the plurality;
- suppress minority evidence.

The purpose is decomposition, not voting.

## Parent-path lineage

Evidence paths may cite parent path IDs when one deliberation output derives from
another.

Direct parent/child paths are dependent.

The parent graph must be acyclic. Cyclic ancestry is rejected because a circular set of
agents citing one another is not independent corroboration, merely paperwork learning to
orbit itself.

## Spine integration

`PhiOSSpine.assess_deliberation_evidence(...)` exposes the contract through the
current runtime.

The method creates a DELIBERATION packet and persists:

```text
IndependenceReceipt
        ↓
DisagreementDecompositionReceipt
```

The Spine authority context is unchanged.

The checked-in `PhiVesselAdapter` remains deterministic. v0.1 deliberately does not
pretend the current repository already contains the future Genius Atlas / council
execution layer.

When that router is connected, it should feed its participant/evidence paths into this
contract rather than inventing a second consensus system.

## Ledger analytics

Read-only Ledger projection exposes only bounded aggregate metadata from the two new
receipts.

For independence:

- claim ID;
- independence status;
- pair counts;
- demonstrated independent group count;
- agreement-without-independence flag;
- assessment hash;
- zero-authority flags.

For disagreement:

- claim ID;
- independence receipt hash;
- disagreement status;
- contested group count;
- independence-qualified agreement;
- consensus-authority flag;
- promotion status;
- assessment hash;
- zero-authority flags.

Raw path evidence, pairwise basis references, and detailed dependency group content are
not copied into the analytics projection.

## Security properties

v0.1 is designed to prevent:

- model-count laundering;
- same-source corroboration laundering;
- parent/child output double counting;
- transformation-lineage double counting;
- unknown relationships receiving independence credit;
- unanimous output being mistaken for independent evidence;
- majority vote becoming an authority source;
- disagreement disappearing inside a synthetic consensus.

## Bounded claim

This contract evaluates supplied provenance structure.

It does not prove that an asserted root source is genuinely independent in the physical
world, that an acquisition device was uncompromised, or that a basis receipt itself is
trustworthy.

Those guarantees require lower-level acquisition, provenance, and observer evidence.

The next P1 candidate is bounded remediation / governance escalation, where a detected
problem must be able to reach an authorized corrective path without allowing the
detector to mint its own authority.
