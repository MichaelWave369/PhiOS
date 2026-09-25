import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchCuriosityProjection,
  validateCuriosityProjectionEnvelope,
} from "./curiosityProjectionProxy.mjs";

function envelope() {
  const now = new Date().toISOString();
  const artifactSha = "a".repeat(64);
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
        curiosity_artifact_sha256: artifactSha,
      }],
      returnPointers: [],
      operationalAuthority: false,
      actionAuthority: false,
      executionAuthority: false,
      effectPerformed: false,
    },
  };
}

test("accepts bounded zero-authority Curiosity projection", async () => {
  const payload = envelope();
  assert.equal(validateCuriosityProjectionEnvelope(payload), true);

  let requested = "";
  const result = await fetchCuriosityProjection({
    port: 3971,
    fetcher: async (url, init) => {
      requested = String(url);
      assert.equal(init.method, "GET");
      return new Response(JSON.stringify(payload), { status: 200 });
    },
  });

  assert.equal(result?.projection.count, 1);
  assert.equal(requested, "http://127.0.0.1:3971/api/v1/curiosity?limit=32");
});

test("rejects authority-bearing Curiosity artifact", () => {
  const payload = envelope();
  payload.projection.artifacts[0].execution_authority = true;
  assert.equal(validateCuriosityProjectionEnvelope(payload), false);
});

test("rejects projection claiming browser write availability", () => {
  const payload = envelope();
  payload.projection.writeAvailable = true;
  assert.equal(validateCuriosityProjectionEnvelope(payload), false);
});

test("returns null when Curiosity sidecar is unavailable", async () => {
  const result = await fetchCuriosityProjection({
    port: 3971,
    fetcher: async () => {
      throw new Error("connection refused");
    },
  });
  assert.equal(result, null);
});
