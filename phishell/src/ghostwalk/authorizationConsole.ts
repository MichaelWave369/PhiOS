export type AuthorizationDecisionKind = "APPROVE" | "DENY" | "HOLD";

export interface GhostWalkAuthorizationReadiness {
  schema_version: "phios.ghostwalk_authorization_readiness.v0.32";
  target_inference_receipt_sha256: string;
  authority_request_sha256: string | null;
  latest_decision_sha256: string | null;
  latest_decision: AuthorizationDecisionKind | null;
  ready: boolean;
  reason:
    | "READY"
    | "AUTHORITY_REQUEST_REQUIRED"
    | "AUTHORITY_REQUEST_STALE"
    | "DECISION_FINAL";
  authorization_granted: boolean;
  capability_binding_created: false;
  action_lease_created: false;
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  readiness_sha256: string;
}

export interface GhostWalkAuthorizationDecision {
  schema_version: "phios.ghostwalk_authorization_decision.v0.32";
  authority_request_sha256: string;
  target_inference_receipt_sha256: string;
  admission_receipt_sha256: string;
  accepted_intent_revision_sha256: string;
  policy_profile_sha256: string;
  intent_code: string;
  authorizer_id: string;
  decision: AuthorizationDecisionKind;
  decision_sequence: number;
  previous_decision_sha256: string | null;
  decided_at: string;
  decision_note: string | null;
  authorization_granted: boolean;
  request_resolved: boolean;
  capability_binding_created: false;
  action_lease_created: false;
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  authorization_decision_sha256: string;
}

export interface GhostWalkBindingReadiness {
  schema_version: "phios.ghostwalk_binding_readiness.v0.33";
  target_inference_receipt_sha256: string;
  authorization_decision_sha256: string | null;
  mapping_set_sha256: string;
  selected_mapping_sha256: string | null;
  action_observation_sha256: string | null;
  existing_binding_sha256: string | null;
  ready: boolean;
  reason:
    | "READY"
    | "AUTHORIZATION_DECISION_REQUIRED"
    | "AUTHORIZATION_NOT_APPROVED"
    | "AUTHORIZATION_STALE"
    | "NO_MAPPING"
    | "AMBIGUOUS_MAPPING"
    | "ACTION_EVIDENCE_MISSING"
    | "MAPPING_CONSTRAINT_MISMATCH"
    | "BINDING_ALREADY_EXISTS";
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  readiness_sha256: string;
}

export interface GhostWalkExecutableBindingSummary {
  schema_version: "phios.ghostwalk_executable_binding_summary.v0.36";
  executable_binding_sha256: string;
  authorization_decision_sha256: string;
  intent_code: string;
  mapping_id: string;
  capability_id: string;
  capability_version: string;
  payload_sha256: string;
  permissions_required: string[];
  effects_declared: string[];
  bound_at: string;
  effect_performed: false;
  action_authority: false;
  execution_authority: false;
}

export interface GhostWalkLeaseReadiness {
  schema_version: "phios.ghostwalk_lease_readiness.v0.34";
  target_inference_receipt_sha256: string;
  executable_binding_sha256: string | null;
  policy_sha256: string | null;
  policy_set_sha256: string;
  enforcement_profile_sha256: string | null;
  authority_epoch_sha256: string | null;
  required_permissions: string[];
  missing_permissions: string[];
  unenforced_effects: string[];
  accepted_unenforced_effects: string[];
  existing_action_lease_sha256: string | null;
  ready: boolean;
  reason:
    | "READY"
    | "EXECUTABLE_BINDING_REQUIRED"
    | "EXECUTABLE_BINDING_STALE"
    | "LEASE_POLICY_MISSING"
    | "ENFORCEMENT_PROFILE_INCOMPLETE"
    | "UNENFORCED_EFFECT_ACK_REQUIRED"
    | "AUTHORITY_EPOCH_UNAVAILABLE"
    | "AUTHORITY_EPOCH_STALE"
    | "AUTHORITY_PRINCIPAL_MISMATCH"
    | "AUTHORITY_PERMISSION_MISSING"
    | "LEASE_ALREADY_EXISTS";
  effect_performed: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  readiness_sha256: string;
}

export interface GhostWalkActionLeaseSummary {
  schema_version: "phios.ghostwalk_action_lease_summary.v0.36";
  action_lease_sha256: string;
  lease_record_sha256: string;
  executable_binding_sha256: string;
  principal_id: string;
  issuer_id: string;
  capability_id: string;
  capability_version: string;
  payload_sha256: string;
  effects_declared: string[];
  permissions_authorized: string[];
  valid_from: string;
  valid_until: string;
  max_uses: 1;
  lease_action_authority: true;
  effect_performed: false;
  execution_authority: false;
}

export interface GhostWalkAuthorizationConsoleSnapshot {
  schema_version: "phios.ghostwalk_authorization_console_snapshot.v0.36";
  target_inference_receipt_sha256: string;
  authorization_readiness: GhostWalkAuthorizationReadiness;
  authorization_decision: GhostWalkAuthorizationDecision | null;
  binding_available: boolean;
  binding_readiness: GhostWalkBindingReadiness | null;
  binding: GhostWalkExecutableBindingSummary | null;
  lease_available: boolean;
  lease_readiness: GhostWalkLeaseReadiness | null;
  lease: GhostWalkActionLeaseSummary | null;
  effect_performed: false;
  policy_authority: false;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  snapshot_sha256: string;
}

export type GhostWalkAuthorizationConsoleReadResult =
  | { kind: "found"; snapshot: GhostWalkAuthorizationConsoleSnapshot }
  | { kind: "unavailable" };

export type GhostWalkAuthorizationConsoleMutationResult =
  | { kind: "applied"; snapshot: GhostWalkAuthorizationConsoleSnapshot }
  | { kind: "conflict" }
  | { kind: "unavailable" };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function nullableSha(value: unknown): value is string | null {
  return value === null || sha(value);
}

function timestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length <= 64 &&
    !Number.isNaN(Date.parse(value))
  );
}

function strings(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.every((item) => typeof item === "string")
  );
}

function zeroAuthority(value: Record<string, unknown>) {
  return (
    value.policy_authority === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false
  );
}

function isAuthorizationReadiness(
  value: unknown,
): value is GhostWalkAuthorizationReadiness {
  if (!record(value) || !zeroAuthority(value)) return false;
  const reason = value.reason;
  return (
    value.schema_version ===
      "phios.ghostwalk_authorization_readiness.v0.32" &&
    sha(value.target_inference_receipt_sha256) &&
    nullableSha(value.authority_request_sha256) &&
    nullableSha(value.latest_decision_sha256) &&
    (
      value.latest_decision === null ||
      value.latest_decision === "APPROVE" ||
      value.latest_decision === "DENY" ||
      value.latest_decision === "HOLD"
    ) &&
    typeof value.ready === "boolean" &&
    (
      reason === "READY" ||
      reason === "AUTHORITY_REQUEST_REQUIRED" ||
      reason === "AUTHORITY_REQUEST_STALE" ||
      reason === "DECISION_FINAL"
    ) &&
    value.ready === (reason === "READY") &&
    typeof value.authorization_granted === "boolean" &&
    value.authorization_granted ===
      (value.latest_decision === "APPROVE") &&
    value.capability_binding_created === false &&
    value.action_lease_created === false &&
    value.effect_performed === false &&
    sha(value.readiness_sha256)
  );
}

function isDecision(
  value: unknown,
): value is GhostWalkAuthorizationDecision {
  if (!record(value) || !zeroAuthority(value)) return false;
  const decision = value.decision;
  return (
    value.schema_version ===
      "phios.ghostwalk_authorization_decision.v0.32" &&
    sha(value.authority_request_sha256) &&
    sha(value.target_inference_receipt_sha256) &&
    sha(value.admission_receipt_sha256) &&
    sha(value.accepted_intent_revision_sha256) &&
    sha(value.policy_profile_sha256) &&
    typeof value.intent_code === "string" &&
    /^[A-Z][A-Z0-9_]{2,127}$/.test(value.intent_code) &&
    typeof value.authorizer_id === "string" &&
    (
      decision === "APPROVE" ||
      decision === "DENY" ||
      decision === "HOLD"
    ) &&
    Number.isInteger(value.decision_sequence) &&
    Number(value.decision_sequence) >= 0 &&
    nullableSha(value.previous_decision_sha256) &&
    timestamp(value.decided_at) &&
    (
      value.decision_note === null ||
      typeof value.decision_note === "string"
    ) &&
    value.authorization_granted === (decision === "APPROVE") &&
    value.request_resolved ===
      (decision === "APPROVE" || decision === "DENY") &&
    value.capability_binding_created === false &&
    value.action_lease_created === false &&
    value.effect_performed === false &&
    sha(value.authorization_decision_sha256)
  );
}

function isBindingReadiness(
  value: unknown,
): value is GhostWalkBindingReadiness {
  if (!record(value) || !zeroAuthority(value)) return false;
  const reason = value.reason;
  return (
    value.schema_version ===
      "phios.ghostwalk_binding_readiness.v0.33" &&
    sha(value.target_inference_receipt_sha256) &&
    nullableSha(value.authorization_decision_sha256) &&
    sha(value.mapping_set_sha256) &&
    nullableSha(value.selected_mapping_sha256) &&
    nullableSha(value.action_observation_sha256) &&
    nullableSha(value.existing_binding_sha256) &&
    typeof value.ready === "boolean" &&
    (
      reason === "READY" ||
      reason === "AUTHORIZATION_DECISION_REQUIRED" ||
      reason === "AUTHORIZATION_NOT_APPROVED" ||
      reason === "AUTHORIZATION_STALE" ||
      reason === "NO_MAPPING" ||
      reason === "AMBIGUOUS_MAPPING" ||
      reason === "ACTION_EVIDENCE_MISSING" ||
      reason === "MAPPING_CONSTRAINT_MISMATCH" ||
      reason === "BINDING_ALREADY_EXISTS"
    ) &&
    value.ready === (reason === "READY") &&
    value.effect_performed === false &&
    sha(value.readiness_sha256)
  );
}

function isBinding(
  value: unknown,
): value is GhostWalkExecutableBindingSummary {
  return (
    record(value) &&
    value.schema_version ===
      "phios.ghostwalk_executable_binding_summary.v0.36" &&
    sha(value.executable_binding_sha256) &&
    sha(value.authorization_decision_sha256) &&
    typeof value.intent_code === "string" &&
    typeof value.mapping_id === "string" &&
    typeof value.capability_id === "string" &&
    typeof value.capability_version === "string" &&
    sha(value.payload_sha256) &&
    strings(value.permissions_required) &&
    strings(value.effects_declared) &&
    timestamp(value.bound_at) &&
    value.effect_performed === false &&
    value.action_authority === false &&
    value.execution_authority === false
  );
}

function isLeaseReadiness(
  value: unknown,
): value is GhostWalkLeaseReadiness {
  if (!record(value)) return false;
  const reason = value.reason;
  return (
    value.schema_version ===
      "phios.ghostwalk_lease_readiness.v0.34" &&
    sha(value.target_inference_receipt_sha256) &&
    nullableSha(value.executable_binding_sha256) &&
    nullableSha(value.policy_sha256) &&
    sha(value.policy_set_sha256) &&
    nullableSha(value.enforcement_profile_sha256) &&
    nullableSha(value.authority_epoch_sha256) &&
    strings(value.required_permissions) &&
    strings(value.missing_permissions) &&
    strings(value.unenforced_effects) &&
    strings(value.accepted_unenforced_effects) &&
    nullableSha(value.existing_action_lease_sha256) &&
    typeof value.ready === "boolean" &&
    (
      reason === "READY" ||
      reason === "EXECUTABLE_BINDING_REQUIRED" ||
      reason === "EXECUTABLE_BINDING_STALE" ||
      reason === "LEASE_POLICY_MISSING" ||
      reason === "ENFORCEMENT_PROFILE_INCOMPLETE" ||
      reason === "UNENFORCED_EFFECT_ACK_REQUIRED" ||
      reason === "AUTHORITY_EPOCH_UNAVAILABLE" ||
      reason === "AUTHORITY_EPOCH_STALE" ||
      reason === "AUTHORITY_PRINCIPAL_MISMATCH" ||
      reason === "AUTHORITY_PERMISSION_MISSING" ||
      reason === "LEASE_ALREADY_EXISTS"
    ) &&
    value.ready === (reason === "READY") &&
    value.effect_performed === false &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.readiness_sha256)
  );
}

function isLease(value: unknown): value is GhostWalkActionLeaseSummary {
  return (
    record(value) &&
    value.schema_version ===
      "phios.ghostwalk_action_lease_summary.v0.36" &&
    sha(value.action_lease_sha256) &&
    sha(value.lease_record_sha256) &&
    sha(value.executable_binding_sha256) &&
    typeof value.principal_id === "string" &&
    typeof value.issuer_id === "string" &&
    typeof value.capability_id === "string" &&
    typeof value.capability_version === "string" &&
    sha(value.payload_sha256) &&
    strings(value.effects_declared) &&
    strings(value.permissions_authorized) &&
    timestamp(value.valid_from) &&
    timestamp(value.valid_until) &&
    value.max_uses === 1 &&
    value.lease_action_authority === true &&
    value.effect_performed === false &&
    value.execution_authority === false
  );
}

function isSnapshot(
  value: unknown,
): value is GhostWalkAuthorizationConsoleSnapshot {
  if (!record(value) || !zeroAuthority(value)) return false;
  if (
    value.schema_version !==
      "phios.ghostwalk_authorization_console_snapshot.v0.36" ||
    !sha(value.target_inference_receipt_sha256) ||
    !isAuthorizationReadiness(value.authorization_readiness) ||
    !(
      value.authorization_decision === null ||
      isDecision(value.authorization_decision)
    ) ||
    typeof value.binding_available !== "boolean" ||
    typeof value.lease_available !== "boolean" ||
    value.effect_performed !== false ||
    !sha(value.snapshot_sha256)
  ) {
    return false;
  }
  if (
    value.binding_available !== (value.binding_readiness !== null) ||
    value.lease_available !== (value.lease_readiness !== null)
  ) {
    return false;
  }
  return (
    (
      value.binding_readiness === null ||
      isBindingReadiness(value.binding_readiness)
    ) &&
    (value.binding === null || isBinding(value.binding)) &&
    (
      value.lease_readiness === null ||
      isLeaseReadiness(value.lease_readiness)
    ) &&
    (value.lease === null || isLease(value.lease))
  );
}

function validEnvelope(
  value: unknown,
  mutationKind: "NONE" | "DECISION" | "BINDING" | "LEASE",
) {
  if (!record(value)) return false;
  const mutated = mutationKind !== "NONE";
  return (
    value.transportSchemaVersion ===
      "phios.ghostwalk-authorization-console-transport.v0.36" &&
    value.transport === "loopback-http" &&
    value.transportIdentity ===
      "phios-ghostwalk-authorization-console" &&
    value.localOnly === true &&
    value.humanAuthorizationSurface === true &&
    value.mutationKind === mutationKind &&
    value.decisionRecorded === (mutationKind === "DECISION") &&
    value.bindingCreated === (mutationKind === "BINDING") &&
    value.actionLeaseCreated === (mutationKind === "LEASE") &&
    value.desktopEffectPerformed === false &&
    value.policyAuthority === false &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === mutated &&
    timestamp(value.servedAt) &&
    isSnapshot(value.snapshot)
  );
}

async function doFetch(
  fetcher: typeof fetch,
  url: string,
  init: RequestInit,
  timeoutMs: number,
) {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetcher(url, { ...init, signal: controller.signal });
  } catch {
    return null;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function createGhostWalkAuthorizationConsoleClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  async function mutate(
    path: string,
    body: Record<string, unknown>,
    kind: "DECISION" | "BINDING" | "LEASE",
  ): Promise<GhostWalkAuthorizationConsoleMutationResult> {
    const response = await doFetch(
      fetcher,
      path,
      {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify(body),
      },
      timeoutMs,
    );
    if (!response) return { kind: "unavailable" };
    if (response.status === 409) return { kind: "conflict" };
    if (!response.ok) return { kind: "unavailable" };
    const payload: unknown = await response.json();
    if (!validEnvelope(payload, kind) || !record(payload)) {
      return { kind: "unavailable" };
    }
    return {
      kind: "applied",
      snapshot: payload.snapshot as GhostWalkAuthorizationConsoleSnapshot,
    };
  }

  return {
    async read(
      targetSha256: string,
    ): Promise<GhostWalkAuthorizationConsoleReadResult> {
      if (!sha(targetSha256)) return { kind: "unavailable" };
      const response = await doFetch(
        fetcher,
        `/api/v1/ghostwalk/authorization-console?target=${targetSha256}`,
        {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
        },
        timeoutMs,
      );
      if (!response?.ok) return { kind: "unavailable" };
      const payload: unknown = await response.json();
      if (!validEnvelope(payload, "NONE") || !record(payload)) {
        return { kind: "unavailable" };
      }
      return {
        kind: "found",
        snapshot: payload.snapshot as GhostWalkAuthorizationConsoleSnapshot,
      };
    },

    recordDecision({
      targetSha256,
      expectedAuthorityRequestSha256,
      expectedPreviousDecisionSha256,
      decision,
      decisionNote,
    }: {
      targetSha256: string;
      expectedAuthorityRequestSha256: string;
      expectedPreviousDecisionSha256: string | null;
      decision: AuthorizationDecisionKind;
      decisionNote: string | null;
    }) {
      if (
        !sha(targetSha256) ||
        !sha(expectedAuthorityRequestSha256) ||
        !nullableSha(expectedPreviousDecisionSha256) ||
        (decisionNote !== null && decisionNote.length > 2048)
      ) {
        return Promise.resolve({ kind: "unavailable" } as const);
      }
      return mutate(
        "/api/v1/ghostwalk/authorization-console/decisions",
        {
          target_inference_receipt_sha256: targetSha256,
          expected_authority_request_sha256:
            expectedAuthorityRequestSha256,
          expected_previous_decision_sha256:
            expectedPreviousDecisionSha256,
          decision,
          decision_note: decisionNote,
        },
        "DECISION",
      );
    },

    createBinding({
      targetSha256,
      expectedAuthorizationDecisionSha256,
      expectedMappingSha256,
      expectedMappingSetSha256,
    }: {
      targetSha256: string;
      expectedAuthorizationDecisionSha256: string;
      expectedMappingSha256: string;
      expectedMappingSetSha256: string;
    }) {
      if (
        !sha(targetSha256) ||
        !sha(expectedAuthorizationDecisionSha256) ||
        !sha(expectedMappingSha256) ||
        !sha(expectedMappingSetSha256)
      ) {
        return Promise.resolve({ kind: "unavailable" } as const);
      }
      return mutate(
        "/api/v1/ghostwalk/authorization-console/bindings",
        {
          target_inference_receipt_sha256: targetSha256,
          expected_authorization_decision_sha256:
            expectedAuthorizationDecisionSha256,
          expected_mapping_sha256: expectedMappingSha256,
          expected_mapping_set_sha256: expectedMappingSetSha256,
        },
        "BINDING",
      );
    },

    issueLease({
      targetSha256,
      expectedExecutableBindingSha256,
      expectedPolicySha256,
      expectedPolicySetSha256,
      expectedEnforcementProfileSha256,
      expectedAuthorityEpochSha256,
    }: {
      targetSha256: string;
      expectedExecutableBindingSha256: string;
      expectedPolicySha256: string;
      expectedPolicySetSha256: string;
      expectedEnforcementProfileSha256: string;
      expectedAuthorityEpochSha256: string;
    }) {
      if (
        !sha(targetSha256) ||
        !sha(expectedExecutableBindingSha256) ||
        !sha(expectedPolicySha256) ||
        !sha(expectedPolicySetSha256) ||
        !sha(expectedEnforcementProfileSha256) ||
        !sha(expectedAuthorityEpochSha256)
      ) {
        return Promise.resolve({ kind: "unavailable" } as const);
      }
      return mutate(
        "/api/v1/ghostwalk/authorization-console/leases",
        {
          target_inference_receipt_sha256: targetSha256,
          expected_executable_binding_sha256:
            expectedExecutableBindingSha256,
          expected_policy_sha256: expectedPolicySha256,
          expected_policy_set_sha256: expectedPolicySetSha256,
          expected_enforcement_profile_sha256:
            expectedEnforcementProfileSha256,
          expected_authority_epoch_sha256:
            expectedAuthorityEpochSha256,
        },
        "LEASE",
      );
    },
  };
}

export const ghostWalkAuthorizationConsoleClient =
  createGhostWalkAuthorizationConsoleClient();
