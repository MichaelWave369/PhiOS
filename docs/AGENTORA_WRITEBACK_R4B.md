# Agentora to PhiOS memory writeback: R4b local transport

This is an opt-in authenticated HTTP adapter for the R4a governed memory
admission and durable receipt outbox. Nothing starts when the module is imported
or when PhiOS boots, installs, tests, or uses disabled default memory settings.

## Contract and security

POST /api/v1/agentora/writeback accepts one JSON object containing precisely
protocol_version, operation_id, created_at_utc, and payload. The protocol is
phios.agentora.writeback.v1. R4a verifies that the supplied SHA-256 operation
identity matches the actual session/task/outcome. HTTP 200 means the ledger
receipt is published; 202 means pending; 409 means that an operation identity
is already used for different canonical content.

GET /api/v1/agentora/writeback/{operation_id} returns durable receipt status,
never memory contents or raw mission outcomes. It uses 200 published, 202 pending
and 404 not found. Invalid requests and authority failures are refused.

Both routes require exactly one X-API-Key, verified through the existing
PhiOS ApiKeyBoundary. There are no logs of credentials, payloads, or operation IDs.
The listener binds 127.0.0.1 only. The network request body is limited to
48 KiB, and the underlying canonical memory envelope still has its independent
32 KiB cap. Duplicate JSON keys and non-finite JSON numbers are rejected.
No CORS, open network interface, or writeback automation is introduced.

## Explicit operator launch (not automatic service activation)

First configure governed-memory with enabled=true and appropriate operator
scope/classification, then supply a unique randomly generated secret of at
least 32 characters via PHIOS_AGENTORA_WRITEBACK_KEY. Do not commit it or pass
it as a command-line argument.

    phi-memory --config /path/to/memory-config.json \
      --state-root /path/to/memory-state \
      --allow memory.read --allow memory.write \
      serve-agentora-writeback --port 8090

The server does not grant memory permission by itself. The configured
principal must already be permitted by the governed memory access policy.
This endpoint is loopback-only, so a remote agent needs a separately
reviewed transport before it can connect.

## Not a live Agentora connection yet

Agentora's existing write_mission_result still uses legacy routes with
a different body and currently treats any JSON 2xx response as success.
R4b does NOT enable that caller or accept its legacy payload. An opt-in
Agentora R4c must persist the complete canonical envelope before transmission,
confirm published receipt/operation ID before reporting success, reconcile
uncertain deliveries via GET only, and retain R3 concurrency/reconciliation
holds. The separate Agentora integration remains disabled by default.

Review requirements: fast HTTP auth/replay/refusal tests, Python quality
checks, complete PhiOS CI and separate approval before any activation.
