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
| **PhiOS App Platform** | governed app lifecycle, release discovery, and structural change evidence | **v0.45** |
| **PhiReflex** | provider-neutral System-One shadow, calibrated live influence, authenticated authority, trust lifecycle, and root attestation | **v0.10** |

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

### App Platform v0.45

The App Platform now covers a governed lifecycle from public source through cleanup recovery, release discovery, explicit candidate selection, and non-authoritative structural change evidence:

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
    ↓
unresolved-transition gate
    ↓
bounded release discovery
    ↓
explicit exact candidate selection
    ↓
exact-commit intake re-entry
    ↓
active-vs-candidate structural change evidence
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

release observed
≠ release selected

release selected
≠ source acquired

candidate selected
≠ update authorized

structural change observed
≠ compatibility verdict

compatibility evidence
≠ build / install / update authority
```

Current App Platform docs:

- [App Platform v0.45 overview](README_APP_PLATFORM_V0.45.md)
- [v0.45 release change evidence contract](docs/PHIOS_APP_PLATFORM_V0.45_RELEASE_CHANGE_EVIDENCE.md)
- [v0.44 governed release discovery contract](docs/PHIOS_APP_PLATFORM_V0.44_GOVERNED_RELEASE_DISCOVERY.md)
- [v0.43 unresolved lifecycle gate](docs/PHIOS_APP_PLATFORM_V0.43_UNRESOLVED_LIFECYCLE_GATE.md)
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

Optional governed semantic-memory backend:

```bash
python -m pip install -e ".[memory-vector]"
```

Optional read-only DuckDB Ledger report backend:

```bash
python -m pip install -e ".[ledger-reports]"
```

The isolated DuckDB worker is qualified on Linux with bubblewrap. There is no
unsandboxed fallback in this increment.

Create a disabled memory config before explicitly enabling it:

```bash
phi-memory init-config
phi-memory status
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
phi-memory --help
phi-ledger --help
phi-mcp
```

Check current Spine state:

```bash
phi-spine status
```

Export a derived, read-only Ledger snapshot:

```bash
phi-ledger \
  --allow ledger.snapshot.export \
  snapshot-export
```

Snapshot export reads only the two canonical JSONL receipt streams. It does not read
execution binding claims, grant stores, or arbitrary operator-selected files.

Build an isolated DuckDB projection from one validated snapshot:

```bash
phi-ledger \
  --allow ledger.report.build \
  projection-build \
  --snapshot-id <snapshot-sha256>
```

Run one closed-catalog report against that projection:

```bash
phi-ledger \
  --allow ledger.report.read \
  report \
  --snapshot-id <snapshot-sha256> \
  --name coverage_v1
```

Use `phi-ledger report-list` to see the named report catalog. The CLI never accepts
arbitrary SQL.

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

## PhiReflex v0.10

**PhiReflex** is a provider-neutral fast advisory judgment layer for bounded
classification, risk signaling, System-Two escalation hints, and verification
hints.

v0.1 established provider-neutral shadow mode. v0.2 connects that layer to the
real dispatch path while preserving planner isolation:



```text
task
  ↓
operational dispatch context
  ↓
operational plan
  ├──────────────→ actual dispatch path
  │
  └──────────────→ PhiReflex shadow observation
                    ├── local rules baseline
                    └── optional Jev shadow
                         ↓
                  separate hashed receipt
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

Try the standalone layer:

```bash
phi-reflex "Build and test this adapter" --tool-intent
```

Observe the real dispatch path without influencing it:

```bash
phi dispatch "build the adapter" --dry-run --reflex-shadow
```

After a shadowed run, explicit observed labels can be calibrated against both
the deterministic baseline and Jev shadow prediction:

```bash
phi agents reflex-evaluate run_123 \
  --outcome succeeded \
  --observer operator-review \
  --evidence-sha <sha256> \
  --role builder \
  --system2-needed yes
```

Missing labels remain unscored; dispatch success/failure is never silently
reinterpreted as prediction ground truth.

Aggregate many calibrated runs into an advisory readiness report:

```bash
phi agents reflex-report
```

The report can say `INSUFFICIENT_EVIDENCE`, `NOT_REVIEW_ELIGIBLE`, or
`REVIEW_ELIGIBLE`. Even `REVIEW_ELIGIBLE` carries zero routing, promotion,
action, or execution authority.

v0.5 adds the governance boundary for adopting an immutable influence policy.

v0.6 is the first rung that may activate **bounded routing influence**. An
exact v0.5 policy plus an exact activation request and external activation
grant may create a live activation state for one declared planner-context
surface. The live signal uses deterministic blending:

```text
blended = (1 - weight) * local baseline + weight * approved provider
```

Only approved dimensions are emitted. Provider/model drift, configured
unavailability, or repeated provider errors can collapse influence back to the
ordinary dispatch path. Operator deactivation does not require a
privilege-expansion grant.

Even while live:

```text
routing_influence_authority = true
action_authority = false
execution_authority = false
```

v0.7 adds the operational control plane around that live authority:

```text
~/.phios/reflex/
  policy.json
  activation.json
  lease.json
  grants/
  ledger.json
  quarantine/
```

Normal `phi dispatch` now restores a valid persisted activation automatically.
Malformed state, expired leases, provider/model drift, or ledger corruption fail
closed to ordinary dispatch.

v0.8 authenticates that runtime authority before normal dispatch will honor it.

An Ed25519-signed activation grant binds the exact issuer/key, validity window,
v0.6 grant, and v0.5/v0.6 hashes. Signed revocations can collapse an active
grant immediately or at a declared future epoch. Legacy unsigned live
activations are no longer honored by the official dispatch path.

The local trust-anchor store is the root of trust. Signatures prove possession
of the configured private key; they do not magically prove a real-world human
identity if the local public-key configuration itself has been replaced.

The v0.7 control plane is also serialized across processes with an OS advisory
lock, and v0.8 exposes a deterministic `control_sha256` for optional
compare-and-swap protection against stale operator state.

v0.9 adds lifecycle rules around that authenticated authority:

```text
signed trust rotation / disablement
signed provider manifests
signed grant-use limits
signed ledger checkpoints
signed lease renewal
```

A live grant signed by a retired key no longer remains live merely because it
was valid yesterday. One-shot grants can be expressed as
`max_activations = 1`, provider manifests bind the exact adapter identity and
version, and lease extension is possible only through an exact signed renewal.

v0.10 adds an external root pin and exact installed-adapter attestation before
the v0.9 lifecycle path may remain live.

```text
external root pin
+ signed provider manifest
+ signed installed-source digest
+ signed one-use activation nonce
→ eligible for existing bounded routing influence
```

The root pin is supplied through `PHIOS_REFLEX_ROOT_PIN`; PhiOS does not claim
that a second local JSON file is a hardware root of trust. Adapter source bytes
are hashed directly, activation nonces are burned before delegation, signed
checkpoint bundles can be verified offline, and imported replication snapshots
can only align or emit conflict receipts. They never overwrite local authority.

Root-attestation surfaces:

```bash
phi agents reflex-root status
phi agents reflex-root adapter-digest
phi agents reflex-root artifact-attest provider-artifact.json
phi agents reflex-root nonce-ingest activation-nonce.json
phi agents reflex-root activate --request request.json --grant-id grant-001 --nonce-id nonce-001 --yes
phi agents reflex-root checkpoint-export cp-001
phi agents reflex-root checkpoint-verify bundle.json
phi agents reflex-root snapshot-ingest snapshot.json
```

Normal `phi dispatch` now uses the v0.10 root-attestation gate before live
Reflex influence can reach the planner.

See [PhiReflex v0.1](docs/PHIOS_REFLEX_V0.1.md),
[PhiReflex v0.2 dispatch shadow](docs/PHIOS_REFLEX_V0.2_DISPATCH_SHADOW.md),
[PhiReflex v0.3 outcome calibration](docs/PHIOS_REFLEX_V0.3_OUTCOME_CALIBRATION.md),
[PhiReflex v0.4 calibration aggregation](docs/PHIOS_REFLEX_V0.4_CALIBRATION_AGGREGATION.md),
[PhiReflex v0.5 governed influence adoption](docs/PHIOS_REFLEX_V0.5_GOVERNED_INFLUENCE_ADOPTION.md),
[PhiReflex v0.6 runtime influence](docs/PHIOS_REFLEX_V0.6_RUNTIME_INFLUENCE.md),
[PhiReflex v0.7 runtime control plane](docs/PHIOS_REFLEX_V0.7_RUNTIME_CONTROL_PLANE.md),
[PhiReflex v0.8 authenticated authority](docs/PHIOS_REFLEX_V0.8_AUTHENTICATED_AUTHORITY.md),
[PhiReflex v0.9 trust lifecycle and attestation](docs/PHIOS_REFLEX_V0.9_TRUST_LIFECYCLE_ATTESTATION.md),
and [PhiReflex v0.10 root pinning and attestation](docs/PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md).

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


### Derived operational observations

PhiOS can export a separate, allowlisted snapshot of persisted kernel rollout,
agent-dispatch, and PhiReflex calibration evidence without copying prompts, raw planner
context, debug payloads, or authority state:

```bash
phi-ledger \
  --allow ledger.observation.export \
  observation-export

phi-ledger observation-report-list

phi-ledger \
  --allow ledger.observation.read \
  observation-report \
  --snapshot-id <observation-sha256> \
  --name reflex_calibration_summary_v1
```

Observation reports are descriptive only and cannot promote adapters or grant execution.
