export type GhostWalkOperatorNoteStatus = "ACTIVE" | "RETRACTED";

export interface GhostWalkOperatorNote {
  schema_version: "phios.ghostwalk_operator_note.v0.28";
  target_inference_receipt_sha256: string;
  note_id: string;
  revision: number;
  revision_sha256: string;
  author_id: string;
  body: string;
  tags: string[];
  status: GhostWalkOperatorNoteStatus;
  created_at: string;
  supersedes_revision_sha256: string | null;
  inference_status: string;
  session_id: string;
  action_observation_sha256: string;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
}

export interface GhostWalkOperatorNoteEnvelope {
  transportSchemaVersion: "phios.ghostwalk-operator-log-transport.v0.28";
  transport: "loopback-http";
  transportIdentity: "phios-ghostwalk-operator-editor";
  localOnly: true;
  annotationMutation: false;
  desktopEffectPerformed: false;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
  note: GhostWalkOperatorNote;
}

export interface GhostWalkOperatorEditEnvelope {
  transportSchemaVersion: "phios.ghostwalk-operator-log-transport.v0.28";
  transport: "loopback-http";
  transportIdentity: "phios-ghostwalk-operator-editor";
  localOnly: true;
  annotationMutation: true;
  desktopEffectPerformed: false;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: true;
  servedAt: string;
  outcome: {
    result: "APPLIED";
    note: GhostWalkOperatorNote;
    annotation_mutation: true;
    desktop_effect_performed: false;
    operational_authority: false;
    action_authority: false;
    execution_authority: false;
  };
}

export type GhostWalkOperatorEditResult =
  | { kind: "applied"; envelope: GhostWalkOperatorEditEnvelope }
  | { kind: "conflict" }
  | { kind: "unavailable" };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function boundedString(value: unknown, maximum = 16384): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function nullableSha(value: unknown): value is string | null {
  return value === null || sha(value);
}

export function isGhostWalkOperatorNote(value: unknown): value is GhostWalkOperatorNote {
  if (!record(value)) return false;
  return (
    value.schema_version === "phios.ghostwalk_operator_note.v0.28" &&
    sha(value.target_inference_receipt_sha256) &&
    boundedString(value.note_id, 512) &&
    typeof value.revision === "number" &&
    Number.isInteger(value.revision) &&
    value.revision >= 1 &&
    sha(value.revision_sha256) &&
    boundedString(value.author_id, 512) &&
    boundedString(value.body, 16384) &&
    Array.isArray(value.tags) &&
    value.tags.length <= 64 &&
    value.tags.every((tag) => boundedString(tag, 128)) &&
    (value.status === "ACTIVE" || value.status === "RETRACTED") &&
    timestamp(value.created_at) &&
    nullableSha(value.supersedes_revision_sha256) &&
    boundedString(value.inference_status, 64) &&
    boundedString(value.session_id, 512) &&
    sha(value.action_observation_sha256) &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false
  );
}

function validBase(
  value: unknown,
  mutation: boolean,
): value is Record<string, unknown> {
  if (!record(value)) return false;
  return (
    value.transportSchemaVersion === "phios.ghostwalk-operator-log-transport.v0.28" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-operator-editor" &&
    value.localOnly === true &&
    value.annotationMutation === mutation &&
    value.desktopEffectPerformed === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === mutation &&
    timestamp(value.servedAt)
  );
}

export function isGhostWalkOperatorNoteEnvelope(
  value: unknown,
): value is GhostWalkOperatorNoteEnvelope {
  return validBase(value, false) && isGhostWalkOperatorNote(value.note);
}

export function isGhostWalkOperatorEditEnvelope(
  value: unknown,
): value is GhostWalkOperatorEditEnvelope {
  if (!validBase(value, true) || !record(value.outcome)) return false;
  return (
    value.outcome.result === "APPLIED" &&
    value.outcome.annotation_mutation === true &&
    value.outcome.desktop_effect_performed === false &&
    value.outcome.operational_authority === false &&
    value.outcome.action_authority === false &&
    value.outcome.execution_authority === false &&
    isGhostWalkOperatorNote(value.outcome.note)
  );
}

export function createGhostWalkOperatorLogClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    async read(targetSha256: string): Promise<GhostWalkOperatorNote | null> {
      if (!sha(targetSha256)) return null;
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          `/api/v1/ghostwalk/operator-log?target=${targetSha256}`,
          {
            method: "GET",
            cache: "no-store",
            credentials: "same-origin",
            headers: { accept: "application/json" },
            signal: controller.signal,
          },
        );
        if (!response.ok) return null;
        const payload: unknown = await response.json();
        return isGhostWalkOperatorNoteEnvelope(payload) ? payload.note : null;
      } catch {
        return null;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },

    async edit({
      targetSha256,
      expectedRevisionSha256,
      body,
      status,
    }: {
      targetSha256: string;
      expectedRevisionSha256: string;
      body: string;
      status: GhostWalkOperatorNoteStatus;
    }): Promise<GhostWalkOperatorEditResult> {
      if (
        !sha(targetSha256) ||
        !sha(expectedRevisionSha256) ||
        !boundedString(body, 16384) ||
        !["ACTIVE", "RETRACTED"].includes(status)
      ) {
        return { kind: "unavailable" };
      }

      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          "/api/v1/ghostwalk/operator-log/revisions",
          {
            method: "POST",
            cache: "no-store",
            credentials: "same-origin",
            headers: {
              accept: "application/json",
              "content-type": "application/json",
            },
            body: JSON.stringify({
              target_inference_receipt_sha256: targetSha256,
              expected_current_revision_sha256: expectedRevisionSha256,
              body,
              status,
            }),
            signal: controller.signal,
          },
        );
        if (response.status === 409) return { kind: "conflict" };
        if (!response.ok) return { kind: "unavailable" };

        const payload: unknown = await response.json();
        if (!isGhostWalkOperatorEditEnvelope(payload)) {
          return { kind: "unavailable" };
        }
        return { kind: "applied", envelope: payload };
      } catch {
        return { kind: "unavailable" };
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const ghostWalkOperatorLogClient =
  createGhostWalkOperatorLogClient();
