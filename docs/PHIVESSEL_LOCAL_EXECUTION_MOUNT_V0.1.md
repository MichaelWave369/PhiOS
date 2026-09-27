# PhiVessel Local Execution Mount v0.1

This rung mounts the already-governed Macro Runtime v0.35 lease executor into
the default local Ghost-Walk / PhiVessel host.

It does not create a new execution system.

The path remains:

```text
Vessie execute(leaseId)
        ↓
PhiVessel ↔ PhiOS Bridge v0.1
        ↓
GhostWalkLeaseExecutionHandoff v0.35
        ↓
exact v0.34 ActionLease custody
        ↓
exact v0.33 executable binding
        ↓
current policy + enforcement + AuthorityEpoch
        ↓
PhiOS Spine
        ↓
governed desktop executor
```

## Why a local execution manifest exists

The default host previously had no trusted source for:

- the server-owned capability mapping registry;
- the server-owned lease policy registry;
- the current AuthorityEpoch;
- permission state used by the local Spine;
- explicit enablement of the desktop executor.

Hardcoding those values would silently create authority at process startup.

Bridge v0.2 therefore introduces a trusted local manifest.

No manifest means no execution mount.

An invalid manifest fails closed.

## Default path

Unless overridden by:

```text
PHIOS_PHIVESSEL_EXECUTION_MANIFEST
```

the host looks for:

```text
<PHIOS_STATE_ROOT>/config/phivessel-execution.json
```

The path is local process configuration. It is never supplied by Vessie,
browser content, model output, ProposalPacket, WorkObject, or ActionLease.

## Manifest contents

The manifest binds:

```text
schema_version
enabled
desktop_executor_enabled
mappings[]
lease_policies[]
authority_epoch
manifest_sha256
```

Every mapping is a canonical v0.33 `GhostWalkCapabilityMapping`.

Every lease policy is the canonical v0.34 policy shape and contains canonical
`EnforcementRule` objects.

The AuthorityEpoch is the canonical content-addressed v0.1 object.

The complete manifest is SHA-256 sealed.

## Static trust vs live authority

Mappings and lease policies are static execution trust configuration for one
host lifetime.

The mount records a static configuration digest at startup.

The AuthorityEpoch provider re-reads the manifest on every current-authority
check.

Therefore:

```text
AuthorityEpoch change
    → visible without restart
    → old ActionLease epoch mismatch
    → execution HELD

mapping / lease-policy change
    → static config mismatch
    → execution HELD
    → host restart required
```

This prevents a running process from quietly redefining the meaning of an
already-issued lease.

## Spine permission state

The local Spine is initialized from the manifest AuthorityEpoch's effective
grant tuple.

This does not turn the AuthorityEpoch into a credential.

v0.35 still re-checks the current AuthorityEpoch digest before lease claim.

If authority is revoked or otherwise changes after startup, the epoch mismatch
holds execution before the Spine executor is entered.

If new permission is added after startup, the existing Spine may remain more
restrictive until restart. That is intentionally fail-closed.

## Desktop execution

The mount installs the existing:

```text
desktop.interaction.click@0.19.0
```

through:

```text
GovernedDesktopClickExecutor.from_windows(...)
install_desktop_click_capability(...)
```

The existing desktop safety chain remains responsible for foreground-window
scope, semantic/pixel revalidation, operator-input change detection, overlay
checks, bounded SendInput injection, and post-action verification.

The local execution mount does not bypass any of those gates.

## Server behavior

The Ghost-Walk control host attempts to load the manifest during startup.

### Absent or disabled manifest

The host still starts.

```text
observe   AVAILABLE
propose   AVAILABLE
execute   UNAVAILABLE
```

### Valid enabled manifest

The host mounts the real v0.35 handoff into `PhiVesselBridgeService`.

```text
execute(leaseId)
    → LIVE GOVERNED PATH
```

### Invalid manifest

The host prints:

```text
PhiOS PhiVessel execution mount HELD: <reason>
```

and continues with execution unavailable.

A bad execution configuration does not take down observation, proposal, or
Ghost-Walk capture.

## Canonical manifest generation

Do not hand-edit the manifest seal.

Use:

```python
manifest = PhiVesselLocalExecutionManifest.build(
    enabled=True,
    desktop_executor_enabled=True,
    mappings=(mapping,),
    lease_policies=(lease_policy,),
    authority_epoch=current_epoch,
)

path.write_text(
    json.dumps(manifest.to_dict(), sort_keys=True),
    encoding="utf-8",
)
```

The mapping, lease policy, enforcement rules, and AuthorityEpoch must already be
canonical governed objects.

## Authority boundary

The manifest is trusted local configuration.

It is not:

- a ProposalPacket;
- an AuthorityRequest;
- an AuthorizationDecision;
- an ActionLease;
- an execution request.

The manifest cannot be supplied through the PhiVessel bridge.

Vessie still only gets:

```text
observe(...)
propose(...)
execute(leaseId)
```

and `execute` still accepts the ActionLease identity only.

## Restart rule

Changes to mappings or lease policies require host restart.

AuthorityEpoch-only changes do not.

This rule is deliberate:

```text
CURRENT AUTHORITY MAY CHANGE LIVE
STATIC MEANING OF A LEASE MAY NOT
```
