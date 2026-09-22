export type SystemStateCoherence = "coherent" | "degraded";
export type ComponentId = "host" | "services" | "processes" | "packages" | "devices";

export interface SystemStateComponentReceipt {
  id: ComponentId;
  schemaVersion: string;
  source: string;
  capturedAt: string;
  availability: "available" | "unavailable";
  digest: string;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
}

export interface SystemStateSummary {
  cpuLogicalCores: number;
  memoryTotalBytes: number;
  rootStorageTotalBytes: number;
  observedServiceCount: number;
  activeServiceCount: number;
  currentUserProcessCount: number;
  installedPackageCount: number;
  blockDeviceCount: number;
  networkDeviceCount: number;
  pciDeviceCount: number;
  usbDeviceCount: number;
  drmDeviceCount: number;
  powerDeviceCount: number;
}

export interface SystemStateReceipt {
  schemaVersion: "phios.system-state.v1";
  source: "phios-system-state-composer";
  composedAt: string;
  captureWindowStart: string;
  captureWindowEnd: string;
  captureSkewMs: number;
  maxCoherentSkewMs: 5000;
  coherence: SystemStateCoherence;
  componentCount: 5;
  availableComponentCount: number;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  components: SystemStateComponentReceipt[];
  summary: SystemStateSummary;
  composeDurationMs: number;
  receiptDigest: string;
}

interface SystemStateTransportEnvelope {
  transportSchemaVersion: "phios.system-state-transport.v1";
  transport: "loopback-http";
  transportIdentity: "phishell-local-observer";
  localOnly: true;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  snapshotAgeMs: number;
  receipt: SystemStateReceipt;
}

const COMPONENTS = [
  { id: "host", schemaVersion: "phios.host-observation.v1", source: "linux-readonly-node-probe" },
  { id: "services", schemaVersion: "phios.service-observation.v1", source: "systemd-dbus-list-units" },
  { id: "processes", schemaVersion: "phios.process-observation.v1", source: "procfs-current-user" },
  { id: "packages", schemaVersion: "phios.package-observation.v1", source: "dpkg-status-file" },
  { id: "devices", schemaVersion: "phios.device-observation.v1", source: "linux-sysfs-bounded" },
] as const;

const SUMMARY_KEYS = [
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]) {
  return Object.keys(value).sort().join("\0") === [...expected].sort().join("\0");
}

function isSystemStateReceipt(value: unknown): value is SystemStateReceipt {
  if (!isRecord(value)) return false;

  const topKeys = [
    "schemaVersion", "source", "composedAt", "captureWindowStart", "captureWindowEnd",
    "captureSkewMs", "maxCoherentSkewMs", "coherence", "componentCount",
    "availableComponentCount", "readOnly", "executionAuthority", "effectPerformed",
    "components", "summary", "composeDurationMs", "receiptDigest",
  ];
  if (!exactKeys(value, topKeys)) return false;

  if (
    value.schemaVersion !== "phios.system-state.v1" ||
    value.source !== "phios-system-state-composer" ||
    !isTimestamp(value.composedAt) ||
    !isTimestamp(value.captureWindowStart) ||
    !isTimestamp(value.captureWindowEnd) ||
    !isFiniteNumber(value.captureSkewMs) ||
    value.captureSkewMs < 0 ||
    value.maxCoherentSkewMs !== 5000 ||
    !["coherent", "degraded"].includes(String(value.coherence)) ||
    value.componentCount !== 5 ||
    !isInteger(value.availableComponentCount) ||
    value.availableComponentCount < 0 ||
    value.availableComponentCount > 5 ||
    value.readOnly !== true ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    !Array.isArray(value.components) ||
    value.components.length !== 5 ||
    !isRecord(value.summary) ||
    !isFiniteNumber(value.composeDurationMs) ||
    value.composeDurationMs < 0 ||
    !isSha256(value.receiptDigest)
  ) {
    return false;
  }

  const componentKeys = [
    "id", "schemaVersion", "source", "capturedAt", "availability", "digest",
    "readOnly", "executionAuthority", "effectPerformed",
  ];

  for (let index = 0; index < COMPONENTS.length; index += 1) {
    const component = value.components[index];
    const expected = COMPONENTS[index];
    if (
      !isRecord(component) ||
      !exactKeys(component, componentKeys) ||
      component.id !== expected.id ||
      component.schemaVersion !== expected.schemaVersion ||
      component.source !== expected.source ||
      !isTimestamp(component.capturedAt) ||
      !["available", "unavailable"].includes(String(component.availability)) ||
      !isSha256(component.digest) ||
      component.readOnly !== true ||
      component.executionAuthority !== false ||
      component.effectPerformed !== false
    ) {
      return false;
    }
    if (expected.id === "host" && component.availability !== "available") return false;
  }

  if (!exactKeys(value.summary, SUMMARY_KEYS)) return false;
  for (const key of SUMMARY_KEYS) {
    const metric = value.summary[key];
    if (!isFiniteNumber(metric) || metric < 0) return false;
  }
  if (value.summary.activeServiceCount > value.summary.observedServiceCount) return false;

  const times = value.components.map((component) => Date.parse(component.capturedAt));
  const expectedStart = new Date(Math.min(...times)).toISOString();
  const expectedEnd = new Date(Math.max(...times)).toISOString();
  const expectedSkew = Math.max(...times) - Math.min(...times);
  if (
    value.captureWindowStart !== expectedStart ||
    value.captureWindowEnd !== expectedEnd ||
    value.captureSkewMs !== expectedSkew
  ) {
    return false;
  }

  const available = value.components.filter(
    (component) => component.availability === "available",
  ).length;
  if (value.availableComponentCount !== available) return false;

  const expectedCoherence =
    expectedSkew <= 5000 && available === COMPONENTS.length ? "coherent" : "degraded";
  return value.coherence === expectedCoherence;
}

function isSystemStateTransportEnvelope(
  value: unknown,
  maxAgeMs = 5_000,
): value is SystemStateTransportEnvelope {
  if (!isRecord(value)) return false;

  return (
    value.transportSchemaVersion === "phios.system-state-transport.v1" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phishell-local-observer" &&
    value.localOnly === true &&
    value.readOnly === true &&
    value.executionAuthority === false &&
    value.effectPerformed === false &&
    isTimestamp(value.servedAt) &&
    isFiniteNumber(value.snapshotAgeMs) &&
    value.snapshotAgeMs >= 0 &&
    value.snapshotAgeMs <= maxAgeMs &&
    isSystemStateReceipt(value.receipt)
  );
}

async function sha256Json(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

async function receiptDigestMatches(receipt: SystemStateReceipt) {
  const { receiptDigest: _ignored, ...body } = receipt;
  return (await sha256Json(body)) === receipt.receiptDigest;
}

export function createSystemStateProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
  maxAgeMs = 5_000,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
  maxAgeMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    executionAuthority: false as const,
    async observe(): Promise<SystemStateReceipt | null> {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetcher("/api/v1/system-state", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return null;

        const envelope: unknown = await response.json();
        if (!isSystemStateTransportEnvelope(envelope, maxAgeMs)) return null;
        if (!(await receiptDigestMatches(envelope.receipt))) return null;
        return envelope.receipt;
      } catch {
        return null;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const systemStateProvider = createSystemStateProvider();
