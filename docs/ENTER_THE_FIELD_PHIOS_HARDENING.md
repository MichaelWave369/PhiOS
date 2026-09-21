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
| P0 | Actor cannot re-enter or mutate its governing control plane | `ControlPlaneIsolationReceipt` | **v0.2 merged via PR #182** |
| P0 | Capability is classified by environmental effects, not method labels | `EffectBoundaryReceipt` | **v0.3 merged via PR #183** |
| P0 | Containment/negative claims are bounded by demonstrated observation coverage | `ObservationFrontier`, `ObservabilityBoundaryReceipt` | **v0.4 merged via PR #184** |
| P1 | Transformations preserve source, taint, exactness, and derivation lineage | `TransformationLineageReceipt`, `ExactnessClass` | **v0.5 merged via PR #185** |
| P1 | Multi-agent corroboration reflects evidence-path independence | `IndependenceReceipt`, `DisagreementDecompositionReceipt` | **v0.6 candidate implemented on this branch** |
| P1 | Detection can reach bounded remediation without minting authority | `GovernanceEscalationReceipt` | planned; not promoted |
| P2 | Corrective/advisory state can decay and terminate deterministically | dynamic-state attenuation / termination | planned; not promoted |
| P2 | Memory phase and evidence horizon are explicit | reconsolidation / evidence-horizon receipts | planned; not promoted |
| P2 | Identity and recovery are invariant-based rather than topology-based | identity/recovery equivalence receipts | planned; not promoted |

## Research-hardening v0.1

v0.1 implemented the first P0 seam and merged through PR #181.

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

v0.2 implemented the second P0 seam: explicit control-plane reachability evidence
for the Linux build sandbox, merged through PR #182.

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

## Research-hardening v0.3

v0.3 implemented the third P0 seam: an explicit environmental-effect boundary
for executable Spine capabilities, merged through PR #183.

### Explicit capability effects

A Spine `Capability` now declares a bounded `effects` tuple independently of its
name, description, permission labels, and risk label.

The v0.1 effect vocabulary distinguishes surfaces such as:

- local/filesystem reads and changes;
- process spawning;
- network requests;
- external-state reads and changes;
- IPC requests;
- display observation/control;
- credential reads;
- control-plane reads and changes;
- `none` and fail-closed `unknown`.

The important rule is that transport or method semantics do not define the effect.
A capability called `GET`, `read`, or `status` can still declare
`network.request` and/or `external_state.change`.

### Independent executor effect contract

`ExecutorRegistry` now stores an effect contract separately from the capability
metadata. Before permission evaluation, PhiOS requires the current capability effects
and current executor effects to match exactly.

This provides two independently declared surfaces:

```text
Capability.effects
        ==
ExecutorRegistry.effects(capability)
```

A missing, unknown, or mismatched declaration blocks before executor entry.

### EffectBoundaryReceipt

Every Spine execution attempt now emits a Mandala `EffectBoundaryReceipt` before the
ordinary ACTION gate.

The receipt binds:

- capability ID/version/risk label;
- capability-declared effects;
- executor-declared effects;
- active environmental effects;
- exact-match status;
- classification completeness;
- semantic read-label conflict status;
- effect-policy SHA-256;
- zero action and execution authority.

The lineage is:

```text
EffectBoundaryReceipt
        ↓
GateReceipt
        ↓
ActionReceipt
```

The existing permission gate remains the authority checkpoint. Effect classification
does not grant permission.

### Active effect rule

The v0.1 policy treats these as active environmental effects:

```text
local_state.change
filesystem.change
process.spawn
network.request
external_state.change
ipc.request
display.control
control_plane.change
```

`network.request` is intentionally active even when a protocol method is commonly
described as read-only. A request can still trigger remote logs, counters, session
changes, lazy initialization, cache changes, hooks, or application-specific behavior.
The method name therefore cannot prove absence of environmental change.

If a capability carries the semantic risk label `read` while declaring any active
effect, the effect boundary blocks rather than allowing the label to launder the
environmental effect.

### Governed binding and execution-time drift

Hardened action bindings now snapshot `effects_declared` in
`phios.plan_action_binding.v0.7.1`.

At governed execution handoff, PhiOS revalidates:

- current capability effects against the bound effect tuple;
- current executor effect contract against current capability effects;
- the rest of the existing version/risk/permission/payload/plan contract.

Effect drift therefore holds the action before the atomic execution claim is consumed.

### Bounded claim

v0.3 classifies **declared possible effects**. It does not prove that the declaration is
complete with respect to every real-world side effect of the implementation.

That gap is intentionally left for the next P0 seam, `ObservationFrontier`, which will
bound negative/containment claims by what was actually observable and tested.

## Research-hardening v0.4

v0.4 implemented the fourth P0 seam: explicit observation-frontier evidence for
Reality Gate claims, merged through PR #184.

The governing distinction is:

```text
NOT OBSERVED
!=
DID NOT OCCUR
```

### ObservationCoverage

Each Reality claim now receives an `ObservationCoverage` record describing the
surface PhiOS actually observed.

Coverage binds:

- exact claim ID and claim kind;
- observation surface;
- bounded target;
- observer/provider identity and version when available;
- coverage kind;
- coverage status;
- exact evidence references;
- explicit limitations;
- whether the claim is a structured negative-state claim;
- whether negative-state support is actually bounded by the observed frontier.

The v0.1 coverage statuses are:

```text
COVERED
PARTIAL
UNOBSERVED
```

Examples include:

- one exact TCP listener filter at one point in time;
- one exact interface at one point in time;
- one bounded HTTP request;
- one bounded discrete HTTP observation series;
- one finite set of cited readable evidence;
- no independent observer for a generic world-state claim.

### ObservationFrontier

The complete verification run aggregates those entries into a hashed
`phios.observation_frontier.v0.1`.

The frontier status is:

```text
COVERED
PARTIAL
UNOBSERVED
```

A mixed run can therefore preserve both:

```text
claim A = directly observed within an exact frontier
claim B = outside the available observation frontier
```

without laundering the first claim's evidence into the second.

### ObservabilityBoundaryReceipt

Every Reality verification result now carries an inline, zero-authority
`phios.observability_boundary_receipt.v0.1`.

It binds:

- the exact Reality packet;
- exact observation-frontier SHA-256;
- covered, partial, and unobserved claim IDs;
- explicit structured negative-state claim IDs;
- bounded and unbounded negative-state claim IDs;
- limitations;
- zero operational/action/execution authority.

Its status is:

```text
BOUNDED
PARTIAL
OUTSIDE_FRONTIER
```

The receipt is intentionally inline rather than becoming another Mandala authority
plane. The persisted `RealityReceipt` binds the frontier SHA-256, observability-receipt
SHA-256, and observability status.

### Negative-state scope

Structured negative-state support is currently recognized only where the claim contract
itself expresses a negative boolean state:

- local interface expected down;
- local TCP listener expected not listening.

A supported negative state is annotated:

```text
supported_only_within_observation_frontier
```

That statement does not mean the state held before or after the observation, on another
host, outside the exact listener/interface target, or through an unobserved channel.

Generic prose such as:

```text
"No external side effect occurred anywhere."
```

remains unresolved and outside the observation frontier unless an independent verifier
actually exists.

### Existing Reality Gate semantics remain canonical

v0.4 does not replace Reality verdicts or create permission authority.

The Reality Gate still owns:

```text
SUPPORTED
CONTRADICTED
UNRESOLVED
BLOCKED
```

Observation-frontier evidence answers a different question:

> What could the verifier legitimately claim to have observed when it issued that
> verdict?

No additional Mandala ledger row is inserted between the existing GateReceipt and
RealityReceipt, preserving the current authority/evidence path while strengthening the
receipt lineage cryptographically.

### v0.4 bounded claim

This increment still does not establish universal observation completeness.

Provider instrumentation can itself be incomplete, compromised, sampled, or unable to
see covert channels. A `COVERED` entry means the declared bounded observer completed
the stated observation contract, not that reality outside that contract ceased to
exist.

## Research-hardening v0.5

v0.5 began the P1 hardening line with explicit transformation lineage and
representation exactness, merged through PR #185.

The governing distinction is:

```text
DERIVED FROM X
!=
IDENTICAL TO X
```

### ExactnessClass

PhiOS now uses a bounded exactness vocabulary for derived artifacts:

```text
BYTE_EXACT
REVERSIBLE
NORMALIZED
LOSSY_DERIVED
INTERPRETIVE
UNKNOWN
```

The classes describe representation/provenance properties. They do not establish truth.

`BYTE_EXACT` requires one source and an identical source/output SHA-256.
`INTERPRETIVE` requires explicit semantic inference. `LOSSY_DERIVED` requires the
transform to admit possible information loss.

A child transform cannot improve the effective exactness inherited from its parents.
A byte-exact copy of a lossy crop therefore remains `LOSSY_DERIVED`, rather than
washing the crop history away with a reassuring new hash.

### TransformationLineageReceipt

`phios.transformation_lineage_receipt.v0.1` binds:

- transform identity and version;
- exact source references and source SHA-256 values;
- exact output reference and SHA-256;
- transform-parameter SHA-256;
- parent transformation receipt hashes;
- requested and effective exactness class;
- inherited and newly-added taint labels;
- possible information loss;
- semantic-inference status;
- explicit limitations;
- zero operational/action/execution authority.

Receipt identity is deterministic over the transformation contract and lineage.

### Taint monotonicity

Transformation taints are monotone across a lineage.

A child inherits parent taints and may add new ones, but cannot silently remove prior
limitations. Examples in the current adapters include:

```text
normalized_representation
cropped_context
resampled_pixels
enhanced_pixels
machine_interpretation
canonicalized_representation
extracted_subset
```

This is provenance taint, not malware taint and not an automatic truth score.

### SOMA transformations

The first integration attaches lineage to existing SOMA transformation seams without
creating another Mandala authority plane.

- unchanged text is `BYTE_EXACT`;
- BOM/newline normalization is `NORMALIZED`;
- screen crop and nearest-neighbor enlargement are conservatively
  `LOSSY_DERIVED`;
- deterministic screen enhancement is `LOSSY_DERIVED`;
- OCR text is `INTERPRETIVE`.

Existing `PerceptionReceipt` and `OcrReceipt` rows bind the transformation receipt
hashes, effective exactness, and taints. The detailed lineage is returned inline with
the SOMA result.

Native/source evidence remains preserved under the existing contracts.

### Governed derived memory

A canonical memory record with:

```text
epistemic_kind = "derived"
```

must now carry:

- `derived_from`;
- an exactness class;
- one or more transformation-lineage receipt SHA-256 values;
- the effective taint set.

At `GovernedMemoryService.put()`, PhiOS validates the full supplied transformation
receipt chain before accepting derived memory.

The write fails closed if:

- lineage receipts are absent or malformed;
- record lineage hashes do not match the supplied receipts;
- a parent link is broken;
- a child tries to upgrade inherited exactness;
- an inherited taint disappears;
- the final output digest does not equal canonical memory content;
- final exactness/taints differ from the record metadata;
- the declared `derived_from` source is absent from the lineage.

Source memory cannot carry derived exactness or transformation taints.

The generic operator CLI therefore no longer permits an arbitrary
`--epistemic-kind derived` write. Derived writes must come through a subsystem or
importer that can produce verifiable lineage.

### Legacy memory import

The explicit legacy agent-memory importer now receipts the extraction of each
deliberation from the source JSON file.

The imported deliberation is marked `LOSSY_DERIVED`, because one deliberation is a
bounded extracted subset of the complete source file, and carries:

```text
canonicalized_representation
extracted_subset
```

The source-file hash remains preserved.

### Consumption and analytics

`ReadAdmissibilityReceipt` now surfaces derived memory exactness, transformation
receipt hashes, and taints alongside its existing zero-authority/currentness fields.

`MemoryOperationReceipt` binds the supplied transformation lineage for canonical
writes.

Read-only Ledger projection exposes only bounded lineage hashes, exactness classes, and
taint labels from Perception/OCR/Memory receipts. Transformation lineage remains
evidence, never authority.

### v0.5 bounded claim

A correctly receipted transformation proves how PhiOS says an artifact was derived and
what representational guarantees it is willing to make.

It does not prove that an OCR interpretation is true, that a summary is complete, that
an enhancement recovered missing information, or that a model-derived statement is
semantically equivalent to its source.

## Research-hardening v0.6

This branch implements the next P1 seam: evidence-path independence and explicit
disagreement decomposition for multi-participant deliberation.

The governing distinction is:

```text
THREE AGENTS AGREE
!=
THREE INDEPENDENT PIECES OF EVIDENCE
```

### EvidencePathDeclaration

Each deliberation path declares the bounded evidence structure PhiOS can actually
inspect:

- path and claim identity;
- actor identity;
- stance: `SUPPORTS`, `CONTRADICTS`, or `UNCERTAIN`;
- output SHA-256;
- direct evidence references;
- declared root-source references;
- parent path IDs;
- transformation-lineage receipt hashes;
- context SHA-256 when available;
- method label.

Different model names are not treated as independence evidence.

### IndependenceAssertion

Independence is explicit rather than inferred from disagreement or model multiplicity.

An `INDEPENDENT` pair assertion requires:

- explicit basis references;
- explicit root-source references on both paths;
- no shared direct evidence;
- no shared root source;
- no shared transformation lineage;
- no direct parent/child derivation.

Known shared ancestry overrides an attempted independence assertion and fails closed.

Relationships without demonstrated independence remain `UNKNOWN`.

### Conservative independence credit

Pairwise relations are:

```text
INDEPENDENT
DEPENDENT
UNKNOWN
```

Assessment status is:

```text
SINGLE_PATH
INDEPENDENT
DEPENDENT
MIXED
UNRESOLVED
```

Unknown relationships do not earn independence credit. For conservative group counting,
both `DEPENDENT` and `UNKNOWN` relations collapse into the same evidence group unless
explicit independence was demonstrated.

This means three agreeing model outputs over the same source can remain:

```text
raw participants = 3
demonstrated independent evidence groups = 1
```

rather than becoming artificial triple corroboration.

### IndependenceReceipt

`IndependenceReceipt` binds:

- exact claim ID;
- bounded path declarations;
- pairwise dependency relations;
- independent/dependent/unknown pair counts;
- demonstrated independent group count;
- dependency groups;
- whether apparent agreement exists without demonstrated independence;
- deterministic assessment SHA-256;
- zero operational/action/execution authority.

An unresolved independence assessment is receipted as `DEGRADED`, not silently
converted into independence.

### DisagreementDecompositionReceipt

The second receipt preserves the shape of disagreement instead of collapsing it into a
majority vote.

It records:

- raw stance counts;
- stance counts across demonstrated independent groups;
- internally contested dependency groups;
- participant-level agreement/disagreement status;
- whether unanimous participant agreement is also independence-qualified;
- `consensus_authority = false`;
- `promotion_status = not_promoted`;
- zero operational/action/execution authority.

The receipt is parent-linked to the exact `IndependenceReceipt`.

### Spine integration

`PhiOSSpine.assess_deliberation_evidence(...)` exposes the seam today even though the
current checked-in `PhiVesselAdapter` remains deterministic and does not yet implement
the full Genius Atlas / council router.

That distinction is intentional. PhiOS now has a governed evidence contract ready for
future multi-model routing without pretending the current repository already contains
an independent multi-agent acquisition system.

The assessment writes two Mandala rows:

```text
IndependenceReceipt
        ↓
DisagreementDecompositionReceipt
```

Neither receipt grants planning, action, or execution authority.

### Ledger analytics

Read-only Ledger projection exposes only bounded aggregate fields such as independence
status, pair counts, demonstrated group count, disagreement status, and assessment
hashes.

Raw evidence-path declarations and pairwise basis references are intentionally excluded
from the analytics projection.

### v0.6 bounded claim

v0.6 proves only what the supplied evidence-path and independence contracts establish.

An explicit independence basis is still evidence that must ultimately be grounded by a
real acquisition/runtime boundary. Distinct model identities, different prose, or
unanimous outputs do not by themselves prove independent evidence.

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

F12/F23 are the direct evidence drivers for v0.1. F24 drives v0.2 control-plane
isolation. F15 drives the v0.3 effect boundary. F22 directly drives v0.4 observation
frontiers. F25 directly drives v0.5 transformation lineage, with F20 reinforcing
exactness requirements for retained/derived information. F17 directly drives v0.6
independence and disagreement decomposition, while F12/F19 reinforce that apparent
corroboration cannot exceed demonstrated evidence-path independence. F26 reinforces
provenance through composition. F01 continues to require that containment claims not
exceed demonstrated coverage. All remaining rows stay candidates until their own bounded
increments and Crucibles exist.

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

## v0.3 Crucibles

The focused environmental-effect test set must prove at minimum:

1. the built-in artifact writer declares `filesystem.change` at both capability and
   executor boundaries;
2. the effect receipt precedes the permission/action receipts in Mandala lineage;
3. a missing capability effect declaration blocks before executor entry;
4. a capability/executor effect mismatch blocks before executor entry;
5. `unknown` cannot become an executable effect classification;
6. a semantic `read` risk label cannot hide an active environmental effect;
7. a network request remains an active effect regardless of GET/read-style naming;
8. governed action bindings snapshot the declared effect tuple;
9. capability-effect drift is held before the execution claim is consumed;
10. executor-effect drift is held before the execution claim is consumed;
11. EffectBoundaryReceipt itself carries zero action or execution authority;
12. Ledger snapshot projection preserves bounded effect evidence without exposing new
    authority state.

## v0.4 Crucibles

The focused observation-frontier test set must prove at minimum:

1. a supported negative TCP-listener claim is scoped to one exact point-in-time
   listener frontier;
2. generic world-state absence remains outside the frontier without an independent
   observer;
3. mixed covered and unobserved claims produce a partial frontier rather than borrowing
   coverage across claims;
4. a RealityReceipt binds the exact frontier and observability receipt SHA-256 values;
5. the inline observability receipt carries zero operational/action/execution authority;
6. no second Mandala authority plane or extra ledger row is created;
7. a missing specific observation grant cannot produce bounded negative support;
8. provider lookup without persisted absence evidence is PARTIAL rather than silently
   COVERED;
9. the same claims and observation evidence produce a deterministic frontier hash;
10. source-content absence remains bounded to the readable cited evidence set;
11. discrete HTTP series remain explicitly non-continuous coverage;
12. read-only Ledger projection can expose observability status/hashes without exposing
    hidden authority state.

## v0.5 Crucibles

The focused transformation-lineage test set must prove at minimum:

1. `BYTE_EXACT` requires an identical single-source/output SHA-256;
2. a child transform cannot upgrade a weaker parent exactness class;
3. inherited taints survive downstream transformation;
4. `INTERPRETIVE` cannot be claimed without semantic inference;
5. tampering with a lineage receipt invalidates its receipt hash;
6. unchanged text receives byte-exact lineage while normalization is explicitly
   `NORMALIZED`;
7. crop/enlarge and enhancement outputs remain derived and cannot replace native
   evidence;
8. OCR output is explicitly `INTERPRETIVE`, not source-equivalent text;
9. derived memory without supplied transformation receipts is rejected;
10. derived memory output digest/exactness/taints must match the final lineage receipt;
11. legacy memory extraction produces deterministic lossy lineage;
12. memory read admissibility exposes exactness/taint while preserving zero authority;
13. direct CLI creation of unreceipted derived memory is blocked;
14. read-only Ledger projection can expose bounded lineage metadata without creating a
    new authority plane.

## v0.6 Crucibles

The focused independence/disagreement test set must prove at minimum:

1. three agreeing actors over one shared source receive one demonstrated independent
   evidence group, not three;
2. distinct actor/model identities alone do not establish independence;
3. unknown pairwise relationships do not earn independence credit;
4. explicit independence requires basis references and explicit root-source references;
5. shared direct evidence/root sources/transformation lineage override an attempted
   independence assertion;
6. direct parent/child derivation is dependent;
7. cyclic evidence-path ancestry is rejected;
8. disagreement among independent paths remains explicit rather than collapsing into a
   winner;
9. unanimous participants are distinguished from independence-qualified agreement;
10. consensus carries zero operational/action/execution authority and cannot promote
    itself;
11. the Spine assessment seam preserves the existing authority context;
12. Ledger projection exposes aggregate independence metadata without exposing raw
    evidence-path or basis details.

## Explicit non-goals

The current research-hardening track does **not**:

- make memory an authority service;
- store executable grants in `MemoryRecord`;
- infer grants from summaries, similarity, consensus, recency, or usefulness;
- authenticate authority events;
- replace `ActionBindingGrant`, PhiReflex grants, or execution-time revalidation;
- treat control-plane isolation as proof of universal sandbox containment;
- treat declared effect classification as proof that every real effect was observed;
- treat a COVERED frontier as universal observation completeness;
- infer covert-channel absence from bounded provider observations;
- treat an exactness class as truth, semantic correctness, or independent validation;
- let a downstream transformation erase inherited taints or improve inherited
  exactness;
- treat model multiplicity, output agreement, or different wording as proof of
  evidence-path independence;
- let consensus mint action/execution authority or self-promote a claim;
- auto-promote any research finding into policy.

Those remain separate, independently reviewable increments.
