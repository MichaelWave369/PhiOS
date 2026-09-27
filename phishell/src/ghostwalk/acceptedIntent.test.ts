import { describe, expect, it, vi } from "vitest";
import {
  createGhostWalkAcceptedIntentClient,
  isGhostWalkAcceptedIntentEnvelope,
} from "./acceptedIntent";

const intent = {
  schema_version: "phios.ghostwalk_accepted_intent_revision.v0.29",
  target_inference_receipt_sha256: "a".repeat(64),
  source_operator_note_revision_sha256: "b".repeat(64),
  revision: 1,
  intent_family: "OPEN",
  intent_code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
  status: "ACTIVE",
  accepted_by: "operator:local",
  accepted_at: "2026-09-27T06:55:00.000Z",
  supersedes_revision_sha256: null,
  human_intent_confirmed: true,
  causation_proven: false,
  policy_authority: false,
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
  revision_sha256: "c".repeat(64),
} as const;

const envelope = {
  transportSchemaVersion: "phios.ghostwalk-accepted-intent-transport.v0.29",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-accepted-intent",
  localOnly: true,
  intentMutation: false,
  desktopEffectPerformed: false,
  policyAuthority: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T06:55:00.000Z",
  intent,
} as const;

describe("Ghost-Walk accepted intent browser client", () => {
  it("validates typed intent while rejecting policy authority", () => {
    expect(isGhostWalkAcceptedIntentEnvelope(envelope, false)).toBe(true);
    expect(
      isGhostWalkAcceptedIntentEnvelope({
        ...envelope,
        policyAuthority: true,
      }, false),
    ).toBe(false);
  });

  it("distinguishes no intent from unavailable", async () => {
    const fetcher = vi.fn(async () => new Response("", { status: 404 }));
    const client = createGhostWalkAcceptedIntentClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(client.read("a".repeat(64))).resolves.toEqual({ kind: "none" });
  });

  it("does not send policy or accepted-by fields", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.intent_family).toBe("OPEN");
      expect(body.intent_code).toBe("OPEN_NETWORK_ADAPTER_PROPERTIES");
      expect("policyAuthority" in body).toBe(false);
      expect("accepted_by" in body).toBe(false);
      return new Response(
        JSON.stringify({
          ...envelope,
          intentMutation: true,
          effectPerformed: true,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      );
    });
    const client = createGhostWalkAcceptedIntentClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(
      client.accept({
        targetSha256: "a".repeat(64),
        sourceOperatorNoteRevisionSha256: "b".repeat(64),
        family: "OPEN",
        code: "OPEN_NETWORK_ADAPTER_PROPERTIES",
        expectedCurrentRevisionSha256: null,
      }),
    ).resolves.toMatchObject({ kind: "applied" });
  });

  it("rejects code whose prefix disagrees with family", async () => {
    const fetcher = vi.fn();
    const client = createGhostWalkAcceptedIntentClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(
      client.accept({
        targetSha256: "a".repeat(64),
        sourceOperatorNoteRevisionSha256: "b".repeat(64),
        family: "OPEN",
        code: "TOGGLE_NETWORK_ADAPTER_PROPERTIES",
        expectedCurrentRevisionSha256: null,
      }),
    ).resolves.toEqual({ kind: "unavailable" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
