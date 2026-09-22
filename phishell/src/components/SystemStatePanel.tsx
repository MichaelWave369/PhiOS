import { useCallback, useEffect, useRef, useState } from "react";
import {
  systemStateProvider,
  type SystemStateReceipt,
} from "../shell/systemState";
import {
  EMPTY_SYSTEM_STATE_HISTORY,
  SYSTEM_HISTORY_LIMIT,
  appendSystemStateHistory,
  type SystemStateHistory,
} from "../shell/systemHistory";

function gib(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
}

function shortDigest(value: string) {
  return value.slice(7, 19);
}

function signed(value: number) {
  if (value > 0) return `+${value}`;
  return String(value);
}

export function SystemStatePanel() {
  const [receipt, setReceipt] = useState<SystemStateReceipt | null>(null);
  const [history, setHistory] = useState<SystemStateHistory>(EMPTY_SYSTEM_STATE_HISTORY);
  const historyRef = useRef<SystemStateHistory>(EMPTY_SYSTEM_STATE_HISTORY);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastCaptureValid, setLastCaptureValid] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const next = await systemStateProvider.observe();
      if (!next) {
        setReceipt(null);
        setLastCaptureValid(false);
        setLoaded(true);
        return;
      }

      const updated = await appendSystemStateHistory(historyRef.current, next);
      historyRef.current = updated;
      setHistory(updated);
      setReceipt(next);
      setLastCaptureValid(true);
      setLoaded(true);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!loaded) {
    return <div className="observation-loading">Composing unified system-state receipt…</div>;
  }

  const recentChanges = [...history.changes].reverse().slice(0, 5);

  return (
    <section className="system-state-panel">
      {!receipt ? (
        <>
          <div className="observation-fixture-warning">
            Unified system-state receipt unavailable or invalid. The failed capture was not admitted
            into session history.
          </div>
          <button className="system-state-refresh" onClick={() => void refresh()} disabled={busy}>
            {busy ? "Composing…" : "Retry receipt"}
          </button>
        </>
      ) : (
        <>
          <div className="system-state-head">
            <div>
              <small>UNIFIED MACHINE RECEIPT</small>
              <b>{receipt.coherence.toUpperCase()}</b>
            </div>
            <div>
              <span>{receipt.availableComponentCount}/{receipt.componentCount} PLANES</span>
              <button onClick={() => void refresh()} disabled={busy}>
                {busy ? "Composing…" : "Capture next"}
              </button>
            </div>
          </div>

          <div className="system-state-ledger">
            <div><span>receipt</span><code>{shortDigest(receipt.receiptDigest)}</code></div>
            <div><span>capture skew</span><b>{receipt.captureSkewMs} ms</b></div>
            <div><span>compose</span><b>{receipt.composeDurationMs} ms</b></div>
            <div><span>authority</span><b>FALSE</b></div>
          </div>

          <div className="system-state-components">
            {receipt.components.map((component) => (
              <article key={component.id}>
                <small>{component.id.toUpperCase()}</small>
                <b>{component.availability.toUpperCase()}</b>
                <span>{component.source}</span>
                <code>{shortDigest(component.digest)}</code>
              </article>
            ))}
          </div>

          <div className="system-state-summary">
            <span>CPU {receipt.summary.cpuLogicalCores}</span>
            <span>MEM {gib(receipt.summary.memoryTotalBytes)}</span>
            <span>ROOT {gib(receipt.summary.rootStorageTotalBytes)}</span>
            <span>SVC {receipt.summary.activeServiceCount}/{receipt.summary.observedServiceCount}</span>
            <span>PROC {receipt.summary.currentUserProcessCount}</span>
            <span>PKG {receipt.summary.installedPackageCount}</span>
            <span>PCI {receipt.summary.pciDeviceCount}</span>
            <span>USB {receipt.summary.usbDeviceCount}</span>
          </div>
        </>
      )}

      <div className="system-history">
        <div className="system-history-head">
          <div>
            <small>OBSERVATION HISTORY · SESSION MEMORY</small>
            <b>{history.receipts.length}/{SYSTEM_HISTORY_LIMIT} RECEIPTS</b>
          </div>
          <span>{lastCaptureValid ? "LAST CAPTURE ADMITTED" : "NO NEW RECEIPT ADMITTED"}</span>
        </div>

        {recentChanges.length === 0 ? (
          <div className="system-history-empty">
            Capture another validated system-state receipt to create the first change receipt.
          </div>
        ) : (
          <div className="system-history-list">
            {recentChanges.map((change) => (
              <article key={change.changeDigest}>
                <div className="system-change-title">
                  <b>CHANGE #{change.sequence}</b>
                  <code>{shortDigest(change.changeDigest)}</code>
                  <span>{change.elapsedMs} ms</span>
                </div>
                <div className="system-change-route">
                  <code>{shortDigest(change.fromReceiptDigest)}</code>
                  <span>→</span>
                  <code>{shortDigest(change.toReceiptDigest)}</code>
                </div>
                <div className="system-change-facts">
                  <span>components changed {change.changedComponentCount}</span>
                  <span>metrics changed {change.changedSummaryMetricCount}</span>
                  <span>coherence {change.coherence.from} → {change.coherence.to}</span>
                </div>
                {change.summaryChanges.length > 0 && (
                  <div className="system-change-metrics">
                    {change.summaryChanges.map((metric) => (
                      <span key={metric.metric}>
                        {metric.metric} {signed(metric.delta)}
                      </span>
                    ))}
                  </div>
                )}
                <div className="system-change-boundary">
                  cause = unassigned · severity = unassigned · authority = false
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="observation-receipt">
        <span>history_scope = session-memory</span>
        <span>persistent = false</span>
        <span>history_limit = {SYSTEM_HISTORY_LIMIT}</span>
        <span>cause_assigned = false</span>
        <span>severity_assigned = false</span>
        <span>execution_authority = false</span>
        <span>effect_performed = false</span>
      </div>
    </section>
  );
}
