# PhiOS Curiosity Authority Broker v0.5

## Status

Local authority-broker candidate for the Curiosity persistence lane.

Primary rule:

```text
BROWSER REQUEST != OPERATOR APPROVAL != ACTIONLEASE != EXECUTION
```

## Purpose

PR #227 introduced the governed `curiosity.persist` capability and deliberately
held browser writes because PhiOS did not yet have a trusted live issuer /
verifier.

This rung adds that missing local authority service without handing authority to
PhiShell JavaScript.

## Trust split

The broker separates three roles:

1. **browser request** — proposes one exact Curiosity persistence payload;
2. **operator CLI approval** — approves that exact payload outside the browser;
3. **broker execution** — verifies the approval, issues one short-lived,
   single-use ActionLease, and immediately invokes the existing governed
   persistence handoff.

The browser never receives:

- the broker HMAC key;
- an ActionLease;
- accepted LeaseVerificationEvidence;
- a general write capability;
- an operator-approval endpoint through the PhiShell host.

## Local key

The broker uses a local 32-byte HMAC key stored by default at:

```text
~/.phios/authority/curiosity-broker.key
```

The file is created with mode `0600`.

The broker refuses a key file that grants group or other access.

This key is a same-user local trust boundary. It is not claimed to protect
against malware already executing as the same operating-system account.

## Request flow

```text
Curiosity persistence proposal
          ↓
broker canonicalizes payload
          ↓
created_by fixed to configured operator principal
          ↓
exact payload SHA-256
          ↓
PENDING request
          ↓
operator CLI reviews title / kind / digest
          ↓
operator types: approve
          ↓
HMAC proof over exact request + payload digest + principal + time
          ↓
broker verifies proof and freshness
          ↓
AuthorityEpoch
          ↓
EffectIntent + EnforcementProfile
          ↓
single-use ActionLease
          ↓
LeaseVerificationEvidence
          ↓
GovernedLeasedExecutionHandoff
          ↓
EffectBoundaryPolicy
          ↓
PermissionGate
          ↓
curiosity.persist
          ↓
CuriosityStore + Reality Ledger
```

## Operator commands

Start the local broker:

```bash
python -m phios.curiosity_authority_broker serve
```

Defaults:

```text
host:       127.0.0.1
port:       3972
principal:  operator:local
state root: ~/.phios
```

The principal can be set with:

```text
PHIOS_OPERATOR_PRINCIPAL
```

A pending request returns an approval command of the form:

```bash
python -m phios.curiosity_authority_broker approve curiosity-request-...
```

The CLI prints the exact request identity, payload digest, artifact kind,
title, and creator, then requires the operator to type `approve`.

## Browser boundary

The broker may expose request creation and request-status responses to the
default local PhiShell origin, but the operator-approval endpoint is not exposed
through that browser boundary.

JSON POSTs require `application/json`, so ordinary cross-origin simple-form
requests cannot invoke approval.

The PhiShell host remains unchanged in this rung. In particular, its CSP is not
weakened to connect directly to the broker.

## Authority construction

An accepted local approval creates an AuthorityEpoch whose ceiling and active
grant contain only:

```text
curiosity.write
```

The issued ActionLease is bound to:

- principal;
- authorization receipt digest;
- exact payload digest;
- `curiosity.persist`;
- capability version;
- `filesystem.change`;
- `curiosity.write`;
- current AuthorityEpoch;
- a 120-second validity window;
- one use.

The broker immediately consumes the lease through the existing execution path.
It does not return the lease to the browser.

## Replay and scope safety

The broker rejects:

- forged HMAC proofs;
- stale proofs;
- future-dated proofs;
- wrong principals;
- payload-digest mismatches;
- approvals for unknown requests;
- approvals for non-pending requests;
- expired requests;
- replay after a request has already executed.

Existing ActionLease and action-binding replay protections remain in force
below this broker layer.

## Stored artifact authority

Successful persistence still does not promote the Curiosity artifact.

```text
artifact persisted != artifact verified
artifact persisted != factual claim
artifact persisted != action authority
```

Canonical Curiosity artifacts remain zero-authority.

## Intentional limitation

v0.5 establishes and tests the authority service first.

It does **not** yet activate the Symbol Lab persistence control. The next UI
rung should connect PhiShell to this broker through a host-mediated handshake
that preserves the existing Content Security Policy and continues to keep
operator approval outside browser authority.

The broker exists before the button does.

That ordering is intentional.
