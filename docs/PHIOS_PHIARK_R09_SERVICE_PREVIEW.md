# PhiOS R0.9: Network-denied PhiARK service command preview

**Status:** HELD_FOR_OPERATOR_REVIEW. This rung does not run a process.

## Purpose

PhiARK has a private Linux Unix socket, and PhiOS R0.7 has a manually controlled localhost diagnostic gateway. R0.8 eliminated the old broad host-network permission. R0.9 now checks an actual (local) PhiOS installed-tree receipt and assembles a **read-only command preview** for the existing Bubblewrap runtime, including the environment variables needed for PhiARK.

The real execution, supervised stop/restart, provenance confirmation, and offline cold start are separate gates. A generated command is not evidence it has been executed.

## Inputs and checks

- One current, fully validated PhiOS v0.33 installed-app receipt and its installed tree.
- PhiARK manifest identity, MIT declaration, GitHub source URL, exact Node entrypoint, and only runtime.data.persist permission.
- One full 40-character *candidate* source commit. The receipt does not bind this commit to installed bytes, so the output explicitly records source_commit_attested_to_installed_tree=false.
- A separate, already-existing private operator-owned 0700 vault directory. The planning code never creates, modifies or deletes it and blocks symlinks, non-private modes, overlap with executable tree and pre-existing socket paths.
- A selected absolute Node/bwrap/prlimit executable set. The command is rendered but **not run**, and its toolchain identities are not attested.

## Network and filesystem boundary

The command invokes Bubblewrap with the generic runtime's enforced network namespace option --unshare-net. The installed artifact is read-only at /app. The only separately writable PhiARK host data bind is the approved private vault at /phios/app-data. The environment is cleared and explicitly sets:

~~~text
PHIARK_DATA_DIR=/phios/app-data
PHIARK_SOCKET_PATH=/phios/app-data/.phiark.sock
~~~

No PHIARK_HOST, PHIARK_PORT, PHIARK_ALLOW_LAN or runtime.network.inherit is admitted.

## Authority and remaining blockers

This is a **library function, not an operator-run background service**. Its preview requires an exact SHA-256 to render argv, but that hash approves *only inspection of the preview*. It cannot be used to launch anything.

Before actual launch: verify installed-source lineage from the approved exact PhiARK commit; review Node >=20 and the sandbox binary identities; approve exact Bubblewrap policy; implement a bounded supervised service lifecycle; confirm socket owner and peer identity for the browser gateway; exercise real Linux namespace separation with WAN/LAN-negative tests; prove stopped/failed states and disconnected restart; add operator-controlled rollback and release receipts.

These gates remain open in [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321).
