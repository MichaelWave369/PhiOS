import { useCallback, useEffect, useState } from "react";
import {
  persistentHistoryProvider,
  type PersistentHistoryProjection,
} from "../shell/persistentHistory";
import {
  historyComparisonProvider,
  type HistoryComparisonReceipt,
} from "../shell/historyComparison";

function shortHash(value: string) {
  return value.slice(0, 12);
}

function localTime(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function shortRecord(value: string) {
  return value.slice(-12);
}

function signed(value: number) {
  if (value > 0) return `+${value}`;
  return String(value);
}

export function PersistentHistoryPanel() {
  const [projection, setProjection] = useState<PersistentHistoryProjection | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fromRecordId, setFromRecordId] = useState("");
  const [toRecordId, setToRecordId] = useState("");
  const [comparison, setComparison] = useState<HistoryComparisonReceipt | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      setProjection(await persistentHistoryProvider.read());
      setComparison(null);
      setLoaded(true);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const compare = useCallback(async () => {
    if (!fromRecordId || !toRecordId || fromRecordId === toRecordId) return;
    setCompareBusy(true);
    try {
      setComparison(await historyComparisonProvider.compare(fromRecordId, toRecordId));
    } finally {
      setCompareBusy(false);
    }
  }, [fromRecordId, toRecordId]);

  const selectFrom = (recordId: string) => {
    setFromRecordId(recordId);
    setComparison(null);
  };

  const selectTo = (recordId: string) => {
    setToRecordId(recordId);
    setComparison(null);
  };

  if (!loaded) {
    return (
      <section className="persistent-history-panel">
        <div className="observation-loading">Reading governed persistent history…</div>
      </section>
    );
  }

  if (!projection) {
    return (
      <section className="persistent-history-panel">
        <div className="persistent-history-head">
          <div>
            <small>CANONICAL HISTORY · GOVERNED MEMORY</small>
            <b>UNAVAILABLE</b>
          </div>
          <button onClick={() => void refresh()} disabled={busy}>
            {busy ? "Reading…" : "Retry read"}
          </button>
        </div>
        <div className="observation-fixture-warning">
          No validated persistent-history projection is available. Start the governed memory
          sidecar with explicit history.read and memory.read grants. PhiShell does not fabricate
          canonical history when that service is absent.
        </div>
      </section>
    );
  }

  return (
    <section className="persistent-history-panel">
      <div className="persistent-history-head">
        <div>
          <small>CANONICAL HISTORY · GOVERNED MEMORY</small>
          <b>{projection.status.toUpperCase()}</b>
        </div>
        <div>
          <span>{projection.count}/{projection.limit} RECORDS</span>
          <button onClick={() => void refresh()} disabled={busy}>
            {busy ? "Reading…" : "Refresh canonical"}
          </button>
        </div>
      </div>

      <div className="persistent-history-meta">
        <span>generated {localTime(projection.generatedAt)}</span>
        <span>omitted {projection.omittedRecordCount}</span>
        <span>persistent = true</span>
        <span>authority = false</span>
      </div>

      <div className="history-compare-panel">
        <div className="history-compare-head">
          <div>
            <small>CANONICAL STATE COMPARISON · TEMPORARY DERIVATION</small>
            <b>COMPARISON != CAUSE != AUTHORITY</b>
          </div>
          <button
            onClick={() => void compare()}
            disabled={
              compareBusy ||
              !fromRecordId ||
              !toRecordId ||
              fromRecordId === toRecordId
            }
          >
            {compareBusy ? "Comparing…" : "Compare selected"}
          </button>
        </div>
        <div className="history-compare-selection">
          <span>A {fromRecordId ? shortRecord(fromRecordId) : "not selected"}</span>
          <span>B {toRecordId ? shortRecord(toRecordId) : "not selected"}</span>
          <span>persistent = false</span>
        </div>

        {comparison && (
          <div className="history-comparison-result">
            <div className="history-comparison-result-head">
              <b>{comparison.chronologicalOrder.toUpperCase()}</b>
              <code>{shortHash(comparison.comparisonDigest.replace("sha256:", ""))}</code>
              <span>{signed(comparison.timeDeltaMs)} ms</span>
            </div>
            <div className="history-comparison-facts">
              <span>components changed {comparison.changedComponentCount}</span>
              <span>metrics changed {comparison.changedSummaryMetricCount}</span>
              <span>
                coherence {comparison.coherence.from} → {comparison.coherence.to}
              </span>
              <span>consecutive claimed = false</span>
            </div>
            {comparison.summaryChanges.length > 0 && (
              <div className="history-comparison-metrics">
                {comparison.summaryChanges.map((change) => (
                  <span key={change.metric}>
                    {change.metric} {signed(change.delta)}
                  </span>
                ))}
              </div>
            )}
            <div className="history-comparison-boundary">
              cause = unassigned · severity = unassigned · persistent = false · authority = false
            </div>
          </div>
        )}
      </div>

      {projection.records.length === 0 ? (
        <div className="system-history-empty">
          Governed memory is readable, but no current canonical PhiShell history records are
          available inside the authorized scope.
        </div>
      ) : (
        <div className="persistent-history-list">
          {projection.records.map((record) => (
            <article key={record.recordId}>
              <div className="persistent-history-row-title">
                <b>{record.kind.toUpperCase()}</b>
                <span>{localTime(record.createdAt)}</span>
              </div>
              <code>{record.recordId}</code>
              <div className="persistent-history-facts">
                <span>{record.epistemicKind}</span>
                <span>{record.exactnessClass ?? "SOURCE"}</span>
                <span>rev {record.revision}</span>
                <span>read {shortHash(record.readAdmissibilityReceiptSha256)}</span>
              </div>
              <div className="persistent-history-provenance">
                <span>record {shortHash(record.recordSha256)}</span>
                <span>content {shortHash(record.contentSha256)}</span>
                {record.kind === "change" && (
                  <span>lineage {shortHash(record.transformationLineageSha256s[0])}</span>
                )}
              </div>
              {record.kind === "state" && (
                <div className="history-compare-row-actions">
                  <button
                    className={fromRecordId === record.recordId ? "selected" : ""}
                    onClick={() => selectFrom(record.recordId)}
                  >
                    Set A
                  </button>
                  <button
                    className={toRecordId === record.recordId ? "selected" : ""}
                    onClick={() => selectTo(record.recordId)}
                  >
                    Set B
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      <div className="observation-receipt">
        <span>history_scope = canonical-memory</span>
        <span>read_only = true</span>
        <span>history_read = operator grant</span>
        <span>memory_read = operator grant</span>
        <span>history_compare = separate operator grant</span>
        <span>comparison_persistent = false</span>
        <span>cause_assigned = false</span>
        <span>severity_assigned = false</span>
        <span>execution_authority = false</span>
        <span>effect_performed = false</span>
      </div>
    </section>
  );
}
