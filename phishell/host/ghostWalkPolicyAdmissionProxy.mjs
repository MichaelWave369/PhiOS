import { ghostWalkSidecarPort, GHOSTWALK_HOST } from "./ghostWalkControlProxy.mjs";

const SHA256 = /^[0-9a-f]{64}$/;
const INTENT_CODE = /^[A-Z][A-Z0-9_]{2,127}$/;
const DECISIONS = new Set(["ALLOW_REQUEST", "HOLD", "DENY"]);
const REASONS = new Set([
  "INTENT_EXPLICITLY_ALLOWED",
  "INTENT_EXPLICITLY_DENIED",
  "INTENT_UNMAPPED",
  "ACCEPTED_INTENT_REVOKED",
  "OPERATOR_NOTE_RETRACTED",
  "STALE_OPERATOR_BINDING",
]);

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value) {
  return typeof value === "string" && SHA256.test(value);
}

function timestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function boundedString(value, maximum = 512) {
  return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function canonicalCodes(value) {
  if (
    !Array.isArray(value) ||
    value.length > 256 ||
    !value.every((item) => typeof item === "string" && INTENT_CODE.test(item))
  ) {
    return false;
  }
  const canonical = [...new Set(value)].sort();
  return canonical.length === value.length &&
    canonical.every((item, index) => item === value[index]);
}

function zeroSnakeAuthority(value) {
  return (
    record(value) &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false
  );
}

function zeroTransportAuthority(value) {
  return (
    record(value) &&
    value.policyAuthority === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false
  );
}

export function validateGhostWalkPolicyProfile(value) {
  return (
    zeroSnakeAuthority(value) &&
    value.schema_version === "phios.ghostwalk_policy_profile.v0.30" &&
    boundedString(value.profile_id) &&
    canonicalCodes(value.allow_request_intent_codes) &&
    canonicalCodes(value.deny_intent_codes) &&
    value.default_decision === "HOLD" &&
    sha(value.profile_sha256) &&
    !value.allow_request_intent_codes.some((code) =>
      value.deny_intent_codes.includes(code)
    )
  );
}

export function validateGhostWalkPolicyAdmissionProjection(value) {
  if (!zeroSnakeAuthority(value)) return false;
  if (
    value.schema_version !== "phios.ghostwalk_policy_admission_projection.v0.30" ||
    !sha(value.target_inference_receipt_sha256) ||
    !sha(value.accepted_intent_revision_sha256) ||
    !sha(value.source_operator_note_revision_sha256) ||
    !sha(value.current_operator_note_revision_sha256) ||
    !sha(value.policy_profile_sha256) ||
    !boundedString(value.intent_family, 64) ||
    typeof value.intent_code !== "string" ||
    !INTENT_CODE.test(value.intent_code) ||
    !["ACTIVE", "REVOKED"].includes(value.accepted_intent_status) ||
    typeof value.operator_binding_current !== "boolean" ||
    !DECISIONS.has(value.decision) ||
    !REASONS.has(value.reason) ||
    typeof value.request_authority_eligible !== "boolean" ||
    value.effect_performed !== false ||
    !sha(value.projection_sha256)
  ) {
    return false;
  }
  return value.request_authority_eligible === (value.decision === "ALLOW_REQUEST");
}

export function validateGhostWalkPolicyAdmissionReceipt(value) {
  if (!zeroSnakeAuthority(value)) return false;
  if (
    value.schema_version !== "phios.ghostwalk_policy_admission_receipt.v0.30" ||
    !sha(value.projection_sha256) ||
    !sha(value.target_inference_receipt_sha256) ||
    !sha(value.accepted_intent_revision_sha256) ||
    !sha(value.policy_profile_sha256) ||
    !DECISIONS.has(value.decision) ||
    !REASONS.has(value.reason) ||
    typeof value.request_authority_eligible !== "boolean" ||
    !timestamp(value.evaluated_at) ||
    value.effect_performed !== true ||
    value.desktop_effect_performed !== false ||
    value.authority_request_created !== false ||
    value.action_lease_created !== false ||
    !sha(value.admission_receipt_sha256)
  ) {
    return false;
  }
  return value.request_authority_eligible === (value.decision === "ALLOW_REQUEST");
}

function validBase(value, recorded) {
  return (
    zeroTransportAuthority(value) &&
    value.transportSchemaVersion === "phios.ghostwalk-policy-admission-transport.v0.30" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-policy-admission" &&
    value.localOnly === true &&
    value.admissionRecorded === recorded &&
    value.desktopEffectPerformed === false &&
    value.authorityRequestCreated === false &&
    value.actionLeaseCreated === false &&
    value.effectPerformed === recorded &&
    timestamp(value.servedAt)
  );
}

export function validateGhostWalkPolicyProjectionEnvelope(value) {
  return (
    validBase(value, false) &&
    validateGhostWalkPolicyProfile(value.profile) &&
    validateGhostWalkPolicyAdmissionProjection(value.projection) &&
    value.profile.profile_sha256 === value.projection.policy_profile_sha256
  );
}

export function validateGhostWalkPolicyReceiptEnvelope(value) {
  return (
    validBase(value, true) &&
    validateGhostWalkPolicyProfile(value.profile) &&
    validateGhostWalkPolicyAdmissionReceipt(value.receipt) &&
    value.profile.profile_sha256 === value.receipt.policy_profile_sha256
  );
}

export function validateGhostWalkPolicyRecordPayload(value) {
  if (!record(value)) return false;
  const keys = Object.keys(value).sort();
  const expected = [
    "expected_accepted_intent_revision_sha256",
    "expected_policy_profile_sha256",
    "target_inference_receipt_sha256",
  ];
  return (
    keys.length === expected.length &&
    keys.every((key, index) => key === expected[index]) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.expected_accepted_intent_revision_sha256) &&
    sha(value.expected_policy_profile_sha256)
  );
}

async function request(url, init, fetcher, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetcher(url, { ...init, signal: controller.signal });
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchGhostWalkPolicyAdmission(targetSha256, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 1500,
} = {}) {
  if (!sha(targetSha256)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/policy-admission?target=${targetSha256}`,
    {
      method: "GET",
      cache: "no-store",
      headers: { accept: "application/json" },
    },
    fetcher,
    timeoutMs,
  );
  if (!response) return null;
  if (response.status === 404) return { kind: "not_ready" };
  if (!response.ok) return null;
  try {
    const payload = await response.json();
    return validateGhostWalkPolicyProjectionEnvelope(payload)
      ? { kind: "found", envelope: payload }
      : null;
  } catch {
    return null;
  }
}

export async function recordGhostWalkPolicyAdmission(payload, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 2500,
} = {}) {
  if (!validateGhostWalkPolicyRecordPayload(payload)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/policy-admission/evaluations`,
    {
      method: "POST",
      cache: "no-store",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    fetcher,
    timeoutMs,
  );
  if (!response) return null;
  if (response.status === 409) return { kind: "conflict" };
  if (!response.ok) return null;
  try {
    const result = await response.json();
    return validateGhostWalkPolicyReceiptEnvelope(result)
      ? { kind: "recorded", envelope: result }
      : null;
  } catch {
    return null;
  }
}
