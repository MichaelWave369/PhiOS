# PhiOS R1.7: offline publisher-key signature and source/toolchain pin declaration

**Status: `SIGNATURE_VALID_UNDER_CALLER_SUPPLIED_PIN_STILL_HELD`. No PhiARK launch, installer, gateway, service-management or release authority.**

PhiOS R1.6 compares historical local receipts. Those receipts are self-consistent but unsigned, can be fabricated, and cannot establish that the operator ever approved the installed software. R1.7 adds a **real Ed25519 signature verification step** over a small canonical JSON statement, with explicit domain separation:

`PhiOS/PhiARK/source-toolchain-statement/v1\0` followed by canonical UTF-8 JSON (sorted keys, compact separators, `ensure_ascii=False`).

The offline verifier `phios.apps.phiark_signed_pins.verify_phiark_offline_signed_pins` requires the exact statement and its canonical base64 Ed25519 signature, **plus** the expected raw 32-byte Ed25519 public key, its SHA-256 fingerprint and its key ID supplied separately by the caller/operator. It does not import a private key, enroll a trust root, generate signatures or fetch any public key from GitHub or the bundle.

## Signed fields

The exact statement schema `phios.phiark_offline_publisher_statement.v0.1` contains the app/source URL, source commit SHA-1 (40-character Git object ID), source archive SHA-256, installed-tree SHA-256, R1.6 evidence-coherence SHA-256, runtime-preview SHA-256, declared Node executable SHA-256, declared Bubblewrap and prlimit SHA-256 pins, publisher key ID, and the exact profile `offline-network-denied`.

A valid statement must reference the still-held R1.6 coherence report, R1.1 source archive review and R1.5 process-executable observation. All three local review hashes are independently recalculated, and unsupported earlier claims of GitHub/source/toolchain/network/supervision/launch authority are rejected. Pin claims must match the historical review's source commit, archive bytes, installed tree, runtime preview and observed Node executable hash. The **Bubblewrap and prlimit hashes are declarations only**. Neither executable is read, fingerprinted against the live device or independently authenticated here.

## Where the trust starts

**Critical:** Passing any random public key alongside a matching signature and fingerprint is *not* independent authentication. A malicious actor can generate their own key, sign a fabricated statement and supply a matching fingerprint. The *operator* must obtain and review the publisher public key and fingerprint through a trusted channel **independent of the signed bundle, repository contents, connected AI session, and app-controlled data**. R1.7 currently cannot verify that the operator did so. It therefore always reports `publisher_key_provenance_independently_verified=false`.

A valid Ed25519 signature authenticates possession of the private key corresponding to the supplied public key. It **does not** prove that GitHub recognizes the stated commit, that the claimed code is identical to approved source, or that the current host actually runs the declared Node/Bubblewrap/prlimit bytes.

The verifier also does not establish freshness, anti-replay, an operator-bound launch session, a pidfd-backed child lease, real network denial, disconnected cold-start correctness, license compliance or a gateway authorization. The signed profile is a declaration, **not** an observed Linux sandbox.

## Fail-closed rules

Reject missing/unknown JSON fields, malformed SHA values, nonmatching app/source/commit/profile, unknown key ID, bad or substituted fingerprint, malformed or noncanonical signature, modified signed fields, mismatched historical receipts, forged authority flags and failed Ed25519 verification. Cryptography support is required (installed by the repository's `dev` or `reflex-authority` optional dependencies); if unavailable the operation refuses verification rather than silently degrading.

The result is a deterministic SHA-256 informational record and always has `launch_authority=false`, `gateway_authority=false`, `publisher_key_provenance_independently_verified=false`, `github_source_commit_independently_authenticated=false`, and separate false flags for installed-host executable pins, network denial and a supervised launch. No process, file, socket, network or trust store is accessed by this function. The test suite uses **ephemeral test-only private keys**, not a deployable publisher identity.

## Next admission requirements

Maintain a separate operator-owned, non-bundle-derived trust anchor and explicit key rotation/revocation policy; independently verify GitHub commit identity and measured executable files on the target machine; bind an operator-approved single-use session nonce to the supervised PID/start identity and socket peer; verify the Linux sandbox's actual network isolation, bounded shutdown and disconnected cold-start; require a separate gateway review. Only a future **distinct**, security-audited supervisor may decide whether any of those can confer launch authority.

Keep [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321) open. Prior evidence: [R1.6 coherence](PHIOS_PHIARK_R16_EVIDENCE_COHERENCE.md).
