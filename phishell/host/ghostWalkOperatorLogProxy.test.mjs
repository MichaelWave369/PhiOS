import test from "node:test";
import assert from "node:assert/strict";

import {
  applyGhostWalkOperatorEdit,
  fetchGhostWalkOperatorNote,
  validateGhostWalkOperatorEditEnvelope,
  validateGhostWalkOperatorEditPayload,
  validateGhostWalkOperatorNoteEnvelope,
} from "./ghostWalkOperatorLogProxy.mjs";

const note = {
  schema_version: "phios.ghostwalk_operator_note.v0.28",
  target_inference_receipt_sha256: "a".repeat(64),
  note_id: "ghostwalk-transition:" + "b".repeat(64),
  revision: 2,
  revision_sha256: "c".repeat(64),
  author_id: "operator:local",
  body: "Correction: opened network adapter properties.",
  tags: ["ghostwalk", "operator-interpretation", "transition-inference"],
  status: "ACTIVE",
  created_at: "2026-09-27T06:31:00.000Z",
  supersedes_revision_sha256: "d".repeat(64),
  inference_status: "CANDIDATES",
  session_id: "demo",
  action_observation_sha256: "b".repeat(64),
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
};

const readEnvelope = {
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
  note,
};

const writeEnvelope = {
  ...readEnvelope,
  annotationMutation: true,
  effectPerformed: true,
  outcome: {
    result: "APPLIED",
    note,
    annotation_mutation: true,
    desktop_effect_performed: false,
    operational_authority: false,
    action_authority: false,
    execution_authority: false,
  },
};
delete writeEnvelope.note;

test("validates read-only OperatorLog projection", () => {
  assert.equal(validateGhostWalkOperatorNoteEnvelope(readEnvelope), true);
  assert.equal(
    validateGhostWalkOperatorNoteEnvelope({
      ...readEnvelope,
      actionAuthority: true,
    }),
    false,
  );
});

test("validates annotation write as a real persistent effect", () => {
  assert.equal(validateGhostWalkOperatorEditEnvelope(writeEnvelope), true);
  assert.equal(
    validateGhostWalkOperatorEditEnvelope({
      ...writeEnvelope,
      effectPerformed: false,
    }),
    false,
  );
});

test("edit payload excludes browser-controlled author identity", () => {
  const payload = {
    target_inference_receipt_sha256: "a".repeat(64),
    expected_current_revision_sha256: "c".repeat(64),
    body: "Human correction.",
    status: "ACTIVE",
  };
  assert.equal(validateGhostWalkOperatorEditPayload(payload), true);
  assert.equal(
    validateGhostWalkOperatorEditPayload({
      ...payload,
      author_id: "browser:fake",
    }),
    false,
  );
});

test("fetches current operator note only after validation", async () => {
  const fetcher = async () => ({
    ok: true,
    async json() {
      return readEnvelope;
    },
  });
  assert.ok(
    await fetchGhostWalkOperatorNote("a".repeat(64), {
      fetcher,
      port: 3973,
    }),
  );
});

test("preserves stale-edit conflict signal", async () => {
  const fetcher = async () => ({
    status: 409,
    ok: false,
    async json() {
      return {};
    },
  });
  assert.deepEqual(
    await applyGhostWalkOperatorEdit(
      {
        target_inference_receipt_sha256: "a".repeat(64),
        expected_current_revision_sha256: "c".repeat(64),
        body: "Human correction.",
        status: "ACTIVE",
      },
      { fetcher, port: 3973 },
    ),
    { kind: "conflict" },
  );
});
