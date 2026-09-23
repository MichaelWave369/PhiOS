const HISTORY_HOST = "127.0.0.1";
const DEFAULT_HISTORY_PORT = 3970;
const MAX_HISTORY_RECORDS = 16;

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value, expected) {
  return (
    record(value) &&
    Object.keys(value).sort().join("\0") === [...expected].sort().join("\0")
  );
}

function timestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function positiveInteger(value) {
  return Number.isInteger(value) && value >= 1;
}

const RECORD_KEYS = [
  "kind",
  "recordId",
  "revision",
  "recordSha256",
  "contentSha256",
  "createdAt",
  "scopeId",
  "classification",
  "retentionPolicyId",
  "epistemicKind",
  "exactnessClass",
  "derivedFrom",
  "transformationLineageSha256s",
  "readAdmissibilityReceiptSha256",
  "payload",
];

const PROJECTION_KEYS = [
  "schemaVersion",
  "source",
  "generatedAt",
  "status",
  "historyScope",
  "persistent",
  "limit",
  "count",
  "omittedRecordCount",
  "records",
  "readAdmissibilityReceiptSha256s",
  "readOnly",
  "causeAssigned",
  "severityAssigned",
  "operationalAuthority",
  "actionAuthority",
  "executionAuthority",
  "effectPerformed",
];

function validPayload(kind, payload) {
  if (!record(payload)) return false;

  if (kind === "state") {
    return (
      payload.schemaVersion === "phios.system-state.v1" &&
      payload.source === "phios-system-state-composer" &&
      payload.readOnly === true &&
      payload.executionAuthority === false &&
      payload.effectPerformed === false &&
      typeof payload.receiptDigest === "string" &&
      /^sha256:[0-9a-f]{64}$/.test(payload.receiptDigest)
    );
  }

  return (
    payload.schemaVersion === "phios.system-change.v1" &&
    payload.source === "phios-system-change-deriver" &&
    payload.causeAssigned === false &&
    payload.severityAssigned === false &&
    payload.readOnly === true &&
    payload.executionAuthority === false &&
    payload.effectPerformed === false &&
    typeof payload.changeDigest === "string" &&
    /^sha256:[0-9a-f]{64}$/.test(payload.changeDigest)
  );
}

function validHistoryRecord(value) {
  if (!exactKeys(value, RECORD_KEYS)) return false;
  if (!["state", "change"].includes(value.kind)) return false;
  if (typeof value.recordId !== "string" || value.recordId.length > 160) return false;
  if (!positiveInteger(value.revision)) return false;
  if (!sha(value.recordSha256) || !sha(value.contentSha256)) return false;
  if (!timestamp(value.createdAt)) return false;
  if (typeof value.scopeId !== "string" || !value.scopeId) return false;
  if (typeof value.classification !== "string" || !value.classification) return false;
  if (typeof value.retentionPolicyId !== "string" || !value.retentionPolicyId) return false;
  if (!Array.isArray(value.derivedFrom) || value.derivedFrom.length > 2) return false;
  if (
    !Array.isArray(value.transformationLineageSha256s) ||
    value.transformationLineageSha256s.some((item) => !sha(item))
  ) {
    return false;
  }
  if (!sha(value.readAdmissibilityReceiptSha256)) return false;
  if (!validPayload(value.kind, value.payload)) return false;

  if (value.kind === "state") {
    return (
      value.recordId.startsWith("phishell.system-state.") &&
      value.epistemicKind === "source" &&
      value.exactnessClass === null &&
      value.derivedFrom.length === 0 &&
      value.transformationLineageSha256s.length === 0
    );
  }

  return (
    value.recordId.startsWith("phishell.system-change.") &&
    value.epistemicKind === "derived" &&
    value.exactnessClass === "REVERSIBLE" &&
    value.derivedFrom.length === 2 &&
    value.derivedFrom.every(
      (item) => typeof item === "string" && item.startsWith("phishell.system-state."),
    ) &&
    value.transformationLineageSha256s.length === 1
  );
}

export function validatePersistentHistoryEnvelope(value) {
  if (!record(value)) return false;
  if (
    value.transportSchemaVersion !== "phios.system-history-transport.v0.12" ||
    value.transport !== "loopback-http" ||
    value.transportIdentity !== "phios-governed-history-reader" ||
    value.localOnly !== true ||
    value.readOnly !== true ||
    value.operationalAuthority !== false ||
    value.actionAuthority !== false ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    !timestamp(value.servedAt) ||
    !record(value.projection)
  ) {
    return false;
  }

  const projection = value.projection;
  if (!exactKeys(projection, PROJECTION_KEYS)) return false;
  if (
    projection.schemaVersion !== "phios.system-history-projection.v0.12" ||
    projection.source !== "governed-memory-system-history" ||
    !timestamp(projection.generatedAt) ||
    !["ok", "degraded"].includes(projection.status) ||
    projection.historyScope !== "canonical-memory" ||
    projection.persistent !== true ||
    !positiveInteger(projection.limit) ||
    projection.limit > MAX_HISTORY_RECORDS ||
    !Number.isInteger(projection.count) ||
    projection.count < 0 ||
    projection.count > projection.limit ||
    !Number.isInteger(projection.omittedRecordCount) ||
    projection.omittedRecordCount < 0 ||
    !Array.isArray(projection.records) ||
    projection.records.length !== projection.count ||
    !Array.isArray(projection.readAdmissibilityReceiptSha256s) ||
    projection.readAdmissibilityReceiptSha256s.length !== projection.count ||
    projection.readOnly !== true ||
    projection.causeAssigned !== false ||
    projection.severityAssigned !== false ||
    projection.operationalAuthority !== false ||
    projection.actionAuthority !== false ||
    projection.executionAuthority !== false ||
    projection.effectPerformed !== false
  ) {
    return false;
  }

  if (projection.status === "ok" && projection.omittedRecordCount !== 0) return false;
  if (projection.status === "degraded" && projection.omittedRecordCount === 0) return false;
  if (projection.records.some((item) => !validHistoryRecord(item))) return false;

  const receiptHashes = projection.records.map(
    (item) => item.readAdmissibilityReceiptSha256,
  );
  return (
    receiptHashes.every((item, index) => item === projection.readAdmissibilityReceiptSha256s[index]) &&
    new Set(receiptHashes).size === receiptHashes.length
  );
}

export function historySidecarPort(env = process.env) {
  const raw = env.PHIOS_HISTORY_PORT;
  if (raw === undefined) return DEFAULT_HISTORY_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("PHIOS_HISTORY_PORT must be an integer from 1024 to 65535");
  }
  return port;
}

export async function fetchPersistentHistoryProjection({
  fetcher = globalThis.fetch.bind(globalThis),
  port = historySidecarPort(),
  limit = MAX_HISTORY_RECORDS,
  timeoutMs = 1500,
} = {}) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("history sidecar port must be an integer from 1024 to 65535");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_HISTORY_RECORDS) {
    throw new Error("persistent history limit must be an integer from 1 to 16");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(
      `http://${HISTORY_HOST}:${port}/api/v1/system-history?limit=${limit}`,
      {
        method: "GET",
        cache: "no-store",
        headers: { accept: "application/json" },
        signal: controller.signal,
      },
    );
    if (!response.ok) return null;
    const payload = await response.json();
    return validatePersistentHistoryEnvelope(payload) ? payload : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export { DEFAULT_HISTORY_PORT, HISTORY_HOST, MAX_HISTORY_RECORDS };
