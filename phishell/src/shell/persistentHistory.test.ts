import { describe, expect, it } from "vitest";
import { createPersistentHistoryProvider } from "./persistentHistory";

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

describe("persistent history provider", () => {
  it("accepts a governed canonical projection", async () => {
    const payload = envelope();
    const provider = createPersistentHistoryProvider({
      fetcher: async (url, init) => {
        expect(url).toBe("/api/v1/persistent-history");
        expect(init?.method).toBe("GET");
        return new Response(JSON.stringify(payload), { status: 200 });
      },
    });

    const projection = await provider.read();
    expect(projection?.count).toBe(1);
    expect(projection?.records[0].kind).toBe("state");
    expect(projection?.executionAuthority).toBe(false);
  });

  it("returns null on safe unavailable projection", async () => {
    const provider = createPersistentHistoryProvider({
      fetcher: async () => new Response(
        JSON.stringify({ error: "persistent_history_unavailable" }),
        { status: 503 },
      ),
    });
    expect(await provider.read()).toBeNull();
  });

  it("rejects authority-bearing canonical history", async () => {
    const payload = envelope();
    payload.projection.executionAuthority = true;
    const provider = createPersistentHistoryProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });
    expect(await provider.read()).toBeNull();
  });

  it("rejects a record whose read receipt is not in the projection ledger", async () => {
    const payload = envelope();
    payload.projection.readAdmissibilityReceiptSha256s[0] = "f".repeat(64);
    const provider = createPersistentHistoryProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });
    expect(await provider.read()).toBeNull();
  });
});
