# PhiShell v0.16 — Curiosity Persistence Doorbell v0.6

## Status

Visual / transport handshake for the merged Curiosity authority broker v0.5.

This rung activates the Symbol Lab persistence request flow without moving
operator approval into the browser.

## Core rule

```text
REQUEST != APPROVAL
APPROVAL != LEASE
LEASE != EXECUTION
PERSISTED != VERIFIED
```

## Symbol Lab flow

A session-local Curiosity node can now request canonical persistence.

```text
Symbol Lab
   ↓
Request Persistence
   ↓
same-origin PhiShell host
   ↓
bounded Curiosity request contract
   ↓
local authority broker
   ↓
PENDING request
```

The browser then shows the exact local approval command returned by the broker:

```bash
python -m phios.curiosity_authority_broker approve curiosity-request-...
```

The operator runs that command outside PhiShell, reviews the exact request
identity / payload digest / kind / title / creator, and explicitly types
`approve`.

After approval, Symbol Lab can check status. A successful result returns the
canonical artifact SHA-256 and refreshes the canonical store projection.

## Browser authority boundary

PhiShell can access only these authority-broker functions through its fixed
same-origin host routes:

- broker health;
- create one bounded persistence request;
- read one bounded persistence-request status.

There is no PhiShell route for operator approval.

The transport regression suite explicitly verifies:

```text
POST /api/v1/operator-approval → 405
```

The browser never receives:

- broker HMAC key;
- ActionLease;
- accepted LeaseVerificationEvidence;
- permission grant;
- arbitrary broker routing.

## Fixed request contract

The same-origin host accepts exactly seven browser fields:

```text
artifact_kind
title
content
created_at
tags
evidence_ref_sha256s
parent_artifact_sha256s
```

Unknown fields are rejected.

Additional bounds include:

- allowlisted Curiosity artifact kinds only;
- title <= 256 characters;
- content <= 32,768 characters;
- canonical timestamp;
- <= 64 tags;
- <= 64 evidence hashes;
- <= 64 parent hashes;
- lowercase, sorted, unique tags;
- lowercase SHA-256 provenance references;
- request body <= 65,536 bytes.

The host does not expose a generic POST relay.

## Lineage preservation

A session-local child cannot be persisted while any parent is still only
session-local.

```text
session parent → session child
       │
       └─ child persistence HELD
```

Persist the parent first. Once its persistence succeeds, Symbol Lab rewrites
child edges from the session parent ID to the returned canonical artifact hash.

```text
session:parent
     ↓ successful persistence
canonical:<sha256>
```

That lets the child persist later without silently dropping provenance.

Canonical read copies are not eligible for re-persistence.

## UI states

The canonical persistence panel can display:

- authority broker availability;
- configured operator principal;
- pending request status;
- exact payload digest prefix;
- external approval command;
- held / failed / expired state;
- successful canonical artifact digest;
- manual status refresh.

The main boundary now reads:

```text
SESSION CREATE · CANONICAL READ
PERSIST REQUEST · EXTERNAL OPERATOR APPROVAL
```

## Legacy endpoint

The old placeholder endpoint:

```text
POST /api/v1/curiosity/artifacts
```

now returns `410 Gone` and directs callers to the governed persistence-request
handshake.

It cannot be used to bypass the authority broker.

## Resulting Curiosity stack

```text
v0.1  Curiosity Artifact Contract
v0.2  Curiosity Store
v0.3  Symbol Lab / Dream workspace
v0.4  lease-gated persistence capability + canonical read
v0.5  local authority broker / operator approval
v0.6  Symbol Lab request-status handshake
```

Operationally:

```text
Dream explores
Store remembers
Broker asks permission
Operator approves
ActionLease bounds execution
Reality Ledger records
```

The Curiosity object itself remains zero-authority throughout.
