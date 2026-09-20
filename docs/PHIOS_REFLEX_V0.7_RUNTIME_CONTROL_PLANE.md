# PhiReflex v0.7 — Runtime Control Plane

## Status

PhiReflex v0.7 turns the live v0.6 routing-influence engine into an operational
control plane.

The central rule is:

```text
live influence
must be restorable, inspectable, collapsible, and auditable
```

v0.7 adds persistence and operator control without broadening the routing
surface introduced by v0.6.

## Runtime storage

The default local control-plane root is:

```text
~/.phios/reflex/
```

It may be overridden with:

```text
PHIOS_REFLEX_HOME
```

The control plane stores:

```text
policy.json
activation.json
lease.json
grants/
ledger.json
quarantine/
```

All authoritative state writes use write-flush-fsync followed by atomic
`os.replace(...)`.

A process crash during a write may leave an unused temporary file, but it does
not expose a partially written authoritative JSON state file.

## Persisted artifacts

### policy.json

Contains one validated v0.5 `ReflexInfluencePolicyState`.

Persisting the policy does not activate runtime influence.

A different policy cannot replace a policy while a live activation tied to the
old policy remains active.

Privilege must collapse first.

### activation.json

Contains the current validated v0.6 `ReflexActivationState`.

An active state may be restored after process restart only when:

- the state hash validates;
- the policy hash validates;
- the activation points to the exact persisted policy;
- any persisted lease validates and points to the exact activation;
- the receipt ledger remains internally valid.

Failure of those checks collapses or removes live routing influence.

### grants/

Activation grants are ingested as external typed artifacts.

Grant ingestion validates the v0.6 grant contract and stores each grant by
`grant_id`.

An exact duplicate is idempotent.

The same `grant_id` with different content is rejected.

Important limitation:

```text
authority_source is still a declared label
```

v0.7 validates grant structure, scope, and hashes, but it does **not**
cryptographically authenticate the identity that issued the grant.

Signed authority artifacts remain a future governance rung.

Grant issuance and grant consumption remain separate operations.

v0.7 does not mint its own expansion grants.

## Activation requests

Runtime activation consumes:

- persisted v0.5 policy;
- explicit v0.6 activation request;
- previously ingested external activation grant.

The request remains bound by the grant's exact
`activation_request_sha256`.

Rejected activation input must not mutate activation state.

## Runtime leases

v0.7 adds an optional local runtime lease:

```text
phios.reflex_runtime_lease.v0.7
```

The lease binds:

- exact activation-state SHA-256;
- caller-supplied expiration epoch;
- caller-supplied evaluation epoch used when the lease was set;
- deterministic lease SHA-256.

Core control-plane methods do not read wall-clock time themselves.

They require an explicit:

```text
evaluation_epoch
```

The shell supplies the current Unix epoch when invoking those methods.

This keeps the core deterministic and testable.

### Lease direction

A lease may:

- be attached when none exists;
- be shortened;
- expire and collapse privilege.

A lease may not be extended by the v0.7 lease operation.

```text
shorter authority lifetime
→ allowed

longer authority lifetime
→ rejected
```

A later reactivation under a new exact activation grant may establish a new
runtime state, but an existing lease is never silently lengthened.

## Startup restoration

Every status/evaluation path performs recovery before using persisted runtime
state.

Healthy state returns:

```text
ACTIVE
```

or:

```text
INACTIVE
```

without rewriting it.

Recovery fails closed when it encounters:

- malformed policy state;
- malformed activation state;
- activation without a policy;
- activation scoped to another policy;
- malformed lease;
- lease scoped to another activation;
- expired lease;
- corrupted receipt ledger.

Invalid persisted artifacts are moved into:

```text
quarantine/
```

using a content SHA in the quarantine filename.

They are not silently repaired into authoritative state.

## Crash-safe rollback

If the persisted activation cannot be trusted, v0.7 restores the ordinary
dispatch path.

When the policy and activation are still individually valid, the runtime uses
the v0.6 deactivation transition so privilege collapse itself remains
receipted.

If state is too malformed to validate, the malformed active artifact is
quarantined and removed from the live slot.

In both cases:

```text
untrusted runtime state
→ no live Reflex routing influence
```

## Hash-chained runtime ledger

The local runtime ledger is:

```text
ledger.json
```

Each entry records:

- monotonic sequence;
- event kind;
- caller-supplied evaluation epoch;
- previous-entry SHA-256;
- embedded receipt;
- entry SHA-256.

The ledger therefore forms a local deterministic hash chain.

The ledger stores:

- control-plane receipts;
- v0.6 activation/deactivation receipts;
- v0.6 runtime influence/fallback/rollback receipts;
- recovery receipts.

If the ledger hash chain is corrupted while routing influence is active, v0.7
fails closed and collapses that routing privilege.

The ledger is a local integrity structure, not a cryptographic signature or
remote attestation.

## Automatic dispatch restoration

Normal:

```bash
phi dispatch ...
```

now consults the persisted Reflex runtime control plane.

If no valid live activation exists:

```text
ordinary dispatch
```

continues unchanged.

If a valid live activation exists and its provider adapter is available:

1. v0.7 restores the exact persisted policy/activation;
2. v0.6 evaluates local baseline + approved provider;
3. runtime receipt is persisted;
4. the validated bounded signal is attached as:
   `context.reflex_influence`;
5. planner execution continues normally.

The currently wired external runtime provider is Jev.

An active policy naming a provider without a runtime adapter is collapsed to
ordinary dispatch rather than guessed at.

## Shadow/live separation

v0.2 shadow observation and v0.6/v0.7 live influence are mutually exclusive for
one dispatch.

If a valid live signal is produced and the operator also requests:

```text
--reflex-shadow
```

the dispatch is refused with:

```text
REFLEX_LIVE_SHADOW_CONFLICT
```

This preserves the independence requirement of shadow calibration.

If runtime influence fails closed before any signal is emitted, the ordinary
non-influenced dispatch path remains available.

## Operator commands

### Status

```bash
phi agents reflex-runtime status
```

Shows:

- recovery result;
- persisted policy;
- persisted activation;
- current lease;
- ingested grant IDs;
- ledger entry count;
- whether live routing influence is active.

### Ingest adopted policy

```bash
phi agents reflex-runtime policy-ingest policy.json
```

This stores an already-created valid v0.5 policy.

It does not create an adoption decision.

### Ingest external activation grant

```bash
phi agents reflex-runtime grant-ingest grant.json
```

This validates and stores an external v0.6 activation grant.

It does not issue that grant.

### Activate

```bash
phi agents reflex-runtime activate \
  --request activation-request.json \
  --grant-id grant-001
```

Optional privilege-limiting lease:

```bash
phi agents reflex-runtime activate \
  --request activation-request.json \
  --grant-id grant-001 \
  --lease-until-epoch 1800000000
```

### Shorten lease

```bash
phi agents reflex-runtime lease \
  --until-epoch 1799990000
```

The lease command cannot extend a current deadline.

### Kill switch

```bash
phi agents reflex-runtime deactivate \
  --reason operator-stop
```

No privilege-expansion grant is required to collapse routing influence.

### Ledger

```bash
phi agents reflex-runtime ledger
```

or:

```bash
phi agents reflex-runtime ledger --tail 20
```

## Authority boundary

An active v0.7 runtime may preserve the v0.6 scoped authority:

```text
routing_influence_authority = true
```

only for the single approved planner-context surface.

It still carries:

```text
promotion_authority = false
action_authority = false
execution_authority = false
```

The control plane cannot:

- issue its own activation authority;
- increase adopted influence weight;
- add dimensions outside the adopted policy;
- silently switch providers/models;
- grant tools;
- execute tools;
- bypass CAPS;
- bypass Spine execution permission;
- treat live-influenced dispatch as clean shadow calibration evidence.

## Tests

v0.7 tests verify:

- policy/grant/activation persistence across restart;
- exact grant ingestion is idempotent;
- conflicting grant IDs fail closed;
- leases may shorten but not extend;
- expired lease collapses privilege during restoration;
- corrupt activation state is quarantined;
- corrupted ledger collapses active privilege;
- runtime receipts enter a valid hash chain;
- operator deactivation persists across restart;
- live policy replacement requires prior privilege collapse;
- rejected lease extension is mutation-free;
- shell status/deactivate behavior;
- file-based policy/grant/request ingestion;
- normal dispatch restores persisted live influence;
- live influence refuses simultaneous shadow measurement;
- ordinary dispatch remains available without an active valid signal.

## Next rung

The next useful rung should strengthen **authority provenance and multi-process
coordination**, not widen model influence.

Potential v0.8 work:

- signed activation grants;
- authenticated authority-source identity;
- single-writer file locking / CAS semantics;
- ledger checkpoints or signatures;
- explicit grant revocation artifacts;
- cross-process state-change notifications;
- provider-adapter registry;
- lease renewal only through an explicitly grant-bound contract.

The routing surface should remain narrow until those operational guarantees are
proven.


---

## Next rung

PhiReflex v0.7 is followed by
[PhiReflex v0.8 Authenticated Authority and Coordination](PHIOS_REFLEX_V0.8_AUTHENTICATED_AUTHORITY.md).
v0.8 requires authenticated Ed25519 grant provenance for official live
dispatch, supports signed revocation and grant validity windows, serializes
control-plane operations across processes, and exposes a deterministic
control-plane fingerprint for optional stale-state compare-and-swap checks.
