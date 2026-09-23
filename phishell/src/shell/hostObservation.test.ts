import { describe, expect, it } from "vitest";
import {
  FIXTURE_HOST_OBSERVATION,
  createFixtureObservationProvider,
  createLocalTransportObservationProvider,
  isHostObservationTransportEnvelope,
  type HostObservationSnapshot,
} from "./hostObservation";

function liveSnapshot(): HostObservationSnapshot {
  return {
    ...FIXTURE_HOST_OBSERVATION,
    source: "linux-readonly-node-probe",
    capturedAt: new Date().toISOString(),
    host: { ...FIXTURE_HOST_OBSERVATION.host, release: "live-test" },
    network: FIXTURE_HOST_OBSERVATION.network.map((entry) => ({ ...entry })),
    power: FIXTURE_HOST_OBSERVATION.power.map((entry) => ({ ...entry })),
  };
}

function envelope(snapshot = liveSnapshot(), snapshotAgeMs = 1) {
  return {
    transportSchemaVersion: "phios.host-transport.v1",
    transport: "loopback-http",
    transportIdentity: "phishell-local-observer",
    localOnly: true,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: new Date().toISOString(),
    snapshotAgeMs,
    snapshot,
  };
}

describe("host observation contract", () => {
  it("keeps read-only observation separate from execution authority", async () => {
    const provider = createFixtureObservationProvider();
    const snapshot = await provider.observe();

    expect(provider.readOnly).toBe(true);
    expect(provider.executionAuthority).toBe(false);
    expect(snapshot.readOnly).toBe(true);
    expect(snapshot.executionAuthority).toBe(false);
    expect(snapshot.effectPerformed).toBe(false);
    expect(snapshot.source).toBe("fixture");
  });

  it("does not model network addresses or MAC values in the shell contract", () => {
    for (const network of FIXTURE_HOST_OBSERVATION.network) {
      expect(Object.keys(network).sort()).toEqual(["families", "internal", "name"]);
    }
  });

  it("does not claim service-status binding", () => {
    expect(FIXTURE_HOST_OBSERVATION.init.serviceStatusBound).toBe(false);
  });

  it("accepts a fresh same-contract loopback observation", async () => {
    const provider = createLocalTransportObservationProvider({
      fetcher: async () =>
        new Response(JSON.stringify(envelope()), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    });

    const snapshot = await provider.observe();

    expect(provider.mode).toBe("auto-local-transport");
    expect(snapshot.source).toBe("linux-readonly-node-probe");
    expect(snapshot.host.release).toBe("live-test");
    expect(snapshot.executionAuthority).toBe(false);
    expect(snapshot.effectPerformed).toBe(false);
  });

  it("accepts a degraded live host snapshot without replacing known facts with fixture data", async () => {
    const partial = {
      ...liveSnapshot(),
      availability: "unavailable" as const,
      reason: "network-enumeration-unavailable",
      network: [],
    };
    const provider = createLocalTransportObservationProvider({
      fetcher: async () =>
        new Response(JSON.stringify(envelope(partial)), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    });

    const snapshot = await provider.observe();

    expect(snapshot.source).toBe("linux-readonly-node-probe");
    expect(snapshot.availability).toBe("unavailable");
    expect(snapshot.reason).toBe("network-enumeration-unavailable");
    expect(snapshot.network).toEqual([]);
    expect(snapshot.host.release).toBe("live-test");
    expect(snapshot.cpu.logicalCores).toBe(FIXTURE_HOST_OBSERVATION.cpu.logicalCores);
  });

  it("falls back rather than trusting a stale transport snapshot", async () => {
    const provider = createLocalTransportObservationProvider({
      maxAgeMs: 5_000,
      fetcher: async () =>
        new Response(JSON.stringify(envelope(liveSnapshot(), 60_000)), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    });

    const snapshot = await provider.observe();
    expect(snapshot.source).toBe("fixture");
  });

  it("rejects an envelope that claims execution authority", () => {
    const unsafe = { ...envelope(), executionAuthority: true };
    expect(isHostObservationTransportEnvelope(unsafe)).toBe(false);
  });

  it("rejects network records that smuggle address data", () => {
    const snapshot = liveSnapshot();
    const unsafeNetwork = [
      ...snapshot.network,
      { name: "eth9", families: ["IPv4"], internal: false, mac: "00:00:00:00:00:00" },
    ];
    const unsafe = envelope({ ...snapshot, network: unsafeNetwork } as HostObservationSnapshot);

    expect(isHostObservationTransportEnvelope(unsafe)).toBe(false);
  });
});
