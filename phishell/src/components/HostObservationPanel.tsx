import { useEffect, useState } from "react";
import {
  hostObservationProvider,
  type HostObservationSnapshot,
} from "../shell/hostObservation";

function gibibytes(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
}

export function HostObservationPanel() {
  const [snapshot, setSnapshot] = useState<HostObservationSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    hostObservationProvider.observe().then((value) => {
      if (active) setSnapshot(value);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!snapshot) {
    return <div className="observation-loading">Reading observation provider…</div>;
  }

  return (
    <div className="host-observation">
      <div className="observation-source">
        <span>OBSERVATION SOURCE</span>
        <b>{snapshot.source.toUpperCase()}</b>
        <em>{snapshot.source === "fixture" ? "NATIVE BRIDGE UNBOUND" : "LIVE READ-ONLY"}</em>
      </div>

      {snapshot.source === "fixture" && (
        <div className="observation-fixture-warning">
          PhiShell is rendering the v0.3 contract fixture. The separate Linux probe is real and
          exercised in CI, but its local transport into this browser shell is intentionally not
          bound yet.
        </div>
      )}

      <div className="observation-grid">
        <article>
          <small>HOST</small>
          <b>{snapshot.host.hostname}</b>
          <span>
            {snapshot.host.platform} · {snapshot.host.arch}
          </span>
          <span>{snapshot.host.release}</span>
        </article>

        <article>
          <small>SESSION</small>
          <b>{snapshot.session.username}</b>
          <span>uid {snapshot.session.uid ?? "n/a"}</span>
          <span>{snapshot.session.sessionType ?? "session type unknown"}</span>
        </article>

        <article>
          <small>CPU</small>
          <b>{snapshot.cpu.logicalCores} logical cores</b>
          <span>{snapshot.cpu.model}</span>
          <span>load {snapshot.cpu.loadAverage.map((value) => value.toFixed(2)).join(" · ")}</span>
        </article>

        <article>
          <small>MEMORY</small>
          <b>{snapshot.memory.usedPercent.toFixed(1)}% used</b>
          <span>{gibibytes(snapshot.memory.freeBytes)} free</span>
          <span>{gibibytes(snapshot.memory.totalBytes)} total</span>
        </article>

        <article>
          <small>ROOT STORAGE</small>
          <b>{snapshot.storage.usedPercent.toFixed(1)}% used</b>
          <span>{gibibytes(snapshot.storage.freeBytes)} free</span>
          <span>{gibibytes(snapshot.storage.totalBytes)} total</span>
        </article>

        <article>
          <small>INIT</small>
          <b>{snapshot.init.systemdPresent ? "systemd observed" : "systemd not observed"}</b>
          <span>service status transport: unbound</span>
          <span>execution authority: false</span>
        </article>
      </div>

      <div className="observation-section">
        <div className="observation-section-title">NETWORK INTERFACES · ADDRESSES OMITTED</div>
        {snapshot.network.map((network) => (
          <div className="observation-row" key={network.name}>
            <b>{network.name}</b>
            <span>{network.families.join(" / ") || "no address family"}</span>
            <em>{network.internal ? "INTERNAL" : "EXTERNAL-FACING"}</em>
          </div>
        ))}
      </div>

      <div className="observation-section">
        <div className="observation-section-title">POWER DISCOVERY</div>
        {snapshot.power.length === 0 ? (
          <div className="observation-empty">No power-supply fixture entries.</div>
        ) : (
          snapshot.power.map((power) => (
            <div className="observation-row" key={power.name}>
              <b>{power.name}</b>
              <span>{power.type ?? "unknown"}</span>
              <em>{power.capacityPercent ?? "n/a"}%</em>
            </div>
          ))
        )}
      </div>

      <div className="observation-receipt">
        <span>read_only = true</span>
        <span>execution_authority = false</span>
        <span>effect_performed = false</span>
      </div>
    </div>
  );
}
