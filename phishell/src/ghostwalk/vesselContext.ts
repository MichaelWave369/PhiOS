import {
  isGhostWalkStatusEnvelope,
  type GhostWalkHostStatus,
  type GhostWalkSnapshot,
} from "./control";

export type GhostWalkVesselHealth =
  | "idle"
  | "healthy"
  | "attention"
  | "failed"
  | "transitioning";

export interface GhostWalkVesselTransition {
  status: string;
  candidateKinds: string[];
  inferredAt: string;
  operatorNoteRevision: number | null;
  operatorNoteStatus: string | null;
}

export interface GhostWalkVesselIssue {
  source: string;
  status: string;
  reason: string;
  observedAt: string;
}

export interface GhostWalkVesselContext {
  schemaVersion: "phios.ghostwalk_vessel_context.v0.27";
  source: "ghostwalk-control-snapshot";
  sourceSnapshotSha256: string;
  observedAt: string;
  hostStatus: GhostWalkHostStatus;
  health: GhostWalkVesselHealth;
  sessionId: string | null;
  runGeneration: number;
  listenerLive: boolean;
  tickerLive: boolean;
  baselineArmed: boolean;
  baselineFresh: boolean;
  baselineAgeMs: number | null;
  recoveryState: "NONE" | "PRIOR_RUN_ABANDONED";
  summary: string;
  explanation: string[];
  learnedTransitions: GhostWalkVesselTransition[];
  recentIssues: GhostWalkVesselIssue[];
  operationalAuthority: false;
  actionAuthority: false;
  executionAuthority: false;
  lifecycleAuthority: false;
  canStart: false;
  canStop: false;
  canArm: false;
  canDisarm: false;
}

function healthFromSnapshot(snapshot: GhostWalkSnapshot): GhostWalkVesselHealth {
  if (snapshot.host_status === "FAILED") return "failed";
  if (snapshot.host_status === "STARTING" || snapshot.host_status === "STOPPING") {
    return "transitioning";
  }
  if (snapshot.host_status === "STOPPED") return "idle";
  if (
    snapshot.host_status === "DEGRADED" ||
    !snapshot.listener_alive ||
    !snapshot.tick_alive ||
    snapshot.baseline_refresh_due ||
    !snapshot.baseline_armed
  ) {
    return "attention";
  }
  return "healthy";
}

function summaryFromSnapshot(
  snapshot: GhostWalkSnapshot,
  health: GhostWalkVesselHealth,
): string {
  if (health === "failed") {
    return `Ghost Walk failed${snapshot.error_type ? ` with ${snapshot.error_type}` : ""}.`;
  }
  if (health === "idle") {
    return "Ghost Walk is stopped. No live demonstration learning is currently running.";
  }
  if (health === "transitioning") {
    return `Ghost Walk is ${snapshot.host_status.toLowerCase()}.`;
  }
  if (health === "attention") {
    const reasons: string[] = [];
    if (!snapshot.listener_alive) reasons.push("listener is not live");
    if (!snapshot.tick_alive) reasons.push("state ticker is not live");
    if (!snapshot.baseline_armed) reasons.push("baseline learning is disarmed");
    if (snapshot.baseline_refresh_due) reasons.push("baseline refresh is due");
    if (snapshot.host_status === "DEGRADED") reasons.push("host reports degraded state");
    return `Ghost Walk needs attention: ${reasons.join("; ") || "runtime health is degraded"}.`;
  }
  return "Ghost Walk is running with live listener and state ticker, and the learning baseline is current.";
}

function explanationFromSnapshot(snapshot: GhostWalkSnapshot): string[] {
  const explanation: string[] = [];

  if (snapshot.recovery_state === "PRIOR_RUN_ABANDONED") {
    explanation.push(
      "The previous host lifetime ended without a clean stop. PhiOS retained the history but started this run with a fresh baseline.",
    );
  }

  if (snapshot.baseline_age_ms !== null) {
    explanation.push(
      `The current baseline is ${snapshot.baseline_age_ms} ms old and ${snapshot.baseline_refresh_due ? "due for refresh" : "within the current refresh window"}.`,
    );
  } else {
    explanation.push("No live baseline age is currently projected.");
  }

  if (snapshot.learned_transitions.length > 0) {
    const latest = snapshot.learned_transitions[0];
    const candidates =
      latest.candidate_kinds.length > 0
        ? latest.candidate_kinds.join(", ")
        : "no candidate meaning";
    explanation.push(
      `The latest learned transition is ${latest.status} with candidate kinds: ${candidates}.`,
    );
  } else {
    explanation.push("No learned transition is currently projected.");
  }

  if (snapshot.recent_issues.length > 0) {
    const latest = snapshot.recent_issues[0];
    explanation.push(
      `The most recent hold or failure is ${latest.reason} from ${latest.source} with status ${latest.status}.`,
    );
  }

  return explanation.slice(0, 5);
}

export function buildGhostWalkVesselContext(
  snapshot: GhostWalkSnapshot,
): GhostWalkVesselContext {
  const health = healthFromSnapshot(snapshot);
  return {
    schemaVersion: "phios.ghostwalk_vessel_context.v0.27",
    source: "ghostwalk-control-snapshot",
    sourceSnapshotSha256: snapshot.snapshot_sha256,
    observedAt: snapshot.observed_at,
    hostStatus: snapshot.host_status,
    health,
    sessionId: snapshot.session_id,
    runGeneration: snapshot.run_generation,
    listenerLive: snapshot.listener_alive,
    tickerLive: snapshot.tick_alive,
    baselineArmed: snapshot.baseline_armed,
    baselineFresh:
      snapshot.baseline_armed &&
      !snapshot.baseline_refresh_due &&
      snapshot.baseline_sha256 !== null,
    baselineAgeMs: snapshot.baseline_age_ms,
    recoveryState: snapshot.recovery_state,
    summary: summaryFromSnapshot(snapshot, health),
    explanation: explanationFromSnapshot(snapshot),
    learnedTransitions: snapshot.learned_transitions.slice(0, 5).map((item) => ({
      status: item.status,
      candidateKinds: [...item.candidate_kinds],
      inferredAt: item.inferred_at,
      operatorNoteRevision: item.operator_note_revision,
      operatorNoteStatus: item.operator_note_status,
    })),
    recentIssues: snapshot.recent_issues.slice(0, 5).map((item) => ({
      source: item.source,
      status: item.status,
      reason: item.reason,
      observedAt: item.observed_at,
    })),
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    lifecycleAuthority: false,
    canStart: false,
    canStop: false,
    canArm: false,
    canDisarm: false,
  };
}

export function createGhostWalkVesselContextProvider({
  fetcher = globalThis.fetch.bind(globalThis),
  timeoutMs = 2_000,
}: {
  fetcher?: typeof fetch;
  timeoutMs?: number;
} = {}) {
  return {
    readOnly: true as const,
    operationalAuthority: false as const,
    actionAuthority: false as const,
    executionAuthority: false as const,
    lifecycleAuthority: false as const,

    async read(): Promise<GhostWalkVesselContext | null> {
      const controller = new AbortController();
      const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetcher("/api/v1/ghostwalk", {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          headers: { accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) return null;

        const payload: unknown = await response.json();
        if (!isGhostWalkStatusEnvelope(payload)) return null;
        return buildGhostWalkVesselContext(payload.snapshot);
      } catch {
        return null;
      } finally {
        globalThis.clearTimeout(timeout);
      }
    },
  };
}

export const ghostWalkVesselContextProvider =
  createGhostWalkVesselContextProvider();
