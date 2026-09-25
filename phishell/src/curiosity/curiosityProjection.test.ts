import { describe, expect, it } from "vitest";
import {
  canonicalArtifactToSessionNode,
  createCuriosityProjectionProvider,
} from "./curiosityProjection";

const now = "2026-09-25T20:00:00.000Z";

function envelope() {
  return {
    transportSchemaVersion: "phios.curiosity-transport.v0.4",
    transport: "loopback-http",
    transportIdentity: "phios-curiosity-store-reader",
    localOnly: true,
    readOnly: true,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
    servedAt: now,
    projection: {
      schemaVersion: "phios.curiosity-projection.v0.4",
      source: "canonical-curiosity-store",
      generatedAt: now,
      persistent: true,
      writeAvailable: false,
      writeHoldReason: "action_lease_broker_unavailable",
      limit: 32,
      count: 1,
      omittedArtifactCount: 0,
      artifacts: [{
        schema_version: "phios.curiosity_artifact.v0.1",
        lane: "curiosity",
        artifact_kind: "symbol",
        claim_class: "non_claim",
        title: "Nested bubble gear",
        content: "A symbolic recursive structure.",
        created_at: now,
        created_by: "operator:mikey",
        tags: ["bubble", "gear"],
        evidence_ref_sha256s: [],
        parent_artifact_sha256s: [],
        effect_performed: false,
        operational_authority: false,
        action_authority: false,
        execution_authority: false,
        curiosity_artifact_sha256: "a".repeat(64),
      }],
      returnPointers: [],
      operationalAuthority: false,
      actionAuthority: false,
      executionAuthority: false,
      effectPerformed: false,
    },
  };
}

describe("Curiosity projection provider", () => {
  it("reads a bounded canonical Curiosity projection", async () => {
    const provider = createCuriosityProjectionProvider({
      fetcher: async () => new Response(JSON.stringify(envelope()), { status: 200 }),
    });

    const projection = await provider.read();

    expect(projection?.count).toBe(1);
    expect(projection?.writeAvailable).toBe(false);
    expect(provider.executionAuthority).toBe(false);
  });

  it("rejects authority-bearing canonical artifacts", async () => {
    const payload = envelope();
    payload.projection.artifacts[0].execution_authority = true;
    const provider = createCuriosityProjectionProvider({
      fetcher: async () => new Response(JSON.stringify(payload), { status: 200 }),
    });

    expect(await provider.read()).toBeNull();
  });

  it("maps canonical artifacts into zero-authority session nodes", () => {
    const artifact = envelope().projection.artifacts[0];
    const node = canonicalArtifactToSessionNode(artifact);

    expect(node.id).toBe("canonical:" + "a".repeat(64));
    expect(node.kind).toBe("symbol");
    expect(node.actionAuthority).toBe(false);
    expect(node.executionAuthority).toBe(false);
  });
});
