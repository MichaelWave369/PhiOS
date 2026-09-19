# PhiOS App Platform v0.28

PhiOS App Platform v0.28 adds the **Build Plan Contract**.

v0.27 can acquire one explicitly approved GitHub revision into a bounded source workspace. v0.28
can inspect that pinned workspace and describe a proposed build without executing it.

## Pipeline

```text
v0.27 acquisition receipt
        +
v0.26/v0.25 intake + manifest
        ↓
bounded local source snapshot
        ↓
bounded root build metadata
        ↓
deterministic build strategy
        ↓
build plan SHA-256
        ↓
operator review
```

## Commands

Create a plan:

```bash
phi-app plan-build intake.json acquisition-receipt.json > build-plan.json
```

Review the exact plan identity:

```bash
phi-app review-build-plan build-plan.json
```

Neither command executes the plan.

## Source snapshot

v0.28 computes a platform-independent source snapshot digest over:

- relative POSIX file path;
- file byte count;
- SHA-256 of file bytes.

The acquisition receipt's v0.27 tree digest remains separately recorded as provenance. The new
source snapshot digest exists so a later build executor can prove that the bytes it is about to use
are the same bytes reviewed in the build plan.

## Build families

v0.28 can propose bounded plans for:

- Node package projects;
- Python `pyproject.toml` / PEP 517 wheel builds;
- Rust / Cargo projects;
- Go module projects;
- static web source that requires no build.

Ambiguous or insufficient build metadata yields `review_required` with no invented execution path.

## No shell interpolation

Build commands are stored as explicit argv arrays.

For example:

```json
{
  "tool": "npm",
  "argv": ["npm", "run", "build"]
}
```

PhiOS does not copy a repository's arbitrary build-script text into a shell command.

## Requested build permissions

Plans may request bounded future permissions such as:

- `build.network.dependencies`;
- `build.process.execute`;
- `build.workspace.write`.

These are requests only. v0.28 grants none of them.

See `docs/PHIOS_APP_PLATFORM_V0.28_BUILD_PLAN.md`.
