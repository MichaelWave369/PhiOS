import { describe, expect, it } from "vitest";
import {
  FIXTURE_SERVICE_OBSERVATION,
  SERVICE_ALLOWLIST,
  createServiceObservationProvider,
  isServiceTransportEnvelope,
} from "./serviceObservation";

function liveObservation() {
  return {
    ...FIXTURE_SERVICE_OBSERVATION,
    source: "systemd-dbus-list-units" as const,
    capturedAt: new Date().toISOString(),
    availability: "available" as const,
    reason: null,
    services: SERVICE_ALLOWLIST.map((definition, index) => ({
      id: definition.id,
      label: definition.label,
      unit: definition.units[0],
      found: index === 0,
      description: index === 0 ? "D-Bus System Message Bus" : null,
      loadState: index === 0 ? "loaded" : null,
      activeState: index === 0 ? "active" : null,
      subState: index === 0 ? "running" : null,
    })),
  };
}

function envelope(snapshotAgeMs = 1) {
  return {
    transportSchemaVersion: "phios.service-transport.v1",
    transport: "loopback-http",
    transportIdentity: "phishell-local-observer",
    localOnly: true,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: new Date().toISOString(),
    snapshotAgeMs,
    observation: liveObservation(),
  };
}

describe("service observation transport", () => {
  it("accepts fresh allowlisted read-only service status", async () => {
    const provider = createServiceObservationProvider({
      fetcher: async () =>
        new Response(JSON.stringify(envelope()), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    });

    const observation = await provider.observe();

    expect(provider.readOnly).toBe(true);
    expect(provider.executionAuthority).toBe(false);
    expect(observation.source).toBe("systemd-dbus-list-units");
    expect(observation.services[0].activeState).toBe("active");
    expect(observation.executionAuthority).toBe(false);
    expect(observation.effectPerformed).toBe(false);
  });

  it("falls back when a service identity escapes the allowlist", async () => {
    const unsafe = JSON.parse(JSON.stringify(envelope())) as {
      observation: { services: Array<Record<string, unknown>> };
    };
    unsafe.observation.services[0].id = "arbitrary-service";
    unsafe.observation.services[0].unit = "arbitrary.service";

    const provider = createServiceObservationProvider({
      fetcher: async () => new Response(JSON.stringify(unsafe), { status: 200 }),
    });

    const observation = await provider.observe();
    expect(observation.source).toBe("fixture");
    expect(observation.reason).toBe("transport-unavailable");
  });

  it("rejects stale or authority-bearing envelopes", () => {
    expect(isServiceTransportEnvelope(envelope(60_000))).toBe(false);
    expect(
      isServiceTransportEnvelope({
        ...envelope(),
        executionAuthority: true,
      }),
    ).toBe(false);
  });
});
