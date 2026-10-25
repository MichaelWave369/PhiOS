# PhiOS R0.6: PhiARK read-only integration and governance boundary

**Historical note (R0.8):** The broad `runtime.network.inherit` manifest proposal described below has been superseded by the [network-denied R0.8 candidate](PHIOS_PHIARK_R08_INSTALL_REVIEW.md). The rest of this document describes the original R0.6 observer, not an installed service.\n\n**Status:** PhiARK source/vault adapter plus PhiShell advisory tile, not a governed installation or running service.
Reference issue: [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321)

## What was implemented

- A read-only PhiOS observer in \`phios/apps/phiark_bridge.py\`; command \`phi-app phiark-status\`.
- A PhiShell **PhiARK Knowledge Vault** app tile whose status is **Integration probe**. Selecting it opens information, not an executable program, browser, browser iframe, service or credential prompt.
- Local document verification against the actual \`catalog.json\`, \`objects/<digest>\`, byte sizes and SHA-256. Hardening rejects symlinks, unsupported paths, over-large catalog objects, wrong file types and corrupt bytes.
- Optional \`--verify-kiwix\` checks local R0.4 archive receipts and official saved checksum bytes, reports missing/failed/verified editions separately. This is intentionally opt-in because hashing multi-hundred-MB ZIM files is not free.
- Optional \`--probe-loopback\` fetches a bounded status response **only from 127.0.0.1:3691**, without DNS or proxies, never from an arbitrary address. It does not authenticate process identity.
- A v0.25-compatible **manifest candidate**, \`integrations/phiark/manifest-candidate.json\`. It is NOT \`phios-app.json\` in PhiARK root, NOT registered, NOT ingested, and NOT a runtime authority grant. This candidate identifies \`src/server.mjs\` and documents the permissions that would currently be required by generic PhiOS adapters.

## Operator commands

\`\`\`bash
# Explicit data root; no guessed user-specific paths:
phi-app phiark-status --data-root /mnt/data/PhiARKVault
# Recompute SHA-256 for each present known Kiwix archive as well:
phi-app phiark-status --data-root /mnt/data/PhiARKVault --verify-kiwix
# Optional: ask the already-running local server for its read-only status:
phi-app phiark-status --data-root /mnt/data/PhiARKVault --probe-loopback
\`\`\`

The default command does **no network access** and performs **no writes**. Normal behavior when no vault exists is \`BLOCKED\` or \`NOT_INSTALLED_OR_EMPTY\`, **not** a made-up installed status. Return code 0 means some local bytes match SHA-256; code 1 means absent, empty or blocked, and code 2 is a malformed explicit request. Passing hashes verifies only byte consistency; source authority, safety, license and proper installed ancestry are **not verified**.

## Why this does not start PhiARK through the existing PhiOS runtime

PhiOS v0.34 supports bounded direct Node targets, but its currently available network permissions are:

- \`network_mode=deny\`: completely separate sandbox network, so a host-loopback Node server will not be browsable from the host.
- \`runtime.network.inherit\`: **broad host-network inheritance**. This is not equivalent to a narrowly authorized loopback listener and remains excessive for a general future install proposal.
- \`runtime.data.persist\`: reviewed writable \`/phios/app-data\` mount, which has not yet been mapped/tested as \`PHIARK_DATA_DIR\` under a real PhiOS installation.

The manifest candidate consequently **does not qualify as an installed/launchable PhiARK app** by virtue of existing. Do not silently pass an empty permission list or claim the host loopback is isolated. The reader's native \`kiwix-serve\` binary is even further from this Node adapter and needs separate reviewed toolchain/runtime and process lifecycle authority.

## Required next gates

1. Bounded v0.26 intake of the actual PhiARK repo and an operator-reviewed exact commit SHA.
2. Compatible installable artifact with precise runtime, Node toolchain evidence, file/executable tree receipt, app data mapping to separate persistent storage.
3. A tighter **loopback-only network boundary** and real sandbox proof, so no broad network inheritance is smuggled into PhiOS.
4. Exact launch/stop approval linked to runtime plan digest, capabilities, and actual installed-tree receipt; no unattended daemon launch.
5. Desktop catalog entry backed by the actual reviewed grant, or an operator-controlled external desktop link, with honest installed/not-installed behavior.
6. Actual disconnected cold-start test with seed, local search, document open and hash integrity checks, then Kiwix offline browser/stop tests.
7. Separate authorized LAN and authentication design before exposing anything to other PhiPie boxes or LAN devices.

**Not covered:** Kiwix reader installation, Kolibri, repository auto-mirroring, machine-specific USB boot, claims of medical source safety, redistribution of third-party reference archives, privilege elevation, or automatic launch by AI agents.

### CI evidence boundary

The Python tests create temporary fake documents and tiny synthetic archive bytes. They verify integrity gating and advisory-only authority. PhiShell Vitest verifies the tile is informational and causes no fetch or grant. Nothing in CI certifies Linux Bubblewrap isolation or proves real PhiPie hardware compatibility.
