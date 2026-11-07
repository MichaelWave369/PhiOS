import { useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkspaceBridgeHost,
  generateBridgeSessionId,
} from "../shell/workspaceBridge";
import { reviewPhiOfficePilotEndpoint } from "../shell/workspaceBridgePilotConfig";

/**
 * Explicit, browser-only test pilot. No backend, no install, no real project
 * data or tokens. Host operator approves one synthetic reference per session.
 */
export function PhiOfficeBridgePilot() {
  const endpoint = useMemo(() => reviewPhiOfficePilotEndpoint(
    import.meta.env.VITE_PHIOS_OFFICE_BRIDGE_URL,
    import.meta.env.VITE_PHIOS_OFFICE_BRIDGE_APPROVED_ORIGIN,
    globalThis.location.origin,
  ), []);
  const [active, setActive] = useState(false);
  const [approved, setApproved] = useState(false);
  const [status, setStatus] = useState("Disconnected");
  const frameRef = useRef<HTMLIFrameElement>(null);
  const hostRef = useRef<ReturnType<typeof createWorkspaceBridgeHost> | null>(null);
  const retryRef = useRef<ReturnType<typeof globalThis.setInterval> | null>(null);

  const stopBootstrapRetry = () => {
    if (retryRef.current !== null) {
      globalThis.clearInterval(retryRef.current);
      retryRef.current = null;
    }
  };

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const host = hostRef.current;
      const frame = frameRef.current?.contentWindow;
      if (!host || !frame) return;
      const response = host.handle(event);
      if (!response) return;
      frame.postMessage(response.message, response.targetOrigin);
      if (response.message.type === "host.ready") {
        stopBootstrapRetry();
        setStatus("Client handshake accepted. Project access remains operator-controlled.");
      } else if (response.message.type === "host.context") {
        setStatus("Shared synthetic project reference only. No files or permissions.");
      } else if (response.message.type === "host.denied") {
        setStatus("Context request denied: approval required.");
      }
    };
    globalThis.addEventListener("message", handleMessage);
    return () => {
      globalThis.removeEventListener("message", handleMessage);
      stopBootstrapRetry();
      hostRef.current?.revokeProject();
      hostRef.current = null;
    };
  }, []);

  const disconnect = () => {
    stopBootstrapRetry();
    hostRef.current?.revokeProject();
    hostRef.current = null;
    setApproved(false);
    setActive(false);
    setStatus("Disconnected");
  };

  const onFrameLoad = () => {
    if (!endpoint || !active || !frameRef.current?.contentWindow) return;
    // Each navigation/reload gets a brand new, unapproved session.
    stopBootstrapRetry();
    hostRef.current?.revokeProject();
    const frame = frameRef.current.contentWindow;
    const host = createWorkspaceBridgeHost({
      appId: "phioffice",
      appOrigin: endpoint.origin,
      frameSource: frame,
      sessionId: generateBridgeSessionId(),
    });
    hostRef.current = host;
    setApproved(false);
    const bootstrap = host.bootstrap();
    // onLoad can precede React's useEffect message listener in the child.
    // Repeat only the same bounded, origin-bound bootstrap, never with '*'.
    // The client treats the same session's duplicate bootstrap as a no-op.
    let attempts = 1;
    frame.postMessage(bootstrap.message, bootstrap.targetOrigin);
    retryRef.current = globalThis.setInterval(() => {
      if (hostRef.current !== host || frameRef.current?.contentWindow !== frame) {
        stopBootstrapRetry();
        return;
      }
      if (attempts >= 10) {
        stopBootstrapRetry();
        setStatus("PhiOffice handshake timed out. Disconnect and review the configured endpoint.");
        return;
      }
      attempts += 1;
      frame.postMessage(bootstrap.message, bootstrap.targetOrigin);
    }, 350);
    setStatus("Waiting for PhiOffice's origin-bound handshake.");
  };

  return (
    <section className="phios-bridge-pilot" aria-label="PhiOffice workspace bridge pilot">
      <div className="panel-title">Φ PHIOFFICE WORKSPACE BRIDGE · PILOT ONLY</div>
      <p>
        This is a browser interoperability pilot. It is not an installed PhiOffice
        application, a general app launcher, or a real project-data connection.
      </p>
      {!endpoint ? (
        <p role="status">
          Disabled until two exact, different-origin build settings identify an
          explicitly reviewed PhiOffice URL and its expected origin.
        </p>
      ) : (
        <>
          <p className="muted">Configured endpoint: {endpoint.origin}</p>
          <div className="phios-bridge-pilot-actions">
            {!active ? (
              <button type="button" onClick={() => {
                setActive(true);
                setStatus("Loading configured PhiOffice pilot");
              }}>Start opt-in pilot</button>
            ) : (
              <>
                <button type="button" disabled={!hostRef.current || approved} onClick={() => {
                  hostRef.current?.approveProject("project:phios-pilot");
                  setApproved(true);
                  setStatus("Synthetic project approved for this session");
                }}>Approve synthetic ref</button>
                <button type="button" disabled={!approved} onClick={() => {
                  hostRef.current?.revokeProject();
                  setApproved(false);
                  setStatus("Access revoked for future project requests");
                }}>Revoke</button>
                <button type="button" onClick={disconnect}>Disconnect</button>
              </>
            )}
          </div>
          <p role="status">{status}</p>
          {active && <iframe
            ref={frameRef}
            title="PhiOffice separately reviewed browser pilot"
            src={endpoint.url}
            referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-same-origin allow-forms"
            onLoad={onFrameLoad}
          />}
        </>
      )}
    </section>
  );
}
