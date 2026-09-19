# PhiOS App Platform v0.27

PhiOS App Platform v0.27 adds **governed source acquisition**.

v0.26 could inspect a public GitHub repository and produce a non-authoritative manifest candidate.
v0.27 can now take an explicitly approved candidate and acquire the exact source commit into a
bounded local workspace.

It still does **not** install dependencies, build, execute, launch, register, or trust the app.

## Operator workflow

```bash
phi-app inspect-github https://github.com/OWNER/REPO > intake.json
phi-app review-intake intake.json
phi-app acquire-github intake.json \
  --approve-commit-sha EXACT_COMMIT_SHA \
  --approve-manifest-sha EXACT_MANIFEST_SHA256
```

`review-intake` performs no acquisition. It exposes the exact revision and canonical manifest digest
that the operator must approve.

## Approval requirement

Acquisition requires the operator to approve the exact canonical SHA-256 of the manifest candidate.

The request binds together:

- repository URL;
- exact commit SHA from v0.26 evidence;
- manifest candidate;
- operator-approved exact commit SHA;
- operator-approved manifest SHA-256.

Either approval mismatch fails closed before network acquisition.

## Exact source acquisition

The built-in provider downloads:

```text
https://codeload.github.com/OWNER/REPO/zip/EXACT_COMMIT_SHA
```

The commit is not replaced by a branch name or moving tag.

## Safe extraction

v0.27 rejects:

- absolute paths;
- parent-directory traversal;
- backslash-based paths;
- multiple unexpected archive roots;
- duplicate paths;
- symlinks;
- special files;
- oversized files;
- too many files;
- oversized total uncompressed content.

Extraction occurs in a staging directory and is atomically moved into the final app workspace only
after validation succeeds.

## Deterministic tree identity

Each regular file contributes:

- relative POSIX path;
- normalized executable/non-executable mode;
- byte count;
- SHA-256.

The sorted canonical file records produce one deterministic source-tree SHA-256.

## Receipt

A successful acquisition writes a receipt outside the acquired source tree containing:

- app ID;
- repository URL;
- exact commit SHA;
- approved manifest SHA-256;
- downloaded archive SHA-256;
- extracted source-tree SHA-256;
- file count;
- total bytes;
- workspace path;
- timestamp and receipt ID.

If receipt persistence fails, the newly acquired workspace is removed rather than leaving
unreceipted source behind.

See `docs/PHIOS_APP_PLATFORM_V0.27_SOURCE_ACQUISITION.md`.
