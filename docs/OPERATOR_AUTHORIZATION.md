# Operator authorization boundary

The PhiShell and GhostWalk HTTP surfaces expose observation and proposal
interfaces. POSTs to authorization-console `decisions`, `bindings`, and `leases`
return **403 operator_channel_required**, before parsing or calling a service.
A loopback address, a browser origin, or a PhiVessel session does not identify
an operator. Other HTTP writes require the exact loopback Host, JSON content
type, and a matching Origin when present; cross-site fetches are rejected.
These checks reduce browser request forgery; they do not authenticate agents.

Install the Python package to obtain `phi-operator`, or run
`python -m phios.ghostwalk_operator` from the source checkout. Use the same
protected state root and policy environment as the host:

```sh
phi-operator --state-root ~/.phios --target <inference-sha256> inspect
phi-operator --state-root ~/.phios --target <inference-sha256> decide APPROVE
phi-operator --state-root ~/.phios --target <inference-sha256> decide HOLD
phi-operator --state-root ~/.phios --target <inference-sha256> decide DENY
phi-operator --state-root ~/.phios --target <inference-sha256> bind
phi-operator --state-root ~/.phios --target <inference-sha256> lease
```

Each mutation displays the current normalized evidence as escaped JSON and
requires typing the action and full snapshot digest. There is no `--yes` or
unattended option. Cancellation does not mutate authority. Changed evidence
requires a new review, and the existing services still check their exact
request, previous decision, mapping, policy, enforcement and epoch hashes.
Approval does not create a binding or lease. The command never executes an
effect or mounts an executor. Refresh PhiShell after terminal operations.

Without a valid trusted execution manifest, only inspection and decisions
are available. Binding and lease issuance currently require the supported
Windows desktop host. Linux previews must report this capability unavailable.
The CLI requires its manifest inside the protected state root, rejects
symlinked state, and on POSIX rejects state owned by another user or writable
by group/others. It does not silently repair existing permissions.

## Trust and remaining release gates

A TTY is an explicit interaction requirement, **not proof of human identity**.
A malicious process sharing the operator's OS account can create a pseudo-TTY,
import Python services, or edit that account's files. Run untrusted agents as
separate OS principals without access to operator state, terminal or desktop.
On Windows, protect the state with an owner-only ACL; this CLI does not attest
Windows ACLs. The Linux OS release remains held until principal separation,
broker authentication, concurrent writer safety and durable state recovery
have independent evidence. Do not describe this patch as universal human
authentication or whole-OS sandboxing.
