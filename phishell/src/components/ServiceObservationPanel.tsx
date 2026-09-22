import { useCallback, useEffect, useState } from "react";
import {
  serviceObservationProvider,
  type ServiceObservationSnapshot,
  type ServiceStatusObservation,
} from "../shell/serviceObservation";

function stateClass(service: ServiceStatusObservation) {
  if (!service.found) return "service-not-loaded";
  if (service.activeState === "active") return "service-active";
  if (service.activeState === "failed") return "service-failed";
  return "service-inactive";
}

function stateText(service: ServiceStatusObservation) {
  if (!service.found) return "NOT LOADED";
  const active = service.activeState?.toUpperCase() ?? "UNKNOWN";
  const sub = service.subState?.toUpperCase();
  return sub ? `${active} · ${sub}` : active;
}

export function ServiceObservationPanel() {
  const [observation, setObservation] = useState<ServiceObservationSnapshot | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setObservation(await serviceObservationProvider.observe());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!observation) {
    return <div className="observation-loading">Reading allowlisted service status…</div>;
  }

  const live = observation.source === "systemd-dbus-list-units";

  return (
    <section className="service-observation">
      <div className="service-observation-head">
        <div>
          <small>SERVICE STATUS · ALLOWLIST ONLY</small>
          <b>{live ? "SYSTEMD D-BUS / LISTUNITS" : "FIXTURE FALLBACK"}</b>
        </div>
        <div className="service-observation-actions">
          <span>{observation.availability.toUpperCase()}</span>
          <button onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? "Reading…" : "Refresh"}
          </button>
        </div>
      </div>

      {observation.availability === "unavailable" && (
        <div className="observation-fixture-warning">
          Service observation is unavailable
          {observation.reason ? ` · ${observation.reason}` : ""}. No service state is inferred.
        </div>
      )}

      <div className="service-list">
        {observation.services.map((service) => (
          <div className="service-row" key={service.id}>
            <div>
              <b>{service.label}</b>
              <small>{service.unit}</small>
            </div>
            <span>{service.loadState ?? "unobserved"}</span>
            <em className={stateClass(service)}>{stateText(service)}</em>
          </div>
        ))}
      </div>

      <div className="observation-receipt">
        <span>method = ListUnits</span>
        <span>allowlist_only = true</span>
        <span>read_only = true</span>
        <span>execution_authority = false</span>
        <span>effect_performed = false</span>
      </div>
    </section>
  );
}
