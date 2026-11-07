import { useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkspaceBridgeHost,
  generateBridgeSessionId,
} from "../shell/workspaceBridge";
import { reviewPhiOfficePilotEndpoint } from "../shell/workspaceBridgePilotConfig";
import {
  extractProjectReference,
  MAX_PROJECT_MANIFEST_BYTES,
  type SelectedProjectReference,
} from "../shell/projectManifestSelection";

/**
 * Explicit, browser-only test pilot. No backend, no install, no real project
 * data or tokens. Operator manually selects a local manifest header per session.
 */
export function PhiOfficeBridgePilot() {
  const endpoint = useMemo(() => reviewPhiOfficePilotEndpoint(
    import.meta.env.VITE_PHIOS_OFFICE_BRIDGE_URL,
    import.meta.env.VITE_PHIOS_OFFICE_BRIDGE_APPROVED_ORIGIN,
    globalThis.location.origin,
  ), []);
  const [active, setActive] = useState(false);
  const [approved, setApproved] = useState(false);
  const [selectedProject, setSelectedProject] = useState<SelectedProjectReference | null>(null);
  const selectionRevisionRef = useRef(0);
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
        setStatus("Shared operator-selected project reference only. No files or permissions.");
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
    selectionRevisionRef.current += 1;
    stopBootstrapRetry();
    hostRef.current?.revokeProject();
    hostRef.current = null;
    setApproved(false);
    setSelectedProject(null);
    setActive(false);
    setStatus("Disconnected");
  };

  const chooseManifest = async (file: File) => {
    const revision = ++selectionRevisionRef.current;
    const host = hostRef.current;
    host?.revokeProject();
    setSelectedProject(null);
    setApproved(false);
    if (!host) {
      setStatus("Start a connected pilot before choosing a project");
      return;
    }
    try {
      if (file.size > MAX_PROJECT_MANIFEST_BYTES) {
        throw new Error("Project manifest must be under 256 KiB");
      }
      const parsed = extractProjectReference(await file.text());
      // A stale file read must not reselect a project in a new session.
      if (selectionRevisionRef.current !== revision || hostRef.current !== host) return;
      setSelectedProject(parsed);
      setStatus("Project header loaded locally; not yet approved for sharing.");
    } catch (error) {
      if (selectionRevisionRef.current !== revision || hostRef.current !== host) return;
      setStatus(error instanceof Error ? error.message : "Invalid project manifest");
    }
  };

  const onFrameLoad = () => {
    if (!endpoint || !active || !frameRef.current?.contentWindow) return;
    // Each navigation/reload gets a brand new, unapproved session.
    selectionRevisionRef.current += 1;
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
        application, a general app launcher, or a project-data connection.
        Select a local manifest to share its ID only, never its files.
      </p>
      {!endpoint ? (
        <p role="status">
          Disabled until two exact, different-origin build settings identify an
          explicitly reviewed PhiOffice URL and its expected origin.
        </p>
      ) : (
        <>
          <p className="muted">Configured endpoint: {endpoint.origin}</p>
          {active && (
            <div className="phios-bridge-project-picker">
              <label htmlFor="phios-pilot-project-manifest">Choose local PhiOffice project manifest</label>
              <input
                id="phios-pilot-project-manifest"
                type="file"
                accept=".json,application/json"
                aria-label="Choose local PhiOffice project manifest"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  event.currentTarget.value = "";
                  if (file) void chooseManifest(file);
                }}
              />
              {selectedProject && (
                <p className="muted">
                  Selected: <strong>{selectedProject.title}</strong>
                  {" · "}<code>{selectedProject.projectRef}</code>
                  {" · Not yet shared until approved"}
                </p>
              )}
            </div>
          )}
          <div className="phios-bridge-pilot-actions">
            {!active ? (
              <button type="button" onClick={() => {
                setActive(true);
                setStatus("Loading configured PhiOffice pilot");
              }}>Start opt-in pilot</button>
            ) : (
              <>
                <button type="button" disabled={!hostRef.current || !selectedProject || approved} onClick={() => {
                  if (!selectedProject) return;
                  hostRef.current?.approveProject(selectedProject.projectRef);
                  setApproved(true);
                  setStatus("Selected project reference approved for this session");
                }}>Approve selected project ref</button>
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
