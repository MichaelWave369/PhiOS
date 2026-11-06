# Φ Universal App Center R5B · Publisher Signature Gate (Linux)

**Implementation status:** *offline signed-release review implemented; installation still held*. This is an extension of the existing PhiOS App Platform, **not** a new package manager. A signature is evidence that some private key signed a particular statement. It is not proof that the key belongs to the repository owner or that the software is suitable to run.

## What actually works

`phios.apps.release_publisher_review` verifies a raw 64-byte **Ed25519 detached signature** covering a strictly formatted, domain-separated JSON publisher statement. The statement is cryptographically bound to an existing validated **v0.50 `ReleaseInstallProposalRecord`**, not merely to an arbitrary repository name. Signed fields include app identity/version, source repository/commit, v0.50 release-install-proposal SHA-256, package plan SHA-256, app manifest SHA-256, and built artifact-set SHA-256. The module reuses the release proposal's own canonical digest and checks every binding.

The operator must supply **both** a 32-byte raw Ed25519 public key and its SHA-256 fingerprint as **separate** command-line input, plus an expected publisher key ID. A key contained in the downloaded release JSON is never an accepted trust root. The code deliberately does not obtain keys from GitHub, keyservers, websites, or a package's own manifest.

Install the optional dependency into a development environment:

```bash
python -m pip install -e '.[publisher-signatures]'
python -m phios.apps.release_publisher_review \
  --proposal /operator/review/exact-v050-proposal.json \
  --statement /operator/review/publisher-statement.json \
  --signature /operator/review/publisher-statement.sig \
  --public-key /operator/trust/publisher-ed25519-raw.pub \
  --trusted-key-sha256 LOWERCASE_64_HEX_OPERATOR_PIN \
  --expected-key-id OPERATOR_VERIFIED_KEY_ID
```

This command **only reads** bounded local files and prints a review JSON receipt to standard output. It refuses symlinks, oversized/non-regular files, unknown fields, stale/mismatched release proposals, wrong key fingerprints, wrong key ID, bad signatures, and any statement that attempts to grant install/update/rollback authority. It performs no downloads, builds, subprocess execution, host permission changes, installs, rollbacks, or signature generation.

The Ed25519 signed bytes are:

`b"PhiOS/release-publisher-statement/v1\\x00" + json.dumps(statement, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")`

The `\\x00` in that description denotes **one NUL byte**, not literal slash characters. The statement's `schema` is `phios.release_publisher_statement.v0.1`. Its required fields are:

| Field | Constraint |
|---|---|
| `publisher_key_id` | Human-controlled, separately expected key ID |
| `app_id`, `app_version`, `repository_url`, `commit_sha` | Exact v0.50 proposal values |
| `release_install_proposal_sha256`, `package_plan_sha256`, `manifest_sha256`, `artifact_set_sha256` | Exact proposal canonical digests |
| `dependency_review_sha256`, `compatibility_review_sha256`, `rollback_rehearsal_sha256` | 64-hex **publisher-declared references**, **NOT independently validated results** |
| `install_authority`, `update_authority`, `rollback_authority` | All **false**, even if signature is valid |

The receipt status is intentionally `SIGNATURE_VALID_UNDER_CALLER_PIN_RELEASE_STILL_HELD`. Its `publisher_identity_independently_verified`, `source_commit_independently_authenticated`, `dependency_compatibility_verified`, `device_compatibility_verified`, `license_distribution_review_cleared`, `sandbox_and_permission_review_cleared`, and `rollback_rehearsal_independently_verified` flags remain **false**.

## Integration with existing v0.50+ governed installer

PhiOS already implements `phios.apps.release_install_proposal`, `AppInstallService` and receipt-linked side-by-side release install, plus desktop update/rollback plans, retention markers, requested permission checks, and rollback services. **R5B does not rewire, weaken, or automatically authorize those existing gates.** This signature verifier is extra, separately operator-reviewed evidence that later release authorization can require.

**Before native INSTALL could safely appear in App Center:** an actual independent owner-to-key trust enrollment, a reproducible source/commit-to-artifact verification, SPDX/license review, compatible dependency/toolchain and sandbox evidence, a disposable-machine rollback rehearsal with matched receipts, and explicit user/device approval remain necessary. That work has to be implemented and tested independently; do not infer it from this receipt.

## Web and Android

PhiOS Web and the PhiOS Mobile PWA already use browser-managed installation and service workers. They should **not** represent a Linux Ed25519 release statement as an Android signature, Play Protect assessment, native package install, or PWA update guarantee. The Android HOME test APK continues delegating installed-app lifecycle actions to Android itself; no APK installer or signing keys have been added.

## Test expectations

`pytest -q tests/test_app_platform_v059_signed_release_review.py` covers real Ed25519 verification, statement tampering, key substitution, release/plan substitution, invalid authority and missing dependency/rollback references, bounded CLI file reads, and symlink refusal. The full PhiOS CI, PhiShell build and Linux VM/recovery qualifications remain independent.

**Signed != trusted. Trusted != compatible. Compatible != recoverable. Reviewed != installed.**
