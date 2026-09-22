import type { ComponentId, SystemStateCoherence, SystemStateReceipt, SystemStateSummary } from "./systemState";

export const SYSTEM_HISTORY_LIMIT = 16;

export interface ComponentChange {
  id: ComponentId;
  fromAvailability: "available" | "unavailable";
  toAvailability: "available" | "unavailable";
  availabilityChanged: boolean;
  digestChanged: boolean;
}

export interface SummaryChange {
  metric: keyof SystemStateSummary;
  from: number;
  to: number;
  delta: number;
}

export interface SystemChangeReceipt {
  schemaVersion: "phios.system-change.v1";
  source: "phios-system-change-deriver";
  recordedAt: string;
  sequence: number;
  historyScope: "session-memory";
  persistent: false;
  historyLimit: 16;
  fromReceiptDigest: string;
  toReceiptDigest: string;
  fromComposedAt: string;
  toComposedAt: string;
  elapsedMs: number;
  coherence: {
    from: SystemStateCoherence;
    to: SystemStateCoherence;
    changed: boolean;
  };
  changedComponentCount: number;
  componentChanges: ComponentChange[];
  changedSummaryMetricCount: number;
  summaryChanges: SummaryChange[];
  causeAssigned: false;
  severityAssigned: false;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  changeDigest: string;
}

export interface SystemStateHistory {
  receipts: SystemStateReceipt[];
  changes: SystemChangeReceipt[];
}

const SUMMARY_METRICS: Array<keyof SystemStateSummary> = [
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

async function sha256Json(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `sha256:${hex}`;
}

export async function deriveSystemChangeReceipt(
  previous: SystemStateReceipt,
  current: SystemStateReceipt,
  sequence: number,
): Promise<SystemChangeReceipt> {
  if (!Number.isInteger(sequence) || sequence < 1) {
    throw new Error("system change sequence must be a positive integer");
  }

  const componentChanges = previous.components.map((fromComponent, index) => {
    const toComponent = current.components[index];
    if (!toComponent || toComponent.id !== fromComponent.id) {
      throw new Error("system-state component order changed");
    }
    return {
      id: fromComponent.id,
      fromAvailability: fromComponent.availability,
      toAvailability: toComponent.availability,
      availabilityChanged: fromComponent.availability !== toComponent.availability,
      digestChanged: fromComponent.digest !== toComponent.digest,
    };
  });

  const summaryChanges: SummaryChange[] = [];
  for (const metric of SUMMARY_METRICS) {
    const from = previous.summary[metric];
    const to = current.summary[metric];
    if (from !== to) {
      summaryChanges.push({ metric, from, to, delta: to - from });
    }
  }

  const body = {
    schemaVersion: "phios.system-change.v1" as const,
    source: "phios-system-change-deriver" as const,
    recordedAt: new Date().toISOString(),
    sequence,
    historyScope: "session-memory" as const,
    persistent: false as const,
    historyLimit: SYSTEM_HISTORY_LIMIT as 16,
    fromReceiptDigest: previous.receiptDigest,
    toReceiptDigest: current.receiptDigest,
    fromComposedAt: previous.composedAt,
    toComposedAt: current.composedAt,
    elapsedMs: Math.max(0, Date.parse(current.composedAt) - Date.parse(previous.composedAt)),
    coherence: {
      from: previous.coherence,
      to: current.coherence,
      changed: previous.coherence !== current.coherence,
    },
    changedComponentCount: componentChanges.filter(
      (change) => change.availabilityChanged || change.digestChanged,
    ).length,
    componentChanges,
    changedSummaryMetricCount: summaryChanges.length,
    summaryChanges,
    causeAssigned: false as const,
    severityAssigned: false as const,
    readOnly: true as const,
    executionAuthority: false as const,
    effectPerformed: false as const,
  };

  return {
    ...body,
    changeDigest: await sha256Json(body),
  };
}

export async function appendSystemStateHistory(
  history: SystemStateHistory,
  next: SystemStateReceipt,
): Promise<SystemStateHistory> {
  const previous = history.receipts.at(-1) ?? null;
  const receipts = [...history.receipts, next].slice(-SYSTEM_HISTORY_LIMIT);
  const changes = [...history.changes];

  if (previous) {
    changes.push(await deriveSystemChangeReceipt(previous, next, changes.length + 1));
  }

  return {
    receipts,
    changes: changes.slice(-(SYSTEM_HISTORY_LIMIT - 1)),
  };
}

export const EMPTY_SYSTEM_STATE_HISTORY: SystemStateHistory = {
  receipts: [],
  changes: [],
};
