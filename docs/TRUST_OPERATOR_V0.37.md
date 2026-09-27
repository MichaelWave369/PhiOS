# Trusted Manifest + AuthorityEpoch Operator v0.37

v0.37 turns the existing sealed PhiVessel local execution configuration into a
human-operable trust surface.

The governing rule remains:

```text
CAPABILITY != AUTHORITY
CONFIGURATION != LEASE
LEASE != EXECUTION
```

## CLI

The new installed command is:

```text
phi-trust
```

Primary commands:

```text
phi-trust status
phi-trust validate
phi-trust mappings
phi-trust policies
phi-trust epoch

phi-trust authority-bootstrap --expect-manifest-sha <SHA>

phi-trust grant ui.interact --expect-manifest-sha <SHA>
phi-trust revoke ui.interact --expect-manifest-sha <SHA>
phi-trust refresh-epoch --expect-manifest-sha <SHA>

phi-trust enable --expect-manifest-sha <SHA>
phi-trust disable --expect-manifest-sha <SHA>

phi-trust recover
```

All mutation commands require the exact current manifest SHA-256. If the
manifest changes after the operator inspected it, mutation fails closed.

## Authority event state

The v0.2 trusted execution mount stores a materialized `AuthorityEpoch`, but
not the authoritative event history that produced it.

v0.37 does not mutate the derived `grants` field directly.

Instead it introduces:

```text
config/phivessel-authority-events.json
```

with:

- principal identity;
- policy digest;
- frozen authority ceiling;
- explicit bootstrap lineage;
- contiguous append-only grant/revoke events;
- content-addressed state identity.

Future AuthorityEpochs are reconstructed from those events using the existing
canonical `AuthorityEpoch.build(...)` path.

## Explicit bootstrap

An existing validated execution manifest may be migrated once:

```text
phi-trust authority-bootstrap \
  --expect-manifest-sha <CURRENT_SHA>
```

Bootstrap creates baseline GRANT events only for permissions currently present
in the validated AuthorityEpoch.

It cannot increase authority beyond the existing grant set or ceiling.

Bootstrap refuses an AuthorityEpoch with `next_known_transition_at` because
the derived snapshot does not contain enough information to safely reconstruct
future expiry or future-event semantics.

After bootstrap, the manifest is resealed with a newly reconstructed
AuthorityEpoch carrying explicit v0.37 event lineage.

No host restart is required because only the AuthorityEpoch changes.

## Grant and revoke

A grant appends one authoritative local event:

```text
phi-trust grant ui.interact \
  --expect-manifest-sha <CURRENT_SHA>
```

Optional expiry:

```text
phi-trust grant ui.interact \
  --expires-at 2026-09-28T00:00:00+00:00 \
  --expect-manifest-sha <CURRENT_SHA>
```

A revoke appends one revocation event:

```text
phi-trust revoke ui.interact \
  --expect-manifest-sha <CURRENT_SHA>
```

The operator cannot:

- grant a permission outside the frozen ceiling;
- grant an already-active permission;
- revoke a permission that is not currently granted;
- move AuthorityEpoch observation time backward;
- bypass the current manifest identity check.

Authority-only changes preserve `static_config_sha256`, so the mounted
`ManifestAuthorityEpochProvider` may observe them without a restart.

This means a live revoke can invalidate later lease readiness without changing
the static execution mapping or policy configuration.

## Epoch refresh

```text
phi-trust refresh-epoch \
  --expect-manifest-sha <CURRENT_SHA>
```

replays the stored event history at the current time.

This is useful for expiring time-bounded grants.

The refresh cannot move observation time backward.

## Static execution enable / disable

```text
phi-trust disable --expect-manifest-sha <CURRENT_SHA>
phi-trust enable  --expect-manifest-sha <CURRENT_SHA>
```

These commands change both:

```text
enabled
desktop_executor_enabled
```

together.

They preserve mappings, lease policies, and AuthorityEpoch contents.

Because these fields are part of `static_config_sha256`, the existing mounted
authority provider detects the change and holds execution until restart.

Mutation receipts explicitly report:

```text
restart_required = true
```

for these operations.

## Atomic mutation and recovery

Trust mutations use:

- a kernel-backed exclusive file lock;
- same-directory temporary writes;
- `fsync`;
- atomic `os.replace`;
- an explicit pending transaction journal.

The journal lives at:

```text
config/phivessel-trust.pending.json
```

If a process or machine dies after the transaction is prepared but before all
files and receipts are finalized, later mutations refuse to proceed.

The operator must explicitly run:

```text
phi-trust recover
```

Recovery accepts only a manifest matching either the recorded previous identity
or the recorded next identity. Any unrelated external manifest change causes
recovery to fail closed.

## Mutation receipts

Completed mutations append to:

```text
ledger/trust-operator-receipts.jsonl
```

Each receipt binds:

- operation;
- local operator identity;
- previous manifest SHA-256;
- next manifest SHA-256;
- previous AuthorityEpoch SHA-256;
- next AuthorityEpoch SHA-256;
- authority-state SHA-256 when present;
- appended authority-event ID when present;
- restart requirement;
- application timestamp.

Receipts are content-addressed and have deterministic receipt IDs so recovery
does not duplicate a receipt that was already written before interruption.

The receipt itself carries no operational, action, or execution authority.

## Filesystem boundaries

Default files under `~/.phios`:

```text
config/
  phivessel-execution.json
  phivessel-authority-events.json
  phivessel-trust.pending.json
  phivessel-trust.lock

ledger/
  trust-operator-receipts.jsonl
```

The manifest path still respects:

```text
PHIOS_PHIVESSEL_EXECUTION_MANIFEST
```

when no explicit `--manifest` override is supplied.

## Operational sequence

A safe first-time operator flow is:

```text
phi-trust status
        ↓
copy current manifest_sha256
        ↓
phi-trust validate
        ↓
phi-trust authority-bootstrap --expect-manifest-sha <SHA>
        ↓
phi-trust status
        ↓
grant/revoke only as needed
        ↓
start or restart Ghost-Walk host when static trust changed
        ↓
use PhiShell human authorization console
        ↓
issue single-use ActionLease
        ↓
Vessie references only leaseId
```

## Deliberate limits

v0.37 does not:

- let Vessie mutate trust configuration;
- expose trust mutation through browser HTTP;
- edit mapping definitions;
- edit lease-policy definitions;
- expand the frozen AuthorityEpoch ceiling;
- create an ActionLease;
- execute a capability.

Mapping and lease-policy authoring remain trusted local configuration tasks.

The next operational rung should add the native/local Vessie host handshake and
then exercise one controlled end-to-end Windows Ghost-Walk acceptance path.
