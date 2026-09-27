import { describe, expect, it, vi } from "vitest";
import { createGhostWalkAuthorityRequestClient } from "./authorityRequest";

describe("Ghost-Walk AuthorityRequest browser client", () => {
  it("distinguishes not-ready status", async () => {
    const fetcher = vi.fn(async () => new Response("", { status: 404 }));
    const client = createGhostWalkAuthorityRequestClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(client.read("a".repeat(64))).resolves.toEqual({
      kind: "not_ready",
    });
  });

  it("sends only target and admission receipt hashes", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({
        target_inference_receipt_sha256: "a".repeat(64),
        expected_admission_receipt_sha256: "b".repeat(64),
      });
      expect("requester_id" in body).toBe(false);
      expect("requested_scope_value" in body).toBe(false);
      return new Response("", { status: 409 });
    });
    const client = createGhostWalkAuthorityRequestClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(
      client.create({
        targetSha256: "a".repeat(64),
        expectedAdmissionReceiptSha256: "b".repeat(64),
      }),
    ).resolves.toEqual({ kind: "conflict" });
  });
});
