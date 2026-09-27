export interface GhostWalkAuthorityRequest {
  schema_version: "phios.ghostwalk_authority_request.v0.31";
  admission_receipt_sha256: string;
  target_inference_receipt_sha256: string;
  accepted_intent_revision_sha256: string;
  policy_profile_sha256: string;
  intent_family: string;
  intent_code: string;
  requester_id: string;
  requested_authority_kind: "ACTION_AUTHORITY";
  requested_scope_kind: "ACCEPTED_INTENT";
  requested_scope_value: string;
  request_state: "PENDING_AUTHORIZATION";
  requested_at: string;
  authorization_granted: false;
  action_lease_created: false;
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  authority_request_sha256: string;
}

export interface GhostWalkAuthorityRequestReadiness {
  schema_version: "phios.ghostwalk_authority_request_readiness.v0.31";
  target_inference_receipt_sha256: string;
  accepted_intent_revision_sha256: string;
  policy_profile_sha256: string;
  policy_decision: "ALLOW_REQUEST" | "HOLD" | "DENY";
  ready: boolean;
  reason:
    | "READY"
    | "POLICY_NOT_ALLOW_REQUEST"
    | "ADMISSION_RECEIPT_REQUIRED"
    | "ADMISSION_RECEIPT_STALE"
    | "REQUEST_ALREADY_EXISTS";
  admission_receipt_sha256: string | null;
  existing_authority_request_sha256: string | null;
  authorization_granted: false;
  action_lease_created: false;
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  readiness_sha256: string;
}

export type GhostWalkAuthorityRequestStatusResult =
  | {
      kind: "found";
      readiness: GhostWalkAuthorityRequestReadiness;
      request: GhostWalkAuthorityRequest | null;
    }
  | { kind: "not_ready" }
  | { kind: "unavailable" };

export type GhostWalkAuthorityRequestCreateResult =
  | { kind: "created"; request: GhostWalkAuthorityRequest }
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

function isRequest(value: unknown): value is GhostWalkAuthorityRequest {
  if (!record(value)) return false;
  return (
    value.schema_version === "phios.ghostwalk_authority_request.v0.31" &&
    sha(value.admission_receipt_sha256) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.accepted_intent_revision_sha256) &&
    sha(value.policy_profile_sha256) &&
    typeof value.intent_family === "string" &&
    typeof value.intent_code === "string" &&
    /^[A-Z][A-Z0-9_]{2,127}$/.test(value.intent_code) &&
    typeof value.requester_id === "string" &&
    value.requested_authority_kind === "ACTION_AUTHORITY" &&
    value.requested_scope_kind === "ACCEPTED_INTENT" &&
    value.requested_scope_value === value.intent_code &&
    value.request_state === "PENDING_AUTHORIZATION" &&
    timestamp(value.requested_at) &&
    value.authorization_granted === false &&
    value.action_lease_created === false &&
    value.effect_performed === false &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.authority_request_sha256)
  );
}

function isReadiness(value: unknown): value is GhostWalkAuthorityRequestReadiness {
  if (!record(value)) return false;
  const reason = value.reason;
  return (
    value.schema_version === "phios.ghostwalk_authority_request_readiness.v0.31" &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.accepted_intent_revision_sha256) &&
    sha(value.policy_profile_sha256) &&
    (value.policy_decision === "ALLOW_REQUEST" ||
      value.policy_decision === "HOLD" ||
      value.policy_decision === "DENY") &&
    typeof value.ready === "boolean" &&
    (reason === "READY" ||
      reason === "POLICY_NOT_ALLOW_REQUEST" ||
      reason === "ADMISSION_RECEIPT_REQUIRED" ||
      reason === "ADMISSION_RECEIPT_STALE" ||
      reason === "REQUEST_ALREADY_EXISTS") &&
    (value.admission_receipt_sha256 === null || sha(value.admission_receipt_sha256)) &&
    (value.existing_authority_request_sha256 === null ||
      sha(value.existing_authority_request_sha256)) &&
    value.ready === (reason === "READY") &&
    value.authorization_granted === false &&
    value.action_lease_created === false &&
    value.effect_performed === false &&
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.readiness_sha256)
  );
}

function validBase(value: unknown, created: boolean): value is Record<string, unknown> {
  if (!record(value)) return false;
  return (
    value.transportSchemaVersion === "phios.ghostwalk-authority-request-transport.v0.31" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-authority-request" &&
    value.localOnly === true &&
    value.requestCreated === created &&
    value.desktopEffectPerformed === false &&
    value.authorizationGranted === false &&
    value.actionLeaseCreated === false &&
    value.policyAuthority === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === created &&
    timestamp(value.servedAt)
  );
}

export function createGhostWalkAuthorityRequestClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    async read(targetSha256: string): Promise<GhostWalkAuthorityRequestStatusResult> {
      if (!sha(targetSha256)) return { kind: "unavailable" };
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          `/api/v1/ghostwalk/authority-request?target=${targetSha256}`,
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
        if (!validBase(payload, false) || !isReadiness(payload.readiness)) {
          return { kind: "unavailable" };
        }
        if (payload.request !== null && !isRequest(payload.request)) {
          return { kind: "unavailable" };
        }
        return {
          kind: "found",
          readiness: payload.readiness,
          request: payload.request as GhostWalkAuthorityRequest | null,
        };
      } catch {
        return { kind: "unavailable" };
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },

    async create({
      targetSha256,
      expectedAdmissionReceiptSha256,
    }: {
      targetSha256: string;
      expectedAdmissionReceiptSha256: string;
    }): Promise<GhostWalkAuthorityRequestCreateResult> {
      if (!sha(targetSha256) || !sha(expectedAdmissionReceiptSha256)) {
        return { kind: "unavailable" };
      }
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher(
          "/api/v1/ghostwalk/authority-request/requests",
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
              expected_admission_receipt_sha256:
                expectedAdmissionReceiptSha256,
            }),
            signal: controller.signal,
          },
        );
        if (response.status === 409) return { kind: "conflict" };
        if (!response.ok) return { kind: "unavailable" };
        const payload: unknown = await response.json();
        if (
          !validBase(payload, true) ||
          !isRequest(payload.request)
        ) {
          return { kind: "unavailable" };
        }
        return { kind: "created", request: payload.request };
      } catch {
        return { kind: "unavailable" };
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const ghostWalkAuthorityRequestClient =
  createGhostWalkAuthorityRequestClient();
