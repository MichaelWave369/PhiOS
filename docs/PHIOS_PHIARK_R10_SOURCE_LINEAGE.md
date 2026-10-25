# PhiOS R1.0: PhiARK installed-package source-commit review gate

**Status: HELD_FOR_SOURCE_ATTESTATION.** This check makes no network calls, grants no app permission, installs nothing, does not launch a service, and does not independently prove any public repository's contents.

## Why this gate exists

R0.9 can check an already-installed PhiOS payload and prepare a Bubblewrap command with private PhiARK vault mapping and denied networking. However, the installation receipt contains hashes of the installed bytes and package plan, while the commit SHA lives in the package plan itself. We must validate the complete *local claim chain* before considering a supervised service.

`phios.apps.phiark_source_lineage.review_phiark_source_lineage` recomputes an R0.9 PhiARK installed runtime preview and checks the canonical installed `/.phios/package-plan.json` as an exact, bounded, non-symlink regular file. It parses that file as a native `BuildPackagePlan` and checks it against the native `AppInstallReceipt`:

- Exact PhiARK repository and 40-character candidate commit SHA.
- Matching package-plan SHA-256, app ID, version, manifest, registry, build and execution receipt hashes.
- Matching offline-build digest and artifact-set SHA-256, item count and total bytes.
- Real installed-tree verification inherited from the PhiOS runtime planner.
- Explicit `launch_authority=false` in package and installation receipts.

Any absent or tampered installed metadata, unsafe file, invalid plan or mismatched claim causes refusal. The output's `local_package_lineage_consistent=true` indicates **local receipt consistency only**.

## What it does NOT establish

A malicious or mistaken author could fabricate a self-consistent package plan and local installation receipt. A matching commit string does not establish that the installed executable bytes came from that public GitHub commit, that dependencies were independently verified or that the code is safe.

The resulting status remains `HELD_FOR_SOURCE_ATTESTATION`. In the output, all fields named `*_attested`, `*_verified`, `*_authority`, `*_qualified` remain false except the specifically named local consistency flag. There is **no path from this report to launching PhiARK**.

## Next gates for an executable PhiOS service

1. Independently link exact acquisition tree receipts, approved build execution, package artifact bytes, and the reviewed PhiARK commit; evaluate the source and licensing evidence rather than trusting a commit label alone.
2. Review actual Node 20+ / Bubblewrap / prlimit toolchain hashes on the target Linux environment, plus the persistent private data root and inode conditions.
3. Build a bounded, explicitly approved supervisor with a foreground child PID, authenticated socket readiness, lifecycle receipts, stop and fail-closed restart behavior. No silent daemon or ambient network inheritance.
4. Demonstrate on Linux that the service cannot reach WAN or LAN; then test an actual offline cold start and local guide search/read/integrity refusal.

Related: [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321), [R0.9 preview](PHIOS_PHIARK_R09_SERVICE_PREVIEW.md).
