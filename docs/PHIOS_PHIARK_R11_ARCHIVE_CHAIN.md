# PhiOS R1.1: PhiARK offline archive-to-install evidence cross-check

**Status:** local-byte verification only. No network download, source authentication, app installation, launch, grant, service process or hardware claim.

## Why

R1.0 binds PhiARK's *claimed* commit SHA to the installed package-plan receipt. That detects local metadata changes, but the commit name alone is not evidence that the source bytes actually match the approved acquisition and build records.

R1.1 adds `phios.apps.phiark_archive_chain.review_phiark_archive_chain`, a **read-only verifier** that accepts actual bounded ZIP bytes and native PhiOS v0.27 acquisition, build-execution, offline-build and installed-app receipts. This function deliberately requires all those local records and rejects absent or conflicting evidence.

## Checks

- Inspect every archive member using the native v0.27 GitHub-archive name, symlink, file-mode, member count and uncompressed size restrictions, without writing files.
- Recompute the full archive SHA-256, normalized v0.27 acquisition-tree digest and v0.28 source-content snapshot digest from the *bytes supplied*, not an author-entered hash.
- Bind repository, 40-character commit claim, manifest, file count and source bytes against the source-acquisition receipt.
- Use native `SuccessfulBuildBinding.from_payloads` to check canonical successful build and offline-build receipts, their digests and sandbox evidence.
- Recheck the R1.0 installed package plan and actual current installed tree, and compare source snapshot, execution, offline and artifact digests through to installed bytes.
- Reject invalid ZIPs, symlinks, path traversal, duplicate archive paths, changed ZIP bytes, altered records, mismatched commits or mismatched installed files.

The result uses `ARCHIVE_BYTES_MATCHED_LOCAL_RECEIPTS` and **always** sets `source_authenticated_against_github=false` and `launch_authority=false`. This is **not** public GitHub verification: a fabricated but self-consistent archive/receipt set could still pass. No external download or signature verification takes place. The actual acquisition workspace or build runner is not reexecuted, and archive inspection is subject to normal filesystem race limitations of the installed-tree checker.

## Next gate

Independently obtain trusted exact-source evidence for the same reviewed Git commit, validate the local source/build lineage and audited toolchain, then add a gated Linux process supervisor with explicit start/stop/restart and evidence receipts. A production launch must also prove Bubblewrap network denial on the target host and an authenticated browser-socket service, followed by real WAN-disconnected cold-start tests.

The entire PhiARK issue [#321](https://github.com/MichaelWave369/PhiOS/issues/321) remains open; this verification does not mark it installed or running.
