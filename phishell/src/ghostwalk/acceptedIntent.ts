export type GhostWalkIntentFamily =
  | "NAVIGATE"
  | "OPEN"
  | "CLOSE"
  | "SELECT"
  | "TOGGLE"
  | "ENTER_TEXT"
  | "SUBMIT"
  | "CONFIRM"
  | "CANCEL"
  | "OTHER";

export type GhostWalkAcceptedIntentStatus = "ACTIVE" | "REVOKED";

export interface GhostWalkAcceptedIntent {
  schema_version: "phios.ghostwalk_accepted_intent_revision.v0.29";
  target_inference_receipt_sha256: string;
  source_operator_note_revision_sha256: string;
  revision: number;
  intent_family: GhostWalkIntentFamily;
  intent_code: string;
  status: GhostWalkAcceptedIntentStatus;
  accepted_by: string;
  accepted_at: string;
  supersedes_revision_sha256: string | null;
  human_intent_confirmed: true;
  causation_proven: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  revision_sha256: string;
}

export interface GhostWalkAcceptedIntentEnvelope {
  transportSchemaVersion: "phios.ghostwalk-accepted-intent-transport.v0.29";
  transport: "loopback-http";
  transportIdentity: "phios-ghostwalk-accepted-intent";
  localOnly: true;
  intentMutation: boolean;
  desktopEffectPerformed: false;
  policyAuthority: false;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: boolean;
  servedAt: string;
  intent: GhostWalkAcceptedIntent;
}

export type GhostWalkAcceptedIntentReadResult =
  | { kind: "found"; intent: GhostWalkAcceptedIntent }
  | { kind: "none" }
  | { kind: "unavailable" };

export type GhostWalkAcceptedIntentMutationResult =
  | { kind: "applied"; intent: GhostWalkAcceptedIntent }
  | { kind: "conflict" }
  | { kind: "unavailable" };

export const GHOSTWALK_INTENT_FAMILIES: GhostWalkIntentFamily[] = [
  "NAVIGATE",
  "OPEN",
  "CLOSE",
  "SELECT",
  "TOGGLE",
  "ENTER_TEXT",
  "SUBMIT",
  "CONFIRM",
  "CANCEL",
  "OTHER",
];

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function boundedString(value: unknown, maximum = 512): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function validCode(family: GhostWalkIntentFamily, code: unknown): code is string {
  if (typeof code !== "string" || !/^[A-Z][A-Z0-9_]{2,127}$/.test(code)) {
    return false;
  }
  return family === "OTHER" || code.startsWith(`${family}_`);
}

export function isGhostWalkAcceptedIntent(
  value: unknown,
): value is GhostWalkAcceptedIntent {
  if (!record(value)) return false;
  const family = value.intent_family as GhostWalkIntentFamily;
  return (
    value.schema_version === "phios.ghostwalk_accepted_intent_revision.v0.29" &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.source_operator_note_revision_sha256) &&
    typeof value.revision === "number" &&
    Number.isInteger(value.revision) &&
    value.revision >= 1 &&
    GHOSTWALK_INTENT_FAMILIES.includes(family) &&
    validCode(family, value.intent_code) &&
    (value.status === "ACTIVE" || value.status === "REVOKED") &&
    boundedString(value.accepted_by) &&
    timestamp(value.accepted_at) &&
    (value.supersedes_revision_sha256 === null || sha(value.supersedes_revision_sha256)) &&
    value.human_intent_confirmed === true &&
    value.causation_proven === false &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.revision_sha256)
  );
}

export function isGhostWalkAcceptedIntentEnvelope(
  value: unknown,
  mutated: boolean,
): value is GhostWalkAcceptedIntentEnvelope {
  if (!record(value)) return false;
  return (
    value.transportSchemaVersion === "phios.ghostwalk-accepted-intent-transport.v0.29" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-accepted-intent" &&
    value.localOnly === true &&
    value.intentMutation === mutated &&
    value.desktopEffectPerformed === false &&
    value.policyAuthority === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === mutated &&
    timestamp(value.servedAt) &&
    isGhostWalkAcceptedIntent(value.intent)
  );
}

export function createGhostWalkAcceptedIntentClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    async read(targetSha256: string): Promise<GhostWalkAcceptedIntentReadResult> {
      if (!sha(targetSha256)) return { kind: "unavailable" };
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          `/api/v1/ghostwalk/accepted-intent?target=${targetSha256}`,
          {
            method: "GET",
            cache: "no-store",
            credentials: "same-origin",
            headers: { accept: "application/json" },
            signal: controller.signal,
          },
        );
        if (response.status === 404) return { kind: "none" };
        if (!response.ok) return { kind: "unavailable" };
        const payload: unknown = await response.json();
        if (!isGhostWalkAcceptedIntentEnvelope(payload, false)) {
          return { kind: "unavailable" };
        }
        return { kind: "found", intent: payload.intent };
      } catch {
        return { kind: "unavailable" };
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },

    async accept({
      targetSha256,
      sourceOperatorNoteRevisionSha256,
      family,
      code,
      expectedCurrentRevisionSha256,
    }: {
      targetSha256: string;
      sourceOperatorNoteRevisionSha256: string;
      family: GhostWalkIntentFamily;
      code: string;
      expectedCurrentRevisionSha256: string | null;
    }): Promise<GhostWalkAcceptedIntentMutationResult> {
      if (
        !sha(targetSha256) ||
        !sha(sourceOperatorNoteRevisionSha256) ||
        !GHOSTWALK_INTENT_FAMILIES.includes(family) ||
        !validCode(family, code) ||
        (
          expectedCurrentRevisionSha256 !== null &&
          !sha(expectedCurrentRevisionSha256)
        )
      ) {
        return { kind: "unavailable" };
      }

      return mutate({
        operation: "ACCEPT",
        target_inference_receipt_sha256: targetSha256,
        source_operator_note_revision_sha256: sourceOperatorNoteRevisionSha256,
        intent_family: family,
        intent_code: code,
        expected_current_revision_sha256: expectedCurrentRevisionSha256,
      });
    },

    async revoke({
      targetSha256,
      expectedCurrentRevisionSha256,
    }: {
      targetSha256: string;
      expectedCurrentRevisionSha256: string;
    }): Promise<GhostWalkAcceptedIntentMutationResult> {
      if (!sha(targetSha256) || !sha(expectedCurrentRevisionSha256)) {
        return { kind: "unavailable" };
      }
      return mutate({
        operation: "REVOKE",
        target_inference_receipt_sha256: targetSha256,
        expected_current_revision_sha256: expectedCurrentRevisionSha256,
      });
    },
  };

  async function mutate(body: Record<string, unknown>): Promise<GhostWalkAcceptedIntentMutationResult> {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetcher(
        "/api/v1/ghostwalk/accepted-intent/revisions",
        {
          method: "POST",
          cache: "no-store",
          credentials: "same-origin",
          headers: {
            accept: "application/json",
            "content-type": "application/json",
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        },
      );
      if (response.status === 409) return { kind: "conflict" };
      if (!response.ok) return { kind: "unavailable" };

      const payload: unknown = await response.json();
      if (!isGhostWalkAcceptedIntentEnvelope(payload, true)) {
        return { kind: "unavailable" };
      }
      return { kind: "applied", intent: payload.intent };
    } catch {
      return { kind: "unavailable" };
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }
}

export const ghostWalkAcceptedIntentClient =
  createGhostWalkAcceptedIntentClient();
