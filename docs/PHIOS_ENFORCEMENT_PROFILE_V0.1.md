# PhiOS Enforcement Profile v0.1

## Status

Architecture contract candidate.

Schemas:

- `phios.enforcement_rule.v0.1`
- `phios.enforcement_profile.v0.1`

Primary rule:

```text
POLICY CLAIM != ENFORCEMENT BOUNDARY != AUTHORITY
```

## Purpose

The Enforcement Profile is PhiOS's explicit trust map for one exact
`EffectIntent`.

It answers:

> For this intended effect, what specific rule is being claimed, which layer is
> responsible for enforcing it, across what trust boundary, and what evidence
> supports that claim?

It does not grant permission and it does not execute anything.

## Relationship to EffectIntent

```text
EvidenceRef(s)
      ↓
EffectIntent
      ↓
EnforcementProfile
      ↓
future authority evaluation
```

The profile binds to one exact `effect_intent_sha256`.

Changing the capability, payload, evidence context, or declared effects changes
the EffectIntent identity and therefore requires a different profile.

## EnforcementRule

Each rule records:

- a canonical `rule_id`;
- the EffectIntent effects it applies to;
- the bounded constraint being claimed;
- the enforcement layer;
- the trust boundary;
- the claim status;
- the named mechanism;
- supporting EvidenceRef digests;
- zero operational, action, and execution authority;
- `effect_performed = false`.

## Enforcement layers

The v0.1 vocabulary is:

```text
python_policy
application_contract
broker
linux_permissions
linux_namespaces
resource_limits
transport_boundary
external_system
none
unknown
```

The vocabulary identifies where a rule is claimed to live. It does not make
the claim true merely by naming the layer.

## Trust boundaries

The v0.1 vocabulary is:

```text
same_process
process_boundary
kernel_boundary
transport_boundary
external_boundary
none
unknown
```

This prevents a same-process Python check from being described as though the
Linux kernel enforced it.

## Status vocabulary

```text
enforced
advisory
not_enforced
unknown
```

### enforced

An `enforced` rule must name:

- a concrete enforcement layer;
- a concrete trust boundary;
- at least one supporting EvidenceRef digest.

This is still a claim about one bounded rule. It is not proof that the entire
system, capability, or effect is secure.

### advisory

An `advisory` rule also requires a concrete layer, boundary, and evidence.

It records a meaningful control that should not be represented as a hard
enforcement boundary.

### not_enforced

A `not_enforced` rule must use:

```text
layer = none
boundary = none
```

and cannot cite enforcement evidence.

This makes absence of enforcement explicit instead of silently disappearing
from the map.

### unknown

An `unknown` rule must use:

```text
layer = unknown
boundary = unknown
```

Unknown enforcement is preserved as unknown. It is not upgraded by optimism.

## Mapping completeness

`mapping_complete` means only:

> Every declared EffectIntent effect has at least one rule entry.

It does **not** mean:

- every effect is adequately constrained;
- every rule is enforced;
- the capability is safe to execute;
- authority should be granted.

A profile may therefore be fully mapped while
`effects_without_enforced_rule` remains non-empty.

Example:

```text
filesystem.change
  workspace-write-confinement
  linux_namespaces / kernel_boundary / enforced

external_state.change
  external-mutation-boundary
  none / none / not_enforced
```

The map is complete, but `external_state.change` still has no enforced rule.

## Existing PhiOS enforcement reality

PhiOS already contains enforcement-relevant mechanisms at different layers,
including:

- Python policy and permission gates;
- effect declaration matching;
- governed action binding;
- Bubblewrap Linux namespaces;
- resource limits;
- control-plane isolation evaluation;
- loopback transport boundaries.

Those mechanisms are not interchangeable.

For example, the build sandbox currently reports explicit control evidence,
including namespace enforcement and resource limits, while also reporting
controls that are not present such as:

```text
seccomp_enforced = false
network_allowlist_enforced = false
process_count_limit_enforced = false
```

The Enforcement Profile contract exists so those distinctions can eventually
be represented in one common trust map without inflating weaker controls into
stronger ones.

## No automatic authority

The profile fixes:

```text
effect_performed = false
operational_authority = false
action_authority = false
execution_authority = false
```

A complete map is evidence for later authority evaluation. It is not authority.

This also preserves the repository rollout rule that readiness and assessment
remain advisory rather than auto-promoting adapters or execution paths.

## What v0.1 does not do

This PR does not:

- integrate the profile into the existing build sandbox;
- integrate the profile into governed execution handoff;
- alter permission or grant behavior;
- create an authority epoch;
- create an Action Lease;
- declare PhiOS security-complete.

The next integration rung should translate one real runtime receipt into
EnforcementProfile rules so the shared contract is tested against actual
enforcement evidence before authority lifetimes are introduced.
