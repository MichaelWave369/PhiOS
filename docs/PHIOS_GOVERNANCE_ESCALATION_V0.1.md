# PhiOS Governance Escalation v0.1

## Status

Research-hardening candidate.

Primary contracts:

```text
phios.verifier_semantics.v0.1
phios.governance_escalation.v0.1
VerifierSemanticsReceipt
GovernanceEscalationReceipt
```

Primary rule:

```text
DETECTION
!=
AUTHORIZED REMEDIATION
```

A verifier may discover a problem, preserve the evidence, and request a governed next
step. It may not grant itself permission to repair, rewrite, promote, disable, launch,
install, or otherwise mutate the system it is judging.

## Why this boundary exists

A verifier that can both declare a defect and directly repair the defect has two roles
collapsed into one actor:

```text
judge
+
authority
```

That creates a circular trust path.

PhiOS instead separates:

```text
observation
→ verification
→ escalation request
→ external/governed authorization
→ existing action/execution boundary
```

The escalation layer is therefore advisory and routing-oriented.

## Source contract

v0.1 accepts the existing `RealityReceipt` as the source detection contract.

The source must:

- be produced by `reality.verifier`;
- retain `promotion_status = not_promoted`;
- declare a verification method;
- already exist in the attached Mandala ledger when ledger-backed validation is used;
- match the persisted receipt contents exactly.

PhiOS computes a canonical SHA-256 over the complete source receipt and binds that digest
into both downstream governance receipts.

A receipt ID alone is not sufficient.

## VerifierSemanticsReceipt

The verifier-semantics receipt explicitly states what the verifier may and may not do.

It binds:

```text
source_reality_receipt_id
source_reality_receipt_sha256

verifier_id
verification_method
source_status
verdict_summary

observation_frontier_sha256
observability_receipt_sha256
observability_status
```

and fixes:

```text
detects_evidence_state         = true
may_emit_escalation_request    = true

may_authorize_remediation      = false
may_execute_remediation        = false
may_promote                    = false

operational_authority          = false
action_authority               = false
execution_authority            = false
```

The observation-frontier linkage matters because a verifier finding must not lose the
bounds established by v0.4 when it crosses into governance.

## Escalation dispositions

v0.1 supports three dispositions.

### REVIEW

```text
ROUTED_FOR_REVIEW
```

Use this when a problematic verifier result should be surfaced to a governance/operator
review boundary.

No action candidate may be attached.

### REVERIFY

```text
ROUTED_FOR_REVERIFICATION
```

Use this when the finding needs another observation, another verifier, or stronger
evidence.

No action candidate may be attached.

### REMEDIATE

```text
ROUTED_FOR_AUTHORIZATION
```

This disposition describes a candidate consequential action.

It does **not** authorize or execute that action.

The request must bind the exact current candidate capability contract:

```text
candidate_capability_id
candidate_capability_version
candidate_capability_risk
candidate_capability_contract_sha256

candidate_payload_sha256
requested_permissions
requested_effects
```

The candidate contract is evidence describing the requested remediation target.

It is not a grant.

## Trigger eligibility

Every escalation references exact Reality claim IDs from the source receipt.

The source verdict is read from the persisted verifier receipt rather than accepted from
the escalation caller.

### Problematic results

The following can be surfaced for review/reverification:

```text
CONTRADICTED
UNRESOLVED
BLOCKED
```

A set containing only:

```text
SUPPORTED
```

is held rather than manufacturing a governance incident from a successful verifier
result.

### Remediation

A remediation candidate is routed for authorization only when every selected trigger
claim is:

```text
CONTRADICTED
```

If even one selected trigger is `UNRESOLVED` or `BLOCKED`, the remediation route is
held.

This does not mean every contradiction should be repaired. It means unresolved evidence
cannot silently be upgraded into a mutation request.

## GovernanceEscalationReceipt

The escalation receipt binds:

- exact source Reality receipt ID/hash;
- exact VerifierSemanticsReceipt hash;
- deterministic escalation-request ID;
- disposition;
- routing status;
- target governance route;
- exact trigger claim IDs and source verdicts;
- exact candidate capability/payload contract for remediation;
- requested permission/effect tuples.

It fixes:

```text
downstream_authority_required = true

remediation_authorized = false
remediation_executed   = false
promotion_status       = not_promoted

operational_authority  = false
action_authority       = false
execution_authority    = false
```

Possible routing states are:

```text
ROUTED_FOR_REVIEW
ROUTED_FOR_REVERIFICATION
ROUTED_FOR_AUTHORIZATION
HELD
```

`ROUTED_FOR_AUTHORIZATION` should be read literally. It is a request arriving at an
authority boundary, not authority itself.

## Spine integration

`PhiOSSpine.escalate_reality_finding(...)` is the v0.1 runtime seam.

It requires the source verification to belong to the active Spine task.

For `REMEDIATE`, Spine looks up the current registered capability and snapshots:

- capability version;
- risk;
- full canonical capability contract SHA-256;
- requested permissions;
- requested environmental effects;
- candidate payload SHA-256.

The method then emits the governance receipts.

It does not:

- call the executor;
- create an `ActionReceipt`;
- consume an action binding;
- create an `ActionBindingGrant`;
- alter `AuthorityContext`;
- install a candidate;
- promote memory or evidence.

## Receipt lineage

The intended lineage is:

```text
Reality GateReceipt
        ↓
RealityReceipt
        ↓
VerifierSemanticsReceipt
        ↓
GovernanceEscalationReceipt
        ↓
external / governed authorization boundary
```

The existing action/effect/execution stack remains downstream.

For a future remediation to execute, it still needs the existing authority path rather
than receiving a shortcut from the verifier.

## Persisted-source integrity

When `GovernanceEscalationService` has a Mandala ledger, it loads the persisted source
receipt by ID and compares its canonical digest with the supplied `RealityReceipt`.

This prevents a caller from:

1. obtaining a legitimate receipt ID;
2. altering its findings in memory;
3. reusing the original ID as though the altered receipt were canonical evidence.

## Ledger analytics

The read-only Ledger projection supports both new receipt types.

For verifier semantics it exposes bounded metadata such as:

- source receipt identity/hash;
- verifier identity and method;
- source status/verdict counts;
- observability linkage;
- authority-denial flags.

For escalation it exposes:

- source/verifier-semantics hashes;
- request ID;
- disposition/routing status;
- target ref;
- trigger count;
- candidate capability identity/version/risk;
- candidate capability/payload hashes;
- requested permission/effect counts;
- authority/remediation/promotion flags.

It deliberately excludes:

- detailed remediation reason;
- raw trigger claim IDs;
- trigger verdict records;
- raw requested permission list;
- raw requested effect list.

Analytics can answer what governance path was requested without automatically receiving
the whole remediation payload or evidence detail.

## Security properties

v0.1 is designed to prevent:

- verifier self-authorization;
- detector-to-executor role collapse;
- unresolved-evidence mutation;
- supported-result incident manufacture;
- action-candidate smuggling through REVIEW/REVERIFY;
- forged source-receipt reuse;
- cross-task escalation through the active Spine;
- escalation-as-promotion;
- escalation-as-action-grant.

## Bounded claim

This layer does not prove that a remediation proposal is correct.

It also does not establish that a contradiction represents a defect in the target system
rather than a bad expectation, stale claim, broken observer, or incomplete context.

The contract proves a narrower property:

> A verifier finding can reach a bounded governance request without allowing the
> verifier or request to become the authority that executes the proposed correction.

Future remediation execution must remain behind the existing governed action and
execution boundaries.
