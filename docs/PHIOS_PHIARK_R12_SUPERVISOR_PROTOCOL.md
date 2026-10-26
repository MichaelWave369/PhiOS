# PhiOS R1.2: PhiARK supervisor lifecycle protocol (simulation)

**Status: SIMULATED_UNQUALIFIED. No PhiARK process or real operating-system service is launched here.**

PhiOS R1.1 verifies actual source ZIP bytes against the native acquisition, build and installation receipt chain, but that chain is **still locally self-consistent evidence**, not authentication to GitHub or qualification of a physical Linux sandbox. It must not be consumed as a launch credential.

R1.2 adds a pure, deterministic Python state-transition model: `phios.apps.phiark_supervisor_protocol`. It is the lifecycle contract that a future separately authorized process supervisor must satisfy. Inputs are explicitly **synthetic** process/socket observations. No subprocess, PID inspection, daemon, signal, socket probe, file deletion, credential sharing, gateway bridge, network call or mutation occurs.

## Lifecycle

- **stopped → starting**: only on an explicit request with synthetic child-not-running and socket-not-present observations. A logical 30-tick startup deadline is opened.
- **starting → ready**: requires synthetic child and private-socket presence plus an opaque socket tag before the deadline. No claim is made that this corresponds to actual peer credentials, ownership, readiness, or isolation.
- **ready/starting → stopping**: explicit stop or restart request creates a bounded 15-tick shutdown deadline. There is no implied signal or termination.
- **stopping → stopped**: requires synthetic evidence that neither the child nor the socket remains. A restart is never automatic. A restart request creates only a manual-start-required receipt on shutdown.
- **starting/ready/stopping → failed**, or **starting/stopping → blocked** on deadline: refuses automatic cleanup, socket unlink, forced restart and new starts.
- **failed/blocked → stopped**: requires an explicit simulated manual recovery event and no child/socket present.

Clock regression, late readiness, fake readiness without child/socket evidence, existing stale socket at start, duplicate unsupported events, inconsistent state, and forged launch authority all fail closed.

## Receipts

Each transition outputs a SHA-256 over canonical JSON with sequence, predecessor receipt digest, source-archive review digest, runtime preview digest, logical timestamp, phase transition, fake observations, a note and **an empty `operations_performed` list**. All receipts have `status=SIMULATED_UNQUALIFIED` and set all launch/install/gateway/source-authentication/physical-isolation/supervision claims to false.

The hash chain detects accidental changes in an exported simulated transcript, **not** malicious forgery, identity or independent device evidence. It is not signed, persistent, monotonic hardware time, a process identity proof or a permission capability.

## Why no automatic start/stop yet?

The real PhiARK service is a Node 20+ process under Bubblewrap, with `PHIARK_DATA_DIR=/phios/app-data` and `PHIARK_SOCKET_PATH=/phios/app-data/.phiark.sock`. The server itself refuses stale sockets and non-private storage. A production supervisor must not bypass those safeguards by unlinking sockets or enabling host networking.

Before real execution, implement an independent trusted exact-source proof and reviewed toolchain; explicit one-shot operator authorization bound to installed-tree, runtime-plan and approved source evidence; process ownership; `SO_PEERCRED` / filesystem socket identity qualification; OS-level network isolation tests; bounded termination and restart receipts; and disconnected cold-start acceptance. The actual browser gateway must only connect to the authorized service identity.

**No test in this rung proves a real process was supervised or stopped.** Issue [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321) remains open.

Related: [R0.9 command preview](PHIOS_PHIARK_R09_SERVICE_PREVIEW.md), [R1.0 package lineage](PHIOS_PHIARK_R10_SOURCE_LINEAGE.md), [R1.1 ZIP evidence](PHIOS_PHIARK_R11_ARCHIVE_CHAIN.md).
