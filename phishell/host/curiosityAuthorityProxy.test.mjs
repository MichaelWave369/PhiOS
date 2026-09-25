import test from "node:test";
import assert from "node:assert/strict";
import {
  createPersistRequest,
  fetchBrokerHealth,
  fetchPersistRequest,
  validateBrokerHealth,
  validatePersistRequest,
} from "./curiosityAuthorityProxy.mjs";

const now = new Date().toISOString();
function health() {
  return {
    schemaVersion: "phios.curiosity-authority-broker.v0.5",
    brokerId: "phios.curiosity-authority-broker.local.v0.5",
    localOnly: true,
    principalId: "operator:local",
    capabilityId: "curiosity.persist",
    permission: "curiosity.write",
    approvalMode: "local_cli_hmac_exact_payload",
    browserCanApprove: false,
    browserReceivesLease: false,
    status: "ready",
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
  };
}
function requestRow(status = "pending") {
  return {
    schemaVersion: "phios.curiosity-persist-request.v0.5",
    requestId: "curiosity-request-" + "a".repeat(32),
    payload: {
      schema_version: "phios.curiosity_persist_payload.v0.4",
      artifact_kind: "symbol",
      title: "Gear",
      content: "Explore.",
      created_at: now,
      created_by: "operator:local",
      tags: ["gear"],
      evidence_ref_sha256s: [],
      parent_artifact_sha256s: [],
    },
    payloadSha256: "b".repeat(64),
    requestedAt: now,
    expiresAt: now,
    status,
    reason: status === "pending" ? "awaiting_operator_approval" : "curiosity_persisted",
    approvedAt: null,
    artifactSha256: status === "succeeded" ? "c".repeat(64) : null,
    executionReceipt: null,
    approvalCommand: "python -m phios.curiosity_authority_broker approve curiosity-request-" + "a".repeat(32),
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: status === "succeeded",
  };
}

test("validates broker that cannot approve from browser", async () => {
  assert.equal(validateBrokerHealth(health()), true);
  const result = await fetchBrokerHealth({
    fetcher: async () => new Response(JSON.stringify(health()), { status: 200 }),
    port: 3972,
  });
  assert.equal(result?.browserCanApprove, false);
});

test("rejects broker claiming browser approval", () => {
  const value = health();
  value.browserCanApprove = true;
  assert.equal(validateBrokerHealth(value), false);
});

test("creates and reads only zero-authority persistence requests", async () => {
  const row = requestRow();
  assert.equal(validatePersistRequest(row), true);
  const created = await createPersistRequest(
    {
      artifact_kind: "symbol",
      title: "Gear",
      content: "Explore.",
      created_at: now,
      tags: ["gear"],
      evidence_ref_sha256s: [],
      parent_artifact_sha256s: [],
    },
    {
      port: 3972,
      fetcher: async (_url, init) => {
        assert.equal(init.method, "POST");
        return new Response(JSON.stringify(row), { status: 201 });
      },
    },
  );
  assert.equal(created?.status, "pending");

  const read = await fetchPersistRequest(row.requestId, {
    port: 3972,
    fetcher: async () => new Response(JSON.stringify(row), { status: 200 }),
  });
  assert.equal(read?.requestId, row.requestId);
});

test("never accepts authority-bearing request state", () => {
  const row = requestRow();
  row.actionAuthority = true;
  assert.equal(validatePersistRequest(row), false);
});
