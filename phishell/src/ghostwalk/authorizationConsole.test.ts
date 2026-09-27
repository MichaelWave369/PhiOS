import { describe, expect, it, vi } from "vitest";
import { createGhostWalkAuthorizationConsoleClient } from "./authorizationConsole";

describe("Ghost-Walk human authorization console client", () => {
  it("sends only explicit human decision evidence", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({
        target_inference_receipt_sha256: "a".repeat(64),
        expected_authority_request_sha256: "b".repeat(64),
        expected_previous_decision_sha256: null,
        decision: "APPROVE",
        decision_note: "approve exact request",
      });
      expect("capability_id" in body).toBe(false);
      expect("payload" in body).toBe(false);
      expect("lease_seconds" in body).toBe(false);
      return new Response("", { status: 409 });
    });
    const client = createGhostWalkAuthorizationConsoleClient({
      fetcher: fetcher as typeof fetch,
    });

    await expect(
      client.recordDecision({
        targetSha256: "a".repeat(64),
        expectedAuthorityRequestSha256: "b".repeat(64),
        expectedPreviousDecisionSha256: null,
        decision: "APPROVE",
        decisionNote: "approve exact request",
      }),
    ).resolves.toEqual({ kind: "conflict" });
  });

  it("lease issuance cannot supply payload, permission, or duration", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(Object.keys(body).sort()).toEqual([
        "expected_authority_epoch_sha256",
        "expected_enforcement_profile_sha256",
        "expected_executable_binding_sha256",
        "expected_policy_set_sha256",
        "expected_policy_sha256",
        "target_inference_receipt_sha256",
      ]);
      expect("payload" in body).toBe(false);
      expect("permissions" in body).toBe(false);
      expect("lease_seconds" in body).toBe(false);
      expect("principal_id" in body).toBe(false);
      expect("issuer_id" in body).toBe(false);
      return new Response("", { status: 409 });
    });
    const client = createGhostWalkAuthorizationConsoleClient({
      fetcher: fetcher as typeof fetch,
    });

    await expect(
      client.issueLease({
        targetSha256: "a".repeat(64),
        expectedExecutableBindingSha256: "b".repeat(64),
        expectedPolicySha256: "c".repeat(64),
        expectedPolicySetSha256: "d".repeat(64),
        expectedEnforcementProfileSha256: "e".repeat(64),
        expectedAuthorityEpochSha256: "f".repeat(64),
      }),
    ).resolves.toEqual({ kind: "conflict" });
  });
});
