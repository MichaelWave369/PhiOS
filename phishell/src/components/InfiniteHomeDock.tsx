import { useState } from "react";
import "./InfiniteHomeDock.css";

/**
 * Operator-initiated navigation only. These destinations are NOT health probes,
 * installed-app registry entries, provider clients, or grants.
 */
export const HOME_DOORWAYS = [
  {
    id: "porch",
    title: "Infinite Porch",
    description: "Local AI home and trusted-device control UI. Requires a separately running Porch node.",
    href: "http://127.0.0.1:7331/",
    action: "OPEN LOCAL PORCH",
    status: "NOT OBSERVED · LOGIN REQUIRED",
  },
  {
    id: "commons",
    title: "Infinite Commons",
    description: "Shared portal/world experience. Opens the public website only when chosen.",
    href: "https://michaelwave369.github.io/Infinite-Commons/",
    action: "VISIT COMMONS PORTAL",
    status: "EXTERNAL WEBSITE · NOT INSTALLED",
  },
] as const;

type HealthOutcome = "CANDIDATE_RESPONSE_OBSERVED" | "INVALID_RESPONSE" | "UNAVAILABLE";
type ProbeResult = { outcome: HealthOutcome; candidateVersion: string | null; identityVerified: false };

export function InfiniteHomeDock() {
  const [porchProbe, setPorchProbe] = useState<ProbeResult | null>(null);
  const [probing, setProbing] = useState(false);

  async function checkLocalPorch() {
    if (probing) return;
    setProbing(true);
    setPorchProbe(null);
    try {
      // Only the same-origin PhiShell local server can attempt this host-side probe.
      // Public Pages, static previews and disconnected sessions fail closed.
      const response = await fetch("/api/v1/porch-health-preflight", {
        method: "GET",
        cache: "no-store",
        redirect: "error",
        credentials: "omit",
        headers: { "x-phios-porch-preflight": "1" },
      });
      if (!response.ok) throw new Error("Local PhiShell transport not available");
      const body: unknown = await response.json();
      if (!body || typeof body !== "object") throw new Error("Invalid preflight response");
      const data = body as Record<string, unknown>;
      const valid = (
        data.schemaVersion === "phios.porch_health_preflight.v0.1" &&
        ["CANDIDATE_RESPONSE_OBSERVED", "INVALID_RESPONSE", "UNAVAILABLE"].includes(
          String(data.outcome),
        ) &&
        data.identityVerified === false &&
        data.executionAuthority === false &&
        data.effectPerformed === false
      );
      if (!valid) throw new Error("Invalid preflight contract");
      setPorchProbe({
        outcome: data.outcome as HealthOutcome,
        candidateVersion: typeof data.candidateVersion === "string" &&
          data.candidateVersion.length <= 48 ? data.candidateVersion : null,
        identityVerified: false,
      });
    } catch {
      setPorchProbe({ outcome: "UNAVAILABLE", candidateVersion: null, identityVerified: false });
    } finally {
      setProbing(false);
    }
  }

  return (
    <section className="panel infinite-home-dock" aria-label="Infinite Porch and Commons doorways">
      <div className="panel-title">Φ HOME · YOUR AI'S PLACE IN PHIOS</div>
      <p className="infinite-home-intro">
        Every PhiOS workspace should have a home for local intelligence and a doorway into
        the Commons. This first step supplies <strong>explicit operator-opened links</strong>.
        It does not start Porch, load a model, join a peer, or install a Commons world.
      </p>
      <div className="infinite-home-grid">
        {HOME_DOORWAYS.map((door) => (
          <article className="infinite-home-door" key={door.id}>
            <div className="infinite-home-door-header">
              <strong>{door.title}</strong>
              <small>{door.status}</small>
            </div>
            <p>{door.description}</p>
            <a href={door.href} target="_blank" rel="noopener noreferrer">
              {door.action} ↗
            </a>
            {door.id === "porch" && (
              <div className="infinite-porch-preflight">
                <button type="button" disabled={probing} onClick={() => void checkLocalPorch()}>
                  {probing ? "CHECKING LOCAL HEALTH…" : "CHECK LOCAL PORCH HEALTH"}
                </button>
                <small role="status" aria-live="polite">
                  {!porchProbe ? "NOT CHECKED · IDENTITY NOT VERIFIED" :
                    porchProbe.outcome === "CANDIDATE_RESPONSE_OBSERVED"
                      ? `PORCH-LIKE RESPONSE ${porchProbe.candidateVersion ?? ""} · IDENTITY NOT VERIFIED`
                      : porchProbe.outcome === "INVALID_RESPONSE"
                        ? "RESPONSE REJECTED · IDENTITY NOT VERIFIED"
                        : "NO VALID RESPONSE · IDENTITY NOT VERIFIED"}
                </small>
              </div>
            )}
          </article>
        ))}
      </div>
      <p className="infinite-home-caution">
        <strong>Connection boundary:</strong> No endpoint probe or background network request
        is made by this dock. The local Porch page uses its own operator token.
        Opening a link grants PhiOS no account, model, file, network, or execution rights.
        Offline availability, device trust, and deployment health remain unverified here.
      </p>
    </section>
  );
}
