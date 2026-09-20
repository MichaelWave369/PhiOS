# PhiReflex v0.1 — Shadow System-One Layer

## Status

PhiReflex v0.1 introduces a provider-neutral, advisory System-One layer beneath
PhiOS routing and deliberative reasoning.

It is deliberately non-authoritative:

```text
probability
!=
permission
```

and:

```text
classification
!=
execution authority
```

Every PhiReflex decision and shadow receipt retains:

```text
action_authority = false
execution_authority = false
```

## Purpose

PhiOS already separates reasoning, routing, authority, verification, and
execution.

PhiReflex adds a bounded low-latency judgment layer for questions such as:

- which advisory role best matches this task;
- how risky the task appears;
- whether deliberative System Two reasoning is probably needed;
- whether downstream verification should be strongly preferred.

v0.1 does not route tasks automatically.

It runs in **shadow mode** so provider behavior can be measured before it is
allowed to influence routing.

## Architecture

```text
task / event
    ↓
PhiReflex
    ├── deterministic local rules baseline
    └── optional shadow provider
            └── Jev / TypeSafe System One
    ↓
ReflexShadowReceipt
    ↓
Ledger / evaluation
```

Future integrations may use validated PhiReflex signals as advisory inputs to
Crane Fly routing, but CAPS / Spine authority remains separate.

## Provider-neutral contract

PhiReflex owns the contract.

Providers implement the same advisory output rather than leaking provider
semantics into the rest of PhiOS.

The v0.1 output contains:

- provider identity and version;
- model identity;
- role choice and probability distribution;
- risk choice and probability distribution;
- probability that System Two reasoning is needed;
- probability that verification is needed;
- confidence;
- observed latency;
- zero action authority;
- zero execution authority.

The fixed v0.1 role set is:

```text
utility
builder
synthesis
translator
ledger
```

The fixed v0.1 risk set is:

```text
low
elevated
high
```

## Local rules baseline

`RulesReflexProvider` is deterministic and requires no network access.

Its purpose is not to pretend handwritten heuristics are intelligence.

It supplies:

- a stable baseline;
- a guaranteed local fallback;
- comparison data for external providers;
- a reference implementation of the PhiReflex contract.

## Jev provider

`JevReflexProvider` is an optional provider backed by TypeSafe AI's official
Python SDK.

PhiOS does not bundle Jev model weights.

The provider is external and requires the official TypeSafe API.

Install the optional extra:

```bash
python -m pip install -e ".[reflex-jev]"
```

The extra currently requires:

```text
typesafe-sdk >= 0.7, < 1
```

Set the provider credential only in the runtime environment:

```bash
export TYPESAFE_API_KEY="..."
```

On Windows PowerShell:

```powershell
$env:TYPESAFE_API_KEY="..."
```

The key must not be committed to the repository or written into PhiReflex
receipts.

## Jev question mapping

v0.1 sends one state object and four bounded Choice questions:

```text
role
risk
needs_system2
needs_verification
```

The provider response is normalized into the provider-neutral
`ReflexDecision`.

If the SDK is not installed, the key is absent, the API fails, or the provider
returns unusable output, the Jev result is marked unavailable/error while the
local baseline remains intact.

## Shadow mode

v0.1 never lets the shadow provider become the operational router.

For each request:

```text
input
  ├── RulesReflexProvider → baseline decision
  └── JevReflexProvider  → shadow decision
                           or unavailable/error
```

The resulting `ReflexShadowReceipt` records:

- canonical input SHA-256;
- complete baseline decision;
- shadow provider status;
- complete shadow decision when available;
- role agreement;
- risk agreement;
- failure/unavailable reason when applicable;
- zero authority.

This creates evidence for later calibration instead of accepting vendor claims
as routing policy.

## Failure behavior

Provider failure must not break PhiOS.

v0.1 distinguishes:

```text
ok
unavailable
error
```

Examples of `unavailable`:

- `TYPESAFE_API_KEY` not configured;
- `typesafe-sdk` not installed;
- provider timeout translated into provider unavailability.

An unexpected provider implementation exception is recorded as `error`.

In every case the deterministic baseline still returns.

## CLI

PhiReflex can be exercised directly:

```bash
phi-reflex "Build and test the new routing adapter" --tool-intent
```

With Jev installed and `TYPESAFE_API_KEY` configured, the command runs Jev in
shadow mode.

Force local rules only:

```bash
phi-reflex "Translate this note" --rules-only
```

Declare an external side effect explicitly:

```bash
phi-reflex "Publish the release" --tool-intent --external-side-effect
```

The command prints the complete JSON receipt.

## Authority boundary

PhiReflex may report:

```text
risk.high = 0.99
needs_verification.yes = 0.98
role.builder = 0.91
```

Those values are information.

They cannot:

- grant a capability;
- authorize tool use;
- adopt a plan;
- execute a plan;
- bypass CAPS;
- bypass Reality Gate;
- bypass the Spine PermissionGate;
- create execution authority.

A future router may consume these values only through an explicit integration
contract.

## Dependency boundary

The TypeSafe SDK is optional.

Importing PhiOS or using the local rules provider does not require
`typesafe-sdk`.

The Jev provider dynamically loads the SDK only when it is actually used.

That preserves local-first operation and avoids making an external API a PhiOS
boot dependency.

## Tests

v0.1 tests verify:

- deterministic local baseline behavior;
- zero authority on every decision;
- Jev-shaped typed probability mapping without network calls;
- shadow comparison receipts;
- missing API key → unavailable shadow result;
- provider failure does not break the baseline;
- rules-only operation;
- invalid probability contracts fail closed;
- SDK/provider exceptions become provider-unavailable outcomes.

Live TypeSafe calls are intentionally excluded from CI because CI must not
require credentials or external network availability.


---

## Next rung

PhiReflex v0.1 is followed by
[PhiReflex v0.2 Dispatch Shadow Integration](PHIOS_REFLEX_V0.2_DISPATCH_SHADOW.md).
v0.2 observes the real PhiOS dispatch path only after the operational plan
already exists, binding the Reflex receipt to exact context and plan hashes
without inserting Reflex/Jev material into planner inputs.
