import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchPersistentHistoryProjection,
  validatePersistentHistoryEnvelope,
} from "./persistentHistoryProxy.mjs";

function envelope() {
  const now = new Date().toISOString();
  const readHash = "a".repeat(64);
  return {
    transportSchemaVersion: "phios.system-history-transport.v0.12",
    transport: "loopback-http",
    transportIdentity: "phios-governed-history-reader",
    localOnly: true,
    readOnly: true,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: now,
    projection: {
      schemaVersion: "phios.system-history-projection.v0.12",
      source: "governed-memory-system-history",
      generatedAt: now,
      status: "ok",
      historyScope: "canonical-memory",
      persistent: true,
      limit: 16,
      count: 1,
      omittedRecordCount: 0,
      records: [{
        kind: "state",
        recordId: "phishell.system-state." + "b".repeat(64),
        revision: 1,
        recordSha256: "c".repeat(64),
        contentSha256: "d".repeat(64),
        createdAt: now,
        scopeId: "system-history",
        classification: "system-observation",
        retentionPolicyId: "retain-system-history",
        epistemicKind: "source",
        exactnessClass: null,
        derivedFrom: [],
        transformationLineageSha256s: [],
        readAdmissibilityReceiptSha256: readHash,
        payload: {
          schemaVersion: "phios.system-state.v1",
          source: "phios-system-state-composer",
          readOnly: true,
          executionAuthority: false,
          effectPerformed: false,
          receiptDigest: "sha256:" + "e".repeat(64),
        },
      }],
      readAdmissibilityReceiptSha256s: [readHash],
      readOnly: true,
      causeAssigned: false,
      severityAssigned: false,
      operationalAuthority: false,
      actionAuthority: false,
      executionAuthority: false,
      effectPerformed: false,
    },
  };
}

test("accepts bounded governed persistent history", async () => {
  const payload = envelope();
  assert.equal(validatePersistentHistoryEnvelope(payload), true);

  let requested = "";
  const result = await fetchPersistentHistoryProjection({
    port: 3970,
    fetcher: async (url, init) => {
      requested = String(url);
      assert.equal(init.method, "GET");
      return new Response(JSON.stringify(payload), { status: 200 });
    },
  });

  assert.equal(result?.projection.count, 1);
  assert.equal(requested, "http://127.0.0.1:3970/api/v1/system-history?limit=16");
});

test("rejects authority-bearing projection", async () => {
  const payload = envelope();
  payload.projection.executionAuthority = true;
  assert.equal(validatePersistentHistoryEnvelope(payload), false);
});

test("rejects mismatched read-admissibility receipts", () => {
  const payload = envelope();
  payload.projection.readAdmissibilityReceiptSha256s[0] = "f".repeat(64);
  assert.equal(validatePersistentHistoryEnvelope(payload), false);
});

test("rejects change records without canonical lineage", () => {
  const payload = envelope();
  const row = payload.projection.records[0];
  row.kind = "change";
  row.recordId = "phishell.system-change." + "b".repeat(64);
  row.epistemicKind = "derived";
  row.exactnessClass = "REVERSIBLE";
  row.derivedFrom = [];
  row.transformationLineageSha256s = ["1".repeat(64)];
  row.payload = {
    schemaVersion: "phios.system-change.v1",
    source: "phios-system-change-deriver",
    causeAssigned: false,
    severityAssigned: false,
    readOnly: true,
    executionAuthority: false,
    effectPerformed: false,
    changeDigest: "sha256:" + "2".repeat(64),
  };
  assert.equal(validatePersistentHistoryEnvelope(payload), false);
});

test("returns null when governed history sidecar is unavailable", async () => {
  const result = await fetchPersistentHistoryProjection({
    port: 3970,
    fetcher: async () => {
      throw new Error("connection refused");
    },
  });
  assert.equal(result, null);
});
