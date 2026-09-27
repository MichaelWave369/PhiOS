import {
  GHOSTWALK_HOST,
  ghostWalkSidecarPort,
} from "./ghostWalkControlProxy.mjs";

const SHA256 = /^[0-9a-f]{64}$/;
const INTENT_CODE = /^[A-Z][A-Z0-9_]{2,127}$/;

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value) {
  return typeof value === "string" && SHA256.test(value);
}

function nullableSha(value) {
  return value === null || sha(value);
}

function timestamp(value) {
  return (
    typeof value === "string" &&
    value.length <= 64 &&
    !Number.isNaN(Date.parse(value))
  );
}

function text(value, maximum = 512) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= maximum
  );
}

function stringArray(value) {
  return (
    Array.isArray(value) &&
    value.every((item) => text(item, 256)) &&
    new Set(value).size === value.length
  );
}

function exactKeys(value, expected) {
  if (!record(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return (
    actual.length === wanted.length &&
    actual.every((key, index) => key === wanted[index])
  );
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

function validateAuthorizationReadiness(value) {
  if (!zeroSnakeAuthority(value)) return false;
  const reasons = [
    "READY",
    "AUTHORITY_REQUEST_REQUIRED",
    "AUTHORITY_REQUEST_STALE",
    "DECISION_FINAL",
  ];
  return (
    value.schema_version ===
      "phios.ghostwalk_authorization_readiness.v0.32" &&
    sha(value.target_inference_receipt_sha256) &&
    nullableSha(value.authority_request_sha256) &&
    nullableSha(value.latest_decision_sha256) &&
    (
      value.latest_decision === null ||
      ["APPROVE", "DENY", "HOLD"].includes(value.latest_decision)
    ) &&
    typeof value.ready === "boolean" &&
    reasons.includes(value.reason) &&
    value.ready === (value.reason === "READY") &&
    typeof value.authorization_granted === "boolean" &&
    value.authorization_granted ===
      (value.latest_decision === "APPROVE") &&
    value.capability_binding_created === false &&
    value.action_lease_created === false &&
    value.effect_performed === false &&
    sha(value.readiness_sha256)
  );
}

export function validateGhostWalkAuthorizationDecision(value) {
  if (!zeroSnakeAuthority(value)) return false;
  if (
    value.schema_version !==
      "phios.ghostwalk_authorization_decision.v0.32" ||
    !sha(value.authority_request_sha256) ||
    !sha(value.target_inference_receipt_sha256) ||
    !sha(value.admission_receipt_sha256) ||
    !sha(value.accepted_intent_revision_sha256) ||
    !sha(value.policy_profile_sha256) ||
    !INTENT_CODE.test(value.intent_code) ||
    !text(value.authorizer_id) ||
    !["APPROVE", "DENY", "HOLD"].includes(value.decision) ||
    !Number.isInteger(value.decision_sequence) ||
    value.decision_sequence < 0 ||
    !nullableSha(value.previous_decision_sha256) ||
    !timestamp(value.decided_at) ||
    !(
      value.decision_note === null ||
      (
        typeof value.decision_note === "string" &&
        value.decision_note.length <= 2048
      )
    ) ||
    typeof value.authorization_granted !== "boolean" ||
    typeof value.request_resolved !== "boolean" ||
    value.capability_binding_created !== false ||
    value.action_lease_created !== false ||
    value.effect_performed !== false ||
    !sha(value.authorization_decision_sha256)
  ) {
    return false;
  }
  if (
    value.authorization_granted !== (value.decision === "APPROVE") ||
    value.request_resolved !==
      (value.decision === "APPROVE" || value.decision === "DENY")
  ) {
    return false;
  }
  return (
    (value.decision_sequence === 0) ===
    (value.previous_decision_sha256 === null)
  );
}

function validateBindingReadiness(value) {
  if (!zeroSnakeAuthority(value)) return false;
  const reasons = [
    "READY",
    "AUTHORIZATION_DECISION_REQUIRED",
    "AUTHORIZATION_NOT_APPROVED",
    "AUTHORIZATION_STALE",
    "NO_MAPPING",
    "AMBIGUOUS_MAPPING",
    "ACTION_EVIDENCE_MISSING",
    "MAPPING_CONSTRAINT_MISMATCH",
    "BINDING_ALREADY_EXISTS",
  ];
  return (
    value.schema_version ===
      "phios.ghostwalk_binding_readiness.v0.33" &&
    sha(value.target_inference_receipt_sha256) &&
    nullableSha(value.authorization_decision_sha256) &&
    sha(value.mapping_set_sha256) &&
    nullableSha(value.selected_mapping_sha256) &&
    nullableSha(value.action_observation_sha256) &&
    nullableSha(value.existing_binding_sha256) &&
    typeof value.ready === "boolean" &&
    reasons.includes(value.reason) &&
    value.ready === (value.reason === "READY") &&
    value.effect_performed === false &&
    sha(value.readiness_sha256)
  );
}

export function validateGhostWalkBindingSummary(value) {
  return (
    record(value) &&
    value.schema_version ===
      "phios.ghostwalk_executable_binding_summary.v0.36" &&
    sha(value.executable_binding_sha256) &&
    sha(value.authorization_decision_sha256) &&
    INTENT_CODE.test(value.intent_code) &&
    text(value.mapping_id, 128) &&
    text(value.capability_id, 256) &&
    text(value.capability_version, 128) &&
    sha(value.payload_sha256) &&
    stringArray(value.permissions_required) &&
    stringArray(value.effects_declared) &&
    timestamp(value.bound_at) &&
    value.effect_performed === false &&
    value.action_authority === false &&
    value.execution_authority === false
  );
}

function validateLeaseReadiness(value) {
  if (!record(value)) return false;
  const reasons = [
    "READY",
    "EXECUTABLE_BINDING_REQUIRED",
    "EXECUTABLE_BINDING_STALE",
    "LEASE_POLICY_MISSING",
    "ENFORCEMENT_PROFILE_INCOMPLETE",
    "UNENFORCED_EFFECT_ACK_REQUIRED",
    "AUTHORITY_EPOCH_UNAVAILABLE",
    "AUTHORITY_EPOCH_STALE",
    "AUTHORITY_PRINCIPAL_MISMATCH",
    "AUTHORITY_PERMISSION_MISSING",
    "LEASE_ALREADY_EXISTS",
  ];
  return (
    value.schema_version ===
      "phios.ghostwalk_lease_readiness.v0.34" &&
    sha(value.target_inference_receipt_sha256) &&
    nullableSha(value.executable_binding_sha256) &&
    nullableSha(value.policy_sha256) &&
    sha(value.policy_set_sha256) &&
    nullableSha(value.enforcement_profile_sha256) &&
    nullableSha(value.authority_epoch_sha256) &&
    stringArray(value.required_permissions) &&
    stringArray(value.missing_permissions) &&
    stringArray(value.unenforced_effects) &&
    stringArray(value.accepted_unenforced_effects) &&
    nullableSha(value.existing_action_lease_sha256) &&
    typeof value.ready === "boolean" &&
    reasons.includes(value.reason) &&
    value.ready === (value.reason === "READY") &&
    value.effect_performed === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.readiness_sha256)
  );
}

export function validateGhostWalkLeaseSummary(value) {
  return (
    record(value) &&
    value.schema_version ===
      "phios.ghostwalk_action_lease_summary.v0.36" &&
    sha(value.action_lease_sha256) &&
    sha(value.lease_record_sha256) &&
    sha(value.executable_binding_sha256) &&
    text(value.principal_id, 256) &&
    text(value.issuer_id, 256) &&
    text(value.capability_id, 256) &&
    text(value.capability_version, 128) &&
    sha(value.payload_sha256) &&
    stringArray(value.effects_declared) &&
    stringArray(value.permissions_authorized) &&
    timestamp(value.valid_from) &&
    timestamp(value.valid_until) &&
    value.max_uses === 1 &&
    value.lease_action_authority === true &&
    value.effect_performed === false &&
    value.execution_authority === false
  );
}

export function validateGhostWalkAuthorizationConsoleSnapshot(value) {
  if (!zeroSnakeAuthority(value)) return false;
  if (
    value.schema_version !==
      "phios.ghostwalk_authorization_console_snapshot.v0.36" ||
    !sha(value.target_inference_receipt_sha256) ||
    !validateAuthorizationReadiness(value.authorization_readiness) ||
    !(
      value.authorization_decision === null ||
      validateGhostWalkAuthorizationDecision(
        value.authorization_decision,
      )
    ) ||
    typeof value.binding_available !== "boolean" ||
    typeof value.lease_available !== "boolean" ||
    value.effect_performed !== false ||
    !sha(value.snapshot_sha256)
  ) {
    return false;
  }
  if (
    value.binding_available !== (value.binding_readiness !== null) ||
    value.lease_available !== (value.lease_readiness !== null)
  ) {
    return false;
  }
  if (
    value.binding_readiness !== null &&
    !validateBindingReadiness(value.binding_readiness)
  ) {
    return false;
  }
  if (
    value.binding !== null &&
    !validateGhostWalkBindingSummary(value.binding)
  ) {
    return false;
  }
  if (
    value.lease_readiness !== null &&
    !validateLeaseReadiness(value.lease_readiness)
  ) {
    return false;
  }
  if (
    value.lease !== null &&
    !validateGhostWalkLeaseSummary(value.lease)
  ) {
    return false;
  }
  return true;
}

function validateBase(value, mutationKind) {
  if (!record(value)) return false;
  const mutated = mutationKind !== "NONE";
  return (
    value.transportSchemaVersion ===
      "phios.ghostwalk-authorization-console-transport.v0.36" &&
    value.transport === "loopback-http" &&
    value.transportIdentity ===
      "phios-ghostwalk-authorization-console" &&
    value.localOnly === true &&
    value.humanAuthorizationSurface === true &&
    value.mutationKind === mutationKind &&
    value.decisionRecorded === (mutationKind === "DECISION") &&
    value.bindingCreated === (mutationKind === "BINDING") &&
    value.actionLeaseCreated === (mutationKind === "LEASE") &&
    value.desktopEffectPerformed === false &&
    value.policyAuthority === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === mutated &&
    timestamp(value.servedAt)
  );
}

export function validateGhostWalkAuthorizationConsoleStatusEnvelope(value) {
  return (
    validateBase(value, "NONE") &&
    validateGhostWalkAuthorizationConsoleSnapshot(value.snapshot)
  );
}

export function validateGhostWalkAuthorizationDecisionEnvelope(value) {
  return (
    validateBase(value, "DECISION") &&
    validateGhostWalkAuthorizationDecision(value.decision) &&
    validateGhostWalkAuthorizationConsoleSnapshot(value.snapshot)
  );
}

export function validateGhostWalkBindingEnvelope(value) {
  return (
    validateBase(value, "BINDING") &&
    validateGhostWalkBindingSummary(value.binding) &&
    validateGhostWalkAuthorizationConsoleSnapshot(value.snapshot)
  );
}

export function validateGhostWalkLeaseEnvelope(value) {
  return (
    validateBase(value, "LEASE") &&
    validateGhostWalkLeaseSummary(value.lease) &&
    validateGhostWalkAuthorizationConsoleSnapshot(value.snapshot)
  );
}

export function validateAuthorizationDecisionPayload(value) {
  const keys = [
    "decision",
    "decision_note",
    "expected_authority_request_sha256",
    "expected_previous_decision_sha256",
    "target_inference_receipt_sha256",
  ];
  return (
    exactKeys(value, keys) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.expected_authority_request_sha256) &&
    nullableSha(value.expected_previous_decision_sha256) &&
    ["APPROVE", "DENY", "HOLD"].includes(value.decision) &&
    (
      value.decision_note === null ||
      (
        typeof value.decision_note === "string" &&
        value.decision_note.length <= 2048 &&
        !value.decision_note.includes("\u0000")
      )
    )
  );
}

export function validateBindingCreatePayload(value) {
  const keys = [
    "expected_authorization_decision_sha256",
    "expected_mapping_set_sha256",
    "expected_mapping_sha256",
    "target_inference_receipt_sha256",
  ];
  return (
    exactKeys(value, keys) &&
    keys.every((key) => sha(value[key]))
  );
}

export function validateLeaseIssuePayload(value) {
  const keys = [
    "expected_authority_epoch_sha256",
    "expected_enforcement_profile_sha256",
    "expected_executable_binding_sha256",
    "expected_policy_set_sha256",
    "expected_policy_sha256",
    "target_inference_receipt_sha256",
  ];
  return (
    exactKeys(value, keys) &&
    keys.every((key) => sha(value[key]))
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

async function post(path, payload, validator, options) {
  const {
    fetcher = globalThis.fetch.bind(globalThis),
    port = ghostWalkSidecarPort(),
    timeoutMs = 2500,
  } = options ?? {};
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}${path}`,
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
  if (response.status === 503) return { kind: "unavailable" };
  if (!response.ok) return null;
  try {
    const envelope = await response.json();
    return validator(envelope)
      ? { kind: "applied", envelope }
      : null;
  } catch {
    return null;
  }
}

export async function fetchGhostWalkAuthorizationConsole(
  targetSha256,
  {
    fetcher = globalThis.fetch.bind(globalThis),
    port = ghostWalkSidecarPort(),
    timeoutMs = 1500,
  } = {},
) {
  if (!sha(targetSha256)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/authorization-console?target=${targetSha256}`,
    {
      method: "GET",
      cache: "no-store",
      headers: { accept: "application/json" },
    },
    fetcher,
    timeoutMs,
  );
  if (!response || !response.ok) return null;
  try {
    const envelope = await response.json();
    return validateGhostWalkAuthorizationConsoleStatusEnvelope(envelope)
      ? { kind: "found", envelope }
      : null;
  } catch {
    return null;
  }
}

export async function recordGhostWalkAuthorizationDecision(
  payload,
  options = {},
) {
  if (!validateAuthorizationDecisionPayload(payload)) return null;
  return post(
    "/api/v1/ghostwalk/authorization-console/decisions",
    payload,
    validateGhostWalkAuthorizationDecisionEnvelope,
    options,
  );
}

export async function createGhostWalkExecutableBinding(
  payload,
  options = {},
) {
  if (!validateBindingCreatePayload(payload)) return null;
  return post(
    "/api/v1/ghostwalk/authorization-console/bindings",
    payload,
    validateGhostWalkBindingEnvelope,
    options,
  );
}

export async function issueGhostWalkActionLease(
  payload,
  options = {},
) {
  if (!validateLeaseIssuePayload(payload)) return null;
  return post(
    "/api/v1/ghostwalk/authorization-console/leases",
    payload,
    validateGhostWalkLeaseEnvelope,
    options,
  );
}
