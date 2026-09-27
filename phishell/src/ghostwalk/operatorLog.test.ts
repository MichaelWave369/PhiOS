import { describe, expect, it, vi } from "vitest";
import {
  createGhostWalkOperatorLogClient,
  isGhostWalkOperatorEditEnvelope,
  isGhostWalkOperatorNoteEnvelope,
} from "./operatorLog";

const note = {
  schema_version: "phios.ghostwalk_operator_note.v0.28",
  target_inference_receipt_sha256: "a".repeat(64),
  note_id: "ghostwalk-transition:" + "b".repeat(64),
  revision: 2,
  revision_sha256: "c".repeat(64),
  author_id: "operator:local",
  body: "Correction: opened network adapter properties.",
  tags: ["ghostwalk", "operator-interpretation", "transition-inference"],
  status: "ACTIVE",
  created_at: "2026-09-27T06:31:00.000Z",
  supersedes_revision_sha256: "d".repeat(64),
  inference_status: "CANDIDATES",
  session_id: "demo",
  action_observation_sha256: "b".repeat(64),
  operational_authority: false,
  action_authority: false,
  execution_authority: false,
} as const;

const readEnvelope = {
  transportSchemaVersion: "phios.ghostwalk-operator-log-transport.v0.28",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-operator-editor",
  localOnly: true,
  annotationMutation: false,
  desktopEffectPerformed: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: false,
  servedAt: "2026-09-27T06:31:00.000Z",
  note,
} as const;

const writeEnvelope = {
  transportSchemaVersion: "phios.ghostwalk-operator-log-transport.v0.28",
  transport: "loopback-http",
  transportIdentity: "phios-ghostwalk-operator-editor",
  localOnly: true,
  annotationMutation: true,
  desktopEffectPerformed: false,
  operationalAuthority: false,
  actionAuthority: false,
  executionAuthority: false,
  effectPerformed: true,
  servedAt: "2026-09-27T06:31:00.000Z",
  outcome: {
    result: "APPLIED",
    note,
    annotation_mutation: true,
    desktop_effect_performed: false,
    operational_authority: false,
    action_authority: false,
    execution_authority: false,
  },
} as const;

describe("Ghost-Walk OperatorLog browser client", () => {
  it("validates read and write envelopes separately", () => {
    expect(isGhostWalkOperatorNoteEnvelope(readEnvelope)).toBe(true);
    expect(isGhostWalkOperatorEditEnvelope(writeEnvelope)).toBe(true);
    expect(
      isGhostWalkOperatorEditEnvelope({
        ...writeEnvelope,
        effectPerformed: false,
      }),
    ).toBe(false);
  });

  it("reads the note by exact inference receipt", async () => {
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify(readEnvelope), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = createGhostWalkOperatorLogClient({
      fetcher: fetcher as typeof fetch,
    });
    const current = await client.read("a".repeat(64));
    expect(current?.revision).toBe(2);
  });

  it("posts no browser-controlled author identity", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({
        target_inference_receipt_sha256: "a".repeat(64),
        expected_current_revision_sha256: "c".repeat(64),
        body: "Human correction.",
        status: "ACTIVE",
      });
      expect("author_id" in body).toBe(false);
      return new Response(JSON.stringify(writeEnvelope), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const client = createGhostWalkOperatorLogClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(
      client.edit({
        targetSha256: "a".repeat(64),
        expectedRevisionSha256: "c".repeat(64),
        body: "Human correction.",
        status: "ACTIVE",
      }),
    ).resolves.toMatchObject({ kind: "applied" });
  });

  it("preserves 409 as revision conflict", async () => {
    const fetcher = vi.fn(async () => new Response("", { status: 409 }));
    const client = createGhostWalkOperatorLogClient({
      fetcher: fetcher as typeof fetch,
    });
    await expect(
      client.edit({
        targetSha256: "a".repeat(64),
        expectedRevisionSha256: "c".repeat(64),
        body: "Human correction.",
        status: "ACTIVE",
      }),
    ).resolves.toEqual({ kind: "conflict" });
  });
});
