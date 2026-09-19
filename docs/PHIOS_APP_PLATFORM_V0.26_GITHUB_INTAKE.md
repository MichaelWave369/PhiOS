# PhiOS App Platform v0.26 — Bounded GitHub Intake

## Status

Alpha contract.

New schemas:

- `phios.app_intake_evidence.v0.1`
- `phios.app_intake_proposal.v0.1`

v0.25 app manifests remain `phios.app_manifest.v0.1`.

## Purpose

v0.26 turns one explicit public GitHub repository URL into a bounded evidence object plus a
non-authoritative app proposal.

The intake pipeline is:

```text
explicit repository URL
        ↓
public GitHub metadata
        ↓
default branch head
        ↓
bounded root listing
        ↓
up to 8 known discovery files
        ↓
content hashes + transient parsing
        ↓
proposal
        ↓
optional v0.25 manifest candidate
```

A proposal is not registration or authority.

## Network boundary

The built-in client accepts only:

- input repository URLs under `https://github.com/OWNER/REPO`;
- API requests to `https://api.github.com`.

It does not accept arbitrary hosts, embedded credentials, repository subpaths, query strings, or
fragments.

Public repositories only are admitted by the v0.26 provider.

## Request and size bounds

The provider has explicit limits:

- no more than 12 API requests;
- no more than 512 KiB per JSON API response;
- no more than 512 repository-root entries;
- no more than 8 discovery files;
- no more than 128 KiB per discovery file.

There is no clone, recursive checkout, package download, dependency resolution, or build.

## Discovery files

The bounded root marker set includes:

- `phios-app.json`;
- `package.json`;
- `pyproject.toml`;
- `index.html`;
- `Cargo.toml`;
- `go.mod`;
- `netlify.toml`;
- `vite.config.js`;
- `vite.config.ts`.

Only markers actually present at repository root are fetched.

## Explicit PhiOS manifest

If `phios-app.json` exists, it must satisfy the frozen v0.25 manifest contract.

If it is malformed, v0.26 fails closed for that declaration and does not silently ignore it in
favor of another marker.

The declared source repository must match the repository being inspected.

A valid declaration is still only a declaration. It has not been independently proven safe or
authorized.

## Inferred runtime candidates

If no `phios-app.json` exists, v0.26 may create a manifest candidate using deterministic marker
rules.

Precedence:

1. `package.json` → `node`;
2. `pyproject.toml` → `python`;
3. `index.html` → `static_web`;
4. `Cargo.toml` → `native`;
5. `go.mod` → `native`.

If no supported marker exists, the result is `insufficient_metadata` and no manifest candidate
is created.

## Permissions

v0.26 does not infer permissions from code, dependency names, README prose, or repository topic
labels.

For inferred candidates:

```text
permissions = []
permissions_source = "not_declared"
```

This means unknown/unprovided, not permission-free.

A future launch contract must require an explicit operator-approved permission declaration.

## License and redistribution

GitHub repository metadata may provide an SPDX identifier. That value can populate the candidate's
declared license expression.

For inferred candidates, redistribution is always:

```text
unknown
```

PhiOS does not convert repository visibility or SPDX recognition into an automatic legal decision.

A valid explicit `phios-app.json` may itself declare `permitted`, `restricted`, or `unknown`,
but v0.26 records that as declared metadata rather than independent legal verification.

## Evidence minimization

The provider temporarily reads selected discovery-file contents so deterministic parsers can
inspect them.

Persisted intake evidence contains:

- repository URL / owner / name;
- default branch;
- head commit SHA;
- archive/disabled flags;
- reported SPDX identifier;
- bounded root paths;
- inspected file path;
- inspected file byte count;
- inspected file SHA-256;
- provider request count.

Raw discovery file content is excluded.

## Repository lifecycle state

A GitHub repository reporting `disabled=true` produces no manifest candidate.

An archived repository may still be described by intake evidence. Archive state is preserved so a
future install/launch policy can decide whether to admit it.

v0.26 itself does not make that future policy decision.

## Explicit non-capabilities

v0.26 adds no:

- repository clone;
- source checkout;
- recursive code scanning;
- dependency installation;
- build execution;
- binary execution;
- registry mutation;
- trust promotion;
- permission grant;
- launch;
- update;
- rollback.

## Planned next rung

v0.27 will add a governed **source acquisition contract**: pin an approved proposal to an exact
commit, acquire it into a bounded app workspace, hash the acquired tree, and produce an acquisition
receipt.

Acquisition will remain separate from build and execution.
