import { describe, expect, it } from "vitest";
import {
  FIXTURE_PROCESS_OBSERVATION,
  createProcessObservationProvider,
  isProcessTransportEnvelope,
} from "./processObservation";

function liveObservation() {
  return {
    ...FIXTURE_PROCESS_OBSERVATION,
    source: "procfs-current-user" as const,
    capturedAt: new Date().toISOString(),
    availability: "available" as const,
    reason: null,
    currentUid: 1000,
    currentUserProcessCount: 1,
    stateCounts: {
      running: 1,
      sleeping: 0,
      diskSleep: 0,
      stopped: 0,
      zombie: 0,
      idle: 0,
      other: 0,
    },
    processes: [
      {
        pid: 123,
        ppid: 1,
        comm: "node",
        state: "R",
        rssBytes: 4096,
        threads: 4,
      },
    ],
  };
}

function envelope(snapshotAgeMs = 1) {
  return {
    transportSchemaVersion: "phios.process-transport.v1",
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

describe("process observation transport", () => {
  it("accepts fresh current-user process metadata", async () => {
    const provider = createProcessObservationProvider({
      fetcher: async () =>
        new Response(JSON.stringify(envelope()), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    });

    const observation = await provider.observe();

    expect(provider.readOnly).toBe(true);
    expect(provider.executionAuthority).toBe(false);
    expect(observation.source).toBe("procfs-current-user");
    expect(observation.scope).toBe("current-user");
    expect(observation.processes[0].comm).toBe("node");
    expect(observation.executionAuthority).toBe(false);
    expect(observation.effectPerformed).toBe(false);
  });

  it("falls back when sensitive process metadata is smuggled into a row", async () => {
    const unsafe = JSON.parse(JSON.stringify(envelope())) as {
      observation: { processes: Array<Record<string, unknown>> };
    };
    unsafe.observation.processes[0].cmdline = "node secret.js --token=hidden";

    const provider = createProcessObservationProvider({
      fetcher: async () => new Response(JSON.stringify(unsafe), { status: 200 }),
    });

    const observation = await provider.observe();
    expect(observation.source).toBe("fixture");
    expect(observation.reason).toBe("transport-unavailable");
  });

  it("rejects stale or authority-bearing envelopes", () => {
    expect(isProcessTransportEnvelope(envelope(60_000))).toBe(false);
    expect(
      isProcessTransportEnvelope({
        ...envelope(),
        executionAuthority: true,
      }),
    ).toBe(false);
  });
});
