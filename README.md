# φ PhiOS

**Local-first, authority-aware computing for human + computational collaboration.**

**Sovereign. Coherent. Local. Free.**

PhiOS is an open-source operator shell and research computing layer built around a simple rule:

> **Capability is not authority. Observation is not truth. Evidence should say exactly what it establishes.**

The repository currently contains three complementary surfaces:

- **PhiOS Shell / MCP** — operator-facing commands, local workflows, observatory surfaces, integrations, and machine-readable interfaces.
- **PhiOS Spine** — the authority-aware execution core built around Mandala contracts, SOMA perception, Reality Gate verification, explicit grants, and receipts.
- **PhiOS App Platform** — strict application manifests and a governed registry for turning external repositories into identifiable PhiOS apps without silently granting install or execution authority.

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

The current merged Spine line is **v0.24**.

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
| v0.23 | bounded first-to-last temporal envelope across cadenced observations |
| v0.24 | bounded numeric transition predicates across adjacent observations |

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

- [Spine v0.24 overview](README_SPINE_V0.24.md)
- [Spine v0.24 numeric-transition contract](docs/PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md)
- [Spine v0.23 temporal-envelope contract](docs/PHIOS_SPINE_V0.23_TEMPORAL_ENVELOPE.md)
- [Spine v0.22 cadence-window contract](docs/PHIOS_SPINE_V0.22_CADENCED_MIXED_OBSERVATION.md)
- [Spine v0.21 timed observation contract](docs/PHIOS_SPINE_V0.21_TIMED_MIXED_OBSERVATION.md)
- [Spine v0.20 repeated observation contract](docs/PHIOS_SPINE_V0.20_REPEATED_MIXED_OBSERVATION.md)
- [Spine v0.19 mixed contract](docs/PHIOS_SPINE_V0.19_JSON_MIXED_CONTRACT.md)
- [Spine v0.18 scalar predicate contract](docs/PHIOS_SPINE_V0.18_JSON_SCALAR_PREDICATES.md)
- [Spine v0.17 same-snapshot contract](docs/PHIOS_SPINE_V0.17_JSON_MULTI_CONTRACT.md)

Older Spine documents remain in the repository as the versioned design trail.

---

## App Platform Alpha

The current App Platform line is **v0.34**. v0.25 introduced strict app manifests and a deterministic registry; v0.26 added bounded public GitHub intake; v0.27 added exact-commit source acquisition; v0.28 added deterministic non-executing build plans; v0.29 added explicitly approved build execution; v0.30 added Linux Bubblewrap containment; v0.31 added SRI-verified dependency staging; v0.32 added verified offline npm builds; v0.33 added artifact-only installation; v0.34 adds separately reviewed installed-app runtime plans and governed foreground Node/Python launch.

A manifest records:

- stable app identity;
- source repository;
- declared license expression and redistribution state;
- runtime kind and bounded entrypoint;
- requested permissions;
- canonical SHA-256 manifest identity.

Registration is deliberately non-executive:

```text
registered app
    ≠ installed app
    ≠ trusted app
    ≠ authorized app
    ≠ running app
```

A public repository is also **not** treated as automatically redistributable. License and
redistribution state remain explicit metadata until later intake and operator decisions establish
more.

See:

- [App Platform v0.34 overview](README_APP_PLATFORM_V0.34.md)
- [App Platform v0.34 installed runtime contract](docs/PHIOS_APP_PLATFORM_V0.34_INSTALLED_RUNTIME.md)
- [App Platform v0.33 overview](README_APP_PLATFORM_V0.33.md)
- [App Platform v0.33 artifact install contract](docs/PHIOS_APP_PLATFORM_V0.33_ARTIFACT_INSTALL.md)
- [App Platform v0.32 overview](README_APP_PLATFORM_V0.32.md)
- [App Platform v0.32 npm offline adapter contract](docs/PHIOS_APP_PLATFORM_V0.32_NPM_OFFLINE_ADAPTER.md)
- [App Platform v0.31 overview](README_APP_PLATFORM_V0.31.md)
- [App Platform v0.31 dependency broker contract](docs/PHIOS_APP_PLATFORM_V0.31_DEPENDENCY_BROKER.md)
- [App Platform v0.30 overview](README_APP_PLATFORM_V0.30.md)
- [App Platform v0.30 Linux build sandbox contract](docs/PHIOS_APP_PLATFORM_V0.30_BUILD_SANDBOX.md)
- [App Platform v0.29 overview](README_APP_PLATFORM_V0.29.md)
- [App Platform v0.29 build execution contract](docs/PHIOS_APP_PLATFORM_V0.29_BUILD_EXECUTION.md)
- [App Platform v0.28 overview](README_APP_PLATFORM_V0.28.md)
- [App Platform v0.28 build plan contract](docs/PHIOS_APP_PLATFORM_V0.28_BUILD_PLAN.md)
- [App Platform v0.27 overview](README_APP_PLATFORM_V0.27.md)
- [App Platform v0.27 governed source acquisition contract](docs/PHIOS_APP_PLATFORM_V0.27_SOURCE_ACQUISITION.md)
- [App Platform v0.26 overview](README_APP_PLATFORM_V0.26.md)
- [App Platform v0.26 bounded GitHub intake contract](docs/PHIOS_APP_PLATFORM_V0.26_GITHUB_INTAKE.md)
- [App Platform v0.25 overview](README_APP_PLATFORM_V0.25.md)
- [App Platform v0.25 manifest + registry contract](docs/PHIOS_APP_PLATFORM_V0.25_MANIFEST_REGISTRY.md)

Inspect one public repository and save the bounded intake result:

```bash
phi-app inspect-github https://github.com/OWNER/REPO > intake.json
```

Review the exact values that acquisition approval must bind:

```bash
phi-app review-intake intake.json
```

Then acquire only the exact reviewed revision and manifest:

```bash
phi-app acquire-github intake.json \
  --approve-commit-sha EXACT_COMMIT_SHA \
  --approve-manifest-sha EXACT_MANIFEST_SHA256
```

Source acquisition does not install dependencies, build, register, trust, or launch an app.

Create and review a non-executing build plan:

```bash
phi-app plan-build intake.json acquisition-receipt.json > build-plan.json
phi-app review-build-plan build-plan.json
```

v0.28 records proposed argv steps, required tools, requested future build permissions, expected outputs where deterministically known, and a canonical plan SHA-256.

Execute only an explicitly approved plan:

```bash
phi-app execute-build build-plan.json acquisition-receipt.json \
  --approve-plan-sha EXACT_PLAN_SHA256 \
  --approve-source-sha EXACT_SOURCE_SNAPSHOT_SHA256 \
  --allow-build-permission build.network.dependencies \
  --allow-build-permission build.process.execute \
  --allow-build-permission build.workspace.write
```

v0.29 recomputes the source snapshot before any process launch, runs reviewed argv with `shell=False` inside a separate working copy, records required tool identities, hashes expected artifacts, and writes a build execution receipt.

Execute the same approved plan through the Linux sandbox:

```bash
phi-app execute-sandboxed-build build-plan.json acquisition-receipt.json \
  --approve-plan-sha EXACT_PLAN_SHA256 \
  --approve-source-sha EXACT_SOURCE_SNAPSHOT_SHA256 \
  --allow-build-permission build.network.dependencies \
  --allow-build-permission build.process.execute \
  --allow-build-permission build.workspace.write
```

v0.30 requires Linux, Bubblewrap, and `prlimit`. It preflights namespace creation, clears the build environment, keeps the host user home unmounted, binds the execution workspace read/write, exposes selected system roots read-only, and defaults to a separate network namespace with no host network.

Dependency-fetch builds can explicitly request `--sandbox-network inherit`, but receipts mark that mode as host-network inheritance, **not** as network isolation or allowlisting.

Plan, review, and stage exact npm dependency artifacts outside the build sandbox:

```bash
phi-app plan-dependencies build-plan.json acquisition-receipt.json > dependency-plan.json
phi-app review-dependency-plan dependency-plan.json
phi-app stage-dependencies dependency-plan.json \
  --approve-dependency-plan-sha EXACT_DEPENDENCY_PLAN_SHA256 \
  --allow-host registry.npmjs.org
```

v0.31 currently supports npm lockfileVersion 2/3. It requires exact HTTPS `resolved` URLs and valid lockfile SRI, requires the approved host set to exactly match the reviewed plan, verifies downloaded bytes before storage, and gives each staged artifact a PhiOS SHA-256 CAS identity.

Turn the v0.31 dependency receipt into an isolated npm cache, derive a new offline plan, review it, and execute it with the v0.30 network namespace denied:

```bash
phi-app prepare-npm-cache dependency-receipt.json \
  --approve-dependency-receipt-sha EXACT_DEPENDENCY_RECEIPT_SHA256 \
  > npm-cache-receipt.json

phi-app plan-offline-npm-build build-plan.json npm-cache-receipt.json \
  > npm-offline-plan.json

phi-app review-offline-npm-build npm-offline-plan.json

phi-app execute-offline-npm-build \
  npm-offline-plan.json \
  acquisition-receipt.json \
  npm-cache-receipt.json \
  --approve-offline-plan-sha EXACT_OFFLINE_PLAN_SHA256
```

v0.32 asks npm itself to populate and verify an isolated cache from the already-SRI-verified v0.31 CAS blobs. It then derives a new plan whose dependency step is `npm ci --offline --cache /phios/npm-cache`, removes `build.network.dependencies`, and requires approval of that new plan digest before execution.

The receipted npm cache remains immutable evidence. A fresh copy is mounted read/write for the actual build, while Bubblewrap runs with `network_mode=deny`.

Package and install only the successful receipted artifact set:

```bash
phi-app plan-package \
  manifest.json \
  registry.json \
  build-execution-receipt.json \
  offline-build-receipt.json \
  > package-plan.json

phi-app review-package package-plan.json

phi-app install-package \
  package-plan.json \
  registry.json \
  build-execution-receipt.json \
  offline-build-receipt.json \
  --approve-package-plan-sha EXACT_PACKAGE_PLAN_SHA256
```

v0.33 copies only the exact build artifacts recorded in the successful build receipt, re-verifies their hashes immediately before and during copy, stages the payload under the configured install root, checks the complete staged payload against the build artifact-set digest, and atomically promotes it to the final install path.

The install receipt still records `launch_authority=false`. Installed does not mean runnable.

An unchanged install can be removed only with explicit approval of its exact install receipt:

```bash
phi-app uninstall-package install-receipt.json \
  --approve-install-receipt-sha EXACT_INSTALL_RECEIPT_SHA256
```

Create a runtime plan only from an unchanged v0.33 install:

```bash
phi-app plan-runtime install-receipt.json > runtime-plan.json
phi-app review-runtime runtime-plan.json
```

v0.34 currently makes only direct installed Node `.js/.mjs/.cjs` targets and Python `.py` targets executable. It deliberately does not infer a built entrypoint from `package.json`, launch native binaries without preserved executable-mode evidence, invent a static-web browser/server, or treat a `local_http` URL as an executable.

Launch requires approval of the exact runtime-plan digest and the exact permission set:

```bash
phi-app launch-runtime \
  runtime-plan.json \
  install-receipt.json \
  --approve-runtime-plan-sha EXACT_RUNTIME_PLAN_SHA256
```

The installed payload is mounted read-only at `/app`. Network is denied by default. Host-network inheritance requires the reviewed `runtime.network.inherit` permission, and persistent writable app data at `/phios/app-data` requires `runtime.data.persist`.

The production runtime performs a real Bubblewrap preflight before execution and emits a strict runtime receipt after process exit or timeout. Portable CI verifies the command/control contract with fake runners rather than claiming kernel isolation that the hosted CI environment did not exercise.

The next planned rung is explicit runtime-adapter mapping, starting with built-output/static-web behavior so typical Vite-style repositories can become runnable without invisible entrypoint inference.

v0.18 adds a stronger semantic boundary for scalar values. Boolean and numeric values may be inspected only with the separate `reality.local_http.semantic.value.read` grant. The observed scalar is used transiently for comparison and is not persisted in semantic evidence.

v0.19 composes type, structural, and scalar clauses against one captured response. Value-read authority is required only when the mixed contract actually contains a scalar clause.

v0.20 can evaluate that same mixed contract across 2-5 discrete observations. Repetition requires the separate `reality.local_http.repeat.read` grant. No minimum sampling interval is enforced, so repeated support does not establish continuous health between observations.

v0.21 adds an explicit 0.05-10 second minimum interval between provider invocation starts. Timing requires `reality.local_http.timing.wait` and uses a monotonic clock; wall-clock capture timestamps do not establish spacing.

v0.22 adds an inclusive minimum/maximum cadence window between provider invocation starts. Cadence requires the separate `reality.local_http.timing.cadence` grant. Semantic success cannot override a missed cadence bound.

v0.23 adds an explicit first-to-last provider-start span window above cadence. Temporal-envelope control requires `reality.local_http.timing.envelope`, rejects impossible cadence/span combinations before I/O, and schedules each next start to preserve future feasibility when possible.

v0.24 adds numeric transition predicates across adjacent observations. Cross-snapshot comparison requires `reality.local_http.semantic.transition.read` in addition to scalar value authority. Observed numbers remain transient; evidence persists only types, derived ordering, and transition outcomes. No timing semantics are implied.








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
phi-app --help
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
├─ apps/       manifests, intake, dependency broker, offline npm builds, install pipeline, registry
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
