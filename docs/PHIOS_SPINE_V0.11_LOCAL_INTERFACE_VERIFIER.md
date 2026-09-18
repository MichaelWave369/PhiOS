# PhiOS Spine v0.11 - Local Interface World Verifier

Spine v0.11 adds the first independent world-state verifier to the Reality Gate.

The verifier observes one exact local network-interface name through the host operating system using `psutil.net_if_stats()`.

## Why this matters

v0.10 could verify:

```text
"The cited evidence contains Ethernet DOWN."
```

It deliberately could not verify:

```text
"The local Ethernet interface is actually down."
```

v0.11 can evaluate the second claim when it is scoped specifically to a local interface and the operator grants direct host-state observation.

## New claim kind

`local_interface_state`

Required claim fields:

- interface_name
- expected_is_up

The verifier asks the provider for that exact interface only.

PhiOS does not expose a broad interface-enumeration command in v0.11.

## Authority

Two grants are required:

`reality.verify`

and:

`reality.local_interface.read`

The first allows Reality Gate evaluation.

The second allows direct observation of local network-interface state.

Verification authority does not imply host-state access.

## Direct observation evidence

A successful interface observation is serialized as deterministic JSON and stored in the content-addressed evidence store.

The evidence includes:

- exact interface name
- is_up state
- duplex value
- speed in Mbps
- MTU
- provider name
- provider version
- capture timestamp

The RealityReceipt links that observation evidence through `evidence_used`.

## Verdicts

If the direct observation matches the expected state:

`SUPPORTED`

If it conflicts:

`CONTRADICTED`

If the interface does not exist or the provider cannot observe it:

`UNRESOLVED`

Missing permission or an invalid claim contract:

`BLOCKED`

## Point-in-time semantics

Interface state is ephemeral.

A supported result means the direct local observation matched the claim **at the recorded capture time**.

It does not claim the interface remained in that state before or after the observation.

## Generic world-state claims remain unresolved

The existing `world_state` claim type is intentionally unchanged.

A vague claim such as:

`The office uplink is healthy.`

still returns UNRESOLVED because v0.11 does not know which device, interface, path, or external system would establish that claim.

Specific verifiers earn authority one bounded observation class at a time.

## CLI

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_interface.read \
  verify-claim \
  --kind local_interface_state \
  --statement "Local interface Ethernet is up." \
  --interface-name Ethernet \
  --expected-state up
```

## Still excluded

v0.11 does not:

- scan the LAN
- probe arbitrary TCP ports
- ping remote hosts
- query switches
- use SNMP
- inspect router APIs
- infer upstream connectivity from local link state
- authorize actions
- promote memory automatically

Those require their own independent contracts.
