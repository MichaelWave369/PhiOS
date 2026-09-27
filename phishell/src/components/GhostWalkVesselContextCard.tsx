import { useCallback, useEffect, useState } from "react";
import {
  ghostWalkVesselContextProvider,
  type GhostWalkVesselContext,
} from "../ghostwalk/vesselContext";

function healthWord(context: GhostWalkVesselContext) {
  if (context.health === "healthy") return "NOMINAL";
  if (context.health === "attention") return "ATTENTION";
  if (context.health === "failed") return "FAILED";
  if (context.health === "transitioning") return "TRANSITION";
  return "IDLE";
}

export function GhostWalkVesselContextCard() {
  const [context, setContext] = useState<GhostWalkVesselContext | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const refresh = useCallback(async () => {
    const next = await ghostWalkVesselContextProvider.read();
    setUnavailable(next === null);
    if (next) setContext(next);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = globalThis.setInterval(() => {
      void refresh();
    }, 2_000);
    return () => globalThis.clearInterval(timer);
  }, [refresh]);

  if (!context) {
    return (
      <section className="vessel-ghostwalk unavailable">
        <div className="vessel-ghostwalk-head">
          <span>GHOST WALK CONTEXT</span>
          <b>UNAVAILABLE</b>
        </div>
        <p>
          No validated Ghost Walk projection is available to PhiVessel. Vessie will not infer
          runtime health from absence.
        </p>
        <small>READ ONLY · LIFECYCLE AUTHORITY FALSE</small>
      </section>
    );
  }

  return (
    <section className={`vessel-ghostwalk ${context.health}`}>
      <div className="vessel-ghostwalk-head">
        <span>GHOST WALK CONTEXT</span>
        <b>{healthWord(context)}</b>
      </div>

      <p>{context.summary}</p>

      <div className="vessel-ghostwalk-facts">
        <span>host {context.hostStatus}</span>
        <span>run {context.runGeneration}</span>
        <span>listener {context.listenerLive ? "live" : "down"}</span>
        <span>baseline {context.baselineFresh ? "fresh" : context.baselineArmed ? "attention" : "disarmed"}</span>
      </div>

      {context.explanation.slice(0, 3).map((item) => (
        <div className="vessel-ghostwalk-explanation" key={item}>
          {item}
        </div>
      ))}

      {unavailable && (
        <div className="vessel-ghostwalk-stale">
          Latest refresh failed validation. This card is showing the last validated context.
        </div>
      )}

      <small>
        READ ONLY · ACTION AUTHORITY FALSE · EXECUTION AUTHORITY FALSE · LIFECYCLE AUTHORITY FALSE
      </small>
    </section>
  );
}
