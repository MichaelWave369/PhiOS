import test from "node:test";
import assert from "node:assert/strict";

import { createLocalObservationServer } from "./localTransport.mjs";

const SHA = (char) => char.repeat(64);

test("local transport forwards human decision without widening it", async () => {
  const seen = [];
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAuthorizationDecisionRecorder: async (payload) => {
      seen.push(payload);
      return { kind: "conflict" };
    },
  });
  const address = await transport.listen();
  try {
    const body = {
      target_inference_receipt_sha256: SHA("a"),
      expected_authority_request_sha256: SHA("b"),
      expected_previous_decision_sha256: null,
      decision: "APPROVE",
      decision_note: "human approval",
    };
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/authorization-console/decisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    assert.equal(response.status, 409);
    assert.deepEqual(seen, [body]);
  } finally {
    await transport.close();
  }
});

test("local transport rejects browser-supplied lease duration", async () => {
  const seen = [];
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkActionLeaseIssuer: async (payload) => {
      seen.push(payload);
      return { kind: "conflict" };
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/authorization-console/leases`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_inference_receipt_sha256: SHA("a"),
          expected_executable_binding_sha256: SHA("b"),
          expected_policy_sha256: SHA("c"),
          expected_policy_set_sha256: SHA("d"),
          expected_enforcement_profile_sha256: SHA("e"),
          expected_authority_epoch_sha256: SHA("f"),
          lease_seconds: 300,
        }),
      },
    );
    assert.equal(response.status, 400);
    assert.deepEqual(seen, []);
  } finally {
    await transport.close();
  }
});
