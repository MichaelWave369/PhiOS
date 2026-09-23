export interface HistoryComparisonComponent {
  id: "host" | "services" | "processes" | "packages" | "devices";
  fromAvailability: "available" | "unavailable";
  toAvailability: "available" | "unavailable";
  availabilityChanged: boolean;
  fromDigest: string;
  toDigest: string;
  digestChanged: boolean;
}

export interface HistoryComparisonSummaryChange {
  metric: string;
  from: number;
  to: number;
  delta: number;
}

export interface HistoryComparisonReceipt {
  schemaVersion: "phios.system-history-comparison.v0.13";
  source: "governed-memory-system-history-comparator";
  generatedAt: string;
  comparisonScope: "canonical-state-pair";
  persistent: false;
  fromRecordId: string;
  toRecordId: string;
  fromRecordSha256: string;
  toRecordSha256: string;
  fromReadAdmissibilityReceiptSha256: string;
  toReadAdmissibilityReceiptSha256: string;
  fromReceiptDigest: string;
  toReceiptDigest: string;
  fromComposedAt: string;
  toComposedAt: string;
  timeDeltaMs: number;
  chronologicalOrder: "forward" | "reverse" | "same-time";
  coherence: {
    from: "coherent" | "degraded";
    to: "coherent" | "degraded";
    changed: boolean;
  };
  changedComponentCount: number;
  componentChanges: HistoryComparisonComponent[];
  changedSummaryMetricCount: number;
  summaryChanges: HistoryComparisonSummaryChange[];
  consecutiveClaimed: false;
  causeAssigned: false;
  severityAssigned: false;
  readOnly: true;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
  comparisonDigest: string;
}

interface HistoryComparisonEnvelope {
  transportSchemaVersion: "phios.system-history-comparison-transport.v0.13";
  transport: "loopback-http";
  transportIdentity: "phios-governed-history-reader";
  localOnly: true;
  readOnly: true;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  comparison: HistoryComparisonReceipt;
}

const COMPONENT_IDS = ["host", "services", "processes", "packages", "devices"] as const;
const SUMMARY_METRICS = [
  "cpuLogicalCores",
  "memoryTotalBytes",
  "rootStorageTotalBytes",
  "observedServiceCount",
  "activeServiceCount",
  "currentUserProcessCount",
  "installedPackageCount",
  "blockDeviceCount",
  "networkDeviceCount",
  "pciDeviceCount",
  "usbDeviceCount",
  "drmDeviceCount",
  "powerDeviceCount",
] as const;


const COMPARISON_KEYS = [
  "schemaVersion","source","generatedAt","comparisonScope","persistent",
  "fromRecordId","toRecordId","fromRecordSha256","toRecordSha256",
  "fromReadAdmissibilityReceiptSha256","toReadAdmissibilityReceiptSha256",
  "fromReceiptDigest","toReceiptDigest","fromComposedAt","toComposedAt",
  "timeDeltaMs","chronologicalOrder","coherence","changedComponentCount",
  "componentChanges","changedSummaryMetricCount","summaryChanges",
  "consecutiveClaimed","causeAssigned","severityAssigned","readOnly",
  "operationalAuthority","actionAuthority","executionAuthority","effectPerformed",
  "comparisonDigest",
] as const;
const COMPONENT_KEYS = [
  "id","fromAvailability","toAvailability","availabilityChanged",
  "fromDigest","toDigest","digestChanged",
] as const;
const SUMMARY_CHANGE_KEYS = ["metric","from","to","delta"] as const;
const ENVELOPE_KEYS = [
  "transportSchemaVersion","transport","transportIdentity","localOnly","readOnly",
  "operationalAuthority","actionAuthority","executionAuthority","effectPerformed",
  "servedAt","comparison",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]) {
  return Object.keys(value).sort().join("\\0") === [...expected].sort().join("\\0");
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function prefixedSha(value: unknown): value is string {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

function stateRecordId(value: unknown): value is string {
  return typeof value === "string" && /^phishell\.system-state\.[0-9a-f]{64}$/.test(value);
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalize(value[key])]),
  );
}

async function comparisonDigest(value: Record<string, unknown>) {
  const body = { ...value };
  delete body.comparisonDigest;
  const encoded = new TextEncoder().encode(JSON.stringify(canonicalize(body)));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", encoded);
  return (
    "sha256:" +
    Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")
  );
}

function comparisonShape(value: unknown): value is HistoryComparisonReceipt {
  if (!isRecord(value) || !exactKeys(value, COMPARISON_KEYS)) return false;
  if (
    value.schemaVersion !== "phios.system-history-comparison.v0.13" ||
    value.source !== "governed-memory-system-history-comparator" ||
    !timestamp(value.generatedAt) ||
    value.comparisonScope !== "canonical-state-pair" ||
    value.persistent !== false ||
    !stateRecordId(value.fromRecordId) ||
    !stateRecordId(value.toRecordId) ||
    value.fromRecordId === value.toRecordId ||
    !sha(value.fromRecordSha256) ||
    !sha(value.toRecordSha256) ||
    !sha(value.fromReadAdmissibilityReceiptSha256) ||
    !sha(value.toReadAdmissibilityReceiptSha256) ||
    !prefixedSha(value.fromReceiptDigest) ||
    !prefixedSha(value.toReceiptDigest) ||
    !timestamp(value.fromComposedAt) ||
    !timestamp(value.toComposedAt) ||
    !Number.isInteger(value.timeDeltaMs) ||
    !["forward", "reverse", "same-time"].includes(String(value.chronologicalOrder)) ||
    value.consecutiveClaimed !== false ||
    value.causeAssigned !== false ||
    value.severityAssigned !== false ||
    value.readOnly !== true ||
    value.operationalAuthority !== false ||
    value.actionAuthority !== false ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    !prefixedSha(value.comparisonDigest)
  ) {
    return false;
  }

  const expectedDelta = Date.parse(value.toComposedAt) - Date.parse(value.fromComposedAt);
  const expectedOrder =
    expectedDelta > 0 ? "forward" : expectedDelta < 0 ? "reverse" : "same-time";
  if (value.timeDeltaMs !== expectedDelta || value.chronologicalOrder !== expectedOrder) {
    return false;
  }

  if (!isRecord(value.coherence) || !exactKeys(value.coherence, ["from", "to", "changed"])) return false;
  if (
    !["coherent", "degraded"].includes(String(value.coherence.from)) ||
    !["coherent", "degraded"].includes(String(value.coherence.to)) ||
    typeof value.coherence.changed !== "boolean" ||
    value.coherence.changed !== (value.coherence.from !== value.coherence.to)
  ) {
    return false;
  }

  if (!Array.isArray(value.componentChanges) || value.componentChanges.length !== COMPONENT_IDS.length) {
    return false;
  }
  for (let index = 0; index < COMPONENT_IDS.length; index += 1) {
    const row = value.componentChanges[index];
    if (
      !isRecord(row) ||
      !exactKeys(row, COMPONENT_KEYS) ||
      row.id !== COMPONENT_IDS[index] ||
      !["available", "unavailable"].includes(String(row.fromAvailability)) ||
      !["available", "unavailable"].includes(String(row.toAvailability)) ||
      typeof row.availabilityChanged !== "boolean" ||
      !prefixedSha(row.fromDigest) ||
      !prefixedSha(row.toDigest) ||
      typeof row.digestChanged !== "boolean" ||
      row.availabilityChanged !== (row.fromAvailability !== row.toAvailability) ||
      row.digestChanged !== (row.fromDigest !== row.toDigest)
    ) {
      return false;
    }
  }
  const changedComponents = value.componentChanges.filter(
    (row) =>
      isRecord(row) && (row.availabilityChanged === true || row.digestChanged === true),
  ).length;
  if (value.changedComponentCount !== changedComponents) return false;

  if (
    !Array.isArray(value.summaryChanges) ||
    !Number.isInteger(value.changedSummaryMetricCount) ||
    value.changedSummaryMetricCount !== value.summaryChanges.length ||
    value.summaryChanges.length > SUMMARY_METRICS.length
  ) {
    return false;
  }
  let priorIndex = -1;
  for (const row of value.summaryChanges) {
    if (!isRecord(row) || !exactKeys(row, SUMMARY_CHANGE_KEYS)) return false;
    const metricIndex = SUMMARY_METRICS.indexOf(
      row.metric as (typeof SUMMARY_METRICS)[number],
    );
    if (
      metricIndex <= priorIndex ||
      !finiteNumber(row.from) ||
      !finiteNumber(row.to) ||
      !finiteNumber(row.delta) ||
      row.delta !== row.to - row.from
    ) {
      return false;
    }
    priorIndex = metricIndex;
  }

  return true;
}

async function validatedComparison(
  value: unknown,
): Promise<HistoryComparisonReceipt | null> {
  if (!comparisonShape(value)) return null;
  return value.comparisonDigest === (await comparisonDigest(value)) ? value : null;
}

async function validatedEnvelope(
  value: unknown,
): Promise<HistoryComparisonEnvelope | null> {
  if (!isRecord(value) || !exactKeys(value, ENVELOPE_KEYS)) return null;
  if (
    value.transportSchemaVersion !== "phios.system-history-comparison-transport.v0.13" ||
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
    return null;
  }
  const comparison = await validatedComparison(value.comparison);
  if (!comparison) return null;
  return {
    transportSchemaVersion: "phios.system-history-comparison-transport.v0.13",
    transport: "loopback-http",
    transportIdentity: "phios-governed-history-reader",
    localOnly: true,
    readOnly: true,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: value.servedAt,
    comparison,
  };
}

export function createHistoryComparisonProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 1800,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    persistent: false as const,
    executionAuthority: false as const,
    async compare(
      fromRecordId: string,
      toRecordId: string,
    ): Promise<HistoryComparisonReceipt | null> {
      if (!stateRecordId(fromRecordId) || !stateRecordId(toRecordId) || fromRecordId === toRecordId) {
        return null;
      }

      const query = new URLSearchParams({
        from: fromRecordId,
        to: toRecordId,
      });
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          "/api/v1/persistent-history-compare?" + query.toString(),
          {
            method: "GET",
            cache: "no-store",
            credentials: "same-origin",
            headers: { accept: "application/json" },
            signal: controller.signal,
          },
        );
        if (!response.ok) return null;
        const payload: unknown = await response.json();
        const envelope = await validatedEnvelope(payload);
        return envelope?.comparison ?? null;
      } catch {
        return null;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const historyComparisonProvider = createHistoryComparisonProvider();
