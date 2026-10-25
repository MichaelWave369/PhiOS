import test from "node:test";
import assert from "node:assert/strict";
import { PORCH_HEALTH_URL, probeLocalPorchCandidateHealth } from "./porchHealthPreflight.mjs";

const healthy = { status: "READY", protocol_version: 1, candidate: "0.1.2" };
function response(data, init = {}) {
  return new Response(JSON.stringify(data), {
    status: init.status ?? 200,
    headers: { "content-type": init.contentType ?? "application/json" },
  });
}

test("candidate probe is a single bounded fixed-target GET without credentials or mutation", async () => {
  let count = 0;
  const receipt = await probeLocalPorchCandidateHealth({ fetchImpl: async (url, init) => {
    count++;
    assert.equal(url, PORCH_HEALTH_URL);
    assert.equal(init.method, "GET");
    assert.equal(init.redirect, "error");
    assert.equal(init.headers.accept, "application/json");
    assert.equal(Object.hasOwn(init.headers, "authorization"), false);
    assert.ok(init.signal instanceof AbortSignal);
    return response(healthy);
  } });
  assert.equal(count, 1);
  assert.equal(receipt.outcome, "CANDIDATE_RESPONSE_OBSERVED");
  assert.equal(receipt.candidateVersion, "0.1.2");
  assert.equal(receipt.protocolVersion, 1);
  for (const flag of [
    "identityVerified", "authenticationPerformed", "modelExecutionAuthorized",
    "peerAuthority", "operationalAuthority", "actionAuthority", "executionAuthority",
    "effectPerformed",
  ]) assert.equal(receipt[flag], false, flag);
});

test("no response is never promoted to identity or readiness", async () => {
  const receipt = await probeLocalPorchCandidateHealth({ fetchImpl: async () => {
    throw new Error("connection refused");
  } });
  assert.equal(receipt.outcome, "UNAVAILABLE");
  assert.equal(receipt.identityVerified, false);
  assert.equal(receipt.protocolVersion, null);
});

test("malformed JSON, fake version and unexpected fields cannot pass", async () => {
  for (const raw of [
    { status: "READY", protocol_version: 1, candidate: "0.1.2", admin: true },
    { status: "READY", protocol_version: 2, candidate: "0.1.2" },
    { status: "LIVE", protocol_version: 1, candidate: "0.1.2" },
    { status: "READY", protocol_version: 1, candidate: "arbitrary string" },
    { status: "READY", protocol_version: 1, candidate: ["0.1.2"] },
  ]) {
    const receipt = await probeLocalPorchCandidateHealth({
      fetchImpl: async () => response(raw),
    });
    assert.equal(receipt.outcome, "INVALID_RESPONSE");
    assert.equal(receipt.candidateVersion, null);
  }
});

test("wrong MIME, oversized body and redirect are not accepted", async () => {
  const cases = [
    async () => response(healthy, { status: 302 }),
    async () => response(healthy, { contentType: "text/html" }),
    async () => response({ ...healthy, padding: "a".repeat(1400) }),
  ];
  for (const fake of cases) {
    const receipt = await probeLocalPorchCandidateHealth({ fetchImpl: fake });
    assert.notEqual(receipt.outcome, "CANDIDATE_RESPONSE_OBSERVED");
  }
});

test("untrusted health probe never includes a local operator token", async () => {
  const receipt = await probeLocalPorchCandidateHealth({ fetchImpl: async () =>
    response({ ...healthy, token: "SECRET" }),
  });
  assert.equal(receipt.outcome, "INVALID_RESPONSE");
  assert.equal(JSON.stringify(receipt).includes("SECRET"), false);
});
