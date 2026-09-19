# φ PhiOS

**Local-first, authority-aware computing for human + computational collaboration.**

**Sovereign. Coherent. Local. Free.**

PhiOS is an open-source operator shell, verification spine, and governed application platform built around one stubborn rule:

> **Capability is not authority. Observation is not truth. Evidence should say exactly what it establishes.**

PhiOS is under active development and should be treated as **alpha software**.

---

## PhiOS in 30 seconds

PhiOS is trying to make computational systems useful without letting capability quietly become permission.

It currently has three major surfaces:

| Surface | Purpose | Current line |
|---|---|---:|
| **PhiOS Shell / MCP** | operator commands, local workflows, integrations, machine-readable capability surfaces | active |
| **PhiOS Spine** | authority-aware observation, verification, evidence, and receipts | **v0.24** |
| **PhiOS App Platform** | governed path from public repository to installed, launchable, updateable desktop app | **v0.42** |

The common pattern is:

```text
request
  ↓
explicit authority
  ↓
bounded action / observation
  ↓
typed evidence
  ↓
narrow receipt
```

A tool existing does not grant permission to use it. A successful check does not establish more than it actually observed.

---

## Why this exists

Modern AI and automation stacks are very good at doing things and surprisingly bad at preserving distinctions like:

```text
can do
≠ may do

observed
≠ inferred

installed
≠ runnable

catalogued
≠ authorized

update approved
≠ rollback approved

receipt exists
≠ system is globally healthy
```

PhiOS makes those differences explicit in code, plans, grants, receipts, and failure behavior.

---

## Core principles

1. **Capability ≠ authority.**
2. **Evidence is scoped to what was actually observed.**
3. **Interpretation is separate from native evidence.**
4. **Missing authority and malformed evidence fail closed.**
5. **Derived artifacts do not gain authority merely by being derived.**
6. **Narrow facts are not promoted into broad conclusions.**
7. **Local-first is the default.**
8. **Important operations leave inspectable receipts.**

These are engineering constraints, not branding decoration.

---

## What works today

### PhiOS Spine v0.24

The current Spine can perform bounded local observations and evaluate explicit contracts across:

- local files and screen regions;
- local interfaces, TCP listeners, and loopback HTTP;
- JSON type, structural, scalar, and mixed predicates;
- repeated observations;
- cadence and temporal-envelope constraints;
- numeric transition predicates across adjacent observations.

A Spine result is intentionally narrow.

For example:

```text
"port 11434 is listening"
```

does **not** automatically become:

```text
"Ollama is healthy"
```

because computers have benefited from that kind of optimism for long enough.

Current Spine docs:

- [Spine v0.24 overview](README_SPINE_V0.24.md)
- [Spine v0.24 numeric-transition contract](docs/PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md)
- [Complete Spine version trail](docs/README.md#spine-version-trail)

### App Platform v0.42

The App Platform now covers a governed lifecycle from public source through desktop update and rollback:

```text
public repository
    ↓
bounded intake
    ↓
exact-commit acquisition
    ↓
reviewed build plan
    ↓
sandboxed build
    ↓
verified dependency staging
    ↓
offline npm build
    ↓
artifact-only install
    ↓
runtime / static-web / browser plans
    ↓
exact Wayland-visible session
    ↓
persistent desktop grant
    ↓
deterministic app catalog
    ↓
side-by-side update
    ↓
separately approved rollback
    ↓
explicit retained-version cleanup
    ↓
stranded-cleanup reconciliation
```

Important boundaries remain explicit:

```text
public repo
≠ redistributable

registered
≠ installed

installed
≠ runnable

desktop entry exists
≠ launch authority

catalog ready
≠ automatic execution

update authority
≠ rollback authority

retained version
≠ cleanup authority

prepared cleanup journal
≠ cleanup completed
```

Current App Platform docs:

- [App Platform v0.42 overview](README_APP_PLATFORM_V0.42.md)
- [v0.42 cleanup reconciliation contract](docs/PHIOS_APP_PLATFORM_V0.42_CLEANUP_RECONCILIATION.md)
- [v0.41 retained cleanup contract](docs/PHIOS_APP_PLATFORM_V0.41_RETAINED_CLEANUP.md)
- [Complete App Platform version trail](docs/README.md#app-platform-version-trail)

---

## Quick start

### Requirements

- Python **3.11+**
- `psutil>=5.9.0`
- `mcp>=1.26,<2`

Some execution paths are Linux-specific. Bubblewrap sandboxing, Linux namespace enforcement, and Wayland desktop launch require the corresponding Linux environment and tools.

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

Optional perception extras:

```bash
python -m pip install -e ".[screen]"
python -m pip install -e ".[ocr]"
```

Inspect the main surfaces:

```bash
phi --help
phi-spine --help
phi-app --help
phi-mcp
```

Check current Spine state:

```bash
phi-spine status
```

---

## A small example

This verifies four facts from **one loopback HTTP response**:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  --allow reality.local_http.semantic.read \
  verify-claim \
  --kind local_http_json_multi_contract \
  --statement "The local model endpoint satisfies the bounded model-list contract." \
  --http-url http://127.0.0.1:11434/api/tags \
  --expected-http-status 200 \
  --json-clause '{"pointer":"/models","type":"array"}' \
  --json-clause '{"pointer":"/models","predicate":"array_length_gte","bound":1}' \
  --json-clause '{"pointer":"/models/0/name","type":"string"}' \
  --json-clause '{"pointer":"/models/0/name","predicate":"string_non_empty"}'
```

A supported result establishes only those clauses for that captured response.

It does not automatically establish model loadability, successful inference, authentication correctness, firewall reachability, or general application health.

That distinction is the point.

---

## Architecture

```text
human / client / local agent
          │
          ▼
   PhiOS Shell / MCP
          │
          ├──────────────► governed app workflows
          │                    │
          ▼                    ▼
     PhiOS Spine          App Platform
          │                    │
          ▼                    ▼
 authority + contracts    plans + grants
          │                    │
          ▼                    ▼
 bounded observation      sandboxed actions
          │                    │
          └────────┬───────────┘
                   ▼
             typed receipts
```

### Repository map

```text
phios/
├─ core/       core services
├─ shell/      operator shell
├─ mcp/        MCP interface
├─ spine/      authority-aware verification runtime
├─ apps/       governed app lifecycle
├─ mandala/    typed contracts and receipts
├─ soma/       bounded perception / evidence
└─ reality/    Reality Gate verification

docs/          current docs, versioned contracts, history, migration material
tests/         regression and contract tests
scripts/       development and policy helpers
```

---

## Geometric, relational, and dynamic field reasoning

PhiOS now has a four-rung advisory core for reasoning over computational state
spaces before exact verification.

**Geometric Reasoning v0.1** reduces state spaces through constraints,
equivalence classes, and conserved invariants.

**Relational Field Geometry v0.2** adds hard transition boundaries plus soft
state / relation costs and bounded least-declared-cost path search.

**Dynamic Field State v0.3** lets evidence, contradiction, failure history, and
resource signals change bounded advisory field values over time under an
immutable hashed law.

**Field-Aware Routing v0.4** binds one exact validated dynamic-field snapshot
into explicit non-negative route-cost terms, so preferred paths can change as
the field changes without changing hard constraints or execution authority.

The critical boundaries are:

```text
hard constraint failure
cannot be outvoted by
lower soft field cost

dynamic field change
cannot rewrite
the governing law

route recommendation
does not become
execution authority
```

Authority therefore remains a gate, not a score, and field adaptation remains
state change rather than self-governance.

All geometric / field states and receipts retain `action_authority = false`.

See:

- [Geometric Reasoning v0.1](docs/PHIOS_GEOMETRIC_REASONING_V0.1.md)
- [Relational Field Geometry v0.2](docs/PHIOS_RELATIONAL_FIELD_V0.2.md)
- [Dynamic Field State v0.3](docs/PHIOS_DYNAMIC_FIELD_V0.3.md)
- [Field-Aware Routing v0.4](docs/PHIOS_FIELD_AWARE_ROUTING_V0.4.md)

---

## SOMA and Reality Gate

**SOMA** is the bounded perception layer. Current work includes local file acquisition, screen-region capture, acuity recovery, multishot selection, deterministic sharpening derivatives, and OCR interpretation.

Its rule is:

```text
enhancement does not create missing information
interpretation does not become native evidence
perception does not grant action authority
```

**Reality Gate** evaluates explicit claims against bounded evidence and returns narrow verdicts such as:

- `SUPPORTED`
- `CONTRADICTED`
- `UNRESOLVED`
- `BLOCKED`

Transport failure, contradictory evidence, and missing authority are deliberately different outcomes.

---

## MCP and optional integrations

`phi-mcp` exposes local resources, tools, prompts, observatory surfaces, and capability-gated actions.

The MCP layer is an interface over PhiOS capabilities. It does not bypass the underlying authority model.

PhiOS also contains optional PhiKernel adapter paths. Where enabled, PhiKernel remains the source of truth for the runtime state it provides.

See:

- [PhiKernel migration runbook](docs/kernel-migration-v50.md)

---

## Development checks

CI enforces the core development gates:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```

New contracts should normally include:

- strict parsing;
- deterministic hashing where applicable;
- explicit authority fields;
- tamper tests;
- failure-path tests;
- receipts for meaningful state transitions.

---

## Documentation

Start here:

- **[Documentation index](docs/README.md)**
- [Living specification](docs/PHIOS_LIVING_SPEC.md)
- [Architecture blueprint](docs/BLUEPRINT.md)
- [App Platform v0.42](README_APP_PLATFORM_V0.42.md)
- [Spine v0.24](README_SPINE_V0.24.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

The older versioned documents are intentionally retained as the design and provenance trail.

Some historical artifacts use earlier naming. See the [historical naming note](docs/README.md#historical-naming). Current work should not revive legacy branding merely because it still appears in provenance documents.

---

## Historical material

PhiOS has changed quickly.

Older documents may preserve previous names, experimental concepts, or contracts that have since been superseded. They remain useful as history, but they are not the current source of truth.

When sources disagree, prefer:

1. code on `main`;
2. current tests;
3. latest versioned contract docs;
4. this README;
5. older historical material.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

The short version:

- keep capability separate from authority;
- fail closed;
- preserve provenance;
- add tests for new contracts;
- document dependencies and license impact;
- do not broaden claims beyond the evidence.

---

## License

PhiOS project-owned code and documentation are released under the **MIT License** unless otherwise noted.

See:

- [LICENSE](LICENSE)
- [PHI_COMMONS.md](PHI_COMMONS.md)
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [MODEL_LICENSES.md](MODEL_LICENSES.md)

---

## Project direction

PhiOS does not need an external slogan to explain what it is trying to do.

The architecture already says it:

**Sovereign. Coherent. Local. Free.**

Build systems that help people without quietly taking authority away from them.
