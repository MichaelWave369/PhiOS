import { describe, expect, it } from "vitest";
import { createHistoryComparisonProvider } from "./historyComparison";

const fromId = "phishell.system-state." + "a".repeat(64);
const toId = "phishell.system-state." + "b".repeat(64);

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (typeof value !== "object" || value === null) return value;
  const record = value as Record<string, unknown>;
  return Object.fromEntries(
    Object.keys(record).sort().map((key) => [key, canonicalize(record[key])]),
  );
}

async function envelope() {
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
  const encoded = new TextEncoder().encode(JSON.stringify(canonicalize(body)));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", encoded);
  comparison.comparisonDigest =
    "sha256:" +
    Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
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

describe("history comparison provider", () => {
  it("accepts a bounded non-persistent canonical comparison", async () => {
    const payload = await envelope();
    const provider = createHistoryComparisonProvider({
      fetcher: async (url, init) => {
        expect(String(url)).toContain("/api/v1/persistent-history-compare?");
        expect(init?.method).toBe("GET");
        return new Response(JSON.stringify(payload), { status: 200 });
      },
    });
    const comparison = await provider.compare(fromId, toId);
    expect(comparison?.persistent).toBe(false);
    expect(comparison?.consecutiveClaimed).toBe(false);
    expect(comparison?.executionAuthority).toBe(false);
  });

  it("rejects an authority-bearing comparison", async () => {
    const payload = await envelope();
    payload.comparison.actionAuthority = true;
    const provider = createHistoryComparisonProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });
    expect(await provider.compare(fromId, toId)).toBeNull();
  });

  it("rejects comparison digest tampering", async () => {
    const payload = await envelope();
    payload.comparison.summaryChanges[0].delta = 999;
    const provider = createHistoryComparisonProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });
    expect(await provider.compare(fromId, toId)).toBeNull();
  });

  it("rejects identical state selections before transport", async () => {
    let called = false;
    const provider = createHistoryComparisonProvider({
      fetcher: async () => {
        called = true;
        return new Response();
      },
    });
    expect(await provider.compare(fromId, fromId)).toBeNull();
    expect(called).toBe(false);
  });
});
