import { useState } from "react";
import { inspectPixelForgeLaunchReadiness } from "../shell/pixelForgeLaunchReadiness";
import { PROJECT_REGISTRY_V2_KEY } from "../shell/projectRegistryV2";

function currentReadiness() {
  let v2Raw: string | null = null;
  try {
    v2Raw = globalThis.localStorage.getItem(PROJECT_REGISTRY_V2_KEY);
  } catch {
    // localStorage can be denied, so "ready" is never inferred.
  }
  return inspectPixelForgeLaunchReadiness({
    configuredUrl: import.meta.env.VITE_PHIOS_PIXELFORGE_BRIDGE_URL,
    approvedOrigin: import.meta.env.VITE_PHIOS_PIXELFORGE_BRIDGE_APPROVED_ORIGIN,
    shellOrigin: globalThis.location.origin,
    v2Raw,
  });
}

/**
 * Read-only launch discovery: never loads PixelForge, creates a session,
 * grants a project, probes the network or installs a package.
 */
export function PixelForgeLaunchCard({ openApp }: { openApp: (id: string) => void }) {
  const [readiness, setReadiness] = useState(currentReadiness);

  const status = readiness.status === "endpoint-disabled"
    ? "DISABLED · No exact reviewed PixelForge endpoint configured"
    : readiness.status === "registry-invalid"
      ? "HELD · V2 identity registry unavailable or invalid"
      : readiness.status === "no-pixelforge-identity"
        ? "HELD · No reviewed PixelForge identity in V2"
        : "BROWSER PILOT ELIGIBLE · Separate operator consent still required";

  return (
    <section className="panel phios-pixelforge-launch-card"
      aria-label="PixelForge governed launch readiness">
      <div className="panel-title">PIXELFORGE · BROWSER PILOT DISCOVERY</div>
      <p>PixelForge is <strong>not a native installed PhiOS app</strong>.
        This is a read-only view of local launch prerequisites, not a network
        health probe or evidence that the remote application is reachable.</p>
      <p role="status"><strong>{status}</strong></p>
      <p>Reviewed PixelForge V2 identities: {readiness.pixelForgeIdentityCount}.
        The PhiOffice registry and its approvals are separate.</p>
      <div className="quick-actions">
        <button type="button" onClick={() => setReadiness(currentReadiness())}>
          Refresh local readiness
        </button>
        <button type="button" onClick={() => openApp("pixelforge")}>
          Open PixelForge pilot in Build Field
        </button>
      </div>
      <p className="muted">Opening Build Field does not load an iframe. If
        configured and ready, you must separately click Start PixelForge pilot,
        select its reviewed ID, and approve sharing for this session.
        No project, VR world, GLB, shell command or permission transfers
        through this tile.</p>
    </section>
  );
}
