import { describe, expect, it } from "vitest";
import { createSystemStateProvider } from "./systemState";

async function digestBody(receipt: Record<string, unknown>) {
  const { receiptDigest: _ignored, ...body } = receipt;
  const bytes = new TextEncoder().encode(JSON.stringify(body));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

async function receipt() {
  const now = new Date().toISOString();
  const value: Record<string, unknown> = {
    schemaVersion: "phios.system-state.v1",
    source: "phios-system-state-composer",
    composedAt: now,
    captureWindowStart: now,
    captureWindowEnd: now,
    captureSkewMs: 0,
    maxCoherentSkewMs: 5000,
    coherence: "coherent",
    componentCount: 5,
    availableComponentCount: 5,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    components: [
      ["host", "phios.host-observation.v1", "linux-readonly-node-probe"],
      ["services", "phios.service-observation.v1", "systemd-dbus-list-units"],
      ["processes", "phios.process-observation.v1", "procfs-current-user"],
      ["packages", "phios.package-observation.v1", "dpkg-status-file"],
      ["devices", "phios.device-observation.v1", "linux-sysfs-bounded"],
    ].map(([id, schemaVersion, source]) => ({
      id,
      schemaVersion,
      source,
      capturedAt: now,
      availability: "available",
      digest: "sha256:" + "a".repeat(64),
      readOnly: true,
      executionAuthority: false,
      effectPerformed: false,
    })),
    summary: {
      cpuLogicalCores: 8,
      memoryTotalBytes: 1024,
      rootStorageTotalBytes: 2048,
      observedServiceCount: 4,
      activeServiceCount: 3,
      currentUserProcessCount: 12,
      installedPackageCount: 500,
      blockDeviceCount: 2,
      networkDeviceCount: 2,
      pciDeviceCount: 8,
      usbDeviceCount: 3,
      drmDeviceCount: 1,
      powerDeviceCount: 0,
    },
    composeDurationMs: 10,
    receiptDigest: "",
  };
  value.receiptDigest = await digestBody(value);
  return value;
}

async function envelope() {
  return {
    transportSchemaVersion: "phios.system-state-transport.v1",
    transport: "loopback-http",
    transportIdentity: "phishell-local-observer",
    localOnly: true,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: new Date().toISOString(),
    snapshotAgeMs: 1,
    receipt: await receipt(),
  };
}

describe("unified system state provider", () => {
  it("accepts a coherent digest-valid receipt", async () => {
    const payload = await envelope();
    const provider = createSystemStateProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });

    const state = await provider.observe();
    expect(state?.coherence).toBe("coherent");
    expect(state?.componentCount).toBe(5);
    expect(state?.executionAuthority).toBe(false);
    expect(state?.effectPerformed).toBe(false);
  });

  it("rejects a receipt whose body no longer matches its digest", async () => {
    const payload = await envelope();
    payload.receipt.summary.installedPackageCount = 999;

    const provider = createSystemStateProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });

    expect(await provider.observe()).toBeNull();
  });

  it("rejects authority-bearing unified state", async () => {
    const payload = await envelope();
    payload.receipt.executionAuthority = true;

    const provider = createSystemStateProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });

    expect(await provider.observe()).toBeNull();
  });
});
