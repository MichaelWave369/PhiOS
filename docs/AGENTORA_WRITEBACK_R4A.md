# Agentora / PhiOS R4a: Shared Idempotency Contract

**Status: implementation candidate, no network transport.** The bridge is a
local Python adapter into PhiOS's existing governed canonical memory service.
It does **not** create an HTTP endpoint, enable governed memory, grant permissions,
or change Agentora's deployed writeback behavior.

## Operation identity

Protocol: `phios.agentora.writeback.v1`.

Both repos produce the same SHA-256 hex operation ID over:

```json
{"outcome":{"job_id":"job-123","status":"completed","summary":"Done"},"session_id":"session-1","task_id":"job-123"}
```

Compute SHA-256 over `b"phios.agentora.writeback.v1\\n"` followed by
UTF-8 JSON serialized with sorted keys, comma/colon separators, and no ASCII
escaping. For the fixture above:

`056f70f4e94787b3aa2f96e82fd93bd173f1b92582deaec4c2f12e698431ba06`

- Logical identity includes session, task and immutable outcome content.
- Operator notes and tags do not change the operation ID, so changing them
  on replay conflicts instead of recording the same outcome twice.
- The complete payload and normalized UTC `created_at_utc` form the
  canonical governed memory record text and are covered by PhiOS's existing
  transactional request hash. Different payload under the same operation ID
  is rejected.
- Client must provide a **stable** UTC record timestamp across retries.
- Keep the write as a provenance-marked `source` record, *not* an
  automatically authoritative agent instruction or a promoted decision.
- PhiOS's existing `MemoryStore.put_pending` uses a SQLite write reservation
  plus a unique operation ID to handle concurrent admission. Pending
  publication is never reported as a fully published memory record.

## Safety

`AgentoraWritebackAdmission` requires:
1. A PhiOS `MemoryRuntimeConfig` explicitly enabled by the operator.
2. `memory.write` grant for admission.
3. `memory.read` grant to query receipt status.
4. A valid bounded protocol payload and stable UTC timestamp.

The adapter does **not** listen on any port. Future loopback HTTP transport
must enforce separate authentication, request-size limits and read-only
operation status; it must not silently activate memory or fabricate
authority. The HTTP bridge is the next reviewed step, not part of R4a.

## Acceptance tests

The tests check fixed cross-repository SHA vectors, replay after a fresh
runtime instance, payload mismatch rejection, changed outcome receiving a
new ID, disabled/unauthorized operations, and malformed or oversized input.
Database counts prove a duplicate replay creates only one canonical record
and one receipt.

No existing memory data or schema is migrated or deleted.
