import { ghostWalkSidecarPort, GHOSTWALK_HOST } from "./ghostWalkControlProxy.mjs";

const SHA256 = /^[0-9a-f]{64}$/;
const INTENT_CODE = /^[A-Z][A-Z0-9_]{2,127}$/;

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

function nullableSha(value) {
  return value === null || sha(value);
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

export function validateGhostWalkAuthorityRequest(value) {
  return (
    zeroSnakeAuthority(value) &&
    value.schema_version === "phios.ghostwalk_authority_request.v0.31" &&
    sha(value.admission_receipt_sha256) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.accepted_intent_revision_sha256) &&
    sha(value.policy_profile_sha256) &&
    boundedString(value.intent_family, 64) &&
    typeof value.intent_code === "string" &&
    INTENT_CODE.test(value.intent_code) &&
    boundedString(value.requester_id) &&
    value.requested_authority_kind === "ACTION_AUTHORITY" &&
    value.requested_scope_kind === "ACCEPTED_INTENT" &&
    value.requested_scope_value === value.intent_code &&
    value.request_state === "PENDING_AUTHORIZATION" &&
    timestamp(value.requested_at) &&
    value.authorization_granted === false &&
    value.action_lease_created === false &&
    value.effect_performed === false &&
    sha(value.authority_request_sha256)
  );
}

export function validateGhostWalkAuthorityRequestReadiness(value) {
  if (!zeroSnakeAuthority(value)) return false;
  if (
    value.schema_version !== "phios.ghostwalk_authority_request_readiness.v0.31" ||
    !sha(value.target_inference_receipt_sha256) ||
    !sha(value.accepted_intent_revision_sha256) ||
    !sha(value.policy_profile_sha256) ||
    !["ALLOW_REQUEST", "HOLD", "DENY"].includes(value.policy_decision) ||
    typeof value.ready !== "boolean" ||
    ![
      "READY",
      "POLICY_NOT_ALLOW_REQUEST",
      "ADMISSION_RECEIPT_REQUIRED",
      "ADMISSION_RECEIPT_STALE",
      "REQUEST_ALREADY_EXISTS",
    ].includes(value.reason) ||
    !nullableSha(value.admission_receipt_sha256) ||
    !nullableSha(value.existing_authority_request_sha256) ||
    value.authorization_granted !== false ||
    value.action_lease_created !== false ||
    value.effect_performed !== false ||
    !sha(value.readiness_sha256)
  ) {
    return false;
  }
  return value.ready === (value.reason === "READY");
}

function validBase(value, created) {
  return (
    zeroTransportAuthority(value) &&
    value.transportSchemaVersion === "phios.ghostwalk-authority-request-transport.v0.31" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-authority-request" &&
    value.localOnly === true &&
    value.requestCreated === created &&
    value.desktopEffectPerformed === false &&
    value.authorizationGranted === false &&
    value.actionLeaseCreated === false &&
    value.effectPerformed === created &&
    timestamp(value.servedAt)
  );
}

export function validateGhostWalkAuthorityRequestStatusEnvelope(value) {
  return (
    validBase(value, false) &&
    validateGhostWalkAuthorityRequestReadiness(value.readiness) &&
    (
      value.request === null ||
      validateGhostWalkAuthorityRequest(value.request)
    )
  );
}

export function validateGhostWalkAuthorityRequestCreateEnvelope(value) {
  return (
    validBase(value, true) &&
    validateGhostWalkAuthorityRequest(value.request)
  );
}

export function validateGhostWalkAuthorityRequestCreatePayload(value) {
  if (!record(value)) return false;
  const keys = Object.keys(value).sort();
  const expected = [
    "expected_admission_receipt_sha256",
    "target_inference_receipt_sha256",
  ];
  return (
    keys.length === expected.length &&
    keys.every((key, index) => key === expected[index]) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.expected_admission_receipt_sha256)
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

export async function fetchGhostWalkAuthorityRequestStatus(targetSha256, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 1500,
} = {}) {
  if (!sha(targetSha256)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/authority-request?target=${targetSha256}`,
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
    return validateGhostWalkAuthorityRequestStatusEnvelope(payload)
      ? { kind: "found", envelope: payload }
      : null;
  } catch {
    return null;
  }
}

export async function createGhostWalkAuthorityRequest(payload, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 2500,
} = {}) {
  if (!validateGhostWalkAuthorityRequestCreatePayload(payload)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/authority-request/requests`,
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
    return validateGhostWalkAuthorityRequestCreateEnvelope(result)
      ? { kind: "created", envelope: result }
      : null;
  } catch {
    return null;
  }
}
