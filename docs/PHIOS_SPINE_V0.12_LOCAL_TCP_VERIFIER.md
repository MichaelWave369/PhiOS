# PhiOS Spine v0.12 - Local TCP Listener World Verifier

Spine v0.12 adds the second direct host-state verifier to the Reality Gate.

It answers one bounded question:

```text
Is this machine currently listening on this local TCP port?
```

It does not send a packet.

## New claim kind

`local_tcp_listener_state`

Required fields:

- local_port
- expected_listening

Optional:

- local_address

Ports must be between 1 and 65535.

If a local address is provided, only an exact match is eligible.

## Authority

Two grants are required:

`reality.verify`

and:

`reality.local_socket.read`

Reality verification does not imply permission to inspect local socket state.

## Observation method

The default provider uses:

`psutil.net_connections(kind="tcp")`

It filters for LISTEN state, then for the exact requested local port and optional exact local address.

It does not:

- connect to the port
- send packets
- probe remote systems
- scan port ranges
- expose process IDs
- identify owning processes

## Observation evidence

The point-in-time observation is written as content-addressed JSON containing:

- requested local port
- optional local address filter
- whether a matching listener was observed
- matching local addresses
- provider
- provider version
- capture timestamp

The RealityReceipt includes the observation evidence reference.

## Verdicts

Observed listener state matches the expected state:

`SUPPORTED`

Observed listener state conflicts:

`CONTRADICTED`

Socket inspection unavailable:

`UNRESOLVED`

Missing permissions or invalid claim:

`BLOCKED`

A successful enumeration with no matching listener is a direct negative observation for that exact bounded query and can therefore support an `expected_listening = false` claim.

## Important limits

A local LISTEN socket does not prove:

- the application is healthy
- the application will respond correctly
- a firewall permits remote access
- another machine can reach it
- the service speaks the expected protocol
- upstream networking works

Those are separate claims requiring separate evidence.

## CLI

Any-address listener check:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_socket.read \
  verify-claim \
  --kind local_tcp_listener_state \
  --statement "Local TCP port 8000 is listening." \
  --local-port 8000 \
  --expected-listening yes
```

Exact-address listener check:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_socket.read \
  verify-claim \
  --kind local_tcp_listener_state \
  --statement "Ollama is bound on local TCP 127.0.0.1:11434." \
  --local-port 11434 \
  --local-address 127.0.0.1 \
  --expected-listening yes
```

## Still excluded

v0.12 does not add active TCP connection attempts, HTTP health checks, LAN scans, remote port probing, SNMP, router queries, switch queries, or process inspection.
