import { useCallback, useEffect, useState } from "react";
import {
  systemStateProvider,
  type SystemStateReceipt,
} from "../shell/systemState";

function gib(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
}

function shortDigest(value: string) {
  return value.slice(7, 19);
}

export function SystemStatePanel() {
  const [receipt, setReceipt] = useState<SystemStateReceipt | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      setReceipt(await systemStateProvider.observe());
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

  if (!receipt) {
    return (
      <section className="system-state-panel">
        <div className="observation-fixture-warning">
          Unified system-state receipt unavailable or invalid. PhiShell does not synthesize a
          trusted receipt when composition, transport validation, freshness, or digest validation
          fails.
        </div>
        <button className="system-state-refresh" onClick={() => void refresh()} disabled={busy}>
          {busy ? "Composing…" : "Retry receipt"}
        </button>
      </section>
    );
  }

  return (
    <section className="system-state-panel">
      <div className="system-state-head">
        <div>
          <small>UNIFIED MACHINE RECEIPT</small>
          <b>{receipt.coherence.toUpperCase()}</b>
        </div>
        <div>
          <span>{receipt.availableComponentCount}/{receipt.componentCount} PLANES</span>
          <button onClick={() => void refresh()} disabled={busy}>
            {busy ? "Composing…" : "Refresh receipt"}
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

      <div className="observation-receipt">
        <span>read_only = true</span>
        <span>execution_authority = false</span>
        <span>effect_performed = false</span>
        <span>hash = integrity identity, not signature</span>
      </div>
    </section>
  );
}
