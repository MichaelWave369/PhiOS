import test from "node:test";
import assert from "node:assert/strict";

import {
  applyGhostWalkAcceptedIntentMutation,
  fetchGhostWalkAcceptedIntent,
  validateGhostWalkAcceptedIntentEnvelope,
  validateGhostWalkAcceptedIntentMutationPayload,
} from "./ghostWalkAcceptedIntentProxy.mjs";

const intent = {
  schema_version: "phios.ghostwalk_accepted_intent_revision.v0.29",
  target_inference_receipt_sha256: "a".repeat(64),
  source_operator_note_revision_sha256: "b".repeat(64),
  revision: 1,
  intent_family: "OPEN",
  intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
  status: "ACTIVE",
  accepted_by: "operator:local",
  accepted_at: "2026-09-27T06:55:00.000Z",
  supersedes_revision_sha256: null,
  human_intent_confirmed: true,
  causation_proven: false,
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  revision_sha256: "c".repeat(64),
};

const readEnvelope = {
  transportSchemaVersion: "phios.ghostwalk-accepted-intent-transport.v0.29",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-accepted-intent",
  localOnly: true,
  intentMutation: false,
  desktopEffectPerformed: false,
  policyAuthority: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T06:55:00.000Z",
  intent,
};

const writeEnvelope = {
  ...readEnvelope,
  intentMutation: true,
  effectPerformed: true,
};

test("validates typed accepted intent without policy authority", () => {
  assert.equal(
    validateGhostWalkAcceptedIntentEnvelope(readEnvelope, { mutated: false }),
    true,
  );
  assert.equal(
    validateGhostWalkAcceptedIntentEnvelope({
      ...readEnvelope,
      policyAuthority: true,
    }, { mutated: false }),
    false,
  );
});

test("rejects mismatched family and intent code", () => {
  assert.equal(
    validateGhostWalkAcceptedIntentEnvelope({
      ...readEnvelope,
      intent: {
        ...intent,
        intent_code: "TOGGLE_NETWORK_ADAPTER_PROPERTIES",
      },
    }, { mutated: false }),
    false,
  );
});

test("accept payload excludes authority and accepted-by fields", () => {
  const payload = {
    operation: "ACCEPT",
    target_inference_receipt_sha256: "a".repeat(64),
    source_operator_note_revision_sha256: "b".repeat(64),
    intent_family: "OPEN",
    intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
    expected_current_revision_sha256: null,
  };
  assert.equal(validateGhostWalkAcceptedIntentMutationPayload(payload), true);
  assert.equal(
    validateGhostWalkAcceptedIntentMutationPayload({
      ...payload,
      accepted_by: "browser:fake",
    }),
    false,
  );
});

test("read distinguishes no accepted intent from unavailable sidecar", async () => {
  const missingFetcher = async () => ({
    status: 404,
    ok: false,
  });
  assert.deepEqual(
    await fetchGhostWalkAcceptedIntent("a".repeat(64), {
      fetcher: missingFetcher,
      port: 3973,
    }),
    { kind: "none" },
  );

  const foundFetcher = async () => ({
    status: 200,
    ok: true,
    async json() {
      return readEnvelope;
    },
  });
  const found = await fetchGhostWalkAcceptedIntent("a".repeat(64), {
    fetcher: foundFetcher,
    port: 3973,
  });
  assert.equal(found?.kind, "found");
});

test("write validates persistent intent mutation envelope", async () => {
  const fetcher = async (_url, init) => {
    const body = JSON.parse(init.body);
    assert.equal("policyAuthority" in body, false);
    assert.equal("accepted_by" in body, false);
    return {
      status: 200,
      ok: true,
      async json() {
        return writeEnvelope;
      },
    };
  };
  const result = await applyGhostWalkAcceptedIntentMutation(
    {
      operation: "ACCEPT",
      target_inference_receipt_sha256: "a".repeat(64),
      source_operator_note_revision_sha256: "b".repeat(64),
      intent_family: "OPEN",
      intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
      expected_current_revision_sha256: null,
    },
    { fetcher, port: 3973 },
  );
  assert.equal(result?.kind, "applied");
});
