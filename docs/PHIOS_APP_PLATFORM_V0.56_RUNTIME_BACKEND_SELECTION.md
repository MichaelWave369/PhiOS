# PhiOS App Platform v0.56 — Runtime Backend Qualification and Selection

## Status

Alpha contract.

New schemas:

- `phios.runtime_backend_qualification.v0.1`
- `phios.runtime_backend_selection_proposal.v0.1`
- `phios.runtime_backend_selection_receipt.v0.1`

Consumes:

- v0.51 reviewed capsules;
- v0.53 attestations and network-denied sandbox plans;
- v0.54 OCI runtime adapter protocol;
- v0.55 rootless Podman adapter.

## Purpose

v0.55 gives PhiOS a concrete rootless Podman runtime adapter.

v0.56 separates three questions that ordinary runtime stacks often collapse:

```text
Is this backend qualified for this exact reviewed plan?
Which qualified backend should the operator select?
May the selected backend execute?
```

Those are three different state transitions.

The governing rule is:

```text
backend qualified
!= backend selected
!= execution authorized
```

## Qualification

`qualify_runtime_backend()` evaluates one explicit adapter instance against one exact
v0.53 sandbox plan, capsule and attestation.

It requires the adapter to bind:

- exact capsule artifact SHA-256;
- exact capsule storage path;
- exact sandbox-plan SHA-256;
- exact sandbox-policy SHA-256;
- enforced network denial.

The function then calls the adapter's existing v0.54 `preflight()` and
`control_evidence()` boundaries.

A qualification is accepted only when:

- the adapter ID is recognized by PhiOS;
- the adapter version matches the frozen adapter contract;
- the implementation backend matches the adapter contract;
- the runtime platform matches the capsule platform;
- the existing strict v0.54 runtime-control evidence validates.

The first recognized adapter is:

```text
phios.podman-rootless / 0.1.0
```

A successful qualification records:

- exact sandbox-plan SHA-256;
- exact capsule SHA-256;
- exact attestation SHA-256;
- capsule family;
- runtime adapter identity;
- runtime control evidence;
- canonical qualification SHA-256.

It grants no selection or execution authority.

## Selection proposal

`propose_runtime_backend_selection()` is advisory-only.

It consumes zero or more exact qualifications for the same reviewed plan.

Possible statuses are:

```text
no_qualified_backend
candidate_available
operator_choice_required
```

The proposal sorts candidates deterministically and binds their exact qualification
digests.

The proposal fixes:

```text
advisory_only = true
selection_authority = false
execution_authority = false
```

The presence of one obvious candidate does not silently select it.

## Operator selection

`select_runtime_backend()` requires:

- a proposal that actually contains selectable candidates;
- one exact candidate qualification;
- explicit approval of that qualification's SHA-256;
- one canonical operator-supplied selection UUID.

The resulting selection receipt binds:

- proposal SHA-256;
- qualification SHA-256;
- sandbox plan;
- capsule;
- attestation;
- selected adapter ID;
- runtime identity SHA-256;
- runtime controls SHA-256.

The receipt records:

```text
operator_confirmed = true
execution_authority = false
network_authority = false
install_authority = false
host_write_authority = false
```

Selection is therefore explicit evidence, not an execution grant.

## Why qualification is request-bound

v0.56 deliberately does not issue a broad statement such as:

```text
Podman on this machine is trusted forever
```

Qualification is bound to the exact reviewed sandbox plan, capsule and attestation.

That prevents a successful check for one capsule or one runtime policy from becoming
ambient authority for unrelated builds.

## Fail-closed behavior

v0.56 rejects:

- non-ready sandbox plans;
- non-denied network policy;
- capsule or attestation mismatch;
- runner capsule/path/plan/policy mismatch;
- a runner that does not enforce network denial;
- unknown adapter IDs;
- unrecognized adapter versions;
- wrong implementation backend;
- platform mismatch;
- qualifications from another request;
- duplicate candidate digests;
- malformed proposal cardinality;
- selecting a qualification absent from the proposal;
- stale qualification approval;
- authority fields changed from false;
- tampered canonical digests.

## Explicit non-capabilities

v0.56 does not:

- discover every OCI engine on the host;
- auto-select Podman;
- install Podman;
- create a v0.54 execution approval;
- consume a v0.54 execution approval;
- execute a build;
- grant network access;
- grant install or launch authority;
- change release or publication authority.

## Next boundary

v0.57 should bind an operator-confirmed v0.56 selection receipt into v0.54 runtime
execution, so a concrete backend cannot execute merely because a caller constructed it.

After that gate is frozen, the App Platform should pivot back toward the user-facing
goal: repo profiling, compatibility classification and GitHub-to-PhiOS installation.

The governing distinction remains:

```text
selected backend
!= execution approval
```
