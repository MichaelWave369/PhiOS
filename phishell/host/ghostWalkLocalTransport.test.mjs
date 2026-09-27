import test from "node:test";
import assert from "node:assert/strict";

import { createLocalObservationServer } from "./localTransport.mjs";

const snapshot = {
  schema_version: "phios.ghostwalk_control_snapshot.v0.25",
  surface_id: "ghostwalk-control:test",
  host_id: "ghostwalk-host:test",
  host_status: "STOPPED",
  run_generation: 0,
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
  observed_at: "2026-09-27T06:00:00.000Z",
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
  servedAt: "2026-09-27T06:00:00.000Z",
};

const receipt = {
  schema_version: "phios.ghostwalk_control_receipt.v0.25",
  surface_id: "ghostwalk-control:test",
  sequence: 0,
  action: "START",
  requested_session_id: "demo",
  result: "APPLIED",
  reason: "HOST_STARTED",
  before_snapshot_sha256: "b".repeat(64),
  after_snapshot_sha256: "c".repeat(64),
  applied_at: "2026-09-27T06:00:01.000Z",
  error_type: null,
  previous_receipt_sha256: null,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  receipt_sha256: "d".repeat(64),
};

test("PhiShell loopback transport proxies Ghost-Walk status and actions", async () => {
  const seen = [];
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkStatusFetcher: async () => ({ ...base, snapshot }),
    ghostWalkActionApplier: async (payload) => {
      seen.push(payload);
      return {
        ...base,
        controlPlaneMutation: true,
        receipt,
        snapshot,
      };
    },
  });
  const address = await transport.listen();

  try {
    const statusResponse = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk`,
    );
    assert.equal(statusResponse.status, 200);
    const status = await statusResponse.json();
    assert.equal(status.executionAuthority, false);
    assert.equal(status.snapshot.host_status, "STOPPED");

    const actionResponse = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/actions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "START",
          session_id: "demo",
        }),
      },
    );
    assert.equal(actionResponse.status, 200);
    const action = await actionResponse.json();
    assert.equal(action.controlPlaneMutation, true);
    assert.equal(action.effectPerformed, false);
    assert.deepEqual(seen, [
      { action: "START", session_id: "demo" },
    ]);
  } finally {
    await transport.close();
  }
});

test("PhiShell transport rejects invalid Ghost-Walk control before proxying", async () => {
  let called = false;
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkActionApplier: async () => {
      called = true;
      return null;
    },
  });
  const address = await transport.listen();

  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/actions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "STOP",
          session_id: "forbidden",
        }),
      },
    );
    assert.equal(response.status, 400);
    assert.equal(called, false);
  } finally {
    await transport.close();
  }
});
