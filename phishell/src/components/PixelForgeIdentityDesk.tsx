import { useRef, useState, type ChangeEvent } from "react";
import {
  confirmPixelForgeV2Import,
  confirmPixelForgeV2Removal,
  inspectPixelForgeV2Identities,
  previewPixelForgeV2Import,
  previewPixelForgeV2Removal,
  type PixelForgeV2ImportReview,
  type PixelForgeV2RemovalReview,
} from "../shell/pixelForgeV2IdentityImport";
import type { ProviderQualifiedProjectReference } from "../shell/projectRegistryV2";

/**
 * Explicit V2 metadata desk, separated from PhiOffice's bridge permission.
 * No PixelForge iframe, app installation or background file scan.
 */
export function PixelForgeIdentityDesk() {
  const revision = useRef(0);
  const [pending, setPending] = useState<PixelForgeV2ImportReview | null>(null);
  const [removal, setRemoval] = useState<PixelForgeV2RemovalReview | null>(null);
  const [saved, setSaved] = useState<readonly ProviderQualifiedProjectReference[] | null>(null);
  const [status, setStatus] = useState(
    "No file read. Export an identity-only sidecar from PixelForge VR Studio first.",
  );
  const clearPlans = () => {
    revision.current += 1;
    setPending(null);
    setRemoval(null);
    setSaved(null);
  };
  const reviewFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    clearPlans();
    const thisRevision = revision.current;
    if (!file) return;
    if (file.size > 4096) {
      setStatus("PixelForge identity file exceeds 4 KiB. Nothing imported.");
      return;
    }
    try {
      const raw = await file.text();
      if (thisRevision !== revision.current) return;
      const plan = previewPixelForgeV2Import(globalThis.localStorage, raw);
      setPending(plan);
      setStatus("Review the provider-qualified identity, then separately confirm the V2 metadata import.");
    } catch (error) {
      if (thisRevision === revision.current) {
        setStatus(error instanceof Error ? error.message : "Identity file not accepted.");
      }
    }
  };
  const commit = () => {
    if (!pending) return;
    if (!globalThis.confirm(
      "Add this PixelForge identity to V2 browser-local metadata? "
      + "PhiOffice records remain unchanged. No sharing approval, "
      + "file access, native installation or ownership verification is granted.",
    )) return;
    try {
      const count = confirmPixelForgeV2Import(globalThis.localStorage, pending, true);
      clearPlans();
      setSaved(inspectPixelForgeV2Identities(globalThis.localStorage));
      setStatus("Saved PixelForge identity in V2 (" + count + " total entries). "
        + "PhiOffice V1 and all permission sessions remain unchanged.");
    } catch (error) {
      clearPlans();
      setStatus(error instanceof Error ? error.message : "V2 import not verified.");
    }
  };
  const inspect = () => {
    clearPlans();
    try {
      const list = inspectPixelForgeV2Identities(globalThis.localStorage);
      setSaved(list);
      setStatus("Found " + list.length + " PixelForge identity references in V2. "
        + "These are not installed applications or permission grants.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "V2 inspection unavailable.");
    }
  };
  const reviewRemoval = (projectRef: string) => {
    clearPlans();
    try {
      const plan = previewPixelForgeV2Removal(globalThis.localStorage, projectRef);
      setRemoval(plan);
      setStatus("Review the exact identity before requesting removal. PhiOffice entries remain in place.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Removal review rejected.");
    }
  };
  const remove = () => {
    if (!removal) return;
    if (!globalThis.confirm(
      "Remove only " + removal.identity.providerAppId + " / " + removal.identity.projectRef
      + " from V2 metadata? No VR world file will be deleted.",
    )) return;
    try {
      const count = confirmPixelForgeV2Removal(globalThis.localStorage, removal, true);
      clearPlans();
      setSaved(inspectPixelForgeV2Identities(globalThis.localStorage));
      setStatus("Removed reviewed PixelForge identity (" + count + " total V2 entries remain). "
        + "PhiOffice V1 and existing project files were untouched.");
    } catch (error) {
      clearPlans();
      setStatus(error instanceof Error ? error.message : "Removal was not verified.");
    }
  };
  return (
    <section className="panel phios-pixelforge-identity-desk"
      aria-label="PixelForge project identity desk">
      <h3>PixelForge → PhiOS · reviewed identity-only metadata</h3>
      <p>
        Import a locally exported <code>pixelforge.phios-vr-world-identity.v0.1</code> file.
        PixelForge's project ID stays distinct from identically spelled PhiOffice IDs.
        V1 remains the active PhiOffice registry. This desk cannot launch PixelForge,
        grant project reads, authenticate ownership, or import a VR world.
      </p>
      <label htmlFor="phios-pixelforge-identity-file">
        Select PixelForge identity-only JSON file (4 KiB maximum)
      </label>
      <input id="phios-pixelforge-identity-file" type="file"
        accept=".json,application/json" onChange={reviewFile}
        aria-label="Select PixelForge identity-only JSON file" />
      {pending && (
        <div className="phios-pixelforge-review" aria-label="PixelForge V2 identity import preview">
          <p><strong>Preview only, not yet saved</strong></p>
          <p>{pending.identity.providerAppId} / <code>{pending.identity.projectRef}</code></p>
          <p>Title: {pending.identity.title}</p>
          <p>Same PhiOffice text ID: {pending.collisionWithPhiOfficeRef ? "Yes, isolated by provider" : "No"}</p>
          <p>V2 after import: {pending.resultCount} metadata records. No approvals transfer.</p>
          <button type="button" onClick={commit}>Confirm PixelForge identity-only import</button>
        </div>
      )}
      <button type="button" onClick={inspect}>Inspect saved PixelForge V2 IDs</button>
      {saved !== null && (
        <div aria-label="Saved PixelForge identities">
          {saved.length === 0 && <p>No PixelForge identity-only metadata saved.</p>}
          <ul>
            {saved.map((entry) => (
              <li key={entry.providerAppId + ":" + entry.projectRef}>
                {entry.providerAppId} / <code>{entry.projectRef}</code> ({entry.title}){" "}
                <button type="button" onClick={() => reviewRemoval(entry.projectRef)}>
                  Review PixelForge identity removal
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {removal && (
        <div className="phios-pixelforge-review"
          aria-label="PixelForge V2 identity removal preview">
          <p><strong>Removal review, no data changed</strong></p>
          <p>{removal.identity.providerAppId} / <code>{removal.identity.projectRef}</code></p>
          <p>Title: {removal.identity.title}</p>
          <p>V2 after removal: {removal.resultCount} records; PhiOffice stays intact.</p>
          <button type="button" onClick={remove}>Confirm removal of this PixelForge identity</button>
        </div>
      )}
      <p role="status">{status}</p>
      <small>localStorage is not a durable backup. No automatic sync or app grant.
        Changes from another tab invalidate the review where detectable.</small>
    </section>
  );
}
