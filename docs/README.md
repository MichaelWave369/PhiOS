# PhiOS Documentation

This directory is the documentation front door for PhiOS.

PhiOS changes quickly. When documents disagree, prefer:

1. code on `main`;
2. current tests and CI-enforced contracts;
3. the latest component contract;
4. the root [README](../README.md);
5. historical material.

## Current architecture

| Surface | Current line | Start here |
|---|---:|---|
| **Spine** | **v0.24** | [Numeric Transition Contract](PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md) |
| **App Platform** | **v0.50** | [Release Install Proposal Gate](PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md) |
| **PhiReflex** | **v0.10** | [Root Pinning and External Attestation](PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md) |
| **Covenant Runtime** | **CR-01 + recovery v0.1** | [Covenant Runtime](PHIOS_COVENANT_RUNTIME_V0.1.md) · [Identity Recovery](PHIOS_IDENTITY_RECOVERY_V0.1.md) |
| **Governed Memory** | active | [Governed Memory](governed-memory.md) · [Evidence Horizon](PHIOS_MEMORY_EVIDENCE_HORIZON_V0.1.md) |
| **Core reasoning** | **v0.8** | [Governed Execution Handoff](PHIOS_GOVERNED_EXECUTION_HANDOFF_V0.8.md) |
| **Research hardening** | active | [ENTER THE FIELD → PhiOS](ENTER_THE_FIELD_PHIOS_HARDENING.md) |

## Start here

- [Root project README](../README.md)
- [Living specification](PHIOS_LIVING_SPEC.md)
- [Architecture blueprint](BLUEPRINT.md)
- [Version and contract history](VERSION_HISTORY.md)
- [Research-hardening traceability](ENTER_THE_FIELD_PHIOS_HARDENING.md)
- [Contributor guide](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)

## Current contract families

### Authority, evidence, and hardening

- [Effect Boundary v0.1](PHIOS_EFFECT_BOUNDARY_V0.1.md)
- [Observation Frontier v0.1](PHIOS_OBSERVATION_FRONTIER_V0.1.md)
- [Transformation Lineage v0.1](PHIOS_TRANSFORMATION_LINEAGE_V0.1.md)
- [Evidence Independence v0.1](PHIOS_EVIDENCE_INDEPENDENCE_V0.1.md)
- [Governance Escalation v0.1](PHIOS_GOVERNANCE_ESCALATION_V0.1.md)
- [Dynamic State Lifecycle v0.1](PHIOS_DYNAMIC_STATE_LIFECYCLE_V0.1.md)
- [Memory Evidence Horizon v0.1](PHIOS_MEMORY_EVIDENCE_HORIZON_V0.1.md)
- [API Key Boundary v0.1](PHIOS_API_KEY_BOUNDARY_V0.1.md)
- [Identity Continuity and Recovery v0.1](PHIOS_IDENTITY_RECOVERY_V0.1.md)

The hardening rule throughout is that evidence may constrain behavior, but evidence,
memory, authentication, topology, consensus, or recovery do not become authority by
implication.

### App Platform

The current App Platform contract is:

- [v0.50 Release Install Proposal Gate](PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md)

The full v0.25 → v0.50 lineage is in [VERSION_HISTORY.md](VERSION_HISTORY.md).

### Spine

The current Spine contract is:

- [v0.24 Numeric Transition Contract](PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md)

The full v0.1 → v0.24 lineage is in [VERSION_HISTORY.md](VERSION_HISTORY.md).

### PhiReflex

Current live-routing trust boundary:

- [v0.10 Root Pinning and External Attestation](PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md)

Earlier provider, shadow, calibration, influence, authentication, and trust-lifecycle
contracts are indexed in [VERSION_HISTORY.md](VERSION_HISTORY.md).

### Core reasoning and governed execution

The current chain is:

```text
Geometric Reasoning v0.1
        ↓
Relational Field Geometry v0.2
        ↓
Dynamic Field State v0.3
        ↓
Field-Aware Routing v0.4
        ↓
Governed Replanning v0.5
        ↓
Governed Plan Adoption v0.6
        ↓
Governed Action Binding v0.7
        ↓
Governed Execution Handoff v0.8
```

The complete contract links are in [VERSION_HISTORY.md](VERSION_HISTORY.md).

### Governed memory and Ledger

- [Governed Memory](governed-memory.md)
- [Memory Evidence Horizon v0.1](PHIOS_MEMORY_EVIDENCE_HORIZON_V0.1.md)
- [Ledger analytics](ledger-analytics.md)
- Ledger reports remain derived/read-only analytics rather than an authority plane.

### Covenant Runtime

- [Covenant Runtime CR-01](PHIOS_COVENANT_RUNTIME_V0.1.md)
- [Identity Continuity and Recovery v0.1](PHIOS_IDENTITY_RECOVERY_V0.1.md)

Covenant describes identity, topology, transition, continuity, and recovery evidence. It
does not mint execution authority.

## Operational and migration material

- [Release setup](RELEASE_SETUP.md)
- [PhiKernel migration runbook](kernel-migration-v50.md)

The `launch/` directory contains announcement, publication, and distribution material.
Those files are communication artifacts, not runtime contracts.

## Historical material

The old root-level:

```text
README_SPINE_V*.md
README_APP_PLATFORM_V*.md
```

overview snapshots were retired from the working tree to keep the repository root
readable.

Their technical contracts remain here under `docs/`, the consolidated lineage is in
[VERSION_HISTORY.md](VERSION_HISTORY.md), and the original overview files remain
available through Git history.

Historical documents may preserve older names, experiments, or contracts that were later
superseded. Do not mechanically rewrite provenance artifacts to make them look current.

### Historical naming

Some retained material uses earlier names, including **Parallax**. Current work should
use the names established by current code and current project documentation. For the
collaborative/network concept outside PhiOS itself, use **Enter the Field (ETF)**.

Historical terminology is evidence of the project's evolution, not the current naming
source of truth.

## Documentation rule

```text
make current guidance easy to find
without pretending history never happened
```

That is the same provenance discipline PhiOS applies to runtime evidence, except this
time the unruly state machine is a documentation folder.
