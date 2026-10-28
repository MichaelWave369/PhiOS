# PhiOS Sovereignty E0: process-level Linux seccomp experiment

**Status: isolated experimental demonstration, not integrated into PhiOS.**
This proof does not change the bootable system, runtime launcher, server, network
settings, or production security configuration.

## Origin and scope

The GypsyAI first-human-pilot review proposed a sovereignty manifest, voluntary
network-request APIs and eventually an OS-mediated deny-by-default boundary.
The core falsifiable hypothesis is that an uncooperative component can be
blocked by kernel controls even when it refuses to use an application API.

This self-contained C harness runs on Linux x86_64 with a C compiler. It
installs a real seccomp BPF filter in a forked child after setting
PR_SET_NO_NEW_PRIVS. The filter rejects selected network-related syscalls
with EACCES. It preserves a preopened Unix-domain socketpair created by a
trusted parent and exchanges a short proof message over that descriptor.

### Local commands

    cc -std=c11 -O2 -Wall -Wextra -Werror experiments/sovereignty_e0/e0_probe.c -o /tmp/phios_e0_probe
    /tmp/phios_e0_probe
    python -m pytest -q tests/test_sovereignty_e0_seccomp.py

No external network, root access, gateway service or package downloads are
needed to run the compiled binary. The pytest check compiles its own binary
and fails if the filter or IPC demonstration fails. On non-Linux-x86_64
platforms, pytest reports a skip, not a verified result.

### Acceptance

- The child must attempt AF_INET, AF_INET6 and AF_UNIX socket creation
  without invoking a voluntary PhiOS helper.
- All three attempts must return -1 / EACCES after installation of the
  process-scoped kernel filter.
- The child must send an observed-result record using write() over the
  previously opened Unix-domain connection. The parent must reply; the child
  must exit successfully.
- The parent prints a bounded PHIOS_SOVEREIGNTY_E0_V1 JSON receipt only for
  the observed test, and exits nonzero on a failure.

### Explicit limits

- This does not establish a complete or production-grade network sandbox.
  Inherited network descriptors, other Linux interfaces, alternate execution
  paths, subprocess containment, identity impersonation and OS-level rollout
  remain untested.
- A preopened Unix-domain socket is an IPC capability, not proof of a secure
  phios-gw service. The parent acknowledges a fixed proof message and makes
  zero remote requests. No actual gateway, manifest parsing, approval UI,
  peer authentication or destination filtering exists in this experiment.
- A runtime-generated compId is not itself a secure identity. A future broker
  needs operating-system-based peer identity, trusted process mappings,
  explicit authorization and strong revocation semantics.
- No independent packet capture is performed. The receipt sets the flags
  independent_packet_capture_performed, inherited_ip_fd_escape_tested and
  full_os_network_isolation_verified to false by design.
- This single Linux-process proof cannot be promoted to a claim that the
  PhiOS live ISO, public web edition or standalone server is network-secure.
  Browser-side choice=yes values are not authentication.
- Only the test binary's own process-scoped effect is demonstrated.
  Application and PhiKernel/TIEKAT authority boundaries remain unchanged.

### Later rungs, not implemented here

1. Restrict inherited descriptors and isolate launch paths in a verified
   non-root network namespace/container model.
2. Establish a protected broker with preconnected IPC, authenticated caller
   identity, fail-closed authorization and narrow destination capabilities.
3. Test actual external/IPv6 egress from a separate listener and capture
   point, subprocess and inherited-descriptor bypass attempts, positive
   approved traffic and revocation under load.
4. Require a distinct release gate to claim security for a specific PhiOS
   Linux image; separately scope public web controls.

The experimental receipt is neither a production EnforcementRule nor an
operator authority grant. PhiOS's public SOVEREIGNTY_CONTRACT.md remains
the source of truth for any future release claim.

**Ledger Above Ego.**
