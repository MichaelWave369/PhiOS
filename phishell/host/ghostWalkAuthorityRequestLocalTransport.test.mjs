import test from "node:test";
import assert from "node:assert/strict";

import { createLocalObservationServer } from "./localTransport.mjs";

const request = {
  schema_version: "phios.ghostwalk_authority_request.v0.31",
  admission_receipt_sha256: "a".repeat(64),
  target_inference_receipt_sha256: "b".repeat(64),
  accepted_intent_revision_sha256: "c".repeat(64),
  policy_profile_sha256: "d".repeat(64),
  intent_family: "OPEN",
  intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
  requester_id: "operator:local",
  requested_authority_kind: "ACTION_AUTHORITY",
  requested_scope_kind: "ACCEPTED_INTENT",
  requested_scope_value: "OPEN_NETWORK_ADAPTER_PROPERTIES",
  request_state: "PENDING_AUTHORIZATION",
  requested_at: "2026-09-27T07:30:00.000Z",
  authorization_granted: false,
  action_lease_created: false,
  effect_performed: false,
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  authority_request_sha256: "e".repeat(64),
};
const readiness = {
  schema_version: "phios.ghostwalk_authority_request_readiness.v0.31",
  target_inference_receipt_sha256: "b".repeat(64),
  accepted_intent_revision_sha256: "c".repeat(64),
  policy_profile_sha256: "d".repeat(64),
  policy_decision: "ALLOW_REQUEST",
  ready: true,
  reason: "READY",
  admission_receipt_sha256: "a".repeat(64),
  existing_authority_request_sha256: null,
  authorization_granted: false,
  action_lease_created: false,
  effect_performed: false,
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  readiness_sha256: "f".repeat(64),
};
const base = {
  transportSchemaVersion: "phios.ghostwalk-authority-request-transport.v0.31",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-authority-request",
  localOnly: true,
  requestCreated: false,
  desktopEffectPerformed: false,
  authorizationGranted: false,
  actionLeaseCreated: false,
  policyAuthority: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T07:30:00.000Z",
};

test("local transport proxies AuthorityRequest readiness", async () => {
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAuthorityRequestFetcher: async () => ({
      kind: "found",
      envelope: { ...base, readiness, request: null },
    }),
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/authority-request?target=${"b".repeat(64)}`,
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.readiness.ready, true);
    assert.equal(payload.authorizationGranted, false);
  } finally {
    await transport.close();
  }
});

test("local transport creates request without granting authority", async () => {
  const seen = [];
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAuthorityRequestCreator: async (payload) => {
      seen.push(payload);
      return {
        kind: "created",
        envelope: {
          ...base,
          requestCreated: true,
          effectPerformed: true,
          request,
        },
      };
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/authority-request/requests`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_inference_receipt_sha256: "b".repeat(64),
          expected_admission_receipt_sha256: "a".repeat(64),
        }),
      },
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.request.request_state, "PENDING_AUTHORIZATION");
    assert.equal(payload.authorizationGranted, false);
    assert.equal(payload.actionLeaseCreated, false);
    assert.equal(seen.length, 1);
  } finally {
    await transport.close();
  }
});
