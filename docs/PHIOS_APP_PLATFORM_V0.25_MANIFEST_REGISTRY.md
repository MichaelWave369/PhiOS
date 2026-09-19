# PhiOS App Platform v0.25 — Manifest + Registry Contract

## Status

Alpha contract.

Schema versions:

- `phios.app_manifest.v0.1`
- `phios.app_registry.v0.1`

## Purpose

v0.25 creates the identity layer required before PhiOS can safely ingest and run external
applications.

The contract answers:

> What application is being discussed, where did it come from, what runtime shape does it
> declare, and what permissions does it request?

It intentionally does not answer:

> Is it safe, buildable, installed, current, healthy, or authorized to execute?

Those are later gates.

## Manifest fields

A manifest contains exactly:

```json
{
  "schema_version": "phios.app_manifest.v0.1",
  "app_id": "phi.example",
  "name": "Example",
  "version": "0.1.0",
  "description": "Example PhiOS application.",
  "source": {
    "repository_url": "https://github.com/example/example",
    "license_expression": "MIT",
    "redistribution": "permitted"
  },
  "entrypoint": {
    "runtime": "python",
    "target": "app.py"
  },
  "permissions": [
    "workspace.read"
  ]
}
```

Unknown fields fail closed.

## App identity

`app_id` is a stable lowercase identifier, 1-64 characters, using letters, numbers, dots,
underscores, and hyphens.

The registry rejects duplicate IDs. It does not silently replace an existing app.

## Source provenance

`source.repository_url` must be an absolute HTTPS repository URL without embedded credentials,
query data, or fragments.

v0.25 records source identity only. It does not fetch the repository.

## License and redistribution

`license_expression` is a bounded declared string. PhiOS does not claim that the expression has
been legally validated.

`redistribution` is one of:

- `permitted`
- `restricted`
- `unknown`

Repository visibility never changes that field automatically.

## Runtime declaration

Supported runtime kinds:

- `static_web`
- `node`
- `python`
- `local_http`
- `native`

For filesystem-backed runtimes, the entrypoint target must be a relative POSIX path and may not
escape the future app root.

For `local_http`, the target must be an HTTP(S) loopback URL using `localhost`, `127.0.0.1`,
or `::1`.

No entrypoint is executed by v0.25.

## Permission declaration

A manifest can request up to 32 permission identifiers.

A request is not a grant.

The future governed launcher must compare requested app permissions against explicit operator
authority before any execution occurs.

## Canonical digest

Each manifest has a canonical JSON representation using:

- sorted object keys;
- compact separators;
- UTF-8;
- deterministically sorted permission identifiers.

The SHA-256 digest of that representation is the manifest identity recorded by the registry.

## Registry snapshot

A registry snapshot contains:

```json
{
  "schema_version": "phios.app_registry.v0.1",
  "apps": [
    {
      "manifest": {},
      "manifest_sha256": "..."
    }
  ]
}
```

The registry:

1. sorts apps by `app_id`;
2. recomputes each manifest digest on load;
3. rejects mismatches;
4. rejects duplicate app IDs;
5. rejects unknown fields.

## Explicit non-capabilities

v0.25 adds no:

- GitHub network intake;
- repository cloning;
- license inference;
- dependency installation;
- build execution;
- runtime adapter;
- desktop launch;
- background process;
- update mechanism;
- rollback mechanism;
- automatic authority grant.

## Planned next rung

v0.26 will add bounded GitHub intake that inspects repository metadata needed to propose an app
manifest, including license, runtime, build shape, entrypoints, and requested permissions.

That intake remains evidence generation. It does not grant execution authority.
