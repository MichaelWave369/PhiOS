import { describe, expect, it, vi } from "vitest";
import {
  createGhostWalkControlClient,
  isGhostWalkActionEnvelope,
  isGhostWalkStatusEnvelope,
} from "./control";

const snapshot = {
  schema_version: "phios.ghostwalk_control_snapshot.v0.25",
  surface_id: "ghostwalk-control:test",
  host_id: "ghostwalk-host:test",
  host_status: "STOPPED",
  run_generation: 1,
  session_id: null,
  listener_alive: false,
  tick_alive: false,
  baseline_armed: false,
  baseline_sha256: null,
  baseline_age_ms: null,
  baseline_refresh_due: false,
  error_type: null,
  recovery_state: "NONE",
  recovery_receipt_sha256: null,
  available_actions: ["START", "STATUS"],
  last_action_observation_sha256: null,
  learned_transitions: [],
  recent_issues: [],
  observed_at: "2026-09-27T05:50:00.000Z",
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  snapshot_sha256: "a".repeat(64),
};

const base = {
  transportSchemaVersion: "phios.ghostwalk-control-transport.v0.26",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-control",
  localOnly: true,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T05:50:00.000Z",
};

const receipt = {
  schema_version: "phios.ghostwalk_control_receipt.v0.25",
  surface_id: "ghostwalk-control:test",
  sequence: 1,
  action: "START",
  requested_session_id: "demo",
  result: "APPLIED",
  reason: "HOST_STARTED",
  before_snapshot_sha256: "b".repeat(64),
  after_snapshot_sha256: "c".repeat(64),
  applied_at: "2026-09-27T05:50:01.000Z",
  error_type: null,
  previous_receipt_sha256: "d".repeat(64),
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  receipt_sha256: "e".repeat(64),
};

describe("Ghost-Walk browser control contract", () => {
  it("accepts only zero-authority status evidence", () => {
    expect(isGhostWalkStatusEnvelope({ ...base, snapshot })).toBe(true);
    expect(
      isGhostWalkStatusEnvelope({
        ...base,
        executionAuthority: true,
        snapshot,
      }),
    ).toBe(false);
  });

  it("accepts a validated control outcome", () => {
    expect(
      isGhostWalkActionEnvelope({
        ...base,
        controlPlaneMutation: true,
        receipt,
        snapshot,
      }),
    ).toBe(true);
  });

  it("does not fabricate a snapshot when transport is unavailable", async () => {
    const fetcher = vi.fn(async () => new Response("", { status: 503 }));
    const client = createGhostWalkControlClient({ fetcher: fetcher as typeof fetch });
    await expect(client.status()).resolves.toBeNull();
  });

  it("sends START with one bounded session id", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        action: "START",
        session_id: "demo",
      });
      return new Response(
        JSON.stringify({
          ...base,
          controlPlaneMutation: true,
          receipt,
          snapshot,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    const client = createGhostWalkControlClient({ fetcher: fetcher as typeof fetch });
    await expect(client.apply("START", "demo")).resolves.not.toBeNull();
  });
});
