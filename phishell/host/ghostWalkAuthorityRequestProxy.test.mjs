import test from "node:test";
import assert from "node:assert/strict";

import {
  createGhostWalkAuthorityRequest,
  fetchGhostWalkAuthorityRequestStatus,
  validateGhostWalkAuthorityRequestCreateEnvelope,
  validateGhostWalkAuthorityRequestCreatePayload,
  validateGhostWalkAuthorityRequestStatusEnvelope,
} from "./ghostWalkAuthorityRequestProxy.mjs";

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

test("status envelope remains zero authority", () => {
  assert.equal(
    validateGhostWalkAuthorityRequestStatusEnvelope({
      ...base,
      readiness,
      request: null,
    }),
    true,
  );
});

test("creation envelope records request without granting it", () => {
  assert.equal(
    validateGhostWalkAuthorityRequestCreateEnvelope({
      ...base,
      requestCreated: true,
      effectPerformed: true,
      request,
    }),
    true,
  );
});

test("browser payload cannot control requester or semantic scope", () => {
  const payload = {
    target_inference_receipt_sha256: "b".repeat(64),
    expected_admission_receipt_sha256: "a".repeat(64),
  };
  assert.equal(validateGhostWalkAuthorityRequestCreatePayload(payload), true);
  assert.equal(
    validateGhostWalkAuthorityRequestCreatePayload({
      ...payload,
      requester_id: "browser:fake",
    }),
    false,
  );
});

test("status distinguishes not-ready", async () => {
  const fetcher = async () => ({ status: 404, ok: false });
  assert.deepEqual(
    await fetchGhostWalkAuthorityRequestStatus("b".repeat(64), {
      fetcher,
      port: 3973,
    }),
    { kind: "not_ready" },
  );
});

test("create preserves conflict and validates success", async () => {
  const payload = {
    target_inference_receipt_sha256: "b".repeat(64),
    expected_admission_receipt_sha256: "a".repeat(64),
  };
  const conflictFetcher = async () => ({ status: 409, ok: false });
  assert.deepEqual(
    await createGhostWalkAuthorityRequest(payload, {
      fetcher: conflictFetcher,
      port: 3973,
    }),
    { kind: "conflict" },
  );

  const successFetcher = async () => ({
    status: 200,
    ok: true,
    async json() {
      return {
        ...base,
        requestCreated: true,
        effectPerformed: true,
        request,
      };
    },
  });
  const result = await createGhostWalkAuthorityRequest(payload, {
    fetcher: successFetcher,
    port: 3973,
  });
  assert.equal(result?.kind, "created");
});
