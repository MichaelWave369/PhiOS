# PhiOS App Platform v0.34

PhiOS App Platform v0.34 adds the **Installed App Runtime Contract**.

v0.33 can install a successful receipted build without granting launch authority. v0.34 adds a
separate, reviewable runtime plan and an explicitly approved foreground launch.

The authority ladder remains:

```text
registered
≠ acquired
≠ built
≠ installed
≠ approved to launch
≠ running
```

## Pipeline

```text
v0.33 install receipt
        ↓
reverify complete installed tree
        ↓
read bound installed manifest
        ↓
resolve bounded direct runtime adapter
        ↓
runtime plan
        ↓
review exact plan SHA + requested permissions
        ↓
explicit approval
        ↓
reverify installed tree again
        ↓
Bubblewrap runtime
  /app              read-only
  /phios/app-data   optional read/write
  network           denied by default
  private home/tmp
  rlimits
        ↓
Node or Python foreground process
        ↓
exit / timeout
        ↓
runtime receipt
```

## Supported direct adapters

v0.34 intentionally starts narrow.

Runnable:

- Node when the manifest target is an installed `.js`, `.mjs`, or `.cjs` file.
- Python when the manifest target is an installed `.py` file.

Explicitly unsupported in this rung:

- Node manifests targeting `package.json`;
- native binaries;
- static-web/browser launch;
- `local_http` service targets;
- undeclared or unsupported runtime permissions.

Unsupported plans remain inspectable but are not executable.

## Runtime permissions

v0.34 understands two runtime permissions:

```text
runtime.network.inherit
runtime.data.persist
```

Without `runtime.network.inherit`, Bubblewrap receives a separate network namespace.

Without `runtime.data.persist`, no persistent writable app-data mount is provided.

The operator must approve the exact reviewed permission set at launch.

## Commands

Plan:

```bash
phi-app plan-runtime install-receipt.json > runtime-plan.json
```

Review:

```bash
phi-app review-runtime runtime-plan.json
```

Launch a plan with no requested runtime permissions:

```bash
phi-app launch-runtime \
  runtime-plan.json \
  install-receipt.json \
  --approve-runtime-plan-sha EXACT_RUNTIME_PLAN_SHA256
```

For a plan requesting permissions, each reviewed permission must be explicitly supplied:

```bash
phi-app launch-runtime \
  runtime-plan.json \
  install-receipt.json \
  --approve-runtime-plan-sha EXACT_RUNTIME_PLAN_SHA256 \
  --allow-runtime-permission runtime.data.persist \
  --allow-runtime-permission runtime.network.inherit
```

Planning never grants launch authority.

See `docs/PHIOS_APP_PLATFORM_V0.34_INSTALLED_RUNTIME.md`.
