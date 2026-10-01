import test from "node:test";
import assert from "node:assert/strict";
import { createLocalObservationServer } from "./localTransport.mjs";

for (const endpoint of ["decisions", "bindings", "leases"]) {
  for (const [label, headers] of [
    ["local agent", { "content-type": "application/json" }],
    ["foreign webpage", { "origin": "https://attacker.invalid", "content-type": "text/plain", "sec-fetch-site": "cross-site" }],
    ["foreign Host and agent session", { "host": "attacker.invalid", "authorization": "Bearer agent-session", "content-type": "application/json" }],
  ]) {
    test(`${label} cannot use HTTP ${endpoint}`, async () => {
      const transport = createLocalObservationServer({ port: 0, serveShell: false });
      const address = await transport.listen();
      try {
        const response = await fetch(`http://${address.host}:${address.port}/api/v1/ghostwalk/authorization-console/${endpoint}`, {
          method: "POST", headers,
          body: JSON.stringify({
            target_inference_receipt_sha256: "a".repeat(64),
            expected_authority_request_sha256: "b".repeat(64),
            expected_previous_decision_sha256: null,
            decision: "APPROVE", decision_note: "forged human approval",
          }),
        });
        assert.equal(response.status, 403);
        const result = await response.json();
        assert.equal(result.error, "operator_channel_required");
        assert.equal(result.actionAuthority, false);
        assert.equal(result.executionAuthority, false);
        assert.equal(result.effectPerformed, false);
      } finally { await transport.close(); }
    });
  }
}

test("foreign browser write is refused before proposal dispatch", async () => {
  let dispatched = false;
  const transport = createLocalObservationServer({ port: 0, serveShell: false,
    ghostWalkAuthorityRequestCreator: async () => { dispatched = true; return { kind: "conflict" }; },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(`http://${address.host}:${address.port}/api/v1/ghostwalk/authority-request/requests`, {
      method: "POST", headers: { origin: "https://attacker.invalid", "content-type": "text/plain" },
      body: JSON.stringify({target_inference_receipt_sha256: "a".repeat(64), expected_admission_receipt_sha256: "b".repeat(64)}),
    });
    assert.equal(response.status, 403);
    assert.equal(dispatched, false);
  } finally { await transport.close(); }
});
