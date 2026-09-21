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
| P0 | Derived memory cannot originate authority | `AuthorityProjection`, `ReadAdmissibilityReceipt`, no-mint Crucibles | **v0.1 candidate implemented on this branch** |
| P0 | Actor cannot re-enter or mutate its governing control plane | `ControlPlaneIsolationReceipt` | planned; not promoted |
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

F12/F23 are the direct evidence drivers for the v0.1 candidate implemented here. Their
architecture consequence is still subject to PhiOS tests and Crucibles. All other rows
remain candidates only.

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

## Explicit non-goals

Research-hardening v0.1 does **not**:

- make memory an authority service;
- store executable grants in `MemoryRecord`;
- infer grants from summaries, similarity, consensus, recency, or usefulness;
- authenticate authority events;
- replace `ActionBindingGrant`, PhiReflex grants, or execution-time revalidation;
- implement control-plane isolation, effect classification, or observation-frontier
  enforcement;
- auto-promote any research finding into policy.

Those remain separate, independently reviewable increments.
