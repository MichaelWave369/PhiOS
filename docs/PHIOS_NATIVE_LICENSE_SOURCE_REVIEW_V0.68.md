# PhiOS v0.68: pinned upstream native dependency legal-source evidence

**Source-evidence verification only. NO redistribution, license-clearance,
installation, model, provider, or external-DONE authority is granted.**

## Context

The v0.67 Linux x64 `npm ci --ignore-scripts` census identified exactly four
platform-specific native dependencies whose installed npm payload contains no
root-level LICENSE, LICENCE, COPYING, NOTICE, UNLICENSE, or PATENTS document.
The installed package manifests declare MIT, but **that is not a completed
license-and-attribution review**.

Instead of weakening the review queue, this change ties each specific
binary package and version to a human-reviewed upstream Git repository
and **immutable commit**. GitHub tag labels are retained only as version
context; **the immutable Git SHA, not a movable tag, is the verification key**.

| Frozen npm native package | Upstream repo / version-tag commit | Source evidence at immutable commit | Evidence state |
| --- | --- | --- | --- |
| `@esbuild/linux-x64@0.25.12` | `evanw/esbuild`, `208f539945b145e7c9d6d844290f81c3fe5af320` | [LICENSE.md](https://github.com/evanw/esbuild/blob/208f539945b145e7c9d6d844290f81c3fe5af320/LICENSE.md), Git blob `2027e8dcf3787f5aac9fcd835e2b80cb75a39211` | Pinned upstream MIT license file found |
| `@napi-rs/lzma-linux-x64-gnu@1.5.1` | `Brooooooklyn/lzma`, `f164df92d83e095f195d628b1a68a141ae2eb638` | [package.json](https://github.com/Brooooooklyn/lzma/blob/f164df92d83e095f195d628b1a68a141ae2eb638/package.json), Git blob `9a9236b1fa29ee472c3bf5efcabf9e7a194a6356` | **Declaration-only: MIT in parent package manifest; no root license file in reviewed tagged tree** |
| `@rollup/rollup-linux-x64-gnu@4.64.5` | `rollup/rollup`, `05a293809848a3d772e7ff2ba44adcbd23bd84b8` | [LICENSE.md](https://github.com/rollup/rollup/blob/05a293809848a3d772e7ff2ba44adcbd23bd84b8/LICENSE.md), Git blob `7b806824370697048284c1726fc4d1b567bfea68` | Pinned upstream license exists; **composite third-party notices need review** |
| `@rolldown/binding-linux-x64-gnu@1.2.13` | `rolldown/rolldown`, `f7de35f45bcd4cb8e4b6d8d11e74fbfb20b03127` | [LICENSE](https://github.com/rolldown/rolldown/blob/f7de35f45bcd4cb8e4b6d8d11e74fbfb20b03127/LICENSE), Git blob `afc0cdbabfb99ed4030bf9be2b852977f1ed72a0` | Pinned upstream MIT license file found |

The `v1.5.1` LZMA tag is an **annotated Git tag** resolved to the
immutable source commit above. The repository references the Rust
`lzma-rust2` crate; its transitive license obligations and any binary-
specific source-to-publish provenance have **not** been independently reviewed.

## CI evidence pipeline

1. Preserve all prior v0.65, v0.66, and v0.67 tests and immutable source/
   lockfile verification.
2. Run real locked npm installs and regenerate per-app installed-package
   license inventories **before Vite may create node_modules build caches**.
3. `scripts/review_native_license_sources.py` checks the four-package
   identity/version set **equals** the v0.67 human review queue. Unexpected
   flags or changed versions fail closed.
4. Fetch exactly four **read-only** pinned files over HTTPS from the trusted
   `raw.githubusercontent.com` host, without redirects. Verify each byte
   length and Git blob SHA-1 for the source file at its reviewed commit.
   Compute SHA-256 for the evidence receipt. For LZMA verify only the parent
   package name, version, and MIT declaration. **Do not upgrade that to a
   confirmed standalone license document.**
5. Retain `native-license-source-review.json` with immutable source IDs,
   artifact hashes, and explicit negative authority states. No license text
   is copied into PhiOS or the evidence artifact. Unit tests prove forged
   approvals, altered source bytes, new native packages, or missing review
   items cannot pass.
6. Continue clean-built frontend byte-comparison regression.

## Human legal/packaging review still required

- Match all four installed binary npm tarballs to their actual published
  source and binary provenance. An upstream repo tag by itself is **not**
  that proof.
- Confirm which license/notice texts must accompany binaries. Examine
  Rollup's long combined LICENSE.md rather than calling it just MIT.
- Obtain and assess adequate standalone license evidence for the LZMA
  native artifact, including Rust dependencies. Review other transitive
  and platform-optional packages before a cross-platform release.
- Assemble and approve the package notice bundle, then separately review
  vulnerabilities and distribution implications.

A green v0.68 result means **source evidence verified at immutable Git
commits**, with one declaration-only gap held for human review. It does
**not** mean PhiOS can redistribute, install, launch, or run either app.
No finished installer or binary is authorized by this PR.

**Ledger Above Ego. DONE Means Verified.**
