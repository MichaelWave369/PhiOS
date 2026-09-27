import { ghostWalkSidecarPort, GHOSTWALK_HOST } from "./ghostWalkControlProxy.mjs";

const SHA256 = /^[0-9a-f]{64}$/;
const INTENT_CODE = /^[A-Z][A-Z0-9_]{2,127}$/;
const FAMILIES = new Set([
  "NAVIGATE",
  "OPEN",
  "CLOSE",
  "SELECT",
  "TOGGLE",
  "ENTER_TEXT",
  "SUBMIT",
  "CONFIRM",
  "CANCEL",
  "OTHER",
]);
const STATUSES = new Set(["ACTIVE", "REVOKED"]);

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

function integer(value, minimum = 1) {
  return Number.isInteger(value) && value >= minimum;
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

export function validateGhostWalkAcceptedIntent(value) {
  if (!zeroSnakeAuthority(value)) return false;
  if (
    value.schema_version !== "phios.ghostwalk_accepted_intent_revision.v0.29" ||
    !sha(value.target_inference_receipt_sha256) ||
    !sha(value.source_operator_note_revision_sha256) ||
    !integer(value.revision) ||
    !FAMILIES.has(value.intent_family) ||
    !INTENT_CODE.test(String(value.intent_code)) ||
    !STATUSES.has(value.status) ||
    !boundedString(value.accepted_by) ||
    !timestamp(value.accepted_at) ||
    !nullableSha(value.supersedes_revision_sha256) ||
    value.human_intent_confirmed !== true ||
    value.causation_proven !== false ||
    !sha(value.revision_sha256)
  ) {
    return false;
  }

  if (value.intent_family !== "OTHER") {
    return String(value.intent_code).startsWith(`${value.intent_family}_`);
  }
  return true;
}

function validEnvelope(value, mutated) {
  return (
    zeroTransportAuthority(value) &&
    value.transportSchemaVersion === "phios.ghostwalk-accepted-intent-transport.v0.29" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-accepted-intent" &&
    value.localOnly === true &&
    value.intentMutation === mutated &&
    value.desktopEffectPerformed === false &&
    value.effectPerformed === mutated &&
    timestamp(value.servedAt)
  );
}

export function validateGhostWalkAcceptedIntentEnvelope(value, { mutated }) {
  return (
    validEnvelope(value, mutated) &&
    validateGhostWalkAcceptedIntent(value.intent)
  );
}

export function validateGhostWalkAcceptedIntentMutationPayload(value) {
  if (!record(value)) return false;
  if (value.operation === "ACCEPT") {
    const keys = Object.keys(value).sort();
    const expected = [
      "expected_current_revision_sha256",
      "intent_code",
      "intent_family",
      "operation",
      "source_operator_note_revision_sha256",
      "target_inference_receipt_sha256",
    ];
    return (
      keys.length === expected.length &&
      keys.every((key, index) => key === expected[index]) &&
      sha(value.target_inference_receipt_sha256) &&
      sha(value.source_operator_note_revision_sha256) &&
      (value.expected_current_revision_sha256 === null ||
        sha(value.expected_current_revision_sha256)) &&
      FAMILIES.has(value.intent_family) &&
      typeof value.intent_code === "string" &&
      INTENT_CODE.test(value.intent_code) &&
      (
        value.intent_family === "OTHER" ||
        value.intent_code.startsWith(`${value.intent_family}_`)
      )
    );
  }

  if (value.operation === "REVOKE") {
    const keys = Object.keys(value).sort();
    const expected = [
      "expected_current_revision_sha256",
      "operation",
      "target_inference_receipt_sha256",
    ];
    return (
      keys.length === expected.length &&
      keys.every((key, index) => key === expected[index]) &&
      sha(value.target_inference_receipt_sha256) &&
      sha(value.expected_current_revision_sha256)
    );
  }

  return false;
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

export async function fetchGhostWalkAcceptedIntent(targetSha256, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 1500,
} = {}) {
  if (!sha(targetSha256)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/accepted-intent?target=${targetSha256}`,
    {
      method: "GET",
      cache: "no-store",
      headers: { accept: "application/json" },
    },
    fetcher,
    timeoutMs,
  );
  if (!response) return null;
  if (response.status === 404) return { kind: "none" };
  if (!response.ok) return null;

  try {
    const payload = await response.json();
    if (!validateGhostWalkAcceptedIntentEnvelope(payload, { mutated: false })) {
      return null;
    }
    return { kind: "found", envelope: payload };
  } catch {
    return null;
  }
}

export async function applyGhostWalkAcceptedIntentMutation(payload, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 2500,
} = {}) {
  if (!validateGhostWalkAcceptedIntentMutationPayload(payload)) return null;
  const response = await request(
    `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/accepted-intent/revisions`,
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
    if (!validateGhostWalkAcceptedIntentEnvelope(result, { mutated: true })) {
      return null;
    }
    return { kind: "applied", envelope: result };
  } catch {
    return null;
  }
}
