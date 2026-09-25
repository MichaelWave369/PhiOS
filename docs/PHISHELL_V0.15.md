# PhiShell v0.15 / Curiosity Persistence Bridge v0.4

## Status

Governed persistence integration rung.

This release connects the visual ΦDream / Symbol Lab to the canonical Python
Curiosity Store without allowing browser state to self-authorize filesystem
writes.

## Core rule

```text
CANONICAL READ != PERSIST AUTHORITY
PERSIST REQUEST != ACTIONLEASE
ACTIONLEASE != EXECUTOR ENTERED
```

## What is now live

### Canonical Curiosity read projection

A loopback-only Python sidecar exposes the canonical Curiosity Store through:

```text
GET /api/v1/curiosity
```

The sidecar binds only to `127.0.0.1`.

Its projection is persistent, read-only, bounded, zero-authority, and
hash-preserving.

PhiShell proxies this through the existing same-origin local transport and
validates the envelope before exposing it to Symbol Lab.

### Symbol Lab canonical view

Symbol Lab can now detect the canonical Curiosity sidecar, list recent canonical
artifacts, show kind / claim class / canonical digest, and open one canonical
artifact as a zero-authority read copy in the session constellation.

Opening a canonical artifact does not mutate the canonical store.

### Governed `curiosity.persist` capability

The Python runtime now defines one bounded active capability:

```text
capability_id: curiosity.persist
permission:    curiosity.write
effect:        filesystem.change
risk:          low
```

The persistence executor validates one exact canonical Curiosity persistence
payload, requires `created_by` to match the ActionLease principal, appends
the resulting zero-authority `CuriosityArtifact` to the existing append-only
`CuriosityStore`, and returns through the existing governed execution receipt
chain.

The persistence service intentionally exposes no unleased write method.

### Existing ActionLease runtime remains authoritative

Persistence uses the current PhiOS chain:

```text
PlanState
   +
PlanActionBinding
   +
ActionLease
   +
LeaseVerificationEvidence
   +
current AuthorityEpoch
        ↓
GovernedLeasedExecutionHandoff
        ↓
EffectBoundaryPolicy
        ↓
PermissionGate
        ↓
curiosity.persist executor
        ↓
CuriosityStore append
        ↓
Reality Ledger execution receipt
```

The Curiosity artifact itself remains:

```text
operational_authority = false
action_authority      = false
execution_authority   = false
```

Authorized persistence does not turn symbolic content into authority.

## Why browser writes are still held

PhiOS currently has the ActionLease contract and leased runtime handoff, but the
browser does not yet have a trusted live issuer/verifier service.

Allowing Symbol Lab to manufacture its own accepted lease-verification evidence
would be authority laundering.

Therefore:

```text
POST /api/v1/curiosity/artifacts
```

fails closed with:

```text
428 Precondition Required
action_lease_required
writeAvailable = false
effectPerformed = false
```

The UI shows this boundary directly as:

```text
SESSION CREATE · CANONICAL READ
WRITE HELD · ACTIONLEASE REQUIRED
```

## Local sidecar

From the repository environment:

```bash
python -m phios.curiosity_projection_server
```

Defaults:

```text
host:       127.0.0.1
port:       3971
store root: ~/.phios/curiosity
```

Optional environment variables:

```text
PHIOS_CURIOSITY_PORT
PHIOS_CURIOSITY_ROOT
```

## Failure behavior

The bridge fails closed when the sidecar is unavailable, the projection envelope
is malformed, an artifact carries authority, a canonical digest is malformed,
a projection claims browser write availability, the persistence payload is
non-canonical, `created_by` does not match the lease principal, the
ActionLease is stale / consumed / mismatched / unverified / denied, the
permission gate denies `curiosity.write`, or the effect contract does not
match `filesystem.change`.

## What this rung deliberately does not do

This release does not issue ActionLeases from the browser, verify a lease issuer
cryptographically, let React state write files, auto-persist session objects,
silently turn a read copy into a canonical record, grant factual status to
persisted symbols, or bypass existing action-binding / effect-boundary
machinery.

## Next rung

The next required piece is a trusted local **authority broker / verifier bridge**
for one narrow capability:

```text
curiosity.persist
```

That broker should let an operator explicitly approve one exact canonical
payload, issue a bounded single-use lease, provide independently verified lease
evidence, and return the resulting Reality Ledger receipt to Symbol Lab.

Only then should the currently disabled **Persist Selected** control become
active.

The door now exists.

The lock is real.
