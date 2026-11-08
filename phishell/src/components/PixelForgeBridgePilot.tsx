import { useEffect, useMemo, useRef, useState } from "react";
import { reviewPhiOfficePilotEndpoint } from "../shell/workspaceBridgePilotConfig";
import {
  createWorkspaceBridgeHost,
  generateBridgeSessionId,
} from "../shell/workspaceBridge";
import {
  PROJECT_REGISTRY_V2_KEY,
  listPixelForgeBridgeChoices,
  verifyPixelForgeBridgeChoice,
  type PixelForgeBridgeChoice,
} from "../shell/pixelForgeBridgeSelection";

/**
 * The PixelForge R12 child is a DIFFERENT app frame from PhiOffice.
 * This opt-in host never reads world files, GLBs, native resources or
 * PhiOffice's V1 project identity list. Only a specific reviewed PixelForge
 * V2 identity can be selected for this iframe's session.
 */
export function PixelForgeBridgePilot() {
  const endpoint = useMemo(() => reviewPhiOfficePilotEndpoint(
    import.meta.env.VITE_PHIOS_PIXELFORGE_BRIDGE_URL,
    import.meta.env.VITE_PHIOS_PIXELFORGE_BRIDGE_APPROVED_ORIGIN,
    globalThis.location.origin,
  ), []);
  const [active, setActive] = useState(false);
  const [options, setOptions] = useState<readonly PixelForgeBridgeChoice[]>([]);
  const [selectedRef, setSelectedRef] = useState("");
  const [approved, setApproved] = useState(false);
  const [status, setStatus] = useState("Not connected. No PixelForge project approval.");
  const frameRef = useRef<HTMLIFrameElement>(null);
  const hostRef = useRef<ReturnType<typeof createWorkspaceBridgeHost> | null>(null);
  const chosenRef = useRef<PixelForgeBridgeChoice | null>(null);
  const approvedRef = useRef<PixelForgeBridgeChoice | null>(null);
  // A separate snapshot is necessary: a changed V2 registry is NOT an
  // extension of a previously approved iframe capability, even if the
  // selected project happens to have the same title and ID.
  const approvedV2BytesRef = useRef<string | null>(null);
  const retryRef = useRef<ReturnType<typeof globalThis.setInterval> | null>(null);

  const stopRetry = () => {
    if (retryRef.current !== null) {
      globalThis.clearInterval(retryRef.current);
      retryRef.current = null;
    }
  };
  const safeRevoke = () => {
    hostRef.current?.revokeProject();
    approvedRef.current = null;
    approvedV2BytesRef.current = null;
    setApproved(false);
  };
  const currentV2 = () => globalThis.localStorage.getItem(PROJECT_REGISTRY_V2_KEY);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const host = hostRef.current;
      const frame = frameRef.current?.contentWindow;
      if (!host || !frame || event.source !== frame) return;
      // Any V2 mutation since approval immediately invalidates authority
      // BEFORE the host responds to another request, including same-tab edits.
      if (approvedRef.current) {
        try {
          if (currentV2() !== approvedV2BytesRef.current) {
            throw new Error("V2 changed since consent");
          }
          verifyPixelForgeBridgeChoice(currentV2(), approvedRef.current);
        } catch {
          host.revokeProject();
          approvedRef.current = null;
          approvedV2BytesRef.current = null;
          setApproved(false);
          setStatus("Saved V2 metadata changed; fresh PixelForge consent required");
        }
      }
      const response = host.handle(event);
      if (!response) return;
      frame.postMessage(response.message, response.targetOrigin);
      if (response.message.type === "host.ready") {
        stopRetry();
        setStatus("PixelForge handshake accepted. No project shared without approval.");
      } else if (response.message.type === "host.denied") {
        setStatus("PixelForge request denied; operator approval required");
      } else if (response.message.type === "host.context") {
        setStatus("Sent approved PixelForge project reference only; no world data");
      }
    };
    const onStorage = (event: StorageEvent) => {
      // Other-tab changes are observable asynchronously. In-tab changes are
      // caught synchronously before any future host reply in onMessage.
      if (event.storageArea !== globalThis.localStorage
          || (event.key !== PROJECT_REGISTRY_V2_KEY && event.key !== null)
          || !approvedRef.current) return;
      if (event.newValue !== approvedV2BytesRef.current) {
        hostRef.current?.revokeProject();
        approvedRef.current = null;
        approvedV2BytesRef.current = null;
        setApproved(false);
        setStatus("V2 registry changed in another tab; PixelForge approval revoked");
      }
    };
    globalThis.addEventListener("message", onMessage);
    globalThis.addEventListener("storage", onStorage);
    return () => {
      globalThis.removeEventListener("message", onMessage);
      globalThis.removeEventListener("storage", onStorage);
      stopRetry();
      hostRef.current?.revokeProject();
      hostRef.current = null;
      approvedRef.current = null;
      approvedV2BytesRef.current = null;
    };
  }, []);

  if (!endpoint) return (
    <section className="panel phios-pixelforge-bridge" aria-label="PixelForge browser pilot">
      <h3>PixelForge browser connection · disabled</h3>
      <p>Only a reviewed, explicitly configured separate-origin PixelForge URL
        and approved origin can activate this opt-in browser pilot.
        No iframe or permission exists in this build.</p>
    </section>
  );

  // Child must see the parent origin via both the exact query and browser
  // origin-only referrer. Never include a token or private project data here.
  const frameUrl = endpoint.url +
    "?phios_parent_origin=" + encodeURIComponent(globalThis.location.origin);

  const start = () => {
    safeRevoke();
    chosenRef.current = null;
    setSelectedRef("");
    try {
      const reviewed = listPixelForgeBridgeChoices(currentV2());
      setOptions(reviewed);
      setActive(true);
      setStatus("Loading configured PixelForge iframe. All project requests default to denial.");
    } catch (error) {
      setActive(false);
      setOptions([]);
      setStatus(error instanceof Error ? error.message : "V2 identities unavailable");
    }
  };

  const disconnect = () => {
    stopRetry();
    safeRevoke();
    hostRef.current = null;
    chosenRef.current = null;
    setSelectedRef("");
    setOptions([]);
    setActive(false);
    setStatus("Disconnected. Any new connection requires fresh operator approval.");
  };

  const choose = (ref: string) => {
    safeRevoke();
    setSelectedRef(ref);
    const found = options.find(e => e.projectRef === ref) ?? null;
    chosenRef.current = null;
    if (!found) {
      setStatus("No selected PixelForge provider-qualified reference");
      return;
    }
    try {
      chosenRef.current = verifyPixelForgeBridgeChoice(currentV2(), found);
      setStatus("Selected reviewed PixelForge V2 identity; explicit approval still required");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Identity changed; refresh list");
    }
  };

  const approve = () => {
    const host = hostRef.current;
    const chosen = chosenRef.current;
    if (!host || !chosen || approvedRef.current) return;
    try {
      const v2AtReview = currentV2();
      const reviewed = verifyPixelForgeBridgeChoice(v2AtReview, chosen);
      if (!globalThis.confirm(
        "Share only " + reviewed.providerAppId + " / " + reviewed.projectRef
        + " with the separate-origin PixelForge iframe for THIS session? "
        + "This shares no world files, GLBs, private assets or execution rights.",
      )) return;
      // The V2 store might have changed while the user considered the prompt.
      if (currentV2() !== v2AtReview) {
        throw new Error("V2 registry changed during confirmation; review and approve again");
      }
      verifyPixelForgeBridgeChoice(currentV2(), reviewed);
      host.approveProject(reviewed.projectRef);
      approvedRef.current = reviewed;
      approvedV2BytesRef.current = v2AtReview;
      setApproved(true);
      setStatus("Operator approved PixelForge identity for this iframe session only");
    } catch (error) {
      safeRevoke();
      setStatus(error instanceof Error ? error.message : "PixelForge project approval refused");
    }
  };

  const onFrameLoad = () => {
    if (!active || !frameRef.current?.contentWindow) return;
    stopRetry();
    safeRevoke();
    const frame = frameRef.current.contentWindow;
    const host = createWorkspaceBridgeHost({
      appId: "pixelforge",
      appOrigin: endpoint.origin,
      frameSource: frame,
      sessionId: generateBridgeSessionId(),
    });
    hostRef.current = host;
    // Browser load may precede child module registration. Repeating a
    // bootstrap for the same session cannot grant any permission.
    let attempts = 0;
    const bootstrap = () => {
      if (hostRef.current !== host || frameRef.current?.contentWindow !== frame) {
        stopRetry(); return;
      }
      if (attempts >= 10) {
        stopRetry();
        setStatus("PixelForge handshake timed out; disconnect and inspect endpoint");
        return;
      }
      attempts += 1;
      const outbound = host.bootstrap();
      frame.postMessage(outbound.message, outbound.targetOrigin);
    };
    bootstrap();
    retryRef.current = globalThis.setInterval(bootstrap, 350);
    setStatus("Waiting for PixelForge's session-bound handshake");
  };

  return (
    <section className="panel phios-pixelforge-bridge" aria-label="PixelForge browser pilot">
      <h3>PixelForge · separately consented browser workspace</h3>
      <p>Experimental local project-ID handoff. A PixelForge V2 label is not proof of
        world ownership or permission to open assets. PhiOffice uses a different
        frame, app ID, origin and approval session.</p>
      {!active ? (
        <button type="button" onClick={start}>Start PixelForge pilot</button>
      ) : (
        <>
          <label htmlFor="phios-pixelforge-bridge-choice">Operator-reviewed PixelForge ID</label>
          <select id="phios-pixelforge-bridge-choice" value={selectedRef}
            onChange={event => choose(event.currentTarget.value)}>
            <option value="">Choose a PixelForge V2 identity</option>
            {options.map(entry => (
              <option key={entry.projectRef} value={entry.projectRef}>
                {entry.title} ({entry.projectRef})
              </option>
            ))}
          </select>
          <p>Available reviewed PixelForge IDs: {options.length}. Neither a
            PhiOffice V1 reference nor an arbitrary typed ID can be selected.</p>
          <button type="button" disabled={!chosenRef.current || !hostRef.current || approved}
            onClick={approve}>Approve selected PixelForge ref</button>
          <button type="button" disabled={!approved} onClick={() => {
            safeRevoke();
            setStatus("Revoked PixelForge project access for future requests");
          }}>Revoke PixelForge approval</button>
          <button type="button" onClick={disconnect}>Disconnect PixelForge pilot</button>
          <iframe ref={frameRef} title="PixelForge independently reviewed browser pilot"
            src={frameUrl} sandbox="allow-scripts allow-same-origin allow-forms"
            referrerPolicy="origin" onLoad={onFrameLoad} />
        </>
      )}
      <p role="status">{status}</p>
      <small>Only an opaque identity label may be shared; no world file transfer,
        native install or persistent app grant. All requests are denied by default.</small>
    </section>
  );
}
