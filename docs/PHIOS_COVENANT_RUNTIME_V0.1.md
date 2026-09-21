# PhiOS Covenant Runtime v0.1

## CR-01 — Contracts, Identity, Topology, and Transition Evidence

**Status:** Alpha contract

**Baseline:** PhiOS App Platform v0.50

**Primary invariant:**

> **CAPABILITY != AUTHORITY**

CR-01 introduces a deterministic, zero-authority vocabulary for describing identity,
actor boundary state, legal topology, transition intent, and transition evidence.

It does not modify the Spine, executor, sandbox, App Platform, governed memory,
Reality Ledger, or Reflex authority plane.

It does not create an authority source.

---

## Scope

CR-01 adds:

~~~text
phios/covenant/
    __init__.py
    models.py
    identity.py
    zones.py
    receipts.py
~~~

Schemas:

~~~text
phios.identity_seal.v0.1
phios.boundary_context.v0.1
phios.boundary_transition_request.v0.1
phios.boundary_transition_receipt.v0.1
~~~

No new dependency is required.

---

## Architectural law

Covenant topology describes constraints. It does not grant permission.

Therefore:

~~~text
known identity != trusted identity
trusted identity != permission
capability != authority
zone membership != authority
seal != authority
receipt != authority
provenance != authority
memory != authority
analytics != authority
proposal != authority
~~~

The existing App Platform laws remain unchanged:

~~~text
PROVENANCE != INSTALL AUTHORITY
INSTALL != UPDATE AUTHORITY
INSTALL != LAUNCH AUTHORITY
~~~

Every CR-01 actor context, transition request, and transition receipt fixes:

~~~text
action_authority = false
execution_authority = false
~~~

---

## IdentitySeal

Schema:

~~~text
phios.identity_seal.v0.1
~~~

An IdentitySeal binds:

~~~text
subject_id
subject_kind
implementation_sha256
manifest_sha256
source_sha256
issuer_id
issuer_key_id
~~~

CR-01 also fixes:

~~~text
trusted_identity = false
action_authority = false
execution_authority = false
~~~

The canonical seal_sha256 is deterministic over the exact record body.

The CR-01 seal is a digest-bound provenance record. It is not yet a Reflex-signed
trust assertion and it is never an execution grant.

Changing implementation, manifest, source, issuer, kind, or subject identity changes
the canonical seal digest.

Unknown fields fail closed.

---

## Trust topology

The strict actor topology is:

~~~text
EXTERNAL
  ↓
INTAKE
  ↓
IDENTIFIED
  ↓
BOUNDED
  ↓
GOVERNED_EXECUTION
  ↓
OBSERVED
  ↓
VERIFIED_OUTPUT
~~~

ROOT is represented in the vocabulary only so the contract can reject it explicitly.

It is not an actor execution zone.

No actor context or transition may use ROOT as a source or destination.

The allowed transition set is exactly:

~~~text
EXTERNAL -> INTAKE
INTAKE -> IDENTIFIED
IDENTIFIED -> BOUNDED
BOUNDED -> GOVERNED_EXECUTION
GOVERNED_EXECUTION -> OBSERVED
OBSERVED -> VERIFIED_OUTPUT
~~~

Skipping zones, moving backward, or entering ROOT fails closed.

---

## BoundaryContext

Schema:

~~~text
phios.boundary_context.v0.1
~~~

A BoundaryContext describes:

~~~text
zone
identity_seal_sha256
execution_circle_sha256 | null
previous_transition_receipt_sha256 | null
action_authority = false
execution_authority = false
~~~

The optional execution-circle digest is a forward-compatible reference only in CR-01.

CR-01 does not implement ExecutionCircle policy. That remains a later increment.

The context has its own canonical boundary_context_sha256.

---

## BoundaryTransitionRequest

Schema:

~~~text
phios.boundary_transition_request.v0.1
~~~

A request binds:

~~~text
source_zone
target_zone
subject_seal_sha256
sorted evidence_refs
action_authority = false
execution_authority = false
~~~

Only one exact legal adjacent crossing can be represented.

The request has a canonical boundary_transition_request_sha256.

Creating the request grants nothing.

---

## BoundaryTransitionReceipt

Schema:

~~~text
phios.boundary_transition_receipt.v0.1
~~~

A receipt binds:

~~~text
status = ACCEPTED | HELD | BLOCKED
source_zone
target_zone
subject_seal_sha256
boundary_transition_request_sha256
sorted evidence_refs
requirements_satisfied
reason
action_authority = false
execution_authority = false
~~~

Status semantics are strict:

~~~text
ACCEPTED -> requirements_satisfied = true
HELD    -> requirements_satisfied = false
BLOCKED -> requirements_satisfied = false
~~~

The canonical receipt_sha256 is deterministic. CR-01 intentionally omits random
receipt IDs and timestamps from this contract so identical evidence produces identical
transition receipts.

An ACCEPTED transition means only:

> the represented boundary requirements were recorded as satisfied.

It does not mean:

> the actor may execute.

---

## ROOT rule

CR-01 encodes this directly:

> **No model, agent, tool, app, workflow, memory record, or execution graph may
> transition into ROOT authority.**

ROOT remains external to actor execution topology.

Future authority integration must reference existing explicit PhiOS grant machinery.
Covenant must never mint authority merely because an actor occupies a more constrained
zone.

---

## Relationship to existing authority

CR-01 does not import or export ActionBindingGrant.

A Covenant receipt is not an ActionBindingGrant and cannot be reconstructed as one.

Unknown authority-like fields such as:

~~~text
authority_source
memory_authority
analytics_authority
~~~

fail strict schema reconstruction.

This is structural separation, not merely documentation.

---

## Fail-closed behavior

CR-01 rejects:

- unknown schema fields;
- malformed SHA-256 values;
- unsupported identity kinds;
- identity records asserting trust or authority;
- unsupported zone names;
- ROOT actor contexts;
- ROOT transitions;
- skipped or reversed transitions;
- unsorted or duplicate evidence references;
- transition requests asserting authority;
- receipt status/requirements contradictions;
- receipts asserting authority;
- canonical digest mismatches;
- authority-like fields not present in the schema.

---

## Acceptance tests

CR-01 tests demonstrate:

~~~text
IdentitySeal canonical hashing is deterministic.
Tampering changes or invalidates the seal.
Unknown fields fail closed.
Zone names are strictly enumerated.
ROOT cannot be used as an actor destination.
Illegal transitions reject.
Transition requests hash deterministically.
Transition receipts hash deterministically.
Transition receipts fix action_authority = false.
Transition receipts fix execution_authority = false.
Covenant exports no ActionBindingGrant.
Covenant receipts are not ActionBindingGrant instances.
Memory/analytics authority fields cannot be inserted into Covenant records.
~~~

The repository CI must continue to pass:

~~~text
ruff
mypy
full pytest
no-telemetry policy
governed-memory vector lane
native DuckDB / Linux-isolation lane
~~~

---

## What CR-01 deliberately does not do

CR-01 does not:

- sign identity seals with Reflex keys;
- establish trusted identity;
- evaluate dynamic boundary prerequisites;
- add shadow or enforce runtime modes;
- create InvocationContract;
- create PreflightAttestation;
- create ExecutionCircle policy;
- alter Bubblewrap;
- create or consume ActionBindingGrant;
- call GovernedExecutionHandoff;
- call PhiOSSpine.run();
- sequence GovernedExecutionGraph steps;
- alter App Platform v0.50 behavior;
- read authority from memory;
- read authority from analytics.

---

## Next increment

CR-02 should add the BoundaryTransition evaluator and:

~~~text
PHIOS_COVENANT_MODE=off|shadow
~~~

with default:

~~~text
off
~~~

Shadow mode may evaluate and receipt topology but must not block or authorize existing
execution.

Promotion to future enforcement remains an explicit operator action.
