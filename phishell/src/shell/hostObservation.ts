export type ObservationSource = "fixture" | "linux-readonly-node-probe";

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

export interface HostObservationProvider {
  readonly source: ObservationSource;
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
    reason: "Specific service-state transport is intentionally not bound in PhiShell v0.3.",
  },
};

export function createFixtureObservationProvider(): HostObservationProvider {
  return {
    source: "fixture",
    readOnly: true,
    executionAuthority: false,
    async observe() {
      return FIXTURE_HOST_OBSERVATION;
    },
  };
}

export const hostObservationProvider = createFixtureObservationProvider();
