const GHOSTWALK_HOST = "127.0.0.1";
const DEFAULT_GHOSTWALK_PORT = 3973;
const MAX_RECENT_ITEMS = 25;
const ACTIONS = new Set(["STATUS", "START", "STOP", "ARM", "DISARM"]);
const HOST_STATUSES = new Set([
  "STOPPED",
  "STARTING",
  "RUNNING",
  "DEGRADED",
  "STOPPING",
  "FAILED",
]);

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function timestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function optionalSha(value) {
  return value === null || sha(value);
}

function nullableString(value, maximum = 512) {
  return value === null || (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= maximum
  );
}

function boundedString(value, maximum = 512) {
  return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function integer(value, minimum = 0) {
  return Number.isInteger(value) && value >= minimum;
}

function zeroAuthority(value) {
  return (
    record(value) &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === false
  );
}

function validTransition(value) {
  return (
    record(value) &&
    sha(value.inference_receipt_sha256) &&
    boundedString(value.session_id) &&
    sha(value.action_observation_sha256) &&
    boundedString(value.status, 64) &&
    Array.isArray(value.candidate_kinds) &&
    value.candidate_kinds.length <= MAX_RECENT_ITEMS &&
    value.candidate_kinds.every((item) => boundedString(item, 128)) &&
    timestamp(value.inferred_at) &&
    optionalSha(value.operator_note_revision_sha256) &&
    (value.operator_note_revision === null || integer(value.operator_note_revision, 1)) &&
    nullableString(value.operator_note_status, 64)
  );
}

function validIssue(value) {
  return (
    record(value) &&
    boundedString(value.source, 128) &&
    boundedString(value.status, 64) &&
    boundedString(value.reason, 128) &&
    timestamp(value.observed_at) &&
    sha(value.receipt_sha256)
  );
}

export function validateGhostWalkSnapshot(value) {
  if (!record(value)) return false;
  if (
    value.schema_version !== "phios.ghostwalk_control_snapshot.v0.25" ||
    !boundedString(value.surface_id) ||
    !boundedString(value.host_id) ||
    !HOST_STATUSES.has(value.host_status) ||
    !integer(value.run_generation) ||
    !nullableString(value.session_id) ||
    typeof value.listener_alive !== "boolean" ||
    typeof value.tick_alive !== "boolean" ||
    typeof value.baseline_armed !== "boolean" ||
    !optionalSha(value.baseline_sha256) ||
    !(value.baseline_age_ms === null || integer(value.baseline_age_ms)) ||
    typeof value.baseline_refresh_due !== "boolean" ||
    !nullableString(value.error_type, 256) ||
    !["NONE", "PRIOR_RUN_ABANDONED"].includes(value.recovery_state) ||
    !optionalSha(value.recovery_receipt_sha256) ||
    !optionalSha(value.last_action_observation_sha256) ||
    !timestamp(value.observed_at) ||
    value.operational_authority !== false ||
    value.action_authority !== false ||
    value.execution_authority !== false ||
    !sha(value.snapshot_sha256)
  ) {
    return false;
  }

  if (
    !Array.isArray(value.available_actions) ||
    value.available_actions.length > ACTIONS.size ||
    !value.available_actions.every((item) => ACTIONS.has(item)) ||
    new Set(value.available_actions).size !== value.available_actions.length
  ) {
    return false;
  }

  return (
    Array.isArray(value.learned_transitions) &&
    value.learned_transitions.length <= MAX_RECENT_ITEMS &&
    value.learned_transitions.every(validTransition) &&
    Array.isArray(value.recent_issues) &&
    value.recent_issues.length <= MAX_RECENT_ITEMS &&
    value.recent_issues.every(validIssue)
  );
}

function validateGhostWalkReceipt(value) {
  return (
    record(value) &&
    value.schema_version === "phios.ghostwalk_control_receipt.v0.25" &&
    boundedString(value.surface_id) &&
    integer(value.sequence) &&
    ACTIONS.has(value.action) &&
    nullableString(value.requested_session_id) &&
    ["OBSERVED", "APPLIED", "NOOP", "REJECTED"].includes(value.result) &&
    boundedString(value.reason, 128) &&
    sha(value.before_snapshot_sha256) &&
    sha(value.after_snapshot_sha256) &&
    timestamp(value.applied_at) &&
    nullableString(value.error_type, 256) &&
    optionalSha(value.previous_receipt_sha256) &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.receipt_sha256)
  );
}

function validTransportBase(value) {
  return (
    zeroAuthority(value) &&
    value.transportSchemaVersion === "phios.ghostwalk-control-transport.v0.26" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-control" &&
    value.localOnly === true &&
    timestamp(value.servedAt)
  );
}

export function validateGhostWalkStatusEnvelope(value) {
  return validTransportBase(value) && validateGhostWalkSnapshot(value.snapshot);
}

export function validateGhostWalkActionEnvelope(value) {
  return (
    validTransportBase(value) &&
    typeof value.controlPlaneMutation === "boolean" &&
    validateGhostWalkReceipt(value.receipt) &&
    validateGhostWalkSnapshot(value.snapshot)
  );
}

export function validateGhostWalkActionPayload(value) {
  if (!record(value)) return false;
  const keys = Object.keys(value);
  if (!keys.includes("action") || keys.some((key) => !["action", "session_id"].includes(key))) {
    return false;
  }
  if (!ACTIONS.has(value.action)) return false;

  const session = value.session_id;
  if (value.action === "START") {
    return boundedString(session);
  }
  return session === undefined || session === null;
}

export function ghostWalkSidecarPort(env = process.env) {
  const raw = env.PHIOS_GHOSTWALK_PORT;
  if (raw === undefined) return DEFAULT_GHOSTWALK_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("PHIOS_GHOSTWALK_PORT must be an integer from 1024 to 65535");
  }
  return port;
}

async function fetchJson(url, init, fetcher, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(url, { ...init, signal: controller.signal });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function fetchGhostWalkStatus({
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 1500,
} = {}) {
  const payload = await fetchJson(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk`,
    {
      method: "GET",
      cache: "no-store",
      headers: { accept: "application/json" },
    },
    fetcher,
    timeoutMs,
  );
  return validateGhostWalkStatusEnvelope(payload) ? payload : null;
}

export async function applyGhostWalkAction(payload, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 2500,
} = {}) {
  if (!validateGhostWalkActionPayload(payload)) return null;
  const response = await fetchJson(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/actions`,
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
  return validateGhostWalkActionEnvelope(response) ? response : null;
}

export {
  GHOSTWALK_HOST,
  DEFAULT_GHOSTWALK_PORT,
};
