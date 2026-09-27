import test from "node:test";
import assert from "node:assert/strict";

import {
  applyGhostWalkAction,
  fetchGhostWalkStatus,
  validateGhostWalkActionEnvelope,
  validateGhostWalkActionPayload,
  validateGhostWalkStatusEnvelope,
} from "./ghostWalkControlProxy.mjs";

const snapshot = {
  schema_version: "phios.ghostwalk_control_snapshot.v0.25",
  surface_id: "ghostwalk-control:test",
  host_id: "ghostwalk-host:test",
  host_status: "STOPPED",
  run_generation: 2,
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
  sequence: 4,
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

test("validates zero-authority status envelope", () => {
  assert.equal(
    validateGhostWalkStatusEnvelope({ ...base, snapshot }),
    true,
  );
  assert.equal(
    validateGhostWalkStatusEnvelope({
      ...base,
      executionAuthority: true,
      snapshot,
    }),
    false,
  );
});

test("validates bounded Ghost-Walk action payloads", () => {
  assert.equal(
    validateGhostWalkActionPayload({
      action: "START",
      session_id: "demo",
    }),
    true,
  );
  assert.equal(
    validateGhostWalkActionPayload({ action: "START" }),
    false,
  );
  assert.equal(
    validateGhostWalkActionPayload({
      action: "STOP",
      session_id: "demo",
    }),
    false,
  );
  assert.equal(
    validateGhostWalkActionPayload({
      action: "ARM",
      extra: true,
    }),
    false,
  );
});

test("validates action outcome envelope", () => {
  assert.equal(
    validateGhostWalkActionEnvelope({
      ...base,
      controlPlaneMutation: true,
      receipt,
      snapshot,
    }),
    true,
  );
});

test("fetchGhostWalkStatus rejects malformed sidecar evidence", async () => {
  const goodFetcher = async () => ({
    ok: true,
    async json() {
      return { ...base, snapshot };
    },
  });
  assert.ok(await fetchGhostWalkStatus({ fetcher: goodFetcher, port: 3973 }));

  const badFetcher = async () => ({
    ok: true,
    async json() {
      return {
        ...base,
        actionAuthority: true,
        snapshot,
      };
    },
  });
  assert.equal(
    await fetchGhostWalkStatus({ fetcher: badFetcher, port: 3973 }),
    null,
  );
});

test("applyGhostWalkAction forwards only governed control payload", async () => {
  let seenBody = null;
  const fetcher = async (_url, init) => {
    seenBody = JSON.parse(init.body);
    return {
      ok: true,
      async json() {
        return {
          ...base,
          controlPlaneMutation: true,
          receipt,
          snapshot,
        };
      },
    };
  };

  const result = await applyGhostWalkAction(
    { action: "START", session_id: "demo" },
    { fetcher, port: 3973 },
  );
  assert.ok(result);
  assert.deepEqual(seenBody, {
    action: "START",
    session_id: "demo",
  });
});
