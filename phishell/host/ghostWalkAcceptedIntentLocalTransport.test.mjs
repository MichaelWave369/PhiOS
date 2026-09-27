import test from "node:test";
import assert from "node:assert/strict";

import { createLocalObservationServer } from "./localTransport.mjs";

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

test("local transport distinguishes no accepted intent", async () => {
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAcceptedIntentFetcher: async () => ({ kind: "none" }),
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/accepted-intent?target=${"a".repeat(64)}`,
    );
    assert.equal(response.status, 404);
  } finally {
    await transport.close();
  }
});

test("local transport proxies accepted intent read", async () => {
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAcceptedIntentFetcher: async () => ({
      kind: "found",
      envelope: readEnvelope,
    }),
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/accepted-intent?target=${"a".repeat(64)}`,
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.intent.intent_code, "OPEN_NETWORK_ADAPTER_PROPERTIES");
    assert.equal(payload.policyAuthority, false);
  } finally {
    await transport.close();
  }
});

test("local transport proxies intent acceptance without policy authority", async () => {
  const seen = [];
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAcceptedIntentMutator: async (payload) => {
      seen.push(payload);
      return { kind: "applied", envelope: writeEnvelope };
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/accepted-intent/revisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          operation: "ACCEPT",
          target_inference_receipt_sha256: "a".repeat(64),
          source_operator_note_revision_sha256: "b".repeat(64),
          intent_family: "OPEN",
          intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
          expected_current_revision_sha256: null,
        }),
      },
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.effectPerformed, true);
    assert.equal(payload.desktopEffectPerformed, false);
    assert.equal(payload.policyAuthority, false);
    assert.equal(seen.length, 1);
  } finally {
    await transport.close();
  }
});

test("local transport rejects browser policy authority injection", async () => {
  let called = false;
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkAcceptedIntentMutator: async () => {
      called = true;
      return null;
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/accepted-intent/revisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          operation: "ACCEPT",
          target_inference_receipt_sha256: "a".repeat(64),
          source_operator_note_revision_sha256: "b".repeat(64),
          intent_family: "OPEN",
          intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
          expected_current_revision_sha256: null,
          policyAuthority: true,
        }),
      },
    );
    assert.equal(response.status, 400);
    assert.equal(called, false);
  } finally {
    await transport.close();
  }
});
