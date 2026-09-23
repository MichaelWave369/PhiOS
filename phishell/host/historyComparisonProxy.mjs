import { createHash } from "node:crypto";
import {
  HISTORY_HOST,
  historySidecarPort,
} from "./persistentHistoryProxy.mjs";

const COMPONENT_IDS = ["host", "services", "processes", "packages", "devices"];
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
];

const COMPARISON_KEYS = [
  "schemaVersion",
  "source",
  "generatedAt",
  "comparisonScope",
  "persistent",
  "fromRecordId",
  "toRecordId",
  "fromRecordSha256",
  "toRecordSha256",
  "fromReadAdmissibilityReceiptSha256",
  "toReadAdmissibilityReceiptSha256",
  "fromReceiptDigest",
  "toReceiptDigest",
  "fromComposedAt",
  "toComposedAt",
  "timeDeltaMs",
  "chronologicalOrder",
  "coherence",
  "changedComponentCount",
  "componentChanges",
  "changedSummaryMetricCount",
  "summaryChanges",
  "consecutiveClaimed",
  "causeAssigned",
  "severityAssigned",
  "readOnly",
  "operationalAuthority",
  "actionAuthority",
  "executionAuthority",
  "effectPerformed",
  "comparisonDigest",
];

const COMPONENT_KEYS = [
  "id",
  "fromAvailability",
  "toAvailability",
  "availabilityChanged",
  "fromDigest",
  "toDigest",
  "digestChanged",
];

const SUMMARY_CHANGE_KEYS = ["metric", "from", "to", "delta"];
const ENVELOPE_KEYS = [
  "transportSchemaVersion",
  "transport",
  "transportIdentity",
  "localOnly",
  "readOnly",
  "operationalAuthority",
  "actionAuthority",
  "executionAuthority",
  "effectPerformed",
  "servedAt",
  "comparison",
];

function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value, expected) {
  return (
    record(value) &&
    Object.keys(value).sort().join("\\0") === [...expected].sort().join("\\0")
  );
}

function timestamp(value) {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function prefixedSha(value) {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function stateRecordId(value) {
  return (
    typeof value === "string" &&
    /^phishell\.system-state\.[0-9a-f]{64}$/.test(value)
  );
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (!record(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalize(value[key])]),
  );
}

function comparisonDigest(value) {
  const body = { ...value };
  delete body.comparisonDigest;
  return "sha256:" + createHash("sha256")
    .update(JSON.stringify(canonicalize(body)))
    .digest("hex");
}

function validComparison(value) {
  if (!exactKeys(value, COMPARISON_KEYS)) return false;
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
    !["forward", "reverse", "same-time"].includes(value.chronologicalOrder) ||
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

  if (!exactKeys(value.coherence, ["from", "to", "changed"])) return false;
  if (
    !["coherent", "degraded"].includes(value.coherence.from) ||
    !["coherent", "degraded"].includes(value.coherence.to) ||
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
      !exactKeys(row, COMPONENT_KEYS) ||
      row.id !== COMPONENT_IDS[index] ||
      !["available", "unavailable"].includes(row.fromAvailability) ||
      !["available", "unavailable"].includes(row.toAvailability) ||
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
    (row) => row.availabilityChanged || row.digestChanged,
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
  let previousMetricIndex = -1;
  for (const row of value.summaryChanges) {
    if (!exactKeys(row, SUMMARY_CHANGE_KEYS)) return false;
    const metricIndex = SUMMARY_METRICS.indexOf(row.metric);
    if (
      metricIndex <= previousMetricIndex ||
      !finiteNumber(row.from) ||
      !finiteNumber(row.to) ||
      !finiteNumber(row.delta) ||
      row.delta !== row.to - row.from
    ) {
      return false;
    }
    previousMetricIndex = metricIndex;
  }

  return value.comparisonDigest === comparisonDigest(value);
}

export function validateHistoryComparisonEnvelope(value) {
  if (!exactKeys(value, ENVELOPE_KEYS)) return false;
  return (
    value.transportSchemaVersion === "phios.system-history-comparison-transport.v0.13" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-governed-history-reader" &&
    value.localOnly === true &&
    value.readOnly === true &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === false &&
    timestamp(value.servedAt) &&
    validComparison(value.comparison)
  );
}

export async function fetchHistoryComparison({
  fromRecordId,
  toRecordId,
  fetcher = globalThis.fetch.bind(globalThis),
  port = historySidecarPort(),
  timeoutMs = 1500,
} = {}) {
  if (!stateRecordId(fromRecordId) || !stateRecordId(toRecordId) || fromRecordId === toRecordId) {
    throw new Error("history comparison requires two distinct canonical state record ids");
  }
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error("history sidecar port must be an integer from 1024 to 65535");
  }

  const query = new URLSearchParams({
    from: fromRecordId,
    to: toRecordId,
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(
      "http://" + HISTORY_HOST + ":" + port + "/api/v1/system-history-compare?" + query.toString(),
      {
        method: "GET",
        cache: "no-store",
        headers: { accept: "application/json" },
        signal: controller.signal,
      },
    );
    if (!response.ok) return null;
    const payload = await response.json();
    return validateHistoryComparisonEnvelope(payload) ? payload : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

export { COMPONENT_IDS, SUMMARY_METRICS };
