export type GhostWalkAction = "STATUS" | "START" | "STOP" | "ARM" | "DISARM";
export type GhostWalkHostStatus =
  | "STOPPED"
  | "STARTING"
  | "RUNNING"
  | "DEGRADED"
  | "STOPPING"
  | "FAILED";

export interface GhostWalkLearnedTransition {
  inference_receipt_sha256: string;
  session_id: string;
  action_observation_sha256: string;
  status: string;
  candidate_kinds: string[];
  inferred_at: string;
  operator_note_revision_sha256: string | null;
  operator_note_revision: number | null;
  operator_note_status: string | null;
}

export interface GhostWalkIssue {
  source: string;
  status: string;
  reason: string;
  observed_at: string;
  receipt_sha256: string;
}

export interface GhostWalkSnapshot {
  schema_version: "phios.ghostwalk_control_snapshot.v0.25";
  surface_id: string;
  host_id: string;
  host_status: GhostWalkHostStatus;
  run_generation: number;
  session_id: string | null;
  listener_alive: boolean;
  tick_alive: boolean;
  baseline_armed: boolean;
  baseline_sha256: string | null;
  baseline_age_ms: number | null;
  baseline_refresh_due: boolean;
  error_type: string | null;
  recovery_state: "NONE" | "PRIOR_RUN_ABANDONED";
  recovery_receipt_sha256: string | null;
  available_actions: GhostWalkAction[];
  last_action_observation_sha256: string | null;
  learned_transitions: GhostWalkLearnedTransition[];
  recent_issues: GhostWalkIssue[];
  observed_at: string;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  snapshot_sha256: string;
}

export interface GhostWalkControlReceipt {
  schema_version: "phios.ghostwalk_control_receipt.v0.25";
  surface_id: string;
  sequence: number;
  action: GhostWalkAction;
  requested_session_id: string | null;
  result: "OBSERVED" | "APPLIED" | "NOOP" | "REJECTED";
  reason: string;
  before_snapshot_sha256: string;
  after_snapshot_sha256: string;
  applied_at: string;
  error_type: string | null;
  previous_receipt_sha256: string | null;
  operational_authority: false;
  action_authority: false;
  execution_authority: false;
  receipt_sha256: string;
}

interface GhostWalkTransportBase {
  transportSchemaVersion: "phios.ghostwalk-control-transport.v0.26";
  transport: "loopback-http";
  transportIdentity: "phios-ghostwalk-control";
  localOnly: true;
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  effectPerformed: false;
  servedAt: string;
}

export interface GhostWalkStatusEnvelope extends GhostWalkTransportBase {
  snapshot: GhostWalkSnapshot;
}

export interface GhostWalkActionEnvelope extends GhostWalkTransportBase {
  controlPlaneMutation: boolean;
  receipt: GhostWalkControlReceipt;
  snapshot: GhostWalkSnapshot;
}

const ACTIONS: GhostWalkAction[] = ["STATUS", "START", "STOP", "ARM", "DISARM"];
const HOST_STATUSES: GhostWalkHostStatus[] = [
  "STOPPED",
  "STARTING",
  "RUNNING",
  "DEGRADED",
  "STOPPING",
  "FAILED",
];

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function sha(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function optionalSha(value: unknown): value is string | null {
  return value === null || sha(value);
}

function nullableString(value: unknown, maximum = 512): value is string | null {
  return value === null || (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= maximum
  );
}

function integer(value: unknown, minimum = 0): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum;
}

function validTransition(value: unknown): value is GhostWalkLearnedTransition {
  if (!record(value)) return false;
  return (
    sha(value.inference_receipt_sha256) &&
    typeof value.session_id === "string" &&
    sha(value.action_observation_sha256) &&
    typeof value.status === "string" &&
    Array.isArray(value.candidate_kinds) &&
    value.candidate_kinds.length <= 25 &&
    value.candidate_kinds.every((item) => typeof item === "string") &&
    timestamp(value.inferred_at) &&
    optionalSha(value.operator_note_revision_sha256) &&
    (value.operator_note_revision === null || integer(value.operator_note_revision, 1)) &&
    nullableString(value.operator_note_status, 64)
  );
}

function validIssue(value: unknown): value is GhostWalkIssue {
  if (!record(value)) return false;
  return (
    typeof value.source === "string" &&
    typeof value.status === "string" &&
    typeof value.reason === "string" &&
    timestamp(value.observed_at) &&
    sha(value.receipt_sha256)
  );
}

export function isGhostWalkSnapshot(value: unknown): value is GhostWalkSnapshot {
  if (!record(value)) return false;
  return (
    value.schema_version === "phios.ghostwalk_control_snapshot.v0.25" &&
    typeof value.surface_id === "string" &&
    typeof value.host_id === "string" &&
    HOST_STATUSES.includes(value.host_status as GhostWalkHostStatus) &&
    integer(value.run_generation) &&
    nullableString(value.session_id) &&
    typeof value.listener_alive === "boolean" &&
    typeof value.tick_alive === "boolean" &&
    typeof value.baseline_armed === "boolean" &&
    optionalSha(value.baseline_sha256) &&
    (value.baseline_age_ms === null || integer(value.baseline_age_ms)) &&
    typeof value.baseline_refresh_due === "boolean" &&
    nullableString(value.error_type, 256) &&
    (value.recovery_state === "NONE" || value.recovery_state === "PRIOR_RUN_ABANDONED") &&
    optionalSha(value.recovery_receipt_sha256) &&
    Array.isArray(value.available_actions) &&
    value.available_actions.length <= ACTIONS.length &&
    value.available_actions.every((action) => ACTIONS.includes(action as GhostWalkAction)) &&
    optionalSha(value.last_action_observation_sha256) &&
    Array.isArray(value.learned_transitions) &&
    value.learned_transitions.length <= 25 &&
    value.learned_transitions.every(validTransition) &&
    Array.isArray(value.recent_issues) &&
    value.recent_issues.length <= 25 &&
    value.recent_issues.every(validIssue) &&
    timestamp(value.observed_at) &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.snapshot_sha256)
  );
}

function isTransportBase(value: unknown): value is Record<string, unknown> & GhostWalkTransportBase {
  if (!record(value)) return false;
  return (
    value.transportSchemaVersion === "phios.ghostwalk-control-transport.v0.26" &&
    value.transport === "loopback-http" &&
    value.transportIdentity === "phios-ghostwalk-control" &&
    value.localOnly === true &&
    value.operationalAuthority === false &&
    value.actionAuthority === false &&
    value.executionAuthority === false &&
    value.effectPerformed === false &&
    timestamp(value.servedAt)
  );
}

function isReceipt(value: unknown): value is GhostWalkControlReceipt {
  if (!record(value)) return false;
  return (
    value.schema_version === "phios.ghostwalk_control_receipt.v0.25" &&
    typeof value.surface_id === "string" &&
    integer(value.sequence) &&
    ACTIONS.includes(value.action as GhostWalkAction) &&
    nullableString(value.requested_session_id) &&
    ["OBSERVED", "APPLIED", "NOOP", "REJECTED"].includes(String(value.result)) &&
    typeof value.reason === "string" &&
    sha(value.before_snapshot_sha256) &&
    sha(value.after_snapshot_sha256) &&
    timestamp(value.applied_at) &&
    nullableString(value.error_type, 256) &&
    optionalSha(value.previous_receipt_sha256) &&
    value.operational_authority === false &&
    value.action_authority === false &&
    value.execution_authority === false &&
    sha(value.receipt_sha256)
  );
}

export function isGhostWalkStatusEnvelope(value: unknown): value is GhostWalkStatusEnvelope {
  return isTransportBase(value) && isGhostWalkSnapshot(value.snapshot);
}

export function isGhostWalkActionEnvelope(value: unknown): value is GhostWalkActionEnvelope {
  return (
    isTransportBase(value) &&
    typeof value.controlPlaneMutation === "boolean" &&
    isReceipt(value.receipt) &&
    isGhostWalkSnapshot(value.snapshot)
  );
}

async function fetchJson(
  url: string,
  init: RequestInit,
  fetcher: typeof fetch,
  timeoutMs: number,
): Promise<unknown> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(url, { ...init, signal: controller.signal });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function createGhostWalkControlClient({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_500,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    async status(): Promise<GhostWalkSnapshot | null> {
      const payload = await fetchJson(
        "/api/v1/ghostwalk",
        {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
        },
        fetcher,
        timeoutMs,
      );
      return isGhostWalkStatusEnvelope(payload) ? payload.snapshot : null;
    },

    async apply(
      action: Exclude<GhostWalkAction, "STATUS">,
      sessionId?: string,
    ): Promise<GhostWalkActionEnvelope | null> {
      const body: { action: GhostWalkAction; session_id?: string } = { action };
      if (action === "START") {
        const session = sessionId?.trim();
        if (!session || session.length > 512) return null;
        body.session_id = session;
      }

      const payload = await fetchJson(
        "/api/v1/ghostwalk/actions",
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
        fetcher,
        timeoutMs,
      );
      return isGhostWalkActionEnvelope(payload) ? payload : null;
    },
  };
}

export const ghostWalkControlClient = createGhostWalkControlClient();
