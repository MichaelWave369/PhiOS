import test from "node:test";
import assert from "node:assert/strict";

import {
  fetchGhostWalkPolicyAdmission,
  recordGhostWalkPolicyAdmission,
  validateGhostWalkPolicyProjectionEnvelope,
  validateGhostWalkPolicyRecordPayload,
  validateGhostWalkPolicyReceiptEnvelope,
} from "./ghostWalkPolicyAdmissionProxy.mjs";

const profile = {
  schema_version: "phios.ghostwalk_policy_profile.v0.30",
  profile_id: "ghostwalk-policy:test",
  allow_request_intent_codes: ["OPEN_NETWORK_ADAPTER_PROPERTIES"],
  deny_intent_codes: [],
  default_decision: "HOLD",
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  profile_sha256: "a".repeat(64),
};

const projection = {
  schema_version: "phios.ghostwalk_policy_admission_projection.v0.30",
  target_inference_receipt_sha256: "b".repeat(64),
  accepted_intent_revision_sha256: "c".repeat(64),
  source_operator_note_revision_sha256: "d".repeat(64),
  current_operator_note_revision_sha256: "d".repeat(64),
  policy_profile_sha256: "a".repeat(64),
  intent_family: "OPEN",
  intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
  accepted_intent_status: "ACTIVE",
  operator_binding_current: true,
  decision: "ALLOW_REQUEST",
  reason: "INTENT_EXPLICITLY_ALLOWED",
  request_authority_eligible: true,
  effect_performed: false,
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  projection_sha256: "e".repeat(64),
};

const base = {
  transportSchemaVersion: "phios.ghostwalk-policy-admission-transport.v0.30",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-policy-admission",
  localOnly: true,
  admissionRecorded: false,
  desktopEffectPerformed: false,
  authorityRequestCreated: false,
  actionLeaseCreated: false,
  policyAuthority: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T07:15:00.000Z",
};

const projectionEnvelope = { ...base, profile, projection };
const receipt = {
  schema_version: "phios.ghostwalk_policy_admission_receipt.v0.30",
  projection_sha256: "e".repeat(64),
  target_inference_receipt_sha256: "b".repeat(64),
  accepted_intent_revision_sha256: "c".repeat(64),
  policy_profile_sha256: "a".repeat(64),
  decision: "ALLOW_REQUEST",
  reason: "INTENT_EXPLICITLY_ALLOWED",
  request_authority_eligible: true,
  evaluated_at: "2026-09-27T07:15:00.000Z",
  effect_performed: true,
  desktop_effect_performed: false,
  authority_request_created: false,
  action_lease_created: false,
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  admission_receipt_sha256: "f".repeat(64),
};
const receiptEnvelope = {
  ...base,
  admissionRecorded: true,
  effectPerformed: true,
  profile,
  receipt,
};

test("validates policy projection as zero authority", () => {
  assert.equal(validateGhostWalkPolicyProjectionEnvelope(projectionEnvelope), true);
  assert.equal(
    validateGhostWalkPolicyProjectionEnvelope({
      ...projectionEnvelope,
      actionLeaseCreated: true,
    }),
    false,
  );
});

test("validates recorded admission without authority request", () => {
  assert.equal(validateGhostWalkPolicyReceiptEnvelope(receiptEnvelope), true);
  assert.equal(
    validateGhostWalkPolicyReceiptEnvelope({
      ...receiptEnvelope,
      authorityRequestCreated: true,
    }),
    false,
  );
});

test("record payload is exact and authority-free", () => {
  const payload = {
    target_inference_receipt_sha256: "b".repeat(64),
    expected_accepted_intent_revision_sha256: "c".repeat(64),
    expected_policy_profile_sha256: "a".repeat(64),
  };
  assert.equal(validateGhostWalkPolicyRecordPayload(payload), true);
  assert.equal(
    validateGhostWalkPolicyRecordPayload({
      ...payload,
      actionAuthority: true,
    }),
    false,
  );
});

test("fetch distinguishes not-ready from invalid transport", async () => {
  const fetcher = async () => ({ status: 404, ok: false });
  assert.deepEqual(
    await fetchGhostWalkPolicyAdmission("b".repeat(64), {
      fetcher,
      port: 3973,
    }),
    { kind: "not_ready" },
  );
});

test("record preserves conflict and validates success", async () => {
  const conflictFetcher = async () => ({ status: 409, ok: false });
  assert.deepEqual(
    await recordGhostWalkPolicyAdmission(
      {
        target_inference_receipt_sha256: "b".repeat(64),
        expected_accepted_intent_revision_sha256: "c".repeat(64),
        expected_policy_profile_sha256: "a".repeat(64),
      },
      { fetcher: conflictFetcher, port: 3973 },
    ),
    { kind: "conflict" },
  );

  const successFetcher = async () => ({
    status: 200,
    ok: true,
    async json() {
      return receiptEnvelope;
    },
  });
  const result = await recordGhostWalkPolicyAdmission(
    {
      target_inference_receipt_sha256: "b".repeat(64),
      expected_accepted_intent_revision_sha256: "c".repeat(64),
      expected_policy_profile_sha256: "a".repeat(64),
    },
    { fetcher: successFetcher, port: 3973 },
  );
  assert.equal(result?.kind, "recorded");
});
