# PhiOS App Platform v0.32

PhiOS App Platform v0.32 adds the **npm Offline Dependency Adapter**.

v0.31 stages exact npm package artifacts in a PhiOS content-addressed store. v0.32 asks npm itself
to turn those already-verified local tarballs into an isolated npm cache, then derives a separately
reviewable build plan whose dependency step is truly offline.

## Pipeline

```text
v0.31 dependency receipt
        ↓
reverify every PhiOS CAS blob
        ↓
npm cache add LOCAL_TARBALL --offline
        ↓
npm cache verify --offline
        ↓
hash isolated npm cache tree
        ↓
npm cache receipt
        ↓
derive NEW offline build plan
        ↓
review exact offline-plan SHA
        ↓
copy receipted cache for execution
        ↓
mount copy at /phios/npm-cache
        ↓
npm ci --offline
        ↓
v0.30 Bubblewrap network_mode=deny
        ↓
build + execution + sandbox + offline receipts
```

## Commands

Prepare npm's cache from one explicitly approved v0.31 dependency receipt:

```bash
phi-app prepare-npm-cache dependency-receipt.json \
  --approve-dependency-receipt-sha EXACT_DEPENDENCY_RECEIPT_SHA256 \
  > npm-cache-receipt.json
```

Derive and review a new offline execution plan:

```bash
phi-app plan-offline-npm-build build-plan.json npm-cache-receipt.json \
  > npm-offline-plan.json

phi-app review-offline-npm-build npm-offline-plan.json
```

Execute only after approving the exact offline-plan digest:

```bash
phi-app execute-offline-npm-build \
  npm-offline-plan.json \
  acquisition-receipt.json \
  npm-cache-receipt.json \
  --approve-offline-plan-sha EXACT_OFFLINE_PLAN_SHA256
```

## Important authority change

The original v0.28 npm plan contains:

```text
npm ci
requires_network = true
build.network.dependencies
```

v0.32 does not silently reinterpret that plan.

It derives a new hash-bound plan containing:

```text
npm ci --offline --cache /phios/npm-cache
requires_network = false
```

The derived plan removes `build.network.dependencies` and must be reviewed separately.

## Two network controls

npm cache preparation records:

```text
population_network_control = npm_offline_flag
os_network_namespace_enforced = false
```

The actual build then runs under v0.30 with:

```text
network_mode = deny
network_namespace_enforced = true
host_network_inherited = false
```

v0.32 does not confuse those controls.

See `docs/PHIOS_APP_PLATFORM_V0.32_NPM_OFFLINE_ADAPTER.md`.
