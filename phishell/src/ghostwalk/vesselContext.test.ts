import { describe, expect, it, vi } from "vitest";
import {
  buildGhostWalkVesselContext,
  createGhostWalkVesselContextProvider,
} from "./vesselContext";
import type { GhostWalkSnapshot } from "./control";

function snapshot(
  overrides: Partial<GhostWalkSnapshot> = {},
): GhostWalkSnapshot {
  return {
    schema_version: "phios.ghostwalk_control_snapshot.v0.25",
    surface_id: "ghostwalk-control:test",
    host_id: "ghostwalk-host:test",
    host_status: "RUNNING",
    run_generation: 7,
    session_id: "demo",
    listener_alive: true,
    tick_alive: true,
    baseline_armed: true,
    baseline_sha256: "a".repeat(64),
    baseline_age_ms: 180,
    baseline_refresh_due: false,
    error_type: null,
    recovery_state: "NONE",
    recovery_receipt_sha256: null,
    available_actions: ["DISARM", "STATUS", "STOP"],
    last_action_observation_sha256: "b".repeat(64),
    learned_transitions: [],
    recent_issues: [],
    observed_at: "2026-09-27T06:20:00.000Z",
    operational_authority: false,
    action_authority: false,
    execution_authority: false,
    snapshot_sha256: "c".repeat(64),
    ...overrides,
  };
}

function envelope(item: GhostWalkSnapshot) {
  return {
    transportSchemaVersion: "phios.ghostwalk-control-transport.v0.26",
    transport: "loopback-http",
    transportIdentity: "phios-ghostwalk-control",
    localOnly: true,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: "2026-09-27T06:20:00.000Z",
    snapshot: item,
  };
}

describe("Ghost-Walk PhiVessel context", () => {
  it("projects healthy runtime evidence without lifecycle controls", () => {
    const context = buildGhostWalkVesselContext(snapshot());

    expect(context.health).toBe("healthy");
    expect(context.baselineFresh).toBe(true);
    expect(context.canStart).toBe(false);
    expect(context.canStop).toBe(false);
    expect(context.canArm).toBe(false);
    expect(context.canDisarm).toBe(false);
    expect(context.lifecycleAuthority).toBe(false);
    expect("available_actions" in context).toBe(false);
  });

  it("explains degraded baseline state", () => {
    const context = buildGhostWalkVesselContext(
      snapshot({
        host_status: "DEGRADED",
        baseline_refresh_due: true,
      }),
    );

    expect(context.health).toBe("attention");
    expect(context.summary).toContain("baseline refresh is due");
  });

  it("explains abandoned-run recovery without implying recovered baseline", () => {
    const context = buildGhostWalkVesselContext(
      snapshot({
        recovery_state: "PRIOR_RUN_ABANDONED",
        recovery_receipt_sha256: "d".repeat(64),
      }),
    );

    expect(context.explanation.join(" ")).toContain("fresh baseline");
  });

  it("provider performs GET only and returns the stripped read model", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe("GET");
      expect(init?.body).toBeUndefined();
      return new Response(JSON.stringify(envelope(snapshot())), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    const provider = createGhostWalkVesselContextProvider({
      fetcher: fetcher as typeof fetch,
    });
    const context = await provider.read();

    expect(context?.hostStatus).toBe("RUNNING");
    expect(context?.executionAuthority).toBe(false);
    expect(context?.lifecycleAuthority).toBe(false);
  });

  it("fails closed on non-zero authority evidence", async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ...envelope(snapshot()),
          actionAuthority: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const provider = createGhostWalkVesselContextProvider({
      fetcher: fetcher as typeof fetch,
    });
    await expect(provider.read()).resolves.toBeNull();
  });
});
