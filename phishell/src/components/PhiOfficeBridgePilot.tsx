import { useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkspaceBridgeHost,
  generateBridgeSessionId,
} from "../shell/workspaceBridge";
import { reviewPhiOfficePilotEndpoint } from "../shell/workspaceBridgePilotConfig";
import {
  MAX_PROJECT_MANIFEST_BYTES,
  type SelectedProjectReference,
} from "../shell/projectManifestSelection";
import {
  PROJECT_REGISTRY_KEY,
  forgetProject,
  loadProjectRegistry,
  rememberReviewedProject,
  storeProjectRegistry,
  type SavedProjectReference,
} from "../shell/projectRegistry";
import {
  PHIOFFICE_PROJECT_ADAPTER_ID,
  findProjectAdapterForTarget,
  listReviewedProjectAdapters,
  type ReviewedProjectSource,
} from "../shell/projectAdapters";
import { readProjectIdentityWithAdapter } from "../shell/projectAdapterReader";
import { type V2MigrationPreview } from "../shell/projectRegistryV2";
import {
  commitProviderV2Copy,
  inspectProviderV2Rollback,
  prepareProviderV2Copy,
  rollbackProviderV2Copy,
  type ProviderV2CopyPlan,
  type ProviderV2RollbackReview,
} from "../shell/projectRegistryV2Copy";
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
  const [selectedProject, setSelectedProject] = useState<
    (SelectedProjectReference & { source: ReviewedProjectSource }) | null
  >(null);
  const [remembered, setRemembered] = useState<SavedProjectReference[]>([]);
  const [rememberedPick, setRememberedPick] = useState("");
  const [registryReadable, setRegistryReadable] = useState(true);
  const [registryNotice, setRegistryNotice] = useState("");
  const [v2Preview, setV2Preview] = useState<V2MigrationPreview | null>(null);
  const [v2CopyPlan, setV2CopyPlan] = useState<ProviderV2CopyPlan | null>(null);
  const [v2RollbackReview, setV2RollbackReview] = useState<ProviderV2RollbackReview | null>(null);
  const [v2Notice, setV2Notice] = useState("");
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
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
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
      const parsed = readProjectIdentityWithAdapter(
        PHIOFFICE_PROJECT_ADAPTER_ID, await file.text(),
      );
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
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
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
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
    if (!selectedProject || !registryReadable) return;
    try {
      const next = rememberReviewedProject(remembered, selectedProject);
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
    if (!found || !hostRef.current
      || !findProjectAdapterForTarget(found.source, "phioffice")) return;
    selectionRevisionRef.current += 1;
    hostRef.current.revokeProject();
    setApproved(false);
    setSelectedProject({ projectRef: found.projectRef, title: found.title, source: found.source });
    setStatus("Remembered project selected. Explicit approval is still required.");
  };

  const forgetRemembered = () => {
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
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
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
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
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
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

  const inspectQualifiedIdentityPreview = () => {
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    setV2Notice("");
    if (!active || !registryReadable) return;
    try {
      const plan = prepareProviderV2Copy(globalThis.localStorage);
      setV2Preview(plan.preview);
      setV2CopyPlan(plan);
      setV2Notice("Preview only. V1 is unchanged. Creating V2 requires separate operator confirmation.");
    } catch (error) {
      setV2Notice(error instanceof Error ? error.message : "Project identity preview unavailable");
    }
  };

  const createQualifiedIdentityCopy = () => {
    if (!active || !registryReadable || !v2CopyPlan) return;
    if (!globalThis.confirm(
      "Create a separate V2 browser-local metadata copy? V1 stays intact. "
      + "No permissions, project files or installed apps transfer. "
      + "Browser storage is not a guaranteed backup.",
    )) return;
    try {
      const count = commitProviderV2Copy(globalThis.localStorage, v2CopyPlan, true);
      setV2Preview(null);
      setV2CopyPlan(null);
      setV2Notice(`Created a separate V2 metadata copy of ${count} project references. `
        + "V1 remains active. No approvals transferred. Inspect V2 before requesting rollback.");
    } catch (error) {
      setV2Preview(null);
      setV2CopyPlan(null);
      setV2Notice(error instanceof Error ? error.message : "V2 copy could not be verified");
    }
  };

  const inspectExistingQualifiedCopy = () => {
    if (!active || !registryReadable) return;
    setV2Preview(null);
    setV2CopyPlan(null);
    setV2RollbackReview(null);
    try {
      const review = inspectProviderV2Rollback(globalThis.localStorage);
      setV2RollbackReview(review);
      setV2Notice("V2 and V1 contain equivalent references. Review identities before optional rollback.");
    } catch (error) {
      setV2Notice(error instanceof Error ? error.message : "V2 rollback inspection unavailable");
    }
  };

  const removeQualifiedIdentityCopy = () => {
    if (!active || !registryReadable || !v2RollbackReview) return;
    if (!globalThis.confirm(
      "Remove ONLY the reviewed V2 browser-local copy? "
      + "V1 remains in place. This will not revoke or install any app.",
    )) return;
    try {
      rollbackProviderV2Copy(globalThis.localStorage, v2RollbackReview, true);
      setV2RollbackReview(null);
      setV2Notice("Reviewed V2 copy removed and absence verified. V1 remains unchanged.");
    } catch (error) {
      setV2RollbackReview(null);
      setV2Notice(error instanceof Error ? error.message : "V2 rollback could not be verified");
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
                <div className="phios-project-adapter-catalog" aria-label="Reviewed project adapters">
                  <b>Reviewed project adapters · reference-only</b>
                  {listReviewedProjectAdapters().map((adapter) => (
                    <p key={adapter.id} className="muted">
                      {adapter.title}: {adapter.providerAppId} → {adapter.targetAppId}
                      {" · "}{adapter.status}
                      {" · "}No file authority
                    </p>
                  ))}
                  <p className="muted">
                    PhiID and PhiCloud do not have reviewed project adapters yet.
                  </p>
                </div>
                <p className="muted">
                  Saving is optional. Only ID and display title are retained,
                  never files, credentials, or sharing approval.
                </p>
                {registryReadable && (
                  <>
                    <button type="button"
                      disabled={!selectedProject
                        || !findProjectAdapterForTarget(selectedProject.source, "phioffice")
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
                {registryReadable && (
                  <div className="phios-bridge-qualified-preview" aria-label="Provider-qualified identity preview">
                    <b>Project identity V2 · review only</b>
                    <p className="muted">
                      Existing saved projects remain in V1. A future provider-qualified registry
                      would distinguish app providers even when their project IDs match.
                      No source, approvals or installed apps change.
                    </p>
                    <button type="button" onClick={inspectQualifiedIdentityPreview}>
                      Preview provider-qualified project IDs
                    </button>
                    {v2Preview && (
                      <div role="status" className="phios-bridge-qualified-results">
                        Preview: {v2Preview.recordCount} project references,
                        0 writes, 0 approvals transferred.
                        <ul>
                          {v2Preview.entries.map((entry) => (
                            <li key={entry.providerAppId + ":" + entry.projectRef}>
                              {entry.providerAppId} / {entry.projectRef}
                            </li>
                          ))}
                        </ul>
                        No V2 registry was written.
                      </div>
                    )}
                    {v2Notice && <p role="status" className="muted">{v2Notice}</p>}
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
                <button type="button" disabled={!hostRef.current || !selectedProject || approved
                  || !findProjectAdapterForTarget(selectedProject.source, "phioffice")} onClick={() => {
                  if (!selectedProject
                    || !findProjectAdapterForTarget(selectedProject.source, "phioffice")) return;
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
