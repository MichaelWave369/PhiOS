import { useCallback, useEffect, useState } from "react";
import {
  processObservationProvider,
  type ProcessObservationSnapshot,
} from "../shell/processObservation";

function mib(bytes: number) {
  return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
}

function stateLabel(state: string) {
  const labels: Record<string, string> = {
    R: "RUNNING",
    S: "SLEEPING",
    D: "DISK WAIT",
    T: "STOPPED",
    t: "TRACED",
    Z: "ZOMBIE",
    I: "IDLE",
    X: "DEAD",
    P: "PARKED",
    "?": "OTHER",
  };
  return labels[state] ?? state;
}

export function ProcessObservationPanel() {
  const [observation, setObservation] = useState<ProcessObservationSnapshot | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setObservation(await processObservationProvider.observe());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!observation) {
    return <div className="observation-loading">Reading current-user process census…</div>;
  }

  const live = observation.source === "procfs-current-user";

  return (
    <section className="process-observation">
      <div className="service-observation-head">
        <div>
          <small>PROCESS CENSUS · CURRENT USER ONLY</small>
          <b>{live ? "PROCFS / LIVE LOCAL" : "FIXTURE FALLBACK"}</b>
        </div>
        <div className="service-observation-actions">
          <span>{observation.currentUserProcessCount} OBSERVED</span>
          <button onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? "Reading…" : "Refresh"}
          </button>
        </div>
      </div>

      {observation.availability === "unavailable" && (
        <div className="observation-fixture-warning">
          Process observation is unavailable
          {observation.reason ? ` · ${observation.reason}` : ""}. No process state is inferred.
        </div>
      )}

      <div className="process-summary">
        <span>running {observation.stateCounts.running}</span>
        <span>sleeping {observation.stateCounts.sleeping}</span>
        <span>disk-wait {observation.stateCounts.diskSleep}</span>
        <span>stopped {observation.stateCounts.stopped}</span>
        <span>zombie {observation.stateCounts.zombie}</span>
      </div>

      <div className="process-table">
        <div className="process-row process-header">
          <span>PID</span>
          <span>PROCESS</span>
          <span>STATE</span>
          <span>RSS</span>
          <span>THREADS</span>
        </div>
        {observation.processes.map((item) => (
          <div className="process-row" key={item.pid}>
            <code>{item.pid}</code>
            <b>{item.comm}</b>
            <span>{stateLabel(item.state)}</span>
            <span>{mib(item.rssBytes)}</span>
            <span>{item.threads}</span>
          </div>
        ))}
        {observation.processes.length === 0 && (
          <div className="observation-empty">No current-user process rows exposed.</div>
        )}
      </div>

      <div className="observation-receipt">
        <span>scope = current-user</span>
        <span>detail_limit = {observation.processLimit}</span>
        <span>cmdline = omitted</span>
        <span>environment = omitted</span>
        <span>execution_authority = false</span>
        <span>effect_performed = false</span>
      </div>
    </section>
  );
}
