import { ghostWalkSidecarPort, GHOSTWALK_HOST } from "./ghostWalkControlProxy.mjs";

const SHA256 = /^[0-9a-f]{64}$/;
const STATUSES = new Set(["ACTIVE", "RETRACTED"]);

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value) {
  return typeof value === "string" && SHA256.test(value);
}

function timestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function boundedString(value, maximum = 16384) {
  return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function nullableSha(value) {
  return value === null || sha(value);
}

function integer(value, minimum = 1) {
  return Number.isInteger(value) && value >= minimum;
}

function zeroAuthority(value) {
  return (
    record(value) &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false
  );
}

export function validateGhostWalkOperatorNote(value) {
  return (
    zeroAuthority(value) &&
    value.schema_version === "phios.ghostwalk_operator_note.v0.28" &&
    sha(value.target_inference_receipt_sha256) &&
    boundedString(value.note_id, 512) &&
    integer(value.revision) &&
    sha(value.revision_sha256) &&
    boundedString(value.author_id, 512) &&
    boundedString(value.body, 16384) &&
    Array.isArray(value.tags) &&
    value.tags.length <= 64 &&
    value.tags.every((item) => boundedString(item, 128)) &&
    STATUSES.has(value.status) &&
    timestamp(value.created_at) &&
    nullableSha(value.supersedes_revision_sha256) &&
    boundedString(value.inference_status, 64) &&
    boundedString(value.session_id, 512) &&
    sha(value.action_observation_sha256)
  );
}

function validTransportBase(value, { mutated }) {
  return (
    zeroAuthority(value) &&
    value.transportSchemaVersion === "phios.ghostwalk-operator-log-transport.v0.28" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-operator-editor" &&
    value.localOnly === true &&
    value.annotationMutation === mutated &&
    value.desktopEffectPerformed === false &&
    value.effectPerformed === mutated &&
    timestamp(value.servedAt)
  );
}

export function validateGhostWalkOperatorNoteEnvelope(value) {
  return (
    validTransportBase(value, { mutated: false }) &&
    validateGhostWalkOperatorNote(value.note)
  );
}

export function validateGhostWalkOperatorEditEnvelope(value) {
  if (!validTransportBase(value, { mutated: true }) || !record(value.outcome)) {
    return false;
  }
  return (
    value.outcome.result === "APPLIED" &&
    value.outcome.annotation_mutation === true &&
    value.outcome.desktop_effect_performed === false &&
    value.outcome.operational_authority === false &&
    value.outcome.action_authority === false &&
    value.outcome.execution_authority === false &&
    validateGhostWalkOperatorNote(value.outcome.note)
  );
}

export function validateGhostWalkOperatorEditPayload(value) {
  if (!record(value)) return false;
  const keys = Object.keys(value).sort();
  const expected = [
    "body",
    "expected_current_revision_sha256",
    "status",
    "target_inference_receipt_sha256",
  ];
  return (
    keys.length === expected.length &&
    keys.every((key, index) => key === expected[index]) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.expected_current_revision_sha256) &&
    boundedString(value.body, 16384) &&
    STATUSES.has(value.status)
  );
}

export async function fetchGhostWalkOperatorNote(targetSha256, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 1500,
} = {}) {
  if (!sha(targetSha256)) return null;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(
      `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/operator-log?target=${targetSha256}`,
      {
        method: "GET",
        cache: "no-store",
        headers: { accept: "application/json" },
        signal: controller.signal,
      },
    );
    if (!response.ok) return null;
    const payload = await response.json();
    return validateGhostWalkOperatorNoteEnvelope(payload) ? payload : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export async function applyGhostWalkOperatorEdit(payload, {
  fetcher = globalThis.fetch.bind(globalThis),
  port = ghostWalkSidecarPort(),
  timeoutMs = 2500,
} = {}) {
  if (!validateGhostWalkOperatorEditPayload(payload)) return null;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(
      `http://${GHOSTWALK_HOST}:${port}/api/v1/ghostwalk/operator-log/revisions`,
      {
        method: "POST",
        cache: "no-store",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
    );
    if (response.status === 409) return { kind: "conflict" };
    if (!response.ok) return null;
    const result = await response.json();
    if (!validateGhostWalkOperatorEditEnvelope(result)) return null;
    return { kind: "applied", envelope: result };
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}
