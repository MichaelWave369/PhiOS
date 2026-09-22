export type ServiceObservationSource = "systemd-dbus-list-units" | "fixture";
export type ServiceAvailability = "available" | "unavailable";

export interface ServiceStatusObservation {
  id: string;
  label: string;
  unit: string;
  found: boolean;
  description: string | null;
  loadState: string | null;
  activeState: string | null;
  subState: string | null;
}

export interface ServiceObservationSnapshot {
  schemaVersion: "phios.service-observation.v1";
  source: ServiceObservationSource;
  capturedAt: string;
  availability: ServiceAvailability;
  reason:
    | null
    | "non-linux-host"
    | "systemd-runtime-not-present"
    | "system-bus-unavailable"
    | "transport-unavailable";
  allowlistOnly: true;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  services: ServiceStatusObservation[];
}

export interface ServiceTransportEnvelope {
  transportSchemaVersion: "phios.service-transport.v1";
  transport: "loopback-http";
  transportIdentity: "phishell-local-observer";
  localOnly: true;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  snapshotAgeMs: number;
  observation: ServiceObservationSnapshot;
}

export const SERVICE_ALLOWLIST = [
  { id: "dbus", label: "D-Bus", units: ["dbus.service"] },
  { id: "journald", label: "systemd-journald", units: ["systemd-journald.service"] },
  { id: "resolved", label: "systemd-resolved", units: ["systemd-resolved.service"] },
  { id: "network-manager", label: "NetworkManager", units: ["NetworkManager.service"] },
  { id: "networkd", label: "systemd-networkd", units: ["systemd-networkd.service"] },
  { id: "ssh", label: "SSH", units: ["ssh.service", "sshd.service"] },
  { id: "docker", label: "Docker", units: ["docker.service"] },
  { id: "ollama", label: "Ollama", units: ["ollama.service"] },
  { id: "bluetooth", label: "Bluetooth", units: ["bluetooth.service"] },
] as const;

export const FIXTURE_SERVICE_OBSERVATION: ServiceObservationSnapshot = {
  schemaVersion: "phios.service-observation.v1",
  source: "fixture",
  capturedAt: "2026-09-21T00:00:00.000Z",
  availability: "unavailable",
  reason: "transport-unavailable",
  allowlistOnly: true,
  readOnly: true,
  executionAuthority: false,
  effectPerformed: false,
  services: SERVICE_ALLOWLIST.map((definition) => ({
    id: definition.id,
    label: definition.label,
    unit: definition.units[0],
    found: false,
    description: null,
    loadState: null,
    activeState: null,
    subState: null,
  })),
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

function isNativeServiceObservation(value: unknown): value is ServiceObservationSnapshot {
  if (!isRecord(value)) return false;

  if (
    value.schemaVersion !== "phios.service-observation.v1" ||
    value.source !== "systemd-dbus-list-units" ||
    typeof value.capturedAt !== "string" ||
    Number.isNaN(Date.parse(value.capturedAt)) ||
    !["available", "unavailable"].includes(String(value.availability)) ||
    value.allowlistOnly !== true ||
    value.readOnly !== true ||
    value.executionAuthority !== false ||
    value.effectPerformed !== false ||
    !Array.isArray(value.services) ||
    value.services.length !== SERVICE_ALLOWLIST.length
  ) {
    return false;
  }

  if (value.availability === "available" && value.reason !== null) return false;
  if (
    value.availability === "unavailable" &&
    !["non-linux-host", "systemd-runtime-not-present", "system-bus-unavailable"].includes(
      String(value.reason),
    )
  ) {
    return false;
  }

  return value.services.every((service, index) => {
    if (!isRecord(service)) return false;
    const definition = SERVICE_ALLOWLIST[index];

    if (
      service.id !== definition.id ||
      service.label !== definition.label ||
      typeof service.unit !== "string" ||
      !definition.units.some((unit) => unit === service.unit) ||
      typeof service.found !== "boolean"
    ) {
      return false;
    }

    if (service.found) {
      return (
        isNullableString(service.description) &&
        typeof service.loadState === "string" &&
        typeof service.activeState === "string" &&
        typeof service.subState === "string"
      );
    }

    return (
      service.description === null &&
      service.loadState === null &&
      service.activeState === null &&
      service.subState === null
    );
  });
}

export function isServiceTransportEnvelope(
  value: unknown,
  maxAgeMs = 5_000,
): value is ServiceTransportEnvelope {
  if (!isRecord(value)) return false;

  return (
    value.transportSchemaVersion === "phios.service-transport.v1" &&
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
    isNativeServiceObservation(value.observation)
  );
}

export function createServiceObservationProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  fallback = FIXTURE_SERVICE_OBSERVATION,
  timeoutMs = 1_500,
  maxAgeMs = 5_000,
}: {
  fetcher?: typeof fetch;
  fallback?: ServiceObservationSnapshot;
  timeoutMs?: number;
  maxAgeMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    executionAuthority: false as const,
    async observe(): Promise<ServiceObservationSnapshot> {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetcher("/api/v1/service-observation", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return fallback;

        const envelope: unknown = await response.json();
        if (!isServiceTransportEnvelope(envelope, maxAgeMs)) return fallback;
        return envelope.observation;
      } catch {
        return fallback;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const serviceObservationProvider = createServiceObservationProvider();
