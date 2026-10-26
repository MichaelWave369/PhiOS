# PhiOS R1.6: PhiARK source/install/peer/executable evidence coherence

**Status: `HELD_FOR_INDEPENDENT_TRUST_AND_LAUNCH_PROOF`. No launch authority can be produced by this module.**

The existing PhiARK rungs protect different boundaries:
- R1.0: claimed Git commit matches the *currently observed* installed package-plan and tree.
- R1.1: supplied source ZIP bytes match local acquisition, offline build and installed-package receipts.
- R1.4: an operator-requested active AF_UNIX diagnostic obtains `SO_PEERCRED` and ties a **historical** peer PID/UID to a process/socket snapshot. This connection is itself an observable local side effect.
- R1.5: the same **historical** process PID/start/boot/UID was inspected and its executable matched a **caller-supplied** SHA-256. The Linux network namespace relation was observed but **not** qualified for network denial.

R1.6 adds a **pure, offline coherence join** in `phios.apps.phiark_evidence_coherence.review_phiark_evidence_coherence`. It takes those four existing report dictionaries and performs **no filesystem, process or network operations**.

## Checked linkages

- All four reports have their exact known schema, stage-specific status and fields. Each internal hash is recomputed over its canonical JSON; unknown, missing, oversized or tampered fields fail closed.
- Repository and exact 40-character commit claim agree across the R1.0 and R1.1 reports.
- R1.1's installed-lineage review hash matches the R1.0 receipt itself, and both report the same installed-tree SHA-256.
- The source, archive, package and preview digests have the right length, and original local proof flags must be true.
- The R1.5 executable receipt explicitly names the same R1.4 peer-receipt hash, PID, UID, Linux boot UUID and process-start ticks.
- The historical binary SHA-256 matches the one previously supplied and the reported network-namespace relation is internally consistent with the observed device/inode values.
- All fields claiming unsupported authority or independent attestation are **required to be `false`**, even when a malicious actor recomputes the report's SHA-256. No receipt may silently promote a locally consistent claim into a signed or trusted fact.

## What this does NOT prove

**Important temporal discontinuity:** the source/installed-tree checks run while PhiARK's service socket is **absent**. The peer/binary observations run **later**, after an external actor has created a service/socket. There is no signed session nonce, supervisor-owned child handle, protected monotonic evidence log or one-shot launch authorization connecting those two moments. Thus a coherent R1.0/R1.1/R1.4/R1.5 bundle **does not** prove it is the same installed service, nor that it remains running now.

An attacker may fabricate a fully self-consistent unsigned bundle by computing all hashes. Such a bundle passes a **coherence diagnostic only**. No independent GitHub source authentication, trusted Node/Bubblewrap/prlimit pin, sandbox enforcement, disconnected cold-start test, or gateway approval is implied.

The returned review has:
- `status=HELD_FOR_INDEPENDENT_TRUST_AND_LAUNCH_PROOF`
- `local_cross_receipt_coherence=true` for valid inputs, **not authentication**
- `evidence_temporally_bound_to_approved_launch=false`
- `current_process_and_socket_rechecked=false`
- `source_commit_independently_authenticated=false`
- `toolchain_pin_independently_authenticated=false`
- `physical_network_denial_verified=false`
- `real_service_supervision_verified=false`
- `install_authority=false`, `launch_authority=false`, `gateway_authority=false`
- a clear `remaining_blockers` list and a canonical SHA-256 informational review hash.

The module does not inspect, launch, signal, delete, install, deploy, connect to, proxy, or modify any running service. The R0.7 browser gateway remains a **separate** operator opt-in.

## Next: a genuine process/session trust bridge

A later rung must implement externally trusted source/toolchain pins and a privileged, carefully scoped supervisor that actually starts the reviewed installed tree under verified Linux isolation. Its one-shot operator approval, child pidfd/start identity, socket-peer identity and termination receipts must be tied to a fresh, unforgeable session. Only then can an actual launch-readiness gate consider promotion. Keep [PhiOS issue #321](https://github.com/MichaelWave369/PhiOS/issues/321) open.

Related merged PRs: [#331](https://github.com/MichaelWave369/PhiOS/pull/331), [#333](https://github.com/MichaelWave369/PhiOS/pull/333), [#336](https://github.com/MichaelWave369/PhiOS/pull/336), [#337](https://github.com/MichaelWave369/PhiOS/pull/337).
