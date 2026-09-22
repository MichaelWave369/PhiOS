# PhiOS Version and Contract History

This file preserves the active contract lineage after the redundant root-level versioned
overview READMEs were retired.

The historical overview files remain available through Git history. The technical
contracts below remain in the working tree and are the better source for exact behavior.

## Source-of-truth order

When historical documents disagree with current behavior, prefer:

1. code on `main`;
2. current tests and CI-enforced contracts;
3. the latest component contract;
4. the root README;
5. older historical material.

## App Platform

| Version | Boundary / capability | Contract |
|---|---|---|
| v0.25 | Manifest + deterministic registry | [contract](PHIOS_APP_PLATFORM_V0.25_MANIFEST_REGISTRY.md) |
| v0.26 | Bounded GitHub intake | [contract](PHIOS_APP_PLATFORM_V0.26_GITHUB_INTAKE.md) |
| v0.27 | Governed source acquisition | [contract](PHIOS_APP_PLATFORM_V0.27_SOURCE_ACQUISITION.md) |
| v0.28 | Deterministic build plan | [contract](PHIOS_APP_PLATFORM_V0.28_BUILD_PLAN.md) |
| v0.29 | Build execution | [contract](PHIOS_APP_PLATFORM_V0.29_BUILD_EXECUTION.md) |
| v0.30 | Linux build sandbox | [contract](PHIOS_APP_PLATFORM_V0.30_BUILD_SANDBOX.md) |
| v0.31 | Dependency broker | [contract](PHIOS_APP_PLATFORM_V0.31_DEPENDENCY_BROKER.md) |
| v0.32 | Offline npm adapter | [contract](PHIOS_APP_PLATFORM_V0.32_NPM_OFFLINE_ADAPTER.md) |
| v0.33 | Artifact install | [contract](PHIOS_APP_PLATFORM_V0.33_ARTIFACT_INSTALL.md) |
| v0.34 | Installed runtime | [contract](PHIOS_APP_PLATFORM_V0.34_INSTALLED_RUNTIME.md) |
| v0.35 | Static-web adapter | [contract](PHIOS_APP_PLATFORM_V0.35_STATIC_WEB_ADAPTER.md) |
| v0.36 | Browser session | [contract](PHIOS_APP_PLATFORM_V0.36_BROWSER_SESSION.md) |
| v0.37 | Visible Wayland browser | [contract](PHIOS_APP_PLATFORM_V0.37_VISIBLE_BROWSER.md) |
| v0.38 | Persistent desktop launch | [contract](PHIOS_APP_PLATFORM_V0.38_DESKTOP_LAUNCH.md) |
| v0.39 | Desktop app catalog | [contract](PHIOS_APP_PLATFORM_V0.39_DESKTOP_CATALOG.md) |
| v0.40 | Governed update / rollback | [contract](PHIOS_APP_PLATFORM_V0.40_UPDATE_ROLLBACK.md) |
| v0.41 | Retained-version cleanup | [contract](PHIOS_APP_PLATFORM_V0.41_RETAINED_CLEANUP.md) |
| v0.42 | Cleanup-journal reconciliation | [contract](PHIOS_APP_PLATFORM_V0.42_CLEANUP_RECONCILIATION.md) |
| v0.43 | Unresolved lifecycle transition gate | [contract](PHIOS_APP_PLATFORM_V0.43_UNRESOLVED_LIFECYCLE_GATE.md) |
| v0.44 | Governed release discovery / candidate selection | [contract](PHIOS_APP_PLATFORM_V0.44_GOVERNED_RELEASE_DISCOVERY.md) |
| v0.45 | Release structural-change evidence | [contract](PHIOS_APP_PLATFORM_V0.45_RELEASE_CHANGE_EVIDENCE.md) |
| v0.46 | Human release change review / acceptance record | [contract](PHIOS_APP_PLATFORM_V0.46_HUMAN_CHANGE_REVIEW.md) |
| v0.47 | Candidate advancement gate | [contract](PHIOS_APP_PLATFORM_V0.47_CANDIDATE_ADVANCEMENT_GATE.md) |
| v0.48 | Release build-review binding | [contract](PHIOS_APP_PLATFORM_V0.48_RELEASE_BUILD_REVIEW_BINDING.md) |
| v0.49 | Release execution lineage | [contract](PHIOS_APP_PLATFORM_V0.49_RELEASE_EXECUTION_LINEAGE.md) |
| v0.50 | Release-install proposal gate | [contract](PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md) |

## Spine

| Version | Boundary / capability | Contract |
|---|---|---|
| v0.1 | Spine foundation | [contract](PHIOS_SPINE_V0.1.md) |
| v0.2 | Mandala contract | [contract](PHIOS_SPINE_V0.2_MANDALA_CONTRACT.md) |
| v0.3 | North Gate | [contract](PHIOS_SPINE_V0.3_NORTH_GATE.md) |
| v0.4 | File acquisition | [contract](PHIOS_SPINE_V0.4_FILE_ACQUISITION.md) |
| v0.5 | Screen acquisition | [contract](PHIOS_SPINE_V0.5_SCREEN_ACQUISITION.md) |
| v0.6 | Acuity recovery | [contract](PHIOS_SPINE_V0.6_ACUITY_RECOVERY.md) |
| v0.7 | Multishot selection | [contract](PHIOS_SPINE_V0.7_MULTISHOT_SELECTION.md) |
| v0.8 | Derived sharpening | [contract](PHIOS_SPINE_V0.8_DERIVED_SHARPENING.md) |
| v0.9 | OCR interpretation | [contract](PHIOS_SPINE_V0.9_OCR_INTERPRETATION.md) |
| v0.10 | Reality Gate | [contract](PHIOS_SPINE_V0.10_REALITY_GATE.md) |
| v0.11 | Local interface verifier | [contract](PHIOS_SPINE_V0.11_LOCAL_INTERFACE_VERIFIER.md) |
| v0.12 | Local TCP verifier | [contract](PHIOS_SPINE_V0.12_LOCAL_TCP_VERIFIER.md) |
| v0.13 | Local HTTP verifier | [contract](PHIOS_SPINE_V0.13_LOCAL_HTTP_VERIFIER.md) |
| v0.14 | Local HTTP adapter | [contract](PHIOS_SPINE_V0.14_LOCAL_HTTP_ADAPTER.md) |
| v0.15 | JSON contract | [contract](PHIOS_SPINE_V0.15_LOCAL_HTTP_JSON_CONTRACT.md) |
| v0.16 | JSON structural predicates | [contract](PHIOS_SPINE_V0.16_JSON_STRUCTURAL_PREDICATES.md) |
| v0.17 | JSON multi-contract | [contract](PHIOS_SPINE_V0.17_JSON_MULTI_CONTRACT.md) |
| v0.18 | JSON scalar predicates | [contract](PHIOS_SPINE_V0.18_JSON_SCALAR_PREDICATES.md) |
| v0.19 | JSON mixed contract | [contract](PHIOS_SPINE_V0.19_JSON_MIXED_CONTRACT.md) |
| v0.20 | Repeated mixed observation | [contract](PHIOS_SPINE_V0.20_REPEATED_MIXED_OBSERVATION.md) |
| v0.21 | Timed mixed observation | [contract](PHIOS_SPINE_V0.21_TIMED_MIXED_OBSERVATION.md) |
| v0.22 | Cadenced mixed observation | [contract](PHIOS_SPINE_V0.22_CADENCED_MIXED_OBSERVATION.md) |
| v0.23 | Temporal envelope | [contract](PHIOS_SPINE_V0.23_TEMPORAL_ENVELOPE.md) |
| v0.24 | Numeric transition contract | [contract](PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md) |

## PhiReflex

| Version | Boundary / capability | Contract |
|---|---|---|
| v0.1 | Provider-neutral baseline + optional Jev shadow | [contract](PHIOS_REFLEX_V0.1.md) |
| v0.2 | Real dispatch-path shadow observation | [contract](PHIOS_REFLEX_V0.2_DISPATCH_SHADOW.md) |
| v0.3 | Explicit observed-label calibration | [contract](PHIOS_REFLEX_V0.3_OUTCOME_CALIBRATION.md) |
| v0.4 | Multi-run calibration aggregation | [contract](PHIOS_REFLEX_V0.4_CALIBRATION_AGGREGATION.md) |
| v0.5 | Governed influence-policy adoption | [contract](PHIOS_REFLEX_V0.5_GOVERNED_INFLUENCE_ADOPTION.md) |
| v0.6 | Exact-grant bounded runtime influence | [contract](PHIOS_REFLEX_V0.6_RUNTIME_INFLUENCE.md) |
| v0.7 | Persistent runtime control plane | [contract](PHIOS_REFLEX_V0.7_RUNTIME_CONTROL_PLANE.md) |
| v0.8 | Authenticated grants / signed revocation | [contract](PHIOS_REFLEX_V0.8_AUTHENTICATED_AUTHORITY.md) |
| v0.9 | Trust lifecycle, manifests, use limits, checkpoints, renewal | [contract](PHIOS_REFLEX_V0.9_TRUST_LIFECYCLE_ATTESTATION.md) |
| v0.10 | External root pin + exact adapter attestation | [contract](PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md) |

## Core reasoning and governed execution

| Version | Boundary / capability | Contract |
|---|---|---|
| v0.1 | Geometric state reduction | [contract](PHIOS_GEOMETRIC_REASONING_V0.1.md) |
| v0.2 | Relational field geometry | [contract](PHIOS_RELATIONAL_FIELD_V0.2.md) |
| v0.3 | Dynamic field state | [contract](PHIOS_DYNAMIC_FIELD_V0.3.md) |
| v0.4 | Field-aware routing | [contract](PHIOS_FIELD_AWARE_ROUTING_V0.4.md) |
| v0.5 | Governed replanning | [contract](PHIOS_GOVERNED_REPLANNING_V0.5.md) |
| v0.6 | Governed plan adoption | [contract](PHIOS_GOVERNED_PLAN_ADOPTION_V0.6.md) |
| v0.7 | Governed action binding | [contract](PHIOS_GOVERNED_ACTION_BINDING_V0.7.md) |
| v0.8 | Governed execution handoff | [contract](PHIOS_GOVERNED_EXECUTION_HANDOFF_V0.8.md) |

## Research-hardening lineage

| PR | Rung | Primary boundary |
|---:|---|---|
| #181 | v0.1 | Authority projection + no-mint memory read admissibility |
| #182 | v0.2 | Control-plane isolation |
| #183 | v0.3 | Environmental effect boundary |
| #184 | v0.4 | Observation Frontier |
| #185 | v0.5 | Transformation lineage + exactness |
| #186 | v0.6 | Evidence-path independence + disagreement |
| #187 | v0.7 | Verifier semantics + bounded governance escalation |
| #188 | v0.8 | Dynamic-state decay + termination |
| #189 | v0.9 | Memory evidence horizon + reconsolidation + API-key boundary |
| #190 | v0.10 | Invariant-bound identity continuity + exact recovery |

The detailed research-to-architecture mapping and Crucibles live in
[ENTER_THE_FIELD_PHIOS_HARDENING.md](ENTER_THE_FIELD_PHIOS_HARDENING.md).

## Why the old root overview READMEs were retired

The root accumulated dozens of files named:

```text
README_APP_PLATFORM_V*.md
README_SPINE_V*.md
```

Those overview snapshots were useful while the architecture was being built, but they
made the repository front door look like a filing cabinet tipped onto the floor.

The cleanup keeps the exact technical contract trail above, preserves every deleted
overview in Git history, and leaves the root `README.md` responsible for one job:
explaining the current project.
