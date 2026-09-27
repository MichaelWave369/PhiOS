import test from "node:test";
import assert from "node:assert/strict";

import { createLocalObservationServer } from "./localTransport.mjs";

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
const readEnvelope = { ...base, profile, projection };
const receiptEnvelope = {
  ...base,
  admissionRecorded: true,
  effectPerformed: true,
  profile,
  receipt: {
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
  },
};

test("local transport proxies zero-authority policy projection", async () => {
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkPolicyAdmissionFetcher: async () => ({
      kind: "found",
      envelope: readEnvelope,
    }),
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/policy-admission?target=${"b".repeat(64)}`,
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.projection.decision, "ALLOW_REQUEST");
    assert.equal(payload.actionLeaseCreated, false);
  } finally {
    await transport.close();
  }
});

test("local transport records admission without authority request", async () => {
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkPolicyAdmissionRecorder: async () => ({
      kind: "recorded",
      envelope: receiptEnvelope,
    }),
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/policy-admission/evaluations`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_inference_receipt_sha256: "b".repeat(64),
          expected_accepted_intent_revision_sha256: "c".repeat(64),
          expected_policy_profile_sha256: "a".repeat(64),
        }),
      },
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.effectPerformed, true);
    assert.equal(payload.authorityRequestCreated, false);
    assert.equal(payload.actionLeaseCreated, false);
  } finally {
    await transport.close();
  }
});
