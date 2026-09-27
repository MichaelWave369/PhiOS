import test from "node:test";
import assert from "node:assert/strict";

import { createLocalObservationServer } from "./localTransport.mjs";

const noteEnvelope = {
  transportSchemaVersion: "phios.ghostwalk-operator-log-transport.v0.28",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-operator-editor",
  localOnly: true,
  annotationMutation: false,
  desktopEffectPerformed: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T06:31:00.000Z",
  note: {
    schema_version: "phios.ghostwalk_operator_note.v0.28",
    target_inference_receipt_sha256: "a".repeat(64),
    note_id: "ghostwalk-transition:" + "b".repeat(64),
    revision: 1,
    revision_sha256: "c".repeat(64),
    author_id: "operator:local",
    body: "Machine summary.",
    tags: ["ghostwalk", "transition-inference"],
    status: "ACTIVE",
    created_at: "2026-09-27T06:30:00.000Z",
    supersedes_revision_sha256: null,
    inference_status: "CANDIDATES",
    session_id: "demo",
    action_observation_sha256: "b".repeat(64),
    operational_authority: false,
    action_authority: false,
    execution_authority: false,
  },
};

const editEnvelope = {
  ...noteEnvelope,
  annotationMutation: true,
  effectPerformed: true,
  outcome: {
    result: "APPLIED",
    note: {
      ...noteEnvelope.note,
      revision: 2,
      revision_sha256: "d".repeat(64),
      body: "Correction: opened network adapter properties.",
      tags: ["ghostwalk", "operator-interpretation", "transition-inference"],
      supersedes_revision_sha256: "c".repeat(64),
    },
    annotation_mutation: true,
    desktop_effect_performed: false,
    operational_authority: false,
    action_authority: false,
    execution_authority: false,
  },
};
delete editEnvelope.note;

test("local transport proxies current OperatorLog revision", async () => {
  let seenTarget = null;
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkOperatorNoteFetcher: async (target) => {
      seenTarget = target;
      return noteEnvelope;
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/operator-log?target=${"a".repeat(64)}`,
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.note.revision, 1);
    assert.equal(payload.effectPerformed, false);
    assert.equal(seenTarget, "a".repeat(64));
  } finally {
    await transport.close();
  }
});

test("local transport proxies append-only OperatorLog edit", async () => {
  const seen = [];
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkOperatorEditApplier: async (payload) => {
      seen.push(payload);
      return { kind: "applied", envelope: editEnvelope };
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/operator-log/revisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_inference_receipt_sha256: "a".repeat(64),
          expected_current_revision_sha256: "c".repeat(64),
          body: "Correction: opened network adapter properties.",
          status: "ACTIVE",
        }),
      },
    );
    assert.equal(response.status, 200);
    const payload = await response.json();
    assert.equal(payload.effectPerformed, true);
    assert.equal(payload.desktopEffectPerformed, false);
    assert.equal(payload.outcome.note.revision, 2);
    assert.equal(seen.length, 1);
  } finally {
    await transport.close();
  }
});

test("local transport preserves OperatorLog revision conflicts", async () => {
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkOperatorEditApplier: async () => ({ kind: "conflict" }),
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/operator-log/revisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_inference_receipt_sha256: "a".repeat(64),
          expected_current_revision_sha256: "c".repeat(64),
          body: "Stale correction.",
          status: "ACTIVE",
        }),
      },
    );
    assert.equal(response.status, 409);
  } finally {
    await transport.close();
  }
});

test("local transport rejects browser author injection", async () => {
  let called = false;
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    ghostWalkOperatorEditApplier: async () => {
      called = true;
      return null;
    },
  });
  const address = await transport.listen();
  try {
    const response = await fetch(
      `http://${address.host}:${address.port}/api/v1/ghostwalk/operator-log/revisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_inference_receipt_sha256: "a".repeat(64),
          expected_current_revision_sha256: "c".repeat(64),
          body: "Correction.",
          status: "ACTIVE",
          author_id: "browser:fake",
        }),
      },
    );
    assert.equal(response.status, 400);
    assert.equal(called, false);
  } finally {
    await transport.close();
  }
});
