# PhiOS Documentation

This directory is the documentation front door for PhiOS.

PhiOS changes quickly, so use this source-of-truth order when documents disagree:

1. code on `main`;
2. current tests and CI-enforced contracts;
3. latest versioned contract documents;
4. the root `README.md`;
5. older versioned and historical material.

## Current state

| Surface | Current line | Start here |
|---|---:|---|
| App Platform | **v0.50** | [overview](../README_APP_PLATFORM_V0.50.md) · [contract](PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md) |
| Spine | **v0.24** | [overview](../README_SPINE_V0.24.md) · [contract](PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md) |
| PhiReflex | **v0.10** | [v0.1 provider contract](PHIOS_REFLEX_V0.1.md) · [v0.2 dispatch shadow](PHIOS_REFLEX_V0.2_DISPATCH_SHADOW.md) · [v0.3 outcome calibration](PHIOS_REFLEX_V0.3_OUTCOME_CALIBRATION.md) · [v0.4 calibration aggregation](PHIOS_REFLEX_V0.4_CALIBRATION_AGGREGATION.md) · [v0.5 influence adoption](PHIOS_REFLEX_V0.5_GOVERNED_INFLUENCE_ADOPTION.md) · [v0.6 runtime influence](PHIOS_REFLEX_V0.6_RUNTIME_INFLUENCE.md) · [v0.7 runtime control plane](PHIOS_REFLEX_V0.7_RUNTIME_CONTROL_PLANE.md) · [v0.8 authenticated authority](PHIOS_REFLEX_V0.8_AUTHENTICATED_AUTHORITY.md) · [v0.9 trust lifecycle](PHIOS_REFLEX_V0.9_TRUST_LIFECYCLE_ATTESTATION.md) · [v0.10 root attestation](PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md) |
| Covenant Runtime | **CR-01 / v0.1** | [zero-authority contracts](PHIOS_COVENANT_RUNTIME_V0.1.md) |\n| Core geometric / relational reasoning | **v0.8** | [v0.1 geometry](PHIOS_GEOMETRIC_REASONING_V0.1.md) · [v0.2 relational field](PHIOS_RELATIONAL_FIELD_V0.2.md) · [v0.3 dynamic field](PHIOS_DYNAMIC_FIELD_V0.3.md) · [v0.4 field-aware routing](PHIOS_FIELD_AWARE_ROUTING_V0.4.md) · [v0.5 governed replanning](PHIOS_GOVERNED_REPLANNING_V0.5.md) · [v0.6 plan adoption](PHIOS_GOVERNED_PLAN_ADOPTION_V0.6.md) · [v0.7 action binding](PHIOS_GOVERNED_ACTION_BINDING_V0.7.md) · [v0.8 execution handoff](PHIOS_GOVERNED_EXECUTION_HANDOFF_V0.8.md) |
| Living specification | current | [PHIOS_LIVING_SPEC.md](PHIOS_LIVING_SPEC.md) |
| Architecture blueprint | current / evolving | [BLUEPRINT.md](BLUEPRINT.md) |

## Project and contributor docs

- [ENTER THE FIELD → PhiOS research hardening](ENTER_THE_FIELD_PHIOS_HARDENING.md) — evidence-to-architecture traceability, priority stack, and candidate Crucibles. Research mappings remain non-authoritative until independently tested and promoted.
- [Effect Boundary v0.1](PHIOS_EFFECT_BOUNDARY_V0.1.md) — explicit capability/executor environmental-effect contracts, zero-authority effect receipts, and fail-closed read-label laundering defense.
- [Transformation Lineage v0.1](PHIOS_TRANSFORMATION_LINEAGE_V0.1.md) — exact source/output lineage, monotone exactness classes, taint propagation, and fail-closed derived-memory provenance.
- [Evidence Independence v0.1](PHIOS_EVIDENCE_INDEPENDENCE_V0.1.md) — conservative evidence-path independence, disagreement decomposition, and zero-authority consensus accounting.
- [Governance Escalation v0.1](PHIOS_GOVERNANCE_ESCALATION_V0.1.md) — verifier semantics, bounded review/reverification/remediation requests, and explicit non-authoritative escalation.
- [Observation Frontier v0.1](PHIOS_OBSERVATION_FRONTIER_V0.1.md) — per-claim observation coverage, bounded negative-state support, and zero-authority observability lineage.
- [Root README](../README.md) — concise project front door and current capabilities.
- [AGENTS.md](../AGENTS.md) — repository operating constraints for computational collaborators.
- [CONTRIBUTING.md](../CONTRIBUTING.md) — contribution workflow.
- [CHANGELOG.md](../CHANGELOG.md) — release and development history.
- [RELEASE_SETUP.md](RELEASE_SETUP.md) — release setup notes.
- [PhiKernel migration runbook](kernel-migration-v50.md) — optional migration material.

## App Platform version trail

The App Platform trail is intentionally retained. Each overview explains the rung in approachable form; each contract document records the narrower technical boundary.

| Version | Capability | Overview | Contract |
|---|---|---|---|
| v0.25 | Manifest + registry | [overview](../README_APP_PLATFORM_V0.25.md) | [contract](PHIOS_APP_PLATFORM_V0.25_MANIFEST_REGISTRY.md) |
| v0.26 | Bounded GitHub intake | [overview](../README_APP_PLATFORM_V0.26.md) | [contract](PHIOS_APP_PLATFORM_V0.26_GITHUB_INTAKE.md) |
| v0.27 | Governed source acquisition | [overview](../README_APP_PLATFORM_V0.27.md) | [contract](PHIOS_APP_PLATFORM_V0.27_SOURCE_ACQUISITION.md) |
| v0.28 | Deterministic build plan | [overview](../README_APP_PLATFORM_V0.28.md) | [contract](PHIOS_APP_PLATFORM_V0.28_BUILD_PLAN.md) |
| v0.29 | Build execution | [overview](../README_APP_PLATFORM_V0.29.md) | [contract](PHIOS_APP_PLATFORM_V0.29_BUILD_EXECUTION.md) |
| v0.30 | Linux build sandbox | [overview](../README_APP_PLATFORM_V0.30.md) | [contract](PHIOS_APP_PLATFORM_V0.30_BUILD_SANDBOX.md) |
| v0.31 | Dependency broker | [overview](../README_APP_PLATFORM_V0.31.md) | [contract](PHIOS_APP_PLATFORM_V0.31_DEPENDENCY_BROKER.md) |
| v0.32 | Offline npm adapter | [overview](../README_APP_PLATFORM_V0.32.md) | [contract](PHIOS_APP_PLATFORM_V0.32_NPM_OFFLINE_ADAPTER.md) |
| v0.33 | Artifact install | [overview](../README_APP_PLATFORM_V0.33.md) | [contract](PHIOS_APP_PLATFORM_V0.33_ARTIFACT_INSTALL.md) |
| v0.34 | Installed runtime | [overview](../README_APP_PLATFORM_V0.34.md) | [contract](PHIOS_APP_PLATFORM_V0.34_INSTALLED_RUNTIME.md) |
| v0.35 | Static-web adapter | [overview](../README_APP_PLATFORM_V0.35.md) | [contract](PHIOS_APP_PLATFORM_V0.35_STATIC_WEB_ADAPTER.md) |
| v0.36 | Browser session | [overview](../README_APP_PLATFORM_V0.36.md) | [contract](PHIOS_APP_PLATFORM_V0.36_BROWSER_SESSION.md) |
| v0.37 | Visible Wayland browser | [overview](../README_APP_PLATFORM_V0.37.md) | [contract](PHIOS_APP_PLATFORM_V0.37_VISIBLE_BROWSER.md) |
| v0.38 | Persistent desktop launch | [overview](../README_APP_PLATFORM_V0.38.md) | [contract](PHIOS_APP_PLATFORM_V0.38_DESKTOP_LAUNCH.md) |
| v0.39 | Desktop app catalog | [overview](../README_APP_PLATFORM_V0.39.md) | [contract](PHIOS_APP_PLATFORM_V0.39_DESKTOP_CATALOG.md) |
| v0.40 | Governed update / rollback | [overview](../README_APP_PLATFORM_V0.40.md) | [contract](PHIOS_APP_PLATFORM_V0.40_UPDATE_ROLLBACK.md) |
| v0.41 | Retained version cleanup | [overview](../README_APP_PLATFORM_V0.41.md) | [contract](PHIOS_APP_PLATFORM_V0.41_RETAINED_CLEANUP.md) |
| v0.42 | Cleanup journal reconciliation | [overview](../README_APP_PLATFORM_V0.42.md) | [contract](PHIOS_APP_PLATFORM_V0.42_CLEANUP_RECONCILIATION.md) |
| v0.43 | Unresolved lifecycle transition gate | — | [contract](PHIOS_APP_PLATFORM_V0.43_UNRESOLVED_LIFECYCLE_GATE.md) |
| v0.44 | Governed release discovery / candidate selection | [overview](../README_APP_PLATFORM_V0.44.md) | [contract](PHIOS_APP_PLATFORM_V0.44_GOVERNED_RELEASE_DISCOVERY.md) |
| v0.45 | Release structural change evidence | [overview](../README_APP_PLATFORM_V0.45.md) | [contract](PHIOS_APP_PLATFORM_V0.45_RELEASE_CHANGE_EVIDENCE.md) |
| v0.46 | Human release change review / acceptance record | [overview](../README_APP_PLATFORM_V0.46.md) | [contract](PHIOS_APP_PLATFORM_V0.46_HUMAN_CHANGE_REVIEW.md) |
| v0.47 | Candidate advancement gate | [overview](../README_APP_PLATFORM_V0.47.md) | [contract](PHIOS_APP_PLATFORM_V0.47_CANDIDATE_ADVANCEMENT_GATE.md) |
| v0.48 | Release build review binding | [overview](../README_APP_PLATFORM_V0.48.md) | [contract](PHIOS_APP_PLATFORM_V0.48_RELEASE_BUILD_REVIEW_BINDING.md) |
| v0.49 | Release execution lineage | [overview](../README_APP_PLATFORM_V0.49.md) | [contract](PHIOS_APP_PLATFORM_V0.49_RELEASE_EXECUTION_LINEAGE.md) |
| v0.50 | Release install proposal gate | [overview](../README_APP_PLATFORM_V0.50.md) | [contract](PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md) |

## PhiReflex version trail

| Version | Capability | Contract |
|---|---|---|
| v0.1 | Provider-neutral rules baseline + optional Jev shadow evaluation | [contract](PHIOS_REFLEX_V0.1.md) |
| v0.2 | Real dispatch-path shadow observation with planner isolation | [contract](PHIOS_REFLEX_V0.2_DISPATCH_SHADOW.md) |
| v0.3 | Explicit observed-label calibration against persisted shadow predictions | [contract](PHIOS_REFLEX_V0.3_OUTCOME_CALIBRATION.md) |
| v0.4 | Multi-run calibration aggregation + advisory review-readiness receipt | [contract](PHIOS_REFLEX_V0.4_CALIBRATION_AGGREGATION.md) |
| v0.5 | Scoped governed adoption of an inactive Reflex influence policy | [contract](PHIOS_REFLEX_V0.5_GOVERNED_INFLUENCE_ADOPTION.md) |
| v0.6 | Exact-grant runtime activation + deterministic bounded planner influence | [contract](PHIOS_REFLEX_V0.6_RUNTIME_INFLUENCE.md) |
| v0.7 | Persistent activation control, startup recovery, leases, and hash-chained runtime ledger | [contract](PHIOS_REFLEX_V0.7_RUNTIME_CONTROL_PLANE.md) |
| v0.8 | Ed25519 authenticated grants, signed revocation, CAS fingerprint, and cross-process coordination | [contract](PHIOS_REFLEX_V0.8_AUTHENTICATED_AUTHORITY.md) |
| v0.9 | Signed trust lifecycle, provider manifests, grant-use limits, checkpoints, and lease renewal | [contract](PHIOS_REFLEX_V0.9_TRUST_LIFECYCLE_ATTESTATION.md) |
| v0.10 | External root pin, exact adapter-source attestation, activation nonces, offline checkpoint bundles, and conflict-only replication snapshots | [contract](PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md) |

## Core reasoning version trail

| Version | Capability | Contract |
|---|---|---|
| v0.1 | Quotient reduction, constraints, conserved invariants | [contract](PHIOS_GEOMETRIC_REASONING_V0.1.md) |
| v0.2 | Hard transition boundaries + relational field path cost | [contract](PHIOS_RELATIONAL_FIELD_V0.2.md) |
| v0.3 | Immutable-law dynamic field state + bounded evidence/failure updates | [contract](PHIOS_DYNAMIC_FIELD_V0.3.md) |
| v0.4 | Exact-snapshot dynamic field → relational route-cost integration | [contract](PHIOS_FIELD_AWARE_ROUTING_V0.4.md) |
| v0.5 | Same-snapshot incumbent/candidate comparison + hysteresis decisions | [contract](PHIOS_GOVERNED_REPLANNING_V0.5.md) |
| v0.6 | Scoped-grant plan adoption + immutable incumbent plan state | [contract](PHIOS_GOVERNED_PLAN_ADOPTION_V0.6.md) |
| v0.7 | Scoped plan-edge → Spine capability/payload binding | [contract](PHIOS_GOVERNED_ACTION_BINDING_V0.7.md) |
| v0.8 | Execution-time revalidation + atomic binding claim + Spine handoff | [contract](PHIOS_GOVERNED_EXECUTION_HANDOFF_V0.8.md) |

## Spine version trail

The Spine trail preserves the authority/evidence architecture as it evolved from the first execution core through bounded temporal and numeric-transition verification.

| Version | Capability | Overview | Contract |
|---|---|---|---|
| v0.1 | Spine foundation | [overview](../README_SPINE_V0.1.md) | [contract](PHIOS_SPINE_V0.1.md) |
| v0.2 | Mandala contract | [overview](../README_SPINE_V0.2.md) | [contract](PHIOS_SPINE_V0.2_MANDALA_CONTRACT.md) |
| v0.3 | North Gate | [overview](../README_SPINE_V0.3.md) | [contract](PHIOS_SPINE_V0.3_NORTH_GATE.md) |
| v0.4 | File acquisition | [overview](../README_SPINE_V0.4.md) | [contract](PHIOS_SPINE_V0.4_FILE_ACQUISITION.md) |
| v0.5 | Screen acquisition | [overview](../README_SPINE_V0.5.md) | [contract](PHIOS_SPINE_V0.5_SCREEN_ACQUISITION.md) |
| v0.6 | Acuity recovery | [overview](../README_SPINE_V0.6.md) | [contract](PHIOS_SPINE_V0.6_ACUITY_RECOVERY.md) |
| v0.7 | Multishot selection | [overview](../README_SPINE_V0.7.md) | [contract](PHIOS_SPINE_V0.7_MULTISHOT_SELECTION.md) |
| v0.8 | Derived sharpening | [overview](../README_SPINE_V0.8.md) | [contract](PHIOS_SPINE_V0.8_DERIVED_SHARPENING.md) |
| v0.9 | OCR interpretation | [overview](../README_SPINE_V0.9.md) | [contract](PHIOS_SPINE_V0.9_OCR_INTERPRETATION.md) |
| v0.10 | Reality Gate | [overview](../README_SPINE_V0.10.md) | [contract](PHIOS_SPINE_V0.10_REALITY_GATE.md) |
| v0.11 | Local interface verifier | [overview](../README_SPINE_V0.11.md) | [contract](PHIOS_SPINE_V0.11_LOCAL_INTERFACE_VERIFIER.md) |
| v0.12 | Local TCP verifier | [overview](../README_SPINE_V0.12.md) | [contract](PHIOS_SPINE_V0.12_LOCAL_TCP_VERIFIER.md) |
| v0.13 | Local HTTP verifier | [overview](../README_SPINE_V0.13.md) | [contract](PHIOS_SPINE_V0.13_LOCAL_HTTP_VERIFIER.md) |
| v0.14 | Local HTTP adapter | [overview](../README_SPINE_V0.14.md) | [contract](PHIOS_SPINE_V0.14_LOCAL_HTTP_ADAPTER.md) |
| v0.15 | JSON contract | [overview](../README_SPINE_V0.15.md) | [contract](PHIOS_SPINE_V0.15_LOCAL_HTTP_JSON_CONTRACT.md) |
| v0.16 | JSON structural predicates | [overview](../README_SPINE_V0.16.md) | [contract](PHIOS_SPINE_V0.16_JSON_STRUCTURAL_PREDICATES.md) |
| v0.17 | JSON multi-contract | [overview](../README_SPINE_V0.17.md) | [contract](PHIOS_SPINE_V0.17_JSON_MULTI_CONTRACT.md) |
| v0.18 | JSON scalar predicates | [overview](../README_SPINE_V0.18.md) | [contract](PHIOS_SPINE_V0.18_JSON_SCALAR_PREDICATES.md) |
| v0.19 | JSON mixed contract | [overview](../README_SPINE_V0.19.md) | [contract](PHIOS_SPINE_V0.19_JSON_MIXED_CONTRACT.md) |
| v0.20 | Repeated mixed observation | [overview](../README_SPINE_V0.20.md) | [contract](PHIOS_SPINE_V0.20_REPEATED_MIXED_OBSERVATION.md) |
| v0.21 | Timed mixed observation | [overview](../README_SPINE_V0.21.md) | [contract](PHIOS_SPINE_V0.21_TIMED_MIXED_OBSERVATION.md) |
| v0.22 | Cadenced mixed observation | [overview](../README_SPINE_V0.22.md) | [contract](PHIOS_SPINE_V0.22_CADENCED_MIXED_OBSERVATION.md) |
| v0.23 | Temporal envelope | [overview](../README_SPINE_V0.23.md) | [contract](PHIOS_SPINE_V0.23_TEMPORAL_ENVELOPE.md) |
| v0.24 | Numeric transition contract | [overview](../README_SPINE_V0.24.md) | [contract](PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md) |

## Launch and publication material

The `launch/` directory contains announcement, distribution, and publication drafts. These are communication artifacts, not runtime contracts.

- [Extended announcement](launch/announcement_extended.md)
- [Technical announcement](launch/announcement_technical.md)
- [Short-form announcement](launch/announcement_x.md)
- [DistroWatch submission draft](launch/distrowatch_submission.md)
- [Investor summary](launch/investor_summary.md)

## Historical naming

Some retained documents use earlier names, including **Parallax**. Those files are kept for provenance and design history; they are **not the current project or network naming source of truth**.

Current work should use the names established by the current code, README, and active project documentation. Where the collaborative/network concept is referenced outside PhiOS itself, use **Enter the Field (ETF)** rather than reviving the older Parallax branding.

Historical artifacts include:

- [PARALLAX_FOUNDING_DOCUMENT.md](PARALLAX_FOUNDING_DOCUMENT.md)
- `PARALLAX_FOUNDING_DOCUMENT.html`
- historical seals and launch drafts where older terminology may still appear.

Historical terminology should not be mechanically rewritten inside provenance artifacts unless a dedicated migration explicitly chooses to create a new edition.

## Why the history stays

PhiOS treats receipts and provenance seriously. The same principle applies to design history: older documents may be obsolete as current guidance while still being useful evidence of how a contract evolved.

The cleanup rule is therefore:

```text
make current guidance easy to find
without pretending old guidance never existed
```

That is less aesthetically pure than deleting everything old, but considerably more honest.
