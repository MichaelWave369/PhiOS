export type ObservationSource = "fixture" | "linux-readonly-node-probe";
export type ObservationProviderMode = "fixture" | "auto-local-transport";

export interface HostIdentityObservation {
  hostname: string;
  platform: string;
  release: string;
  arch: string;
}

export interface SessionIdentityObservation {
  username: string;
  uid: number | null;
  shell: string | null;
  sessionType: string | null;
}

export interface CpuObservation {
  logicalCores: number;
  model: string;
  loadAverage: [number, number, number];
}

export interface MemoryObservation {
  totalBytes: number;
  freeBytes: number;
  usedPercent: number;
}

export interface StorageObservation {
  mount: "/";
  totalBytes: number;
  freeBytes: number;
  usedPercent: number;
}

export interface NetworkInterfaceObservation {
  name: string;
  families: string[];
  internal: boolean;
}

export interface PowerSupplyObservation {
  name: string;
  type: string | null;
  status: string | null;
  capacityPercent: number | null;
}

export interface InitObservation {
  systemdPresent: boolean;
  serviceStatusBound: false;
  reason: string;
}

export interface HostObservationSnapshot {
  schemaVersion: "phios.host-observation.v1";
  source: ObservationSource;
  capturedAt: string;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  host: HostIdentityObservation;
  session: SessionIdentityObservation;
  cpu: CpuObservation;
  memory: MemoryObservation;
  storage: StorageObservation;
  network: NetworkInterfaceObservation[];
  power: PowerSupplyObservation[];
  init: InitObservation;
}

export interface HostObservationTransportEnvelope {
  transportSchemaVersion: "phios.host-transport.v1";
  transport: "loopback-http";
  transportIdentity: "phishell-local-observer";
  localOnly: true;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  snapshotAgeMs: number;
  snapshot: HostObservationSnapshot;
}

export interface HostObservationProvider {
  readonly mode: ObservationProviderMode;
  readonly readOnly: true;
  readonly executionAuthority: false;
  observe(): Promise<HostObservationSnapshot>;
}

export const FIXTURE_HOST_OBSERVATION: HostObservationSnapshot = {
  schemaVersion: "phios.host-observation.v1",
  source: "fixture",
  capturedAt: "2026-09-21T00:00:00.000Z",
  readOnly: true,
  executionAuthority: false,
  effectPerformed: false,
  host: {
    hostname: "phi-host",
    platform: "linux",
    release: "fixture",
    arch: "x64",
  },
  session: {
    username: "operator",
    uid: 1000,
    shell: "/bin/bash",
    sessionType: "wayland",
  },
  cpu: {
    logicalCores: 16,
    model: "Fixture CPU",
    loadAverage: [0.42, 0.31, 0.28],
  },
  memory: {
    totalBytes: 32 * 1024 ** 3,
    freeBytes: 17 * 1024 ** 3,
    usedPercent: 46.9,
  },
  storage: {
    mount: "/",
    totalBytes: 1024 * 1024 ** 3,
    freeBytes: 620 * 1024 ** 3,
    usedPercent: 39.5,
  },
  network: [
    { name: "lo", families: ["IPv4", "IPv6"], internal: true },
    { name: "eth0", families: ["IPv4", "IPv6"], internal: false },
  ],
  power: [],
  init: {
    systemdPresent: true,
    serviceStatusBound: false,
    reason: "Specific service-state transport is intentionally not bound in PhiShell v0.4.",
  },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isHostObservationSnapshot(value: unknown): value is HostObservationSnapshot {
  if (!isRecord(value)) return false;

  const host = value.host;
  const session = value.session;
  const cpu = value.cpu;
  const memory = value.memory;
  const storage = value.storage;
  const network = value.network;
  const power = value.power;
  const init = value.init;

  return (
    value.schemaVersion === "phios.host-observation.v1" &&
    value.source === "linux-readonly-node-probe" &&
    typeof value.capturedAt === "string" &&
    !Number.isNaN(Date.parse(value.capturedAt)) &&
    value.readOnly === true &&
    value.executionAuthority === false &&
    value.effectPerformed === false &&
    isRecord(host) &&
    typeof host.hostname === "string" &&
    typeof host.platform === "string" &&
    typeof host.release === "string" &&
    typeof host.arch === "string" &&
    isRecord(session) &&
    typeof session.username === "string" &&
    (session.uid === null || Number.isInteger(session.uid)) &&
    isNullableString(session.shell) &&
    isNullableString(session.sessionType) &&
    isRecord(cpu) &&
    Number.isInteger(cpu.logicalCores) &&
    typeof cpu.model === "string" &&
    Array.isArray(cpu.loadAverage) &&
    cpu.loadAverage.length === 3 &&
    cpu.loadAverage.every(isFiniteNumber) &&
    isRecord(memory) &&
    isFiniteNumber(memory.totalBytes) &&
    isFiniteNumber(memory.freeBytes) &&
    isFiniteNumber(memory.usedPercent) &&
    isRecord(storage) &&
    storage.mount === "/" &&
    isFiniteNumber(storage.totalBytes) &&
    isFiniteNumber(storage.freeBytes) &&
    isFiniteNumber(storage.usedPercent) &&
    Array.isArray(network) &&
    network.length <= 64 &&
    network.every(
      (item) =>
        isRecord(item) &&
        typeof item.name === "string" &&
        Array.isArray(item.families) &&
        item.families.every((family) => typeof family === "string") &&
        typeof item.internal === "boolean" &&
        !("address" in item) &&
        !("mac" in item),
    ) &&
    Array.isArray(power) &&
    power.length <= 32 &&
    power.every(
      (item) =>
        isRecord(item) &&
        typeof item.name === "string" &&
        isNullableString(item.type) &&
        isNullableString(item.status) &&
        (item.capacityPercent === null || isFiniteNumber(item.capacityPercent)),
    ) &&
    isRecord(init) &&
    typeof init.systemdPresent === "boolean" &&
    init.serviceStatusBound === false &&
    typeof init.reason === "string"
  );
}

export function isHostObservationTransportEnvelope(
  value: unknown,
  maxAgeMs = 5_000,
): value is HostObservationTransportEnvelope {
  if (!isRecord(value)) return false;
  if (
    value.transportSchemaVersion !== "phios.host-transport.v1" ||
    value.transport !== "loopback-http" ||
    value.transportIdentity !== "phishell-local-observer" ||
    value.localOnly !== true ||
    value.readOnly !== true ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    typeof value.servedAt !== "string" ||
    Number.isNaN(Date.parse(value.servedAt)) ||
    !isFiniteNumber(value.snapshotAgeMs) ||
    value.snapshotAgeMs < 0 ||
    value.snapshotAgeMs > maxAgeMs
  ) {
    return false;
  }

  return isHostObservationSnapshot(value.snapshot);
}

export function createFixtureObservationProvider(): HostObservationProvider {
  return {
    mode: "fixture",
    readOnly: true,
    executionAuthority: false,
    async observe() {
      return FIXTURE_HOST_OBSERVATION;
    },
  };
}

export function createLocalTransportObservationProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  fallback = FIXTURE_HOST_OBSERVATION,
  timeoutMs = 1_500,
  maxAgeMs = 5_000,
}: {
  fetcher?: typeof fetch;
  fallback?: HostObservationSnapshot;
  timeoutMs?: number;
  maxAgeMs?: number;
} = {}): HostObservationProvider {
  return {
    mode: "auto-local-transport",
    readOnly: true,
    executionAuthority: false,
    async observe() {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetcher("/api/v1/host-observation", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return fallback;

        const envelope: unknown = await response.json();
        if (!isHostObservationTransportEnvelope(envelope, maxAgeMs)) {
          return fallback;
        }
        return envelope.snapshot;
      } catch {
        return fallback;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const hostObservationProvider = createLocalTransportObservationProvider();
