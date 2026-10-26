# PhiOS R1.5: running executable SHA-256 and network-namespace observation

**Status: EXECUTABLE_HASH_MATCHES_CALLER_INPUT_UNQUALIFIED. This is not permission to launch, operate, expose or trust PhiARK.**

R1.4 measured the Linux `SO_PEERCRED` PID and UID from an operator-requested, no-application-payload AF_UNIX connection. Those credentials are stronger evidence that a specific Linux process was at the other end of a local socket, but do **not** establish which executable is running, the executable's provenance or the isolation of that process.

R1.5 adds the **read-only** `inspect_phiark_process_executable` API to compare a running process against a supplied expected SHA-256 and observe its Linux network namespace:

- Revalidate the canonical, unsigned R1.4 peer report and its expected PID, UID, Linux boot ID and process start ticks.
- Check that the same process is still alive and matches the earlier peer observation.
- Open the kernel-managed `/proc/<pid>/exe` descriptor, SHA-256-hash bounded executable bytes (at most 128 MiB), and compare to the caller-supplied digest. The file descriptor is closed. Reject missing, oversized, inconsistent or changed executable evidence.
- Observe `/proc/<pid>/ns/net` and `/proc/self/ns/net` identity before/after hashing. Detect a changed identity during observation, and record whether the process is in the **same** namespace as the observer or a **different** one.

**A different namespace alone cannot prove network denial.** Network interfaces, routing, namespace configuration, external connectivity and firewall policy are not tested; even a genuinely different namespace could still have connectivity. A same-namespace result is useful negative evidence of network namespace separation, not a complete isolation assessment.

**A caller-provided digest is not a trust anchor.** This API checks bytes against that input, but does not independently obtain a signed upstream toolchain manifest or authenticate the declared executable to a GitHub release. The earlier R1.4 report is unsigned and may be stale or fabricated. The API explicitly reports `peer_receipt_is_signed_or_fresh=false`, `executable_pin_independently_authenticated=false`, `source_authenticated_against_github=false`, `network_access_denial_verified=false`, `service_supervision_verified=false`, `launch_authority=false`, and `gateway_authority=false`.

The inspector does **not** connect to a socket or make any network calls itself, send signals, start/stop/restart services, unlink stale sockets, grant permissions, install software or deploy an image. Unit tests on a live Linux CI process intentionally use a **Python** executable, not PhiARK. A passing test proves the inspection mechanism, not operational readiness for PhiARK.

## Next checks before a production supervisor

An independently trusted source/release key and binary digest; bounded reviewer-authorized start permission; an actual supervised service with pinned process identity, executable and Bubblewrap constraints; a connected peer lease; explicit operator-controlled shutdown; real network-denial tests; disconnected cold start and recoverable audit trail. See [PhiOS #321](https://github.com/MichaelWave369/PhiOS/issues/321), still open.

Related: [R1.3 Linux host observation](PHIOS_PHIARK_R13_LINUX_OBSERVATION.md) and [R1.4 peer credential diagnostic](PHIOS_PHIARK_R14_PEER_CREDENTIALS.md).
