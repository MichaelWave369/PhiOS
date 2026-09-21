# ENTER THE FIELD → PhiOS Research Hardening

Status: **candidate implementation track**  
Research report: **20 Sep 2026**  
Repository baseline reviewed: `main @ 4a5600acfafe6dc693eaef2a653f0503e4443ec1`  
Primary invariant: **CAPABILITY != AUTHORITY**

This document is a traceability layer between the ENTER THE FIELD research report and
the PhiOS runtime. It does not promote research findings into runtime policy. Research
produces candidates; frozen contracts, Crucibles, independent evaluation, replayable
evidence, tests, and operator review determine promotion.

## Why this is incremental

The current PhiOS architecture already contains strong authority/evidence separation:
governed memory, execution-time revalidation, immutable lineage receipts, read-only
analytics, dynamic advisory fields, PhiReflex trust lifecycles, and zero-authority
Covenant topology.

The research therefore does **not** justify a redesign. The implementation order is to
harden seams, beginning with the highest-risk P0 boundaries, while keeping every
increment independently reviewable and replaceable.

## Priority stack

| Priority | Property to prove | Candidate surface | Status |
|---|---|---|---|
| P0 | Derived memory cannot originate authority | `AuthorityProjection`, `ReadAdmissibilityReceipt`, no-mint Crucibles | **v0.1 merged via PR #181** |
| P0 | Actor cannot re-enter or mutate its governing control plane | `ControlPlaneIsolationReceipt` | **v0.2 candidate implemented on this branch** |
| P0 | Capability is classified by environmental effects, not method labels | `EffectBoundaryReceipt` | planned; not promoted |
| P0 | Containment/negative claims are bounded by demonstrated observation coverage | `ObservationFrontier` | planned; not promoted |
| P1 | Transformations preserve source, taint, exactness, and derivation lineage | `TransformationLineageReceipt`, `ExactnessClass` | planned; not promoted |
| P1 | Multi-agent corroboration reflects evidence-path independence | `IndependenceReceipt`, `DisagreementDecompositionReceipt` | planned; not promoted |
| P1 | Detection can reach bounded remediation without minting authority | `GovernanceEscalationReceipt` | planned; not promoted |
| P2 | Corrective/advisory state can decay and terminate deterministically | dynamic-state attenuation / termination | planned; not promoted |
| P2 | Memory phase and evidence horizon are explicit | reconsolidation / evidence-horizon receipts | planned; not promoted |
| P2 | Identity and recovery are invariant-based rather than topology-based | identity/recovery equivalence receipts | planned; not promoted |

## Research-hardening v0.1

This branch implements the first P0 seam only.

### Read-only AuthorityProjection

`phios.mandala.AuthorityProjection` reconstructs a present-tense
`AuthorityContext` from already-authoritative grant/revoke events.

Properties:

- explicit observation time;
- deterministic replay order;
- grant, revoke, and expiry handling;
- frozen authority ceiling;
- fail closed if an event attempts to exceed that ceiling;
- future events do not become present authority;
- output binds source-event and projection digests.

The projection is **read-only**. It does not authenticate events, create grants, write
authority state, or bypass existing action/execution gates.

### ReadAdmissibilityReceipt

Every successful canonical `get()` and every returned semantic-search hit now carries a
`ReadAdmissibilityReceipt` binding:

- exact record ID, revision, and canonical SHA-256;
- principal/task context;
- current memory policy digest;
- current supplied `AuthorityContext` digest;
- scope and classification;
- source-vs-derived epistemic kind;
- currentness at the point of consumption.

The receipt fixes:

```text
readable_as_context = true
operational_authority = false
action_authority = false
execution_authority = false
```

A memory may therefore contain text *about* authority, including instruction-like text,
without that text becoming authority.

The existing durable `MemoryOperationReceipt` remains the semantic-operation receipt.
The v0.1 admissibility receipt is an inline consumption-boundary artifact, not a new
authority store.

## Research-hardening v0.2

This branch implements the second P0 seam: explicit control-plane reachability evidence
for the Linux build sandbox.

### ControlPlaneSurfaceMap

`ControlPlaneSurfaceMap` declares host surfaces that a bounded build actor must not
observe or mutate. The current PhiOS default map includes:

- the PhiReflex runtime/control root;
- the default Spine execution-ledger root, including governed binding claims;
- the `PHIOS_REFLEX_HOME` control-location environment key.

The surface map is explicit and hashed. Custom deployments may supply an exact map for
non-default control roots. A surface is not silently assumed safe merely because it is
not part of the default installation layout.

### SandboxReachabilitySnapshot

Before build execution, the Bubblewrap runner describes the actual host reachability
offered to the build:

- acquisition/source workspace;
- auxiliary read-only host binds;
- auxiliary read-write host binds;
- explicitly injected environment keys;
- network mode;
- mount, user, PID, IPC, and network namespace evidence.

The snapshot is separate from the declared control-plane map so policy and observation
cannot quietly collapse into one assertion.

### ControlPlaneIsolationReceipt

The evaluator compares the declared control surfaces with the concrete reachability
snapshot and returns one of:

```text
ISOLATED
BLOCKED
UNKNOWN
```

`BLOCKED` means a declared control-plane path, protected environment key, or declared
loopback control endpoint is reachable. `UNKNOWN` means required namespace evidence is
missing. Only `ISOLATED` permits the sandboxed build to continue.

The receipt independently distinguishes:

```text
control_plane_reachable
mutation_reachable
```

A read-only mount of a control surface is therefore still a reachability failure even
when it does not itself prove mutation capability.

Every isolation receipt fixes:

```text
action_authority = false
execution_authority = false
```

The current build sandbox receipt advances to
`phios.build_sandbox_receipt.v0.2` and binds the exact
`ControlPlaneIsolationReceipt` SHA-256. Downstream receipts that already bind the
sandbox receipt therefore retain this hardening evidence without treating it as
authority.

### v0.2 fail-closed boundary

The control-plane check runs after Bubblewrap backend preflight but before any reviewed
build command executes. A reachable declared control surface or incomplete required
namespace evidence terminates the build path before tool execution.

This is deliberately narrower than claiming universal containment. It proves
unreachability only for the declared surface map and the observed sandbox boundary.
Future control APIs, sockets, plugins, or alternate state roots must be added to the map
before the same claim can remain valid.

## Finding traceability

The table records architecture candidates motivated by F01–F26. A mapping is not a
promotion decision.

| Finding | Candidate connection |
|---|---|
| F01 | `ContainmentBoundaryReceipt`; `AttackBudget`; sandbox-label laundering; `PATCH_SUCCESS != PROPERTY_SUCCESS` |
| F02 | `IdentityInvariantSet`; `FunctionalEquivalenceReceipt`; topology-identity laundering |
| F03 | `StateTransitionReceipt`; `EpochBoundIdentity`; substrate-continuity laundering |
| F04 | `InterpreterStateCouplingMap`; `BootstrappingDepth`; `InterpreterArtifactReceipt`; role-collapse laundering |
| F05 | `ContextAssemblyReceipt`; `EvaluationBoundaryReceipt`; role-authority and scope-persistence laundering |
| F06 | `WorkflowLineageReceipt`; `PropagationFrontier`; locally-valid chain failure |
| F07 | `RecoveryPathReceipt`; `PhaseBoundNecessity`; genesis-replay assumption |
| F08 | `ReactivationWindowReceipt`; `ReconsolidationGate`; temporal-context laundering |
| F09 | `PathwayInvariantReceipt`; microtopology overfitting; risk-weighted feedback investigation |
| F10 | `SufficiencyBoundaryReceipt`; `BiologicalSpecificityReceipt`; precondition illusion; `POLICY_COMPLETE != PATH_COMPLETE` |
| F11 | `GapBridgeReceipt`; `ComplementarityReceipt`; gap-closure laundering; `BiologicalValidationStage` |
| F12 | `ReadAdmissibilityReceipt`; `AuthorityInheritance`; `IndependenceReceipt`; historical-authority rebirth | 
| F13 | `PreCommitImpactReceipt`; `ImpactCalibrationReceipt`; low-semantic/high-impact memory failure |
| F14 | `EvidenceHorizonReceipt`; `MultiScaleEvidenceProbe`; context-horizon overreach |
| F15 | `EffectBoundaryReceipt`; `CovertChannelSurfaceMap`; semantic-write-through-read |
| F16 | `GovernanceEscalationReceipt`; `VerifierSemanticsReceipt`; detection-without-remediation |
| F17 | `DisagreementDecompositionReceipt`; uncertainty collapse; evidence-path independence |
| F18 | `DynamicStateReceipt`; state-decay calibration; attenuation on `PropagationFrontier` |
| F19 | `MonitorIndependenceReceipt`; `RealityBoundaryReceipt`; epistemic monitor capture |
| F20 | `RetentionDecisionReceipt`; `ExactnessClass`; summary-substitution error |
| F21 | `RepresentationDomainReceipt`; `ObservationTranslationReceipt`; alphabet-closure error |
| F22 | `ObservabilityBoundaryReceipt`; `ObservationFrontier`; observability-boundary leak |
| F23 | `AuthoritySourceReceipt`; `AuthorityProjection`; endogenous authority minting; `DERIVATION_CANNOT_AMPLIFY_AUTHORITY` |
| F24 | `ControlPlaneIsolationReceipt`; `AuthorityPlaneSplit`; control-plane reentry |
| F25 | `TransformationLineageReceipt`; `ContaminationLifecycleProfile`; `DefenseBottleneckReceipt`; transformation trust laundering |
| F26 | `TransformationLineageReceipt`; `ContextAssemblyReceipt`; `EffectBoundaryReceipt`; `CovertChannelSurfaceMap`; `GovernanceEscalationReceipt` |

F12/F23 are the direct evidence drivers for v0.1. F24 is the direct evidence driver for
the v0.2 control-plane isolation candidate. F01 also supports the narrower rule that a
containment label is not itself containment evidence. All remaining rows stay candidates
until their own bounded increments and Crucibles exist.

## v0.1 Crucibles

The focused test set must prove at minimum:

1. grant → revoke → expiry replay produces deterministic current authority;
2. event order at the input boundary cannot change deterministic replay;
3. an authority event cannot widen the frozen ceiling;
4. a future grant cannot become present authority;
5. instruction-like source memory remains contextual data only;
6. derived memory claiming permission remains contextual data only;
7. semantic retrieval returns only policy-eligible canonical records and annotates each
   returned hit with zero operational/action/execution authority;
8. existing action-binding and execution-handoff authority contracts remain unchanged.

## v0.2 Crucibles

The focused control-plane test set must prove at minimum:

1. a normal workspace with no declared control-plane overlap remains executable;
2. a workspace containing or contained by a protected control root blocks before build
   commands run;
3. a read-only bind of a protected control root is still rejected as reachability;
4. a read-write bind of a protected control root is identified as mutation-reachable;
5. a protected control environment key is rejected;
6. inherited host networking is rejected when the surface map declares a loopback
   control endpoint;
7. network-denied mode without network-namespace evidence is `UNKNOWN`, not safe;
8. missing IPC/PID/user/mount namespace evidence cannot produce `ISOLATED`;
9. the sandbox receipt cryptographically binds the exact isolation receipt;
10. the isolation receipt grants zero action or execution authority.

## Explicit non-goals

Research-hardening v0.1 does **not**:

- make memory an authority service;
- store executable grants in `MemoryRecord`;
- infer grants from summaries, similarity, consensus, recency, or usefulness;
- authenticate authority events;
- replace `ActionBindingGrant`, PhiReflex grants, or execution-time revalidation;
- treat control-plane isolation as proof of universal sandbox containment;
- classify environmental effects or enforce an ObservationFrontier;
- auto-promote any research finding into policy.

Those remain separate, independently reviewable increments.
