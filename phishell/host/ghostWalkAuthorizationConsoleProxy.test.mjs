import test from "node:test";
import assert from "node:assert/strict";

import {
  issueGhostWalkActionLease,
  recordGhostWalkAuthorizationDecision,
  validateAuthorizationDecisionPayload,
  validateLeaseIssuePayload,
} from "./ghostWalkAuthorizationConsoleProxy.mjs";

const SHA = (char) => char.repeat(64);

test("authorization decision payload cannot choose executable fields", () => {
  const valid = {
    target_inference_receipt_sha256: SHA("a"),
    expected_authority_request_sha256: SHA("b"),
    expected_previous_decision_sha256: null,
    decision: "APPROVE",
    decision_note: "approve exact request",
  };
  assert.equal(validateAuthorizationDecisionPayload(valid), true);
  assert.equal(
    validateAuthorizationDecisionPayload({
      ...valid,
      capability_id: "desktop.interaction.click",
    }),
    false,
  );
});

test("lease payload is optimistic-concurrency hashes only", () => {
  const valid = {
    target_inference_receipt_sha256: SHA("a"),
    expected_executable_binding_sha256: SHA("b"),
    expected_policy_sha256: SHA("c"),
    expected_policy_set_sha256: SHA("d"),
    expected_enforcement_profile_sha256: SHA("e"),
    expected_authority_epoch_sha256: SHA("f"),
  };
  assert.equal(validateLeaseIssuePayload(valid), true);
  assert.equal(
    validateLeaseIssuePayload({ ...valid, lease_seconds: 300 }),
    false,
  );
  assert.equal(
    validateLeaseIssuePayload({
      ...valid,
      payload: { x: 1 },
    }),
    false,
  );
});

test("decision proxy forwards exact payload to loopback sidecar", async () => {
  const seen = [];
  const fetcher = async (url, init) => {
    seen.push({
      url: String(url),
      body: JSON.parse(String(init.body)),
    });
    return new Response("", { status: 409 });
  };
  const payload = {
    target_inference_receipt_sha256: SHA("a"),
    expected_authority_request_sha256: SHA("b"),
    expected_previous_decision_sha256: null,
    decision: "HOLD",
    decision_note: null,
  };
  const result = await recordGhostWalkAuthorizationDecision(payload, {
    fetcher,
    port: 3973,
  });
  assert.deepEqual(result, { kind: "conflict" });
  assert.equal(seen.length, 1);
  assert.match(
    seen[0].url,
    /\/api\/v1\/ghostwalk\/authorization-console\/decisions$/,
  );
  assert.deepEqual(seen[0].body, payload);
});

test("lease proxy never adds authority-bearing fields", async () => {
  const seen = [];
  const fetcher = async (_url, init) => {
    seen.push(JSON.parse(String(init.body)));
    return new Response("", { status: 409 });
  };
  const payload = {
    target_inference_receipt_sha256: SHA("a"),
    expected_executable_binding_sha256: SHA("b"),
    expected_policy_sha256: SHA("c"),
    expected_policy_set_sha256: SHA("d"),
    expected_enforcement_profile_sha256: SHA("e"),
    expected_authority_epoch_sha256: SHA("f"),
  };
  const result = await issueGhostWalkActionLease(payload, {
    fetcher,
    port: 3973,
  });
  assert.deepEqual(result, { kind: "conflict" });
  assert.deepEqual(seen[0], payload);
  assert.equal("payload" in seen[0], false);
  assert.equal("permissions" in seen[0], false);
  assert.equal("lease_seconds" in seen[0], false);
});
