# PhiOS R1.4: explicit Linux AF_UNIX peer-credential diagnostic

**Status: LOCAL_PEER_CREDENTIALS_MATCH_UNQUALIFIED. This is neither app authentication nor service-launch approval.**

R1.3 provided read-only Linux process and socket identity snapshots. R1.4 provides a **separate, expressly opt-in active diagnostic connection** to an already-existing private Unix socket. It obtains Linux `SO_PEERCRED` on the connected file descriptor and checks that the kernel-reported peer PID/UID matches the operator's expected PID/UID, with R1.3 boot ID, PID start ticks and socket inode/device inspected before and after.

## Operation and trust boundary

Call `probe_phiark_socket_peer(expected_pid=<reviewed PID>, data_directory=<private vault>, operator_requested=True)` only when explicitly requesting a local connection to an already-running service. The default `operator_requested=False` refuses the operation. The probe does not launch a process, open TCP, send any HTTP or other application bytes, read documents, install an app, or enable a browser gateway.

**Unlike R1.3, this is not passive or entirely side-effect-free.** It creates one short-lived AF_UNIX stream connection. The listening service may accept and log that connection, or react to a client disconnect. The operation has a one-second timeout and always closes its local descriptor. It does not close the listener or unlink its socket.

Before connecting, it validates the Linux host, positive expected PID, non-zombie process, owner-only vault, owner-only socket, and actual socket type. It then checks kernel peer credentials and compares two host snapshots for stable boot/PID/start identity and socket inode/device. Invalid PID, wrong live PID, stale socket, overbroad permissions, changed PID start ticks, missing socket or refused connection block the result.

## Limitations that matter

- `SO_PEERCRED` describes peer credentials associated with the connected AF_UNIX endpoint. Matching those credentials to a PID does **not** prove that the process is PhiARK, that its executable matches GitHub, or that it was started through PhiOS. The test uses a Python process, and the result explicitly does not identify it as PhiARK.
- The socket listener may have been inherited, and the process may be replaced after a check. The two snapshots reduce but do not remove all races. No independent capability token, pidfd, live supervisor lease, kernel namespace attestation or lifecycle permission is conferred.
- The existing R0.7 browser gateway is **not automatically routed through this probe**. Its current permission model and manual operator review remain separate. In particular, a successful probe is never a gateway start token.
- Any newly created receipt is an unsigned, local informational SHA-256 report, not a trustworthy authorization artifact. It records `application_bytes_sent=0`, `listener_authenticated_as_phiark=false`, `source_authenticated_against_github=false`, `network_namespace_verified=false`, `process_supervision_verified=false`, and all launch/install/gateway authority flags `false`.

## Still required for a production supervisor

Independent exact-source attestation, trusted process creation linked to the pinned runtime and toolchain, an operator-reviewed one-shot launch decision, pidfd/process lease and socket peer validation across supervision, startup/shutdown timeouts, no automatic stale-socket cleanup, offline cold-start, and WAN/LAN-negative evidence. Keep [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321) open.

Related: [R1.3 read-only observations](PHIOS_PHIARK_R13_LINUX_OBSERVATION.md).
