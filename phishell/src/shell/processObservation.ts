export interface ProcessRow {
  pid: number;
  ppid: number;
  comm: string;
  state: string;
  rssBytes: number;
  threads: number;
}

export interface ProcessStateCounts {
  running: number;
  sleeping: number;
  diskSleep: number;
  stopped: number;
  zombie: number;
  idle: number;
  other: number;
}

export interface ProcessObservationSnapshot {
  schemaVersion: "phios.process-observation.v1";
  source: "procfs-current-user" | "fixture";
  capturedAt: string;
  availability: "available" | "unavailable";
  reason:
    | null
    | "non-linux-host"
    | "current-uid-unavailable"
    | "procfs-unavailable"
    | "transport-unavailable";
  scope: "current-user";
  processLimit: 32;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  currentUid: number | null;
  currentUserProcessCount: number;
  stateCounts: ProcessStateCounts;
  processes: ProcessRow[];
}

export interface ProcessTransportEnvelope {
  transportSchemaVersion: "phios.process-transport.v1";
  transport: "loopback-http";
  transportIdentity: "phishell-local-observer";
  localOnly: true;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  snapshotAgeMs: number;
  observation: ProcessObservationSnapshot;
}

export const FIXTURE_PROCESS_OBSERVATION: ProcessObservationSnapshot = {
  schemaVersion: "phios.process-observation.v1",
  source: "fixture",
  capturedAt: "2026-09-21T00:00:00.000Z",
  availability: "unavailable",
  reason: "transport-unavailable",
  scope: "current-user",
  processLimit: 32,
  readOnly: true,
  executionAuthority: false,
  effectPerformed: false,
  currentUid: null,
  currentUserProcessCount: 0,
  stateCounts: {
    running: 0,
    sleeping: 0,
    diskSleep: 0,
    stopped: 0,
    zombie: 0,
    idle: 0,
    other: 0,
  },
  processes: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isNativeProcessObservation(value: unknown): value is ProcessObservationSnapshot {
  if (!isRecord(value)) return false;

  if (
    value.schemaVersion !== "phios.process-observation.v1" ||
    value.source !== "procfs-current-user" ||
    typeof value.capturedAt !== "string" ||
    Number.isNaN(Date.parse(value.capturedAt)) ||
    !["available", "unavailable"].includes(String(value.availability)) ||
    value.scope !== "current-user" ||
    value.processLimit !== 32 ||
    value.readOnly !== true ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    !(value.currentUid === null || (isInteger(value.currentUid) && value.currentUid >= 0)) ||
    !isInteger(value.currentUserProcessCount) ||
    value.currentUserProcessCount < 0 ||
    !isRecord(value.stateCounts) ||
    !Array.isArray(value.processes) ||
    value.processes.length > 32
  ) {
    return false;
  }

  if (value.availability === "available" && value.reason !== null) return false;
  if (
    value.availability === "unavailable" &&
    !["non-linux-host", "current-uid-unavailable", "procfs-unavailable"].includes(
      String(value.reason),
    )
  ) {
    return false;
  }

  for (const key of [
    "running",
    "sleeping",
    "diskSleep",
    "stopped",
    "zombie",
    "idle",
    "other",
  ]) {
    const count = value.stateCounts[key];
    if (!isInteger(count) || count < 0) return false;
  }

  return value.processes.every(
    (item) =>
      isRecord(item) &&
      isInteger(item.pid) &&
      item.pid > 0 &&
      isInteger(item.ppid) &&
      item.ppid >= 0 &&
      typeof item.comm === "string" &&
      item.comm.length > 0 &&
      item.comm.length <= 128 &&
      typeof item.state === "string" &&
      /^[RSDTtZXIP?]$/.test(item.state) &&
      isFiniteNumber(item.rssBytes) &&
      item.rssBytes >= 0 &&
      isInteger(item.threads) &&
      item.threads >= 1 &&
      !("cmdline" in item) &&
      !("environ" in item) &&
      !("cwd" in item) &&
      !("exe" in item),
  );
}

export function isProcessTransportEnvelope(
  value: unknown,
  maxAgeMs = 5_000,
): value is ProcessTransportEnvelope {
  if (!isRecord(value)) return false;

  return (
    value.transportSchemaVersion === "phios.process-transport.v1" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phishell-local-observer" &&
    value.localOnly === true &&
    value.readOnly === true &&
    value.executionAuthority === false &&
    value.effectPerformed === false &&
    typeof value.servedAt === "string" &&
    !Number.isNaN(Date.parse(value.servedAt)) &&
    isFiniteNumber(value.snapshotAgeMs) &&
    value.snapshotAgeMs >= 0 &&
    value.snapshotAgeMs <= maxAgeMs &&
    isNativeProcessObservation(value.observation)
  );
}

export function createProcessObservationProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  fallback = FIXTURE_PROCESS_OBSERVATION,
  timeoutMs = 1_500,
  maxAgeMs = 5_000,
}: {
  fetcher?: typeof fetch;
  fallback?: ProcessObservationSnapshot;
  timeoutMs?: number;
  maxAgeMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    executionAuthority: false as const,
    async observe(): Promise<ProcessObservationSnapshot> {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetcher("/api/v1/process-observation", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return fallback;

        const envelope: unknown = await response.json();
        if (!isProcessTransportEnvelope(envelope, maxAgeMs)) return fallback;
        return envelope.observation;
      } catch {
        return fallback;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const processObservationProvider = createProcessObservationProvider();
