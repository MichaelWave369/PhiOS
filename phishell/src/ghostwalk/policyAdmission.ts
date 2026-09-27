export type GhostWalkPolicyDecision = "ALLOW_REQUEST" | "HOLD" | "DENY";

export interface GhostWalkPolicyProfile {
  schema_version: "phios.ghostwalk_policy_profile.v0.30";
  profile_id: string;
  allow_request_intent_codes: string[];
  deny_intent_codes: string[];
  default_decision: "HOLD";
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  profile_sha256: string;
}

export interface GhostWalkPolicyProjection {
  schema_version: "phios.ghostwalk_policy_admission_projection.v0.30";
  target_inference_receipt_sha256: string;
  accepted_intent_revision_sha256: string;
  source_operator_note_revision_sha256: string;
  current_operator_note_revision_sha256: string;
  policy_profile_sha256: string;
  intent_family: string;
  intent_code: string;
  accepted_intent_status: string;
  operator_binding_current: boolean;
  decision: GhostWalkPolicyDecision;
  reason: string;
  request_authority_eligible: boolean;
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  projection_sha256: string;
}

export interface GhostWalkPolicyReceipt {
  schema_version: "phios.ghostwalk_policy_admission_receipt.v0.30";
  projection_sha256: string;
  target_inference_receipt_sha256: string;
  accepted_intent_revision_sha256: string;
  policy_profile_sha256: string;
  decision: GhostWalkPolicyDecision;
  reason: string;
  request_authority_eligible: boolean;
  evaluated_at: string;
  effect_performed: true;
  desktop_effect_performed: false;
  authority_request_created: false;
  action_lease_created: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  admission_receipt_sha256: string;
}

export type GhostWalkPolicyReadResult =
  | { kind: "found"; profile: GhostWalkPolicyProfile; projection: GhostWalkPolicyProjection }
  | { kind: "not_ready" }
  | { kind: "unavailable" };

export type GhostWalkPolicyRecordResult =
  | { kind: "recorded"; receipt: GhostWalkPolicyReceipt }
  | { kind: "conflict" }
  | { kind: "unavailable" };

function recordValue(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isProfile(value: unknown): value is GhostWalkPolicyProfile {
  if (!recordValue(value)) return false;
  return (
    value.schema_version === "phios.ghostwalk_policy_profile.v0.30" &&
    typeof value.profile_id === "string" &&
    stringArray(value.allow_request_intent_codes) &&
    stringArray(value.deny_intent_codes) &&
    value.default_decision === "HOLD" &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.profile_sha256)
  );
}

function isProjection(value: unknown): value is GhostWalkPolicyProjection {
  if (!recordValue(value)) return false;
  const decision = value.decision;
  return (
    value.schema_version === "phios.ghostwalk_policy_admission_projection.v0.30" &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.accepted_intent_revision_sha256) &&
    sha(value.source_operator_note_revision_sha256) &&
    sha(value.current_operator_note_revision_sha256) &&
    sha(value.policy_profile_sha256) &&
    typeof value.intent_family === "string" &&
    typeof value.intent_code === "string" &&
    typeof value.accepted_intent_status === "string" &&
    typeof value.operator_binding_current === "boolean" &&
    (decision === "ALLOW_REQUEST" || decision === "HOLD" || decision === "DENY") &&
    typeof value.reason === "string" &&
    typeof value.request_authority_eligible === "boolean" &&
    value.request_authority_eligible === (decision === "ALLOW_REQUEST") &&
    value.effect_performed === false &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.projection_sha256)
  );
}

function isReceipt(value: unknown): value is GhostWalkPolicyReceipt {
  if (!recordValue(value)) return false;
  const decision = value.decision;
  return (
    value.schema_version === "phios.ghostwalk_policy_admission_receipt.v0.30" &&
    sha(value.projection_sha256) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.accepted_intent_revision_sha256) &&
    sha(value.policy_profile_sha256) &&
    (decision === "ALLOW_REQUEST" || decision === "HOLD" || decision === "DENY") &&
    typeof value.reason === "string" &&
    typeof value.request_authority_eligible === "boolean" &&
    value.request_authority_eligible === (decision === "ALLOW_REQUEST") &&
    timestamp(value.evaluated_at) &&
    value.effect_performed === true &&
    value.desktop_effect_performed === false &&
    value.authority_request_created === false &&
    value.action_lease_created === false &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.admission_receipt_sha256)
  );
}

function validBase(value: unknown, recorded: boolean): value is Record<string, unknown> {
  if (!recordValue(value)) return false;
  return (
    value.transportSchemaVersion === "phios.ghostwalk-policy-admission-transport.v0.30" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-policy-admission" &&
    value.localOnly === true &&
    value.admissionRecorded === recorded &&
    value.desktopEffectPerformed === false &&
    value.authorityRequestCreated === false &&
    value.actionLeaseCreated === false &&
    value.policyAuthority === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === recorded &&
    timestamp(value.servedAt)
  );
}

export function createGhostWalkPolicyAdmissionClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    async read(targetSha256: string): Promise<GhostWalkPolicyReadResult> {
      if (!sha(targetSha256)) return { kind: "unavailable" };
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          `/api/v1/ghostwalk/policy-admission?target=${targetSha256}`,
          {
            method: "GET",
            cache: "no-store",
            credentials: "same-origin",
            headers: { accept: "application/json" },
            signal: controller.signal,
          },
        );
        if (response.status === 404) return { kind: "not_ready" };
        if (!response.ok) return { kind: "unavailable" };
        const payload: unknown = await response.json();
        if (
          !validBase(payload, false) ||
          !isProfile(payload.profile) ||
          !isProjection(payload.projection) ||
          payload.profile.profile_sha256 !== payload.projection.policy_profile_sha256
        ) {
          return { kind: "unavailable" };
        }
        return {
          kind: "found",
          profile: payload.profile,
          projection: payload.projection,
        };
      } catch {
        return { kind: "unavailable" };
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },

    async record({
      targetSha256,
      expectedAcceptedIntentRevisionSha256,
      expectedPolicyProfileSha256,
    }: {
      targetSha256: string;
      expectedAcceptedIntentRevisionSha256: string;
      expectedPolicyProfileSha256: string;
    }): Promise<GhostWalkPolicyRecordResult> {
      if (
        !sha(targetSha256) ||
        !sha(expectedAcceptedIntentRevisionSha256) ||
        !sha(expectedPolicyProfileSha256)
      ) {
        return { kind: "unavailable" };
      }
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          "/api/v1/ghostwalk/policy-admission/evaluations",
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
              expected_accepted_intent_revision_sha256:
                expectedAcceptedIntentRevisionSha256,
              expected_policy_profile_sha256: expectedPolicyProfileSha256,
            }),
            signal: controller.signal,
          },
        );
        if (response.status === 409) return { kind: "conflict" };
        if (!response.ok) return { kind: "unavailable" };
        const payload: unknown = await response.json();
        if (
          !validBase(payload, true) ||
          !isProfile(payload.profile) ||
          !isReceipt(payload.receipt) ||
          payload.profile.profile_sha256 !== payload.receipt.policy_profile_sha256
        ) {
          return { kind: "unavailable" };
        }
        return { kind: "recorded", receipt: payload.receipt };
      } catch {
        return { kind: "unavailable" };
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const ghostWalkPolicyAdmissionClient =
  createGhostWalkPolicyAdmissionClient();
