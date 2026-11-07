import { useEffect, useRef, useState } from "react";
import type { ShellEvent } from "../shell/model";
import { PHIPOSE_NAV_PROTOCOL, PhiPoseNavigationHost } from "../shell/phiPoseNavigationHost";

/**
 * Explicit, revocable, 5-minute foreground gesture navigation companion.
 * Requires an OverStrings-opened same-origin PhiShell popup.
 * Nav actions affect ONLY the local shell UI. No OS permissions or execution.
 */
export function PhiPoseCompanion({ dispatch }: { dispatch: (event: ShellEvent) => void }) {
  const hostRef = useRef<PhiPoseNavigationHost | null>(null);
  if (!hostRef.current) hostRef.current = new PhiPoseNavigationHost();
  const host = hostRef.current;
  const [active, setActive] = useState(false);
  const [demo, setDemo] = useState(false);
  const [status, setStatus] = useState("Disconnected. No gesture navigation permission.");
  const openedByOverStrings = (): Window | null => {
    const opener = globalThis.opener as Window | null;
    if (!opener) return null;
    try {
      const url = new URL(opener.location.href);
      const path = url.pathname;
      if (url.origin !== globalThis.location.origin ||
        !/(^|\/)OverStrings\//.test(path)) return null;
      return opener;
    } catch { return null; }
  };
  const revoke = () => {
    host.revoke();
    setActive(false);
    setStatus("Gesture navigation disabled. All earlier sessions revoked.");
  };
  useEffect(() => {
    const onMessage = (message: MessageEvent) => {
      if (!host.active) return;
      const result = host.accept(message, Date.now());
      if (result.reason === "untrusted_source") return;
      if (result.accepted) {
        dispatch(result.event);
        setStatus("Accepted safe UI navigation: " + result.actionId);
      } else {
        setStatus("Gesture request denied: " + result.reason);
        if (result.reason === "expired") setActive(false);
      }
      // A receipt never claims an external effect or completed execution.
      if (message.source && message.source === globalThis.opener) {
        try {
          (globalThis.opener as Window).postMessage({
            protocol: PHIPOSE_NAV_PROTOCOL, type: "receipt",
            accepted: result.accepted,
            status: result.accepted ? "accepted_for_ui_dispatch" : "denied",
            reason: result.reason,
            sequence: result.accepted ? result.sequence : null,
            action_id: result.accepted ? result.actionId : null
          }, globalThis.location.origin);
        } catch { /* no authority or state transfer on failure */ }
      }
    };
    globalThis.addEventListener("message", onMessage);
    return () => {
      globalThis.removeEventListener("message", onMessage);
      host.revoke();
    };
  }, [dispatch,host]);

  const enable = () => {
    const opener = openedByOverStrings();
    if (!opener) {
      setStatus("Open PhiOS using the OverStrings companion button, on the same origin.");
      return;
    }
    try {
      const now=Date.now(), sessionId=globalThis.crypto.randomUUID();
      const expiresAt=now+300_000;
      host.enable({source:opener,origin:globalThis.location.origin,
        sessionId,expiresAt,allowSyntheticDemo:demo},now);
      opener.postMessage({
        protocol:PHIPOSE_NAV_PROTOCOL,type:"ready",
        session_id:sessionId,expires_at:expiresAt
      },globalThis.location.origin);
      setActive(true);
      setStatus("Gesture navigation enabled for 5 minutes; UI-only, no OS effects.");
    } catch {
      revoke();
      setStatus("Could not enable gesture navigation in this browser.");
    }
  };
  return (
    <section aria-label="PhiPose navigation companion"
      style={{display:"flex",alignItems:"center",flexWrap:"wrap",gap:"10px",
        padding:"10px 14px",margin:"5px 0 10px",border:"1px solid #365a70",
        borderRadius:"10px",background:"#0b2133"}}>
      <strong>ΦPose · Shell Navigation</strong>
      <label style={{display:"flex",alignItems:"center",gap:"5px",fontSize:"0.82rem"}}>
        <input type="checkbox" checked={demo} disabled={active}
          onChange={(event)=>setDemo(event.currentTarget.checked)}/>
        Synthetic sandbox (off by default)
      </label>
      <button type="button" onClick={active?revoke:enable}>
        {active ? "Disable ΦPose" : "Enable ΦPose companion"}
      </button>
      <span role="status" style={{fontSize:"0.8rem",maxWidth:"520px"}}>{status}</span>
    </section>
  );
}
