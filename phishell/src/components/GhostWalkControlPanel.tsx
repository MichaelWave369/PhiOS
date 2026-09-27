import { useCallback, useEffect, useState } from "react";
import { GhostWalkOperatorEditor } from "./GhostWalkOperatorEditor";
import {
  ghostWalkControlClient,
  type GhostWalkAction,
  type GhostWalkSnapshot,
} from "../ghostwalk/control";

function shortHash(value: string | null) {
  return value ? `${value.slice(0, 10)}…` : "none";
}

function healthLabel(value: boolean) {
  return value ? "LIVE" : "DOWN";
}

export function GhostWalkControlPanel() {
  const [snapshot, setSnapshot] = useState<GhostWalkSnapshot | null>(null);
  const [sessionId, setSessionId] = useState("ghostwalk-local");
  const [busy, setBusy] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);
  const [selectedInference, setSelectedInference] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const next = await ghostWalkControlClient.status();
    setUnavailable(next === null);
    if (next) setSnapshot(next);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = globalThis.setInterval(() => {
      void refresh();
    }, 1_000);
    return () => globalThis.clearInterval(timer);
  }, [refresh]);

  const apply = useCallback(
    async (action: Exclude<GhostWalkAction, "STATUS">) => {
      setBusy(true);
      try {
        const outcome = await ghostWalkControlClient.apply(
          action,
          action === "START" ? sessionId : undefined,
        );
        if (!outcome) {
          setUnavailable(true);
          setLastResult("control bridge unavailable or returned invalid evidence");
          return;
        }
        setUnavailable(false);
        setSnapshot(outcome.snapshot);
        setLastResult(`${outcome.receipt.result} · ${outcome.receipt.reason}`);
      } finally {
        setBusy(false);
      }
    },
    [sessionId],
  );

  if (!snapshot && unavailable) {
    return (
      <section className="ghostwalk-panel unavailable">
        <div className="ghostwalk-heading">
          <div>
            <small>GHOST WALK · LOCAL CONTROL SURFACE</small>
            <h3>Bridge unavailable</h3>
          </div>
          <b>AUTH 0</b>
        </div>
        <p>
          Start the local Ghost-Walk sidecar on Windows to expose the governed v0.25
          snapshot. PhiShell will not invent fixture health for an automation runtime.
        </p>
        <div className="ghostwalk-boundary">
          UI CONTROL != EXECUTION AUTHORITY
        </div>
      </section>
    );
  }

  if (!snapshot) {
    return <div className="observation-loading">Reading Ghost-Walk control surface…</div>;
  }

  const actions = new Set(snapshot.available_actions);
  const active = ["RUNNING", "DEGRADED"].includes(snapshot.host_status);
  const baselineState = snapshot.baseline_armed
    ? snapshot.baseline_refresh_due
      ? "REFRESH DUE"
      : "ARMED"
    : "DISARMED";

  return (
    <section className={`ghostwalk-panel ${snapshot.host_status.toLowerCase()}`}>
      <div className="ghostwalk-heading">
        <div>
          <small>GHOST WALK · LOCAL CONTROL SURFACE</small>
          <h3>{snapshot.host_status}</h3>
        </div>
        <b>AUTH 0</b>
      </div>

      <div className="ghostwalk-controls">
        {actions.has("START") && (
          <>
            <input
              aria-label="Ghost Walk session"
              value={sessionId}
              maxLength={512}
              onChange={(event) => setSessionId(event.currentTarget.value)}
              placeholder="session id"
            />
            <button
              disabled={busy || sessionId.trim().length === 0}
              onClick={() => void apply("START")}
            >
              START
            </button>
          </>
        )}
        {actions.has("STOP") && (
          <button disabled={busy} onClick={() => void apply("STOP")}>
            STOP
          </button>
        )}
        {actions.has("ARM") && (
          <button disabled={busy} onClick={() => void apply("ARM")}>
            ARM LEARNING
          </button>
        )}
        {actions.has("DISARM") && (
          <button disabled={busy} onClick={() => void apply("DISARM")}>
            DISARM LEARNING
          </button>
        )}
        <button disabled={busy} onClick={() => void refresh()}>
          REFRESH
        </button>
      </div>

      {lastResult && <div className="ghostwalk-result">{lastResult}</div>}
      {unavailable && (
        <div className="ghostwalk-warning">
          Latest poll failed validation. Showing the last valid snapshot instead of pretending
          silence means health.
        </div>
      )}

      <div className="ghostwalk-grid">
        <article>
          <small>SESSION</small>
          <b>{snapshot.session_id ?? "none"}</b>
          <span>run generation {snapshot.run_generation}</span>
        </article>
        <article>
          <small>LISTENER</small>
          <b className={snapshot.listener_alive ? "good" : "held"}>
            {healthLabel(snapshot.listener_alive)}
          </b>
          <span>human click observation</span>
        </article>
        <article>
          <small>STATE TICKER</small>
          <b className={snapshot.tick_alive ? "good" : "held"}>
            {healthLabel(snapshot.tick_alive)}
          </b>
          <span>baseline maintenance</span>
        </article>
        <article>
          <small>BASELINE</small>
          <b className={snapshot.baseline_armed ? "good" : "held"}>
            {baselineState}
          </b>
          <span>
            age {snapshot.baseline_age_ms === null ? "n/a" : `${snapshot.baseline_age_ms} ms`}
          </span>
        </article>
        <article>
          <small>RECOVERY</small>
          <b>{snapshot.recovery_state}</b>
          <span>{shortHash(snapshot.recovery_receipt_sha256)}</span>
        </article>
        <article>
          <small>LAST ACTION</small>
          <b>{shortHash(snapshot.last_action_observation_sha256)}</b>
          <span>{active ? "host observing" : "host inactive"}</span>
        </article>
      </div>

      <div className="ghostwalk-section">
        <div className="ghostwalk-section-title">RECENT LEARNED TRANSITIONS</div>
        {snapshot.learned_transitions.length === 0 ? (
          <div className="ghostwalk-empty">No transition inference is currently projected.</div>
        ) : (
          snapshot.learned_transitions.map((transition) => (
            <div className="ghostwalk-row" key={transition.inference_receipt_sha256}>
              <div>
                <b>{transition.candidate_kinds.join(" · ") || "NO CANDIDATE"}</b>
                <span>{transition.status}</span>
              </div>
              <small>{new Date(transition.inferred_at).toLocaleTimeString()}</small>
              <button
                className="ghostwalk-note-button"
                onClick={() => setSelectedInference(transition.inference_receipt_sha256)}
              >
                {transition.operator_note_revision
                  ? `EDIT NOTE r${transition.operator_note_revision}`
                  : "EDIT NOTE"}
              </button>
            </div>
          ))
        )}
      </div>

      {selectedInference && (
        <GhostWalkOperatorEditor
          targetSha256={selectedInference}
          onClose={() => setSelectedInference(null)}
          onSaved={() => void refresh()}
        />
      )}

      <div className="ghostwalk-section">
        <div className="ghostwalk-section-title">RECENT HOLDS / FAILURES</div>
        {snapshot.recent_issues.length === 0 ? (
          <div className="ghostwalk-empty">No recent issue receipt is projected.</div>
        ) : (
          snapshot.recent_issues.map((issue) => (
            <div className="ghostwalk-row issue" key={issue.receipt_sha256}>
              <div>
                <b>{issue.reason}</b>
                <span>{issue.source}</span>
              </div>
              <small>{issue.status}</small>
              <em>{new Date(issue.observed_at).toLocaleTimeString()}</em>
            </div>
          ))
        )}
      </div>

      <div className="ghostwalk-boundary">
        UI CONTROL != LOW-LEVEL AUTHORITY · ACTIONLEASE NOT EXPOSED · EXECUTION AUTHORITY FALSE
      </div>
    </section>
  );
}
