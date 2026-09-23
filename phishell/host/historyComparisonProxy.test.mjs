import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import {
  fetchHistoryComparison,
  validateHistoryComparisonEnvelope,
} from "./historyComparisonProxy.mjs";

const fromId = "phishell.system-state." + "a".repeat(64);
const toId = "phishell.system-state." + "b".repeat(64);

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
  );
}

function envelope() {
  const comparison = {
    schemaVersion: "phios.system-history-comparison.v0.13",
    source: "governed-memory-system-history-comparator",
    generatedAt: "2026-09-23T04:06:00.000Z",
    comparisonScope: "canonical-state-pair",
    persistent: false,
    fromRecordId: fromId,
    toRecordId: toId,
    fromRecordSha256: "c".repeat(64),
    toRecordSha256: "d".repeat(64),
    fromReadAdmissibilityReceiptSha256: "e".repeat(64),
    toReadAdmissibilityReceiptSha256: "f".repeat(64),
    fromReceiptDigest: "sha256:" + "1".repeat(64),
    toReceiptDigest: "sha256:" + "2".repeat(64),
    fromComposedAt: "2026-09-23T04:00:00.000Z",
    toComposedAt: "2026-09-23T04:05:00.000Z",
    timeDeltaMs: 300000,
    chronologicalOrder: "forward",
    coherence: { from: "coherent", to: "degraded", changed: true },
    changedComponentCount: 1,
    componentChanges: ["host", "services", "processes", "packages", "devices"].map(
      (id, index) => ({
        id,
        fromAvailability: "available",
        toAvailability: "available",
        availabilityChanged: false,
        fromDigest: "sha256:" + (index === 0 ? "3" : "4").repeat(64),
        toDigest: "sha256:" + (index === 0 ? "5" : "4").repeat(64),
        digestChanged: index === 0,
      }),
    ),
    changedSummaryMetricCount: 1,
    summaryChanges: [{ metric: "cpuLogicalCores", from: 8, to: 12, delta: 4 }],
    consecutiveClaimed: false,
    causeAssigned: false,
    severityAssigned: false,
    readOnly: true,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
    comparisonDigest: "",
  };

  const body = { ...comparison };
  delete body.comparisonDigest;
  comparison.comparisonDigest =
    "sha256:" + createHash("sha256").update(JSON.stringify(canonicalize(body))).digest("hex");

  return {
    transportSchemaVersion: "phios.system-history-comparison-transport.v0.13",
    transport: "loopback-http",
    transportIdentity: "phios-governed-history-reader",
    localOnly: true,
    readOnly: true,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: "2026-09-23T04:06:00.000Z",
    comparison,
  };
}

test("accepts bounded non-authoritative canonical comparison", async () => {
  const payload = envelope();
  assert.equal(validateHistoryComparisonEnvelope(payload), true);

  let requested = "";
  const result = await fetchHistoryComparison({
    fromRecordId: fromId,
    toRecordId: toId,
    port: 3970,
    fetcher: async (url, init) => {
      requested = String(url);
      assert.equal(init.method, "GET");
      return new Response(JSON.stringify(payload), { status: 200 });
    },
  });

  assert.equal(result?.comparison.persistent, false);
  assert.match(requested, /127\.0\.0\.1:3970\/api\/v1\/system-history-compare\?/);
  assert.match(requested, /from=phishell\.system-state/);
  assert.match(requested, /to=phishell\.system-state/);
});

test("rejects authority-bearing comparison", () => {
  const payload = envelope();
  payload.comparison.executionAuthority = true;
  assert.equal(validateHistoryComparisonEnvelope(payload), false);
});

test("rejects a consecutive-event claim", () => {
  const payload = envelope();
  payload.comparison.consecutiveClaimed = true;
  assert.equal(validateHistoryComparisonEnvelope(payload), false);
});

test("rejects tampered comparison digest", () => {
  const payload = envelope();
  payload.comparison.summaryChanges[0].delta = 99;
  assert.equal(validateHistoryComparisonEnvelope(payload), false);
});

test("requires two distinct canonical state record ids", async () => {
  await assert.rejects(
    fetchHistoryComparison({
      fromRecordId: fromId,
      toRecordId: fromId,
      fetcher: async () => new Response(),
    }),
    /two distinct canonical state record ids/,
  );
});
