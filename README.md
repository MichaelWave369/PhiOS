# φ PhiOS

**Local-first, authority-aware computing for human + computational collaboration.**

**Sovereign. Coherent. Local. Free.**

PhiOS is an open-source operator shell, verification spine, governed application
platform, memory/ledger system, and constrained agent runtime built around one rule:

> **Capability is not authority.**

The project is under active development and should be treated as **alpha software**.

## What PhiOS is

PhiOS is designed for systems that can observe, reason, retrieve, plan, and act without
quietly collapsing those abilities into permission.

The recurring pattern is:

```text
request
  ↓
explicit authority
  ↓
bounded capability
  ↓
typed evidence
  ↓
narrow receipt
  ↓
revalidation before consequential action
```

A tool existing does not mean it may be used. A memory being retrievable does not mean
it is current. A verifier finding a problem does not mean it may repair it. A recovered
identity does not inherit old authority merely because continuity was demonstrated.

## Current surfaces

| Surface | Current line | Role |
|---|---:|---|
| **Shell / MCP** | active | operator interface, workflows, resources, prompts, capability surfaces |
| **Spine** | **v0.24** | authority-aware observation, verification, evidence, and receipts |
| **App Platform** | **v0.50** | governed intake, build, install, launch, update, rollback, cleanup, and release lineage |
| **PhiReflex** | **v0.10** | provider-neutral fast advisory layer with authenticated bounded routing influence |
| **Governed Memory** | active | canonical local memory, derived semantic index, read admissibility, temporal horizon |
| **Reality Ledger** | active | append-only evidence plus bounded read-only analytics |
| **Covenant Runtime** | **CR-01 + recovery v0.1** | zero-authority identity, topology, transition, continuity, and recovery contracts |
| **Core reasoning** | **v0.8** | geometric reduction, relational fields, dynamic state, routing, replanning, adoption, action binding, execution handoff |

## Architectural laws

PhiOS encodes distinctions that automation stacks often blur:

```text
capability
!=
authority

observation
!=
truth

retrievable
!=
currently admissible

authentication
!=
authorization

detection
!=
authorized remediation

same topology
!=
same identity

recovered state
!=
recovered authority

installed
!=
runnable

update authority
!=
rollback authority

derived evidence
!=
source evidence
```

These are implementation constraints, not slogans pasted over ordinary automation.

## Architecture

```text
human / client / local agent
          │
          ▼
    Shell / MCP boundary
          │
          ├───────────────┐
          ▼               ▼
       Spine         App Platform
          │               │
          ▼               ▼
   Reality Gate      governed plans
          │               │
          ├──────┬────────┘
          ▼      ▼
      Memory   Covenant
          │      │
          └──┬───┘
             ▼
      Mandala contracts
             │
             ▼
       explicit authority
             │
             ▼
    governed action / handoff
             │
             ▼
        typed receipts
             │
             ▼
       Reality Ledger
```

PhiReflex can contribute bounded routing influence, but it does not receive action or
execution authority.

## What works today

### Spine v0.24

The Spine supports bounded local evidence and verification across files, screen regions,
network interfaces, TCP listeners, loopback HTTP, JSON structure/scalars, repeated
observations, cadence, temporal envelopes, and numeric transitions.

A result such as:

```text
"port 11434 is listening"
```

does not become:

```text
"Ollama is healthy"
```

unless the broader claim is separately observed and verified.

Current contract:
[Spine v0.24 numeric-transition verification](docs/PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md).

### App Platform v0.50

The App Platform provides a governed lifecycle from public source intake through
exact-commit acquisition, reviewed build planning, Linux sandboxing, dependency staging,
offline build, artifact installation, visible/persistent launch, app cataloging,
side-by-side update, separately authorized rollback, cleanup recovery, release discovery,
human review, execution lineage, package lineage, and release-install proposal gating.

Important boundaries include:

```text
public repository != redistribution authority
registered        != installed
installed         != launch authority
release observed  != release selected
candidate selected != update authorized
successful build  != install authority
install           != update authority
update            != rollback authority
```

Current contract:
[App Platform v0.50 release-install proposal gate](docs/PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md).

### PhiReflex v0.10

PhiReflex is a provider-neutral fast advisory layer. It began as shadow-only evaluation
and now supports a narrowly governed live routing-influence path with authenticated
grants, trust lifecycle, provider manifests, use limits, root pinning, adapter
attestation, one-use activation nonces, offline checkpoint verification, and
conflict-only replication snapshots.

Even when live:

```text
routing_influence_authority = true
action_authority            = false
execution_authority         = false
```

Current contract:
[PhiReflex v0.10 root pinning and attestation](docs/PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md).

### Governed memory and evidence horizon

Canonical memory belongs to PhiOS. Vector search is a replaceable derived index.

The hardened memory path separates:

```text
record exists canonically
from
record may enter active context now
```

Stale memory can remain auditable while direct context admission expires. Re-entry
requires the configured temporal/reconsolidation path rather than timestamp laundering.

See:
[Governed memory](docs/governed-memory.md) and
[Memory Evidence Horizon v0.1](docs/PHIOS_MEMORY_EVIDENCE_HORIZON_V0.1.md).

### Input and output API keys

PhiOS includes a bounded API-key boundary for both directions:

- **inbound keys** authenticate a configured caller/audience without turning possession
  into action authority;
- **outbound keys** are resolved ephemerally from an external secret source and can be
  leased to adapters without writing the raw credential into normal receipts.

A network adapter still has to declare and pass the normal effect and authority
boundaries.

See [API Key Boundary v0.1](docs/PHIOS_API_KEY_BOUNDARY_V0.1.md).

### Covenant identity and recovery

Covenant CR-01 defines zero-authority identity/topology/transition contracts.

The recovery extension adds invariant-bound identity continuity across topology changes,
exact epoch chaining, exact recovery-state continuity, and mandatory downstream
authority revalidation.

```text
same machine != same identity
same identity != restored authority
```

See:
[Covenant Runtime CR-01](docs/PHIOS_COVENANT_RUNTIME_V0.1.md) and
[Identity Continuity and Recovery v0.1](docs/PHIOS_IDENTITY_RECOVERY_V0.1.md).

### Research hardening

The current hardening line adds explicit contracts for:

- authority projection and no-mint memory reads;
- control-plane isolation;
- environmental effect classification;
- observation frontiers;
- transformation lineage and exactness;
- evidence-path independence and disagreement;
- verifier/governance escalation;
- dynamic-state decay and termination;
- memory evidence horizons and reconsolidation;
- inbound/outbound API-key handling;
- invariant-bound identity recovery.

See [ENTER THE FIELD → PhiOS research hardening](docs/ENTER_THE_FIELD_PHIOS_HARDENING.md).

## Quick start

### Requirements

- Python **3.11+**
- `psutil>=5.9.0`
- `mcp>=1.26,<2`

Clone and install:

```bash
git clone https://github.com/MichaelWave369/PhiOS.git
cd PhiOS
python -m pip install -e .
```

Development install:

```bash
python -m pip install -e ".[dev]"
```

Optional components:

```bash
python -m pip install -e ".[screen]"
python -m pip install -e ".[ocr]"
python -m pip install -e ".[memory-vector]"
python -m pip install -e ".[ledger-reports]"
python -m pip install -e ".[reflex-jev]"
python -m pip install -e ".[reflex-authority]"
```

Some execution paths are Linux-specific. Bubblewrap isolation and Wayland-visible
desktop execution require the corresponding Linux environment and tools.

Main entry points:

```bash
phi --help
phi-spine --help
phi-app --help
phi-reflex --help
phi-memory --help
phi-ledger --help
phi-mcp
```

Initialize governed memory in its disabled state:

```bash
phi-memory init-config
phi-memory status
```

## API-key example

Do not commit real API keys.

An outbound provider key can be supplied through the runtime environment and registered
by reference:

```python
from phios.spine import OutboundApiKeySpec, PhiOSSpine

spine = PhiOSSpine(
    state_root="./state",
    allowed_permissions=(),
    task_id="example",
)

spine.api_keys.register_outbound(
    OutboundApiKeySpec(
        key_id="provider-output",
        provider="provider",
        environment_variable="PROVIDER_API_KEY",
    )
)

lease = spine.api_keys.lease_outbound(
    key_id="provider-output",
    provider="provider",
)
headers = lease.authorization_headers()
```

The lease can produce a Bearer header or a configured `X-API-Key`-style header. The
credential itself is deliberately excluded from ordinary lease receipts and metadata.

## Repository map

```text
phios/
├─ core/           governed reasoning and execution handoff
├─ shell/          operator shell
├─ mcp/            MCP interface
├─ spine/          authority-aware runtime
├─ apps/           governed app lifecycle
├─ mandala/        typed contracts and receipts
├─ memory/         canonical memory + derived retrieval
├─ ledger_reports/ read-only analytics projection
├─ reflex/         bounded advisory/routing layer
├─ covenant/       identity/topology/recovery contracts
├─ soma/           bounded perception/evidence
└─ reality/        Reality Gate verification

docs/              current contracts, architecture, history
tests/             regression and contract tests
scripts/           development and policy helpers
```

## Development gates

CI enforces:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```

Special lanes also exercise the governed-memory vector backend and the isolated
DuckDB/Ledger path.

New contracts should normally include deterministic serialization/hashing where
appropriate, strict parsing, explicit authority fields, tamper tests, and failure-path
tests.

## Documentation

Start here:

- **[Documentation index](docs/README.md)**
- [Living specification](docs/PHIOS_LIVING_SPEC.md)
- [Architecture blueprint](docs/BLUEPRINT.md)
- [Version and contract history](docs/VERSION_HISTORY.md)
- [Research hardening](docs/ENTER_THE_FIELD_PHIOS_HARDENING.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

The old root-level `README_SPINE_V*.md` and `README_APP_PLATFORM_V*.md` overview
snapshots have been retired from the working tree. Their narrower technical contracts
remain under `docs/`, and the original overview files remain available through Git
history.

When documents disagree, prefer:

1. code on `main`;
2. current tests and CI-enforced contracts;
3. the latest component contract;
4. this README;
5. historical material.

## License

PhiOS project-owned code and documentation are released under the **MIT License** unless
otherwise noted.

See [LICENSE](LICENSE), [PHI_COMMONS.md](PHI_COMMONS.md),
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and
[MODEL_LICENSES.md](MODEL_LICENSES.md).

## Direction

PhiOS is trying to make powerful local computation easier to use without allowing
capability, inference, convenience, or recovery to silently become authority.

**Sovereign. Coherent. Local. Free.**
