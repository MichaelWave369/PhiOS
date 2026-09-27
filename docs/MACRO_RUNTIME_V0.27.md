# Macro Runtime v0.27 — Ghost-Walk PhiVessel Context

v0.27 projects validated Ghost-Walk runtime evidence into PhiVessel through a
read-only explanation model.

The important boundary is structural rather than conventional: PhiVessel does
not receive the v0.25 control object. It receives a separate type that contains
no START, STOP, ARM, or DISARM capability.

## Architecture

```text
GhostWalkControlSurface v0.25
        |
        | validated GET projection only
        v
PhiShell /api/v1/ghostwalk
        |
        v
GhostWalkVesselContextProvider
        |
        | strips control actions
        | derives bounded explanation
        v
GhostWalkVesselContext v0.27
        |
        v
PhiVessel read-side context
```

## Context available to PhiVessel

The Vessel projection includes:

- host status
- session identifier
- run generation
- listener liveness
- baseline ticker liveness
- baseline arm/freshness state
- baseline age
- recovery state
- bounded learned-transition summaries
- bounded recent issue summaries
- deterministic health classification
- deterministic plain-language explanation

The projection deliberately omits:

- `available_actions`
- control receipts
- START
- STOP
- ARM
- DISARM
- ActionLease objects
- UIA objects
- listener objects
- execution primitives

## Authority boundary

Every `GhostWalkVesselContext` asserts:

```text
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
lifecycleAuthority   = false

canStart   = false
canStop    = false
canArm     = false
canDisarm  = false
```

Core rule:

```text
VESSIE CAN EXPLAIN GHOST WALK
!=
VESSIE CAN OPERATE GHOST WALK
```

The provider performs GET only. It has no mutation method in its public
interface.

## Health interpretation

The context adapter deterministically classifies a validated snapshot:

```text
STOPPED                 -> idle
STARTING / STOPPING     -> transitioning
FAILED                  -> failed
DEGRADED                -> attention
listener down           -> attention
ticker down             -> attention
baseline disarmed       -> attention
baseline refresh due    -> attention
otherwise RUNNING       -> healthy
```

This classification is advisory presentation state. It is not a new runtime
receipt and does not supersede the source Ghost-Walk evidence.

## Recovery explanation

If v0.24 recorded `PRIOR_RUN_ABANDONED`, PhiVessel may explain that the
previous host lifetime ended without a clean stop and that the new run used a
fresh baseline.

It must not claim that the prior baseline itself was recovered.

```text
RECOVERED HISTORY
!=
RECOVERED BASELINE
```

## Missing evidence

If the local Ghost-Walk projection is unavailable or fails validation,
PhiVessel receives no replacement fixture.

The UI displays the lack of validated context directly.

If a later refresh fails after a valid context was already displayed, the card
retains the last validated context and visibly marks it stale.

```text
MISSING EVIDENCE
!=
HEALTH
```

## PhiVessel UI

The PhiVessel dock now includes a Ghost Walk context card showing:

- NOMINAL / ATTENTION / FAILED / TRANSITION / IDLE
- concise runtime summary
- host/run/listener/baseline facts
- bounded explanation lines
- stale-context warning when a refresh fails
- explicit zero-authority footer

This is currently a typed context projection inside PhiShell. It prepares the
same object for later model prompt/context injection without granting the model
a control-plane object.

## Tests

v0.27 covers:

- healthy context derivation
- degraded baseline explanation
- abandoned-run recovery explanation
- stripping lifecycle controls from the context
- GET-only provider behavior
- fail-closed handling of non-zero authority evidence

## Next rung

v0.28 should add a governed OperatorLog interpretation editor in PhiShell so a
human can revise or annotate Ghost-Walk's inferred transition meaning directly
from the UI while preserving revision history and keeping learned candidates
distinct from accepted intent.
