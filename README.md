# φ PhiOS

**Local-first, authority-aware computing for human + computational collaboration.**

**Sovereign. Coherent. Local. Free.**

PhiOS is an open-source operator shell and research computing layer built around a simple rule:

> **Capability is not authority. Observation is not truth. Evidence should say exactly what it establishes.**

The repository currently contains two complementary surfaces:

- **PhiOS Shell / MCP** — operator-facing commands, local workflows, observatory surfaces, integrations, and machine-readable interfaces.
- **PhiOS Spine** — the newer authority-aware execution core built around Mandala contracts, SOMA perception, Reality Gate verification, explicit grants, and receipts.

PhiOS is under active development and should be treated as **alpha software**.

---

## What PhiOS is trying to solve

Modern AI tooling is very good at producing output and surprisingly bad at remembering the difference between:

- *can do* and *is allowed to do*;
- *observed* and *inferred*;
- *evidence* and *interpretation*;
- *a successful check* and *a broad claim about system health*.

PhiOS makes those boundaries explicit.

```text
human / client / local agent
          ↓
   explicit capability request
          ↓
       authority check
          ↓
    bounded observation
          ↓
   typed evidence / receipt
          ↓
       narrow claim
```

A green check is useful. A green check that explains what it actually proved is much more useful.

---

## Core principles

PhiOS development follows a few hard constraints:

1. **Capability ≠ authority.** A tool existing does not grant permission to use it.
2. **Evidence is scoped.** A local observation proves only the fact actually observed.
3. **Interpretation is separate from native evidence.**
4. **Failure should fail closed.** Missing authority, malformed contracts, and unavailable evidence do not get converted into success.
5. **Derived artifacts do not gain authority merely by being derived.**
6. **No automatic promotion from a narrow fact to a broad conclusion.**
7. **Local-first by default.** The current Spine network verifiers are deliberately loopback-bounded.
8. **Receipts matter.** Important operations should be inspectable after execution.

These are engineering constraints, not branding decoration.

---

## Architecture

### Operator surfaces

```text
phi
├─ interactive/operator shell
├─ local workflows
├─ observatory + archive surfaces
└─ optional PhiKernel integration

phi-mcp
└─ MCP resources, tools, prompts, and local capability surfaces

phi-spine
└─ authority-aware execution + verification runtime
```

### PhiOS Spine

```text
request
  ↓
PhiOS Core
  ↓
Mandala contract + authority gate
  ↓
SOMA perception / bounded acquisition
  ↓
Reality Gate verification
  ↓
content-addressed evidence
  ↓
typed receipts
```

The Spine is intentionally conservative. It tries very hard not to turn:

```text
"port 11434 is listening"
```

into:

```text
"Ollama is healthy"
```

because computers have been exploiting that kind of optimism for decades.

---

## Current Spine verification ladder

The current merged Spine line is **v0.22**.

| Version | Capability |
|---|---|
| v0.10 | source-content verification bridge |
| v0.11 | local network-interface observation |
| v0.12 | local TCP-listener observation |
| v0.13 | local HTTP response contract |
| v0.14 | live bounded loopback HTTP adapter |
| v0.15 | JSON pointer + type verification |
| v0.16 | bounded structural JSON predicates |
| v0.17 | same-snapshot multi-clause JSON contracts |
| v0.18 | bounded Boolean and numeric scalar predicates |
| v0.19 | same-snapshot mixed type / structural / scalar contracts |
| v0.20 | bounded repeated mixed observations across 2-5 discrete samples |
| v0.21 | explicit minimum monotonic spacing between repeated observations |
| v0.22 | bounded monotonic cadence window between repeated observations |

The v0.17 same-snapshot contract can evaluate **1–8 bounded clauses from one HTTP observation**:

```text
one GET
  ↓
one captured body
  ↓
one digest + timestamp
  ↓
one strict JSON parse
  ↓
multiple bounded clauses
  ↓
one evidence record
```

Example clauses:

```json
{"pointer":"/models","type":"array"}
{"pointer":"/models","predicate":"array_length_gte","bound":1}
{"pointer":"/models/0/name","type":"string"}
{"pointer":"/models/0/name","predicate":"string_non_empty"}
```

All clauses describe the **same captured response**, not several requests made at different moments.

See:

- [Spine v0.22 overview](README_SPINE_V0.22.md)
- [Spine v0.22 cadence-window contract](docs/PHIOS_SPINE_V0.22_CADENCED_MIXED_OBSERVATION.md)
- [Spine v0.21 timed observation contract](docs/PHIOS_SPINE_V0.21_TIMED_MIXED_OBSERVATION.md)
- [Spine v0.20 repeated observation contract](docs/PHIOS_SPINE_V0.20_REPEATED_MIXED_OBSERVATION.md)
- [Spine v0.19 mixed contract](docs/PHIOS_SPINE_V0.19_JSON_MIXED_CONTRACT.md)
- [Spine v0.18 scalar predicate contract](docs/PHIOS_SPINE_V0.18_JSON_SCALAR_PREDICATES.md)
- [Spine v0.17 same-snapshot contract](docs/PHIOS_SPINE_V0.17_JSON_MULTI_CONTRACT.md)

Older Spine documents remain in the repository as the versioned design trail.

v0.18 adds a stronger semantic boundary for scalar values. Boolean and numeric values may be inspected only with the separate `reality.local_http.semantic.value.read` grant. The observed scalar is used transiently for comparison and is not persisted in semantic evidence.

v0.19 composes type, structural, and scalar clauses against one captured response. Value-read authority is required only when the mixed contract actually contains a scalar clause.

v0.20 can evaluate that same mixed contract across 2-5 discrete observations. Repetition requires the separate `reality.local_http.repeat.read` grant. No minimum sampling interval is enforced, so repeated support does not establish continuous health between observations.

v0.21 adds an explicit 0.05-10 second minimum interval between provider invocation starts. Timing requires `reality.local_http.timing.wait` and uses a monotonic clock; wall-clock capture timestamps do not establish spacing.

v0.22 adds an inclusive minimum/maximum cadence window between provider invocation starts. Cadence requires the separate `reality.local_http.timing.cadence` grant. Semantic success cannot override a missed cadence bound.






---

## SOMA perception

SOMA is the Spine's bounded perception layer.

Current work includes:

- native text evidence;
- bounded local file acquisition;
- selected screen-region capture;
- acuity recovery;
- multishot native-frame selection;
- deterministic sharpening derivatives;
- OCR interpretation with explicit separation from native image evidence.

The rule remains:

```text
enhancement does not create missing information
interpretation does not become native evidence
perception does not grant action authority
```

---

## Reality Gate

Reality Gate evaluates explicit claims against bounded evidence and returns narrow verdicts such as:

- `SUPPORTED`
- `CONTRADICTED`
- `UNRESOLVED`
- `BLOCKED`

Those verdicts are intentionally different.

For example:

```text
transport failed
    → UNRESOLVED

HTTP status differed from the explicit contract
    → CONTRADICTED

required authority was not granted
    → BLOCKED
```

PhiOS does not collapse all three into “false.”

---

## Install

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

Development environment:

```bash
python -m pip install -e ".[dev]"
```

Optional screen / OCR support:

```bash
python -m pip install -e ".[screen]"
python -m pip install -e ".[ocr]"
```

---

## Quick start

Inspect the shell and Spine surfaces:

```bash
phi --help
phi-spine --help
```

Check the Spine contract state:

```bash
phi-spine status
```

Run the MCP server:

```bash
phi-mcp
```

Run the interactive/operator shell:

```bash
phi
```

---

## Example: bounded local service contract

The following verifies four facts from **one loopback HTTP response**:

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

It does **not** automatically establish:

- model loadability;
- successful inference;
- database health;
- authentication correctness;
- remote reachability;
- firewall reachability;
- general application health.

That distinction is the point.

---

## Optional PhiKernel integration

PhiOS also contains adapter paths for PhiKernel-backed runtime state.

That integration is optional and default-off. Where enabled, PhiKernel remains the source of truth for the runtime data it provides; PhiOS does not silently promote shadow/compare results into authoritative state.

Useful migration material:

- [PhiKernel migration runbook](docs/kernel-migration-v50.md)

---

## MCP interface

`phi-mcp` exposes local resources, tools, prompts, browsing surfaces, observatory summaries, and capability-gated actions.

The MCP layer is an interface over PhiOS capabilities. It does not bypass the underlying authority model.

Because the MCP surface is broad and evolving, use discovery rather than treating this README as an exhaustive registry.

Start with:

```bash
phi-mcp
```

and inspect the available client discovery surfaces from your MCP client.

---

## Development checks

Before merging changes:

```bash
ruff check phios/
mypy phios/ --ignore-missing-imports
pytest -q
bash scripts/policy_no_telemetry_runtime.sh
```

Current CI enforces the same core checks.

---

## Repository map

```text
phios/
├─ core/       legacy/current core services
├─ shell/      operator shell
├─ mcp/        MCP interface
├─ spine/      authority-aware Spine runtime
├─ mandala/    typed contracts and receipts
├─ soma/       bounded perception/evidence
└─ reality/    Reality Gate verification

docs/          design notes, versioned contracts, migration material
tests/         regression and contract tests
scripts/       development and policy helpers
```

---

## Historical material

PhiOS has changed quickly.

Some older documents and changelog entries preserve historical names, experimental concepts, and earlier architectural framing. They are retained as project history, not as the current source of truth.

For current behavior, prefer:

1. the code on `main`;
2. current tests;
3. the latest versioned Spine contract docs;
4. this README.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

The short version:

- keep capability separate from authority;
- add tests for new contracts;
- fail closed;
- document new dependencies and license impact;
- do not weaken provenance or evidence boundaries for convenience.

---

## License

PhiOS project-owned code and documentation are released under the **MIT License** unless otherwise noted.

See:

- [LICENSE](LICENSE)
- [PHI_COMMONS.md](PHI_COMMONS.md)
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [MODEL_LICENSES.md](MODEL_LICENSES.md)

---

## Project principles

PhiOS does not require an external manifesto to explain its direction.

The principles are visible in the architecture:

**Sovereign. Coherent. Local. Free.**

Build tools that help people without quietly taking authority away from them.
