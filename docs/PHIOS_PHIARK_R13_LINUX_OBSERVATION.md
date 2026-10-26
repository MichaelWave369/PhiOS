# PhiOS R1.3: read-only Linux process/socket identity evidence

**Status: HOST_OBSERVED_NOT_ATTESTED. Not a PhiARK supervisor, installer, launcher, authentication grant or readiness certificate.**

PhiOS R1.2 defined a **simulated** deterministic lifecycle protocol. R1.3 adds a small, read-only Linux host observer in `phios.apps.phiark_linux_observation` that inspects current kernel process and Unix-socket metadata without launching or changing anything.

## What it checks

- A specific positive PID's `/proc/<pid>/stat` start time (field 22) and process state, `/proc/<pid>/status` UID row, and the Linux boot UUID. A recorded PID alone is reusable; the tuple `(boot_id, pid, start_ticks, uid)` is a stronger *observation identifier*.
- The separate PhiARK private vault directory is still operator-owned and inaccessible to group/other users under the R0.9 checks.
- If present, `<data-root>/.phiark.sock` must be a real Unix socket, not a symlink, directory, regular file or untrusted device; its owner and restrictive permissions are observed, together with filesystem device/inode and the vault's identity.
- Two observations can be compared for unchanged PID-start and socket-inode identity. A changed process, zombie state, lost socket, wrong permissions, stale regular file, or replaced socket fails closed. Process metadata can race, so this is only a best-effort read-only snapshot.

**Neither an observed PID nor a Unix socket on disk proves that PID owns the socket.** The tests deliberately use the Python CI test process to establish that physical kernel inspection works; the result never describes it as PhiARK. There are no `connect()` calls or `SO_PEERCRED` operations; ownership, executable lineage, namespace controls, and authenticated browser-gateway binding remain unresolved.

## Authority and security limits

Both reports explicitly keep `process_socket_peer_authenticated=false`, `phiark_executable_authenticated=false`, `linux_network_namespace_verified=false`, `service_supervision_verified=false`, `launch_authority=false` and `gateway_authority=false`. The comparator's stronger stability result is only `STABLE_HOST_IDENTITIES_UNQUALIFIED`. SHA-256 report digests are not signatures, remote attestations or privileged tokens.

No new CLI starts services, no socket is removed or modified, no processes are sent signals, no installation takes place, and no OS image is deployed.

## Remaining requirements

The real supervisor needs independently trusted source and dependency provenance; verifiable and operator-approved process creation; an OS-run child identity lease with effective sandbox evidence; authenticated Unix-socket peer identity; explicit start/stop and bounded termination; stale socket manual recovery; fail-closed restart; LAN/WAN-negative tests; disconnected cold-start evidence.

The broader integration issue [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321) remains OPEN.
