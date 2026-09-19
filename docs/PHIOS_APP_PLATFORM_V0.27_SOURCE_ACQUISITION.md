# PhiOS App Platform v0.27 — Governed Source Acquisition

## Status

Alpha contract.

Schemas:

- `phios.source_acquisition_request.v0.1`
- `phios.source_acquisition_receipt.v0.1`

v0.27 builds on the frozen v0.25 manifest and v0.26 intake contracts.

## Purpose

v0.27 answers one narrow question:

> Can PhiOS acquire the exact approved source revision into a bounded local workspace and produce a
> deterministic receipt describing what was acquired?

It does not answer whether the source is safe to build or execute.

## Required inputs

An acquisition request binds:

1. canonical public GitHub repository URL;
2. exact commit SHA observed by v0.26;
3. one v0.25 manifest candidate;
4. the operator-approved exact commit SHA;
5. the operator-approved SHA-256 of that exact manifest.

Before any source download:

- the manifest source repository must match the acquisition repository;
- the approved commit SHA must match the commit captured in intake evidence;
- the approved manifest digest must match the manifest candidate;
- both commit identifiers must be bounded hexadecimal commit identifiers.

## Operator approval semantics

Approval is revision-specific and digest-specific.

Approving commit A does not approve commit B. Approving manifest digest A does not approve modified
manifest B, even when both refer to the same repository and commit.

The approval does not grant build, install, launch, or runtime permissions.

## Network boundary

The built-in source provider accepts a canonical `https://github.com/OWNER/REPO` source and
downloads only the corresponding exact commit ZIP from:

```text
https://codeload.github.com/OWNER/REPO/zip/COMMIT_SHA
```

A redirect outside HTTPS `codeload.github.com` fails closed.

The archive download is bounded to 16 MiB compressed in v0.27.

## Extraction bounds

The default source contract allows at most:

- 4,096 regular files;
- 8 MiB per file;
- 128 MiB total uncompressed regular-file content.

These are alpha safety bounds, not statements about what all future PhiOS apps must fit within.

## Extraction safety

Every archive member is validated before becoming authoritative workspace content.

Rejected forms include:

- absolute paths;
- empty/dot/parent path segments;
- backslash-based path forms;
- path traversal;
- members outside the one expected top-level archive root;
- duplicate relative paths;
- symbolic links;
- device nodes, sockets, FIFOs, and other special file types.

Directory entries receive normalized directory permissions.

Regular files receive normalized permissions:

- executable source file → `0755`;
- non-executable source file → `0644`.

No archive-provided ownership or elevated permission bits are preserved.

## Workspace lifecycle

Acquisition uses:

```text
WORKSPACE_ROOT/
  .acquire-APP-ID-RANDOM/     temporary staging
  APP-ID/
    EXACT_COMMIT_SHA/         final acquired source
  .phios-receipts/
    RECEIPT-ID.json
```

An existing final destination is never overwritten.

Staging is removed on failure.

The final source directory is moved into place only after archive validation and hashing succeed.

If receipt persistence fails after that move, the new final source directory is removed. PhiOS does
not intentionally leave a successful-looking but unreceipted acquisition behind.

## Deterministic source-tree digest

For each regular file, v0.27 records a canonical tuple:

```text
relative_path
normalized_mode
byte_count
sha256(file_bytes)
```

Records are sorted lexicographically by relative POSIX path and hashed into one source-tree SHA-256.

Directory timestamps, archive ordering, ZIP compression, host ownership, and source ZIP timestamps
do not affect the source-tree digest.

## Receipt claims

A successful receipt establishes only that:

- the requested exact commit selector was used for acquisition;
- the downloaded archive had the recorded archive digest;
- extraction satisfied the v0.27 bounded path/type/size contract;
- the resulting regular files produced the recorded deterministic tree digest;
- the workspace was written at the recorded path.

It does not establish:

- source safety;
- source authorship beyond GitHub transport context;
- dependency safety;
- build reproducibility;
- build success;
- runtime safety;
- permission suitability;
- application health.

## Explicit non-capabilities

v0.27 performs no:

- package-manager invocation;
- dependency resolution;
- build script;
- compiler invocation;
- application execution;
- desktop launch;
- registry promotion;
- permission grant;
- trust promotion;
- automatic update;
- rollback.

## Planned next rung

v0.28 will add a **build-plan contract**.

The build-plan rung should identify the commands, tools, dependency managers, working directories,
expected outputs, and requested build permissions without executing them.

Execution of a build plan remains a later, separately authorized rung.
