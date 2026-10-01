# Exact OS candidate and release evidence

`Fixture-free OS candidate (unpublished)` builds the checked-out source with
`PHIOS_CI_SMOKE=0`. It has read-only repository permissions and uploads
seven-day review artifacts. It cannot create a GitHub Release, push a tag,
enroll a production signing key or publish to PyPI. The OS version remains
`0.1.0-alpha.1`; a build does not confer supported-beta status.

The normal profile excludes live QA scripts/services, disposable credentials,
test packages and enrolled PhiOS update trust. The inventory generator checks
actual image paths and refuses a mismatch with the requested fixture scope.
The normal volatile `phios`/`phios` account remains the documented live login;
that public live account does not become an installed user/password.

The external VM harness uses only the finished ISO and fresh OVMF variables,
with no target disk, network or shared folders. It logs in through normal
serial PAM using that public live account, observes the actual non-root
Wayfire/Chromium/HTTP services, tests an observer restart, logs out, enters the
same account at the real greetd keyboard/PAM prompt and checks the restarted
desktop. It resets and repeats with a distinct boot ID. Probe commands are
sent through the normal user terminal; no test code or QA service is inserted
into the image. Logs/screenshots and the exact ISO/source hash are retained.
The separate exact normal-image installed lane described below adds bounded
installation/data/recovery/Linux proof evidence for that same ISO. Real hardware
and the future final signed update transition remain additional release gates.

## Artifact inventory

| Artifact | Observed scope |
| --- | --- |
| `SHA256SUMS` | Every release payload/provenance sidecar; excludes itself and mutable CI logs |
| `provenance.json` | Exact source commit/archive, ISO/hash, Arch date, Archiso, builder digest, artifact hashes and explicit unqualified flags |
| `native-packages.json` | Actual local pacman database, name/version/architecture/base, declared license labels and metadata hashes; cross-checked against pacman output |
| `python-packages.json` | Actual installed dist-info identity/version and declared license metadata |
| `javascript-packages.json` | Actual installed production npm lock, each package.json name/version, declared licenses and supplied lock integrity |
| `javascript-bundled-packages.json` | Actual Rollup chunk participants, package/module identities, emitted chunk hashes and captured supplier notices, including generated runtime helpers |
| `sbom.cdx.json` | CycloneDX 1.6 inventory across native/Python/npm and bundled origins, with origin paths and supplier-declared license names |
| `third-party-notices.tar.gz`, `.json` | Bundled notice bytes and file hashes from native/Python/npm package paths; guest symlinks resolved inside the image |
| `source-review.json` | Exact first-party source archive and explicit pending source-delivery review for each component |
| `fixture-inventory.json` | Requested fixture scope and actual observed paths; separate from readiness |

SBOM validation uses hash-pinned official CycloneDX schemas from the reviewed
1.6 tag. A changed schema download fails validation. No supplier label is
silently translated into a concluded SPDX license, and dependency graphs or
vulnerability results are not inferred from inventory alone. Bundled notices
and a valid SBOM do not establish full distribution source/license compliance.
The exact source material, delivery terms and required notices for each
component must receive a maintainer review under its applicable license.
Arch binary archive URLs alone are not recorded as delivered source code.

## Remaining publication gates

1. Preserve the passed exact normal-image live/install/state/recovery/fixed
   workflow evidence, then qualify the final publication source/artifact and its
   actual maintainer-signed update transition. Earlier QA-image evidence is
   informative but does not silently qualify a different ISO or transition.
2. Complete the declared real-hardware matrix and record limitations, recovery
   procedure, support owner and maintenance policy for that release scope.
3. Complete the component-by-component source/notice review; deliver required
   corresponding source material with exact hashes and custody references.
4. Authenticate a maintainer-controlled public signing fingerprint through an
   independent channel. Keep its private key outside this repo, image and CI
   fixture. Sign the final checksums/provenance and verify the signed bytes
   against the authenticated current public key.
5. Review the exact final commit, artifact hashes, evidence and release notes,
   then have the human release owner authorize a prerelease in the independent
   `phios-linux-v*` tag namespace. Publish ISO, signatures, inventories, source,
   supported scope and recovery/support documentation together.

All generated reports remain `release_ready: false`; they do not grant
execution, signing, adapter-promotion or publication authority. Main/release
branch protection and required-check settings have not been changed by this
candidate workflow. Protecting them remains a maintainer repository setting.

The builder also captures actual Rollup chunk participants before npm pruning,
including Vite-generated runtime helpers. Bundled supplier metadata and license
notices are retained in the installed dist tree; the collector checks final
chunk and notice hashes and emits a separate javascript-bundled inventory.
A pruned runtime package list alone cannot describe all generated frontend code.

The normal candidate workflow also invokes `qemu_install.py --fixture-free
--recovery` against that same ISO. It uses the public live account's narrow
maintenance sudo, an explicitly reviewed standard serial password login,
user-owned canonical data/backup, the actual installed proof broker, deliberate
boot corruption and matched recovery. It introduces no root autologin or QA
service into the image. This exact installed-artifact qualification passed in
[run 36812104386](https://github.com/MichaelWave369/PhiOS/actions/runs/36812104386),
with 441 actual SBOM components and 620 captured supplier notice files. See
`docs/os/evidence/normal-installed-5145b4da.json` and RELEASE_HANDOFF.md for exact
identities and remaining gates. The real final signed package transition and
physical hardware remain separate gates.
