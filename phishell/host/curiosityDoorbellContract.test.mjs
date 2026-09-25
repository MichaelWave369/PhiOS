import test from "node:test";
import assert from "node:assert/strict";
import {
  validateCuriosityPersistRequestId,
  validateCuriosityPersistRequestPayload,
} from "./curiosityDoorbellContract.mjs";

function payload() {
  return {
    artifact_kind: "creative_seed",
    title: "Bubble rhythm",
    content: "Explore the metaphor without claiming it is verified physics.",
    created_at: "2026-09-25T21:30:00.000Z",
    tags: ["gear", "music"],
    evidence_ref_sha256s: [],
    parent_artifact_sha256s: [],
  };
}

test("accepts exact bounded canonical Curiosity request payload", () => {
  assert.equal(validateCuriosityPersistRequestPayload(payload()), true);
});

test("rejects authority or approval fields from browser", () => {
  const value = payload();
  value.approved = true;
  assert.equal(validateCuriosityPersistRequestPayload(value), false);
});

test("rejects noncanonical tags", () => {
  const value = payload();
  value.tags = ["music", "gear"];
  assert.equal(validateCuriosityPersistRequestPayload(value), false);
});

test("rejects oversize content", () => {
  const value = payload();
  value.content = "x".repeat(32769);
  assert.equal(validateCuriosityPersistRequestPayload(value), false);
});

test("accepts only canonical broker request ids", () => {
  assert.equal(
    validateCuriosityPersistRequestId("curiosity-request-" + "a".repeat(32)),
    true,
  );
  assert.equal(validateCuriosityPersistRequestId("../../operator-approval"), false);
});
