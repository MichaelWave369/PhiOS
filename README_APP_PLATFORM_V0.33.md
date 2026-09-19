# PhiOS App Platform v0.33

PhiOS App Platform v0.33 adds the **Build Artifact Package / Install Contract**.

v0.32 proves that an npm application can be built from verified dependencies inside a
network-denied sandbox. v0.33 takes only the successful, receipted build artifacts and turns them
into a governed installation.

The critical boundary remains:

```text
registered
≠ built
≠ installed
≠ authorized to launch
≠ running
```

## Pipeline

```text
registered manifest
        +
successful v0.32 offline build
        ↓
verify execution receipt
        ↓
verify offline-build receipt
        ↓
verify exact artifact set
        ↓
deterministic package plan
        ↓
review exact package-plan SHA
        ↓
explicit approval
        ↓
copy only receipted artifacts
        ↓
verify staged payload digest
        ↓
atomic install promotion
        ↓
install receipt
        ↓
NO LAUNCH AUTHORITY
```

## Commands

Create a package plan:

```bash
phi-app plan-package \
  manifest.json \
  registry.json \
  build-execution-receipt.json \
  offline-build-receipt.json \
  > package-plan.json
```

Review the exact install identity:

```bash
phi-app review-package package-plan.json
```

Install only after approving the exact package-plan digest:

```bash
phi-app install-package \
  package-plan.json \
  registry.json \
  build-execution-receipt.json \
  offline-build-receipt.json \
  --approve-package-plan-sha EXACT_PACKAGE_PLAN_SHA256
```

Uninstall only an unchanged install bound to an explicitly approved install receipt:

```bash
phi-app uninstall-package install-receipt.json \
  --approve-install-receipt-sha EXACT_INSTALL_RECEIPT_SHA256
```

## What gets installed

Only files named in the successful build receipt are copied into the application payload.

The rest of the execution workspace is excluded.

That means source files, `node_modules`, caches, temporary files, and unrelated build residue do
not enter the install merely because they happened to exist next to the build output.

See `docs/PHIOS_APP_PLATFORM_V0.33_ARTIFACT_INSTALL.md`.
