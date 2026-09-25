import { describe, expect, it } from "vitest";
import {
  canonicalParentHashes,
  createCuriosityPersistenceClient,
  nodeToPersistPayload,
} from "./curiosityPersistence";
import { createNode } from "./symbolLab";

const at = "2026-09-25T21:30:00.000Z";

function node(parentIds: string[] = []) {
  return createNode({
    id: "session:1",
    kind: "creative_seed",
    title: "Bubble rhythm",
    content: "Explore the metaphor without declaring a law.",
    tags: ["gear", "music"],
    parentIds,
    createdAt: at,
  });
}

function requestRow() {
  return {
    schemaVersion: "phios.curiosity-persist-request.v0.5",
    requestId: "curiosity-request-" + "a".repeat(32),
    payload: {
      schema_version: "phios.curiosity_persist_payload.v0.4",
      artifact_kind: "creative_seed",
      title: "Bubble rhythm",
      content: "Explore the metaphor without declaring a law.",
      created_at: at,
      created_by: "operator:local",
      tags: ["gear", "music"],
      evidence_ref_sha256s: [],
      parent_artifact_sha256s: [],
    },
    payloadSha256: "b".repeat(64),
    requestedAt: at,
    expiresAt: "2026-09-25T21:40:00.000Z",
    status: "pending",
    reason: "awaiting_operator_approval",
    approvedAt: null,
    artifactSha256: null,
    executionReceipt: null,
    approvalCommand:
      "python -m phios.curiosity_authority_broker approve curiosity-request-" +
      "a".repeat(32),
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
  };
}

describe("Curiosity persistence client", () => {
  it("refuses canonical re-persistence", () => {
    const value = node();
    value.id = "canonical:" + "a".repeat(64);
    expect(nodeToPersistPayload(value)).toBeNull();
  });

  it("requires session parents to be persisted first", () => {
    expect(canonicalParentHashes(node(["session:parent"]))).toBeNull();
    expect(nodeToPersistPayload(node(["session:parent"]))).toBeNull();
  });

  it("preserves canonical parent hashes", () => {
    const parent = "a".repeat(64);
    expect(canonicalParentHashes(node([`canonical:${parent}`]))).toEqual([parent]);
  });

  it("creates a zero-authority persistence request through same-origin host", async () => {
    const row = requestRow();
    let path = "";
    const client = createCuriosityPersistenceClient({
      fetcher: async (input, init) => {
        path = String(input);
        expect(init?.method).toBe("POST");
        return new Response(JSON.stringify(row), { status: 201 });
      },
    });

    const created = await client.request(node());

    expect(path).toBe("/api/v1/curiosity/persist-requests");
    expect(created?.status).toBe("pending");
    expect(created?.actionAuthority).toBe(false);
    expect(created?.executionAuthority).toBe(false);
  });

  it("rejects authority-bearing broker responses", async () => {
    const row = requestRow();
    row.actionAuthority = true;
    const client = createCuriosityPersistenceClient({
      fetcher: async () => new Response(JSON.stringify(row), { status: 201 }),
    });

    expect(await client.request(node())).toBeNull();
  });
});
