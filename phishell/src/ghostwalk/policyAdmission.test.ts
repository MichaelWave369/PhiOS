import { describe, expect, it, vi } from "vitest";
import { createGhostWalkPolicyAdmissionClient } from "./policyAdmission";

describe("Ghost-Walk policy admission browser client", () => {
  it("distinguishes not-ready from unavailable", async () => {
    const fetcher = vi.fn(async () => new Response("", { status: 404 }));
    const client = createGhostWalkPolicyAdmissionClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(client.read("a".repeat(64))).resolves.toEqual({
      kind: "not_ready",
    });
  });

  it("record request contains only expected evidence hashes", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({
        target_inference_receipt_sha256: "a".repeat(64),
        expected_accepted_intent_revision_sha256: "b".repeat(64),
        expected_policy_profile_sha256: "c".repeat(64),
      });
      expect("actionAuthority" in body).toBe(false);
      return new Response("", { status: 409 });
    });
    const client = createGhostWalkPolicyAdmissionClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(
      client.record({
        targetSha256: "a".repeat(64),
        expectedAcceptedIntentRevisionSha256: "b".repeat(64),
        expectedPolicyProfileSha256: "c".repeat(64),
      }),
    ).resolves.toEqual({ kind: "conflict" });
  });
});
