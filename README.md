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
| **PhiReflex** | provider-neutral fast advisory judgment / System-One shadow layer | **v0.1** |

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

Optional PhiReflex Jev provider:

```bash
python -m pip install -e ".[reflex-jev]"
```

Set `TYPESAFE_API_KEY` only in the runtime environment when using Jev. The
local rules baseline and the rest of PhiOS do not require the TypeSafe SDK or
network access.

Inspect the main surfaces:

```bash
phi --help
phi-spine --help
phi-app --help
phi-reflex --help
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

## PhiReflex v0.1

**PhiReflex** is a provider-neutral fast advisory judgment layer for bounded
classification, risk signaling, System-Two escalation hints, and verification
hints.

v0.1 runs external providers in **shadow mode**:

```text
task
  ├── local deterministic rules → baseline
  └── optional Jev provider     → shadow
                                  ↓
                           comparison receipt
```

The optional Jev adapter uses TypeSafe AI's official Python SDK, but the
provider never gains authority:

```text
probability
≠ permission

reflex decision
≠ routing authority

reflex decision
≠ execution authority
```

If Jev is unavailable, unconfigured, or errors, the local baseline still
returns and the provider failure is receipted.

Try it locally:

```bash
phi-reflex "Build and test this adapter" --tool-intent
```

See [PhiReflex v0.1](docs/PHIOS_REFLEX_V0.1.md).

---

## Geometric, relational, and dynamic field reasoning

PhiOS now has an eight-rung governed reasoning and execution-handoff core for
computational state, plan selection, action binding, and bounded side effects.

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

**Governed Replanning v0.5** re-scores the incumbent and candidate under the
same current field snapshot, then applies a fixed hysteresis policy to emit
`KEEP`, `REPLAN`, or `UNRESOLVED`. This prevents small field fluctuations
from causing route thrash.

**Governed Plan Adoption v0.6** adds the explicit authority boundary between a
`REPLAN` recommendation and the immutable incumbent plan. A scoped grant must
match the exact plan state, exact replan receipt, and exact requested
disposition before a candidate can become the next plan revision.

**Governed Action Binding v0.7** binds one exact adopted-plan transition to one
existing Spine capability plus one canonical payload SHA-256. The binding
records requested permissions but does not grant them; the existing Spine
`PermissionGate` remains the execution authority checkpoint.

**Governed Execution Handoff v0.8** revalidates the current plan, binding,
payload digest, and current capability contract immediately before execution,
then delegates authority evaluation and side effects to the existing Spine.
Bindings are atomically claimed to prevent duplicate execution; denied
permission releases the claim, while successful or failed executor entry
consumes it.

The critical boundaries are:

```text
hard constraint failure
cannot be outvoted by
lower soft field cost

dynamic field change
cannot rewrite
the governing law

new preference
does not automatically become
a replacement recommendation

REPLAN
does not mean
ADOPT

ADOPT
does not mean
EXECUTE

BOUND ACTION
does not mean
PERMISSION GRANTED

EARLIER VALIDATION
does not replace
EXECUTION-TIME REVALIDATION
```

Authority therefore remains a gate, not a score, and plan adoption remains
separate from execution authority.

All core reasoning/adoption receipts retain `action_authority = false`; v0.6
plan states also retain `execution_authority = false`.

See:

- [Geometric Reasoning v0.1](docs/PHIOS_GEOMETRIC_REASONING_V0.1.md)
- [Relational Field Geometry v0.2](docs/PHIOS_RELATIONAL_FIELD_V0.2.md)
- [Dynamic Field State v0.3](docs/PHIOS_DYNAMIC_FIELD_V0.3.md)
- [Field-Aware Routing v0.4](docs/PHIOS_FIELD_AWARE_ROUTING_V0.4.md)
- [Governed Replanning v0.5](docs/PHIOS_GOVERNED_REPLANNING_V0.5.md)
- [Governed Plan Adoption v0.6](docs/PHIOS_GOVERNED_PLAN_ADOPTION_V0.6.md)
- [Governed Action Binding v0.7](docs/PHIOS_GOVERNED_ACTION_BINDING_V0.7.md)
- [Governed Execution Handoff v0.8](docs/PHIOS_GOVERNED_EXECUTION_HANDOFF_V0.8.md)

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
