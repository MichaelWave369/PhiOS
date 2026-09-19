# PhiOS App Platform v0.25

PhiOS App Platform v0.25 introduces the first governed application-layer primitive:

**strict app manifests plus a deterministic registry.**

This release deliberately does **not** clone, build, install, update, launch, or execute applications.

## What an app manifest declares

A v0.25 manifest records:

- stable app ID;
- human-readable name and version;
- source repository URL;
- declared license expression;
- explicit redistribution state;
- runtime kind;
- bounded entrypoint target;
- requested PhiOS permissions.

Supported runtime declarations are:

- `static_web`
- `node`
- `python`
- `local_http`
- `native`

The runtime declaration is metadata only in v0.25. Runtime adapters arrive later.

## Authority boundary

Registration means:

> PhiOS can identify this app and preserve its declared metadata.

Registration does **not** mean:

> PhiOS trusts, installs, redistributes, builds, or may execute this app.

Those later actions require their own intake checks, explicit authority, pinned source/build receipts, and governed launch path.

## License boundary

A public repository is not automatically redistributable.

The manifest therefore stores both:

- the declared license expression; and
- an explicit redistribution state: `permitted`, `restricted`, or `unknown`.

PhiOS v0.25 does not infer legal permission from repository visibility.

## Registry integrity

The app registry:

- rejects duplicate app IDs;
- sorts entries deterministically;
- hashes each canonical manifest with SHA-256;
- persists the manifest beside its digest;
- rejects tampered or mismatched digests on load;
- rejects unknown registry and manifest fields.

See `docs/PHIOS_APP_PLATFORM_V0.25_MANIFEST_REGISTRY.md` for the full contract.
