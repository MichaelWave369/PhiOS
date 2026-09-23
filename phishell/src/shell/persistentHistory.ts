export type PersistentHistoryKind = "state" | "change";

export interface PersistentHistoryRecord {
  kind: PersistentHistoryKind;
  recordId: string;
  revision: number;
  recordSha256: string;
  contentSha256: string;
  createdAt: string;
  scopeId: string;
  classification: string;
  retentionPolicyId: string;
  epistemicKind: "source" | "derived";
  exactnessClass: string | null;
  derivedFrom: string[];
  transformationLineageSha256s: string[];
  readAdmissibilityReceiptSha256: string;
  payload: Record<string, unknown>;
}

export interface PersistentHistoryProjection {
  schemaVersion: "phios.system-history-projection.v0.12";
  source: "governed-memory-system-history";
  generatedAt: string;
  status: "ok" | "degraded";
  historyScope: "canonical-memory";
  persistent: true;
  limit: number;
  count: number;
  omittedRecordCount: number;
  records: PersistentHistoryRecord[];
  readAdmissibilityReceiptSha256s: string[];
  readOnly: true;
  causeAssigned: false;
  severityAssigned: false;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
}

interface PersistentHistoryEnvelope {
  transportSchemaVersion: "phios.system-history-transport.v0.12";
  transport: "loopback-http";
  transportIdentity: "phios-governed-history-reader";
  localOnly: true;
  readOnly: true;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  projection: PersistentHistoryProjection;
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
] as const;

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
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]) {
  return Object.keys(value).sort().join("\0") === [...expected].sort().join("\0");
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

function validPayload(kind: PersistentHistoryKind, payload: unknown) {
  if (!isRecord(payload)) return false;
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

function validPersistentRecord(value: unknown): value is PersistentHistoryRecord {
  if (!isRecord(value) || !exactKeys(value, RECORD_KEYS)) return false;
  if (value.kind !== "state" && value.kind !== "change") return false;
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

function validEnvelope(value: unknown): value is PersistentHistoryEnvelope {
  if (!isRecord(value) || !isRecord(value.projection)) return false;
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
    !timestamp(value.servedAt)
  ) {
    return false;
  }

  const projection = value.projection;
  if (!exactKeys(projection, PROJECTION_KEYS)) return false;
  if (
    projection.schemaVersion !== "phios.system-history-projection.v0.12" ||
    projection.source !== "governed-memory-system-history" ||
    !timestamp(projection.generatedAt) ||
    (projection.status !== "ok" && projection.status !== "degraded") ||
    projection.historyScope !== "canonical-memory" ||
    projection.persistent !== true ||
    !positiveInteger(projection.limit) ||
    projection.limit > 16 ||
    typeof projection.count !== "number" ||
    !Number.isInteger(projection.count) ||
    projection.count < 0 ||
    projection.count > projection.limit ||
    typeof projection.omittedRecordCount !== "number" ||
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
  if (!projection.records.every(validPersistentRecord)) return false;

  const readHashes = projection.records.map(
    (item) => item.readAdmissibilityReceiptSha256,
  );
  return (
    readHashes.every(
      (item, index) => item === projection.readAdmissibilityReceiptSha256s[index],
    ) && new Set(readHashes).size === readHashes.length
  );
}

export function createPersistentHistoryProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 1800,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    executionAuthority: false as const,
    async read(): Promise<PersistentHistoryProjection | null> {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher("/api/v1/persistent-history", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return null;
        const payload: unknown = await response.json();
        return validEnvelope(payload) ? payload.projection : null;
      } catch {
        return null;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const persistentHistoryProvider = createPersistentHistoryProvider();
