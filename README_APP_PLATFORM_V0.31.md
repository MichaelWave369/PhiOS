# PhiOS App Platform v0.31

PhiOS App Platform v0.31 adds the **Dependency Staging / Network Broker Contract**.

The first supported dependency family is npm with `package-lock.json` or
`npm-shrinkwrap.json` lockfileVersion 2 or 3.

v0.31 separates network acquisition from build execution:

```text
reviewed v0.28 build plan
       +
v0.27 acquired source
       ↓
parse exact npm lockfile
       ↓
dependency staging plan
       ↓
operator reviews plan digest + host set
       ↓
HTTPS broker downloads exact artifacts
       ↓
verify lockfile SRI
       ↓
hash bytes with SHA-256
       ↓
PhiOS content-addressed dependency store
       ↓
dependency receipt
```

## Commands

Create a deterministic dependency plan:

```bash
phi-app plan-dependencies build-plan.json acquisition-receipt.json \
  > dependency-plan.json
```

Review the exact staging authority:

```bash
phi-app review-dependency-plan dependency-plan.json
```

Stage only after approving the exact plan and exact host set:

```bash
phi-app stage-dependencies dependency-plan.json \
  --approve-dependency-plan-sha EXACT_DEPENDENCY_PLAN_SHA256 \
  --allow-host registry.npmjs.org
```

## Authority boundary

The stage request must approve:

- the exact canonical dependency-plan SHA-256;
- exactly the hosts observed in the reviewed plan.

Missing hosts fail closed.

Extra hosts also fail closed.

## Artifact identity

Every external npm package artifact requires:

- an exact HTTPS `resolved` URL;
- lockfile SRI integrity using SHA-256, SHA-384, or SHA-512.

When multiple valid SRI digests are present, PhiOS chooses the strongest supported algorithm.

Downloaded bytes must match the selected SRI digest before they enter the PhiOS dependency store.

The staged bytes also receive a SHA-256 CAS identity.

## Current boundary

v0.31 does **not** synthesize npm's internal cache layout and does not yet change the reviewed
build step to offline mode.

The next rung is an npm offline-cache adapter that consumes the v0.31 receipt/store through npm's
own supported cache interfaces and then executes `npm ci --offline` inside the v0.30
network-denied sandbox.

See `docs/PHIOS_APP_PLATFORM_V0.31_DEPENDENCY_BROKER.md`.
