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
import {
  PROJECT_REGISTRY_KEY,
  forgetProject,
  loadProjectRegistry,
  rememberProject,
  storeProjectRegistry,
  type SavedProjectReference,
} from "../shell/projectRegistry";
import {
  PORTABLE_PROJECT_BUNDLE_MAX_BYTES,
  decodePortableProjectBundle,
  encodePortableProjectBundle,
  previewProjectBundleMerge,
  type ProjectBundleMergePreview,
} from "../shell/projectRegistryPortable";

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
  const [remembered, setRemembered] = useState<SavedProjectReference[]>([]);
  const [rememberedPick, setRememberedPick] = useState("");
  const [registryReadable, setRegistryReadable] = useState(true);
  const [registryNotice, setRegistryNotice] = useState("");
  const [pendingImport, setPendingImport] = useState<{
    incoming: SavedProjectReference[];
    preview: ProjectBundleMergePreview;
  } | null>(null);
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
    setPendingImport(null);
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

  const startPilot = () => {
    setPendingImport(null);
    // This is an operator-initiated read. No registry or external app is
    // accessed in an ordinary, unconfigured PhiShell deployment.
    try {
      setRemembered(loadProjectRegistry());
      setRememberedPick("");
      setRegistryReadable(true);
      setRegistryNotice("Saved reference labels stay in this browser only.");
    } catch {
      setRemembered([]);
      setRememberedPick("");
      setRegistryReadable(false);
      setRegistryNotice("Saved project list unavailable or invalid. Nothing was overwritten.");
    }
    setActive(true);
    setStatus("Loading configured PhiOffice pilot");
  };

  const rememberSelection = () => {
    if (!selectedProject || !registryReadable) return;
    try {
      const next = rememberProject(remembered, selectedProject);
      storeProjectRegistry(next);
      setRemembered(next);
      setRememberedPick(selectedProject.projectRef);
      setRegistryNotice("Project ID and display title remembered on this device. No approval saved.");
    } catch (error) {
      setRegistryNotice(error instanceof Error ? error.message : "Could not save project reference");
    }
  };

  const useRememberedSelection = () => {
    const found = remembered.find(({ projectRef }) => projectRef === rememberedPick);
    if (!found || !hostRef.current) return;
    selectionRevisionRef.current += 1;
    hostRef.current.revokeProject();
    setApproved(false);
    setSelectedProject({ projectRef: found.projectRef, title: found.title });
    setStatus("Remembered project selected. Explicit approval is still required.");
  };

  const forgetRemembered = () => {
    if (!registryReadable || !rememberedPick) return;
    const projectRef = rememberedPick;
    try {
      const next = forgetProject(remembered, projectRef);
      storeProjectRegistry(next);
      setRemembered(next);
      setRememberedPick("");
      if (selectedProject?.projectRef === projectRef) {
        selectionRevisionRef.current += 1;
        hostRef.current?.revokeProject();
        setApproved(false);
        setSelectedProject(null);
      }
      setRegistryNotice("Saved project reference forgotten on this device.");
    } catch (error) {
      setRegistryNotice(error instanceof Error ? error.message : "Could not forget project");
    }
  };

  const clearRemembered = () => {
    if (!globalThis.confirm("Clear every saved PhiOS project reference on this browser?")) return;
    try {
      globalThis.localStorage.removeItem(PROJECT_REGISTRY_KEY);
      setRemembered([]);
      setRememberedPick("");
      setPendingImport(null);
      setRegistryReadable(true);
      selectionRevisionRef.current += 1;
      hostRef.current?.revokeProject();
      setApproved(false);
      setSelectedProject(null);
      setRegistryNotice("All local project references cleared. Existing app knowledge cannot be erased.");
    } catch {
      setRegistryNotice("Browser storage could not be cleared.");
    }
  };

  const exportReferences = () => {
    if (!registryReadable) return;
    try {
      // Re-read the current browser store to avoid exporting stale UI state.
      const entries = loadProjectRegistry();
      const contents = encodePortableProjectBundle(entries);
      const url = URL.createObjectURL(new Blob([contents], { type: "application/json" }));
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = "phios-project-references-v1.json";
        link.click();
      } finally {
        // A small delay allows the browser download handoff to begin.
        globalThis.setTimeout(() => URL.revokeObjectURL(url), 0);
      }
      setRegistryNotice("Exported IDs, titles and source labels only. No app approvals or project files.");
    } catch (error) {
      setRegistryNotice(error instanceof Error ? error.message : "Could not export local references");
    }
  };

  const inspectImport = async (file: File) => {
    const revision = ++selectionRevisionRef.current;
    setPendingImport(null);
    if (!active || !registryReadable) return;
    try {
      if (file.size > PORTABLE_PROJECT_BUNDLE_MAX_BYTES) {
        throw new Error("Portable project references must be under 16 KiB");
      }
      const incoming = decodePortableProjectBundle(await file.text());
      if (selectionRevisionRef.current !== revision || !active) return;
      const preview = previewProjectBundleMerge(loadProjectRegistry(), incoming);
      setPendingImport({ incoming, preview });
      setRegistryNotice("Import preview ready. No browser data changed; no app approval granted.");
    } catch (error) {
      if (selectionRevisionRef.current !== revision || !active) return;
      setRegistryNotice(error instanceof Error ? error.message : "Portable registry import rejected");
    }
  };

  const commitImport = () => {
    if (!active || !registryReadable || !pendingImport) return;
    try {
      // Fresh storage read prevents accidental replacement of another
      // local record updated after the preview. Local titles always win.
      const latest = loadProjectRegistry();
      const result = previewProjectBundleMerge(latest, pendingImport.incoming);
      if (result.added > 0) storeProjectRegistry(result.entries);
      setRemembered(result.entries);
      setPendingImport(null);
      setRegistryNotice(`Imported ${result.added} new references; skipped ${result.skipped} existing. No approvals changed.`);
    } catch (error) {
      setRegistryNotice(error instanceof Error ? error.message : "Could not import project references");
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
                  {approved ? " · Approved for this session" : " · Not yet shared until approved"}
                </p>
              )}
              <div className="phios-bridge-local-registry" aria-label="Browser-local project references">
                <b>Remembered projects · local-only</b>
                <p className="muted">
                  Saving is optional. Only ID and display title are retained,
                  never files, credentials, or sharing approval.
                </p>
                {registryReadable && (
                  <>
                    <button type="button"
                      disabled={!selectedProject
                        || remembered.some((entry) => entry.projectRef === selectedProject.projectRef
                          && entry.title === selectedProject.title)}
                      onClick={rememberSelection}>
                      Remember this project on device
                    </button>
                    <label htmlFor="phios-pilot-remembered-project">Saved project references</label>
                    <select id="phios-pilot-remembered-project"
                      aria-label="Saved project references"
                      value={rememberedPick}
                      onChange={(event) => setRememberedPick(event.currentTarget.value)}>
                      <option value="">Choose a saved project</option>
                      {remembered.map((entry) => (
                        <option key={entry.projectRef} value={entry.projectRef}>
                          {entry.title} ({entry.projectRef})
                        </option>
                      ))}
                    </select>
                    <div className="phios-bridge-pilot-actions">
                      <button type="button" disabled={!rememberedPick}
                        onClick={useRememberedSelection}>Use remembered project</button>
                      <button type="button" disabled={!rememberedPick}
                        onClick={forgetRemembered}>Forget saved project</button>
                    </div>
                  </>
                )}
                {registryReadable && (
                  <div className="phios-bridge-portable-registry">
                    <b>Portable project references · offline</b>
                    <p className="muted">
                      JSON exports include only project IDs, titles and source labels.
                      No project files or approvals. Treat project titles as private metadata.
                    </p>
                    <button type="button" onClick={exportReferences}
                      disabled={remembered.length === 0}>
                      Export project references
                    </button>
                    <label htmlFor="phios-pilot-reference-import">Import project reference bundle</label>
                    <input id="phios-pilot-reference-import" type="file"
                      accept=".json,application/json"
                      aria-label="Import project reference bundle"
                      onChange={(event) => {
                        const file = event.currentTarget.files?.[0];
                        event.currentTarget.value = "";
                        if (file) void inspectImport(file);
                      }}
                    />
                    {pendingImport && (
                      <div role="status" className="phios-bridge-import-preview">
                        Preview: {pendingImport.preview.added} new,
                        {" "}{pendingImport.preview.skipped} already saved.
                        Local titles are preserved.
                        <button type="button" disabled={pendingImport.preview.added === 0}
                          onClick={commitImport}>Confirm reference import</button>
                        <button type="button" onClick={() => setPendingImport(null)}>
                          Cancel import
                        </button>
                      </div>
                    )}
                  </div>
                )}
                <button type="button" onClick={clearRemembered}
                  disabled={registryReadable && remembered.length === 0}>
                  Clear saved project list
                </button>
                <p role="status" className="muted">{registryNotice}</p>
              </div>
            </div>
          )}
          <div className="phios-bridge-pilot-actions">
            {!active ? (
              <button type="button" onClick={startPilot}>Start opt-in pilot</button>
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
