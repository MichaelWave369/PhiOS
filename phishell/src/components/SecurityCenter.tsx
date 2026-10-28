import { useState, type ChangeEvent } from "react";
import {
  MAX_SECURITY_RECEIPT_BYTES,
  parseSecurityReceipt,
  type ReceiptKind,
  type SecurityReceiptView,
} from "../security/receiptPreview";
import "./SecurityCenter.css";

const LOCAL_COMMANDS = [
  "npm run intel -- verify ./my-trust.json              # in PhiARK directory",
  "python sentinel_verified.py verify --pack ./pack.json --signature ./pack.sig.json --trust ./my-trust.json",
  "python sentinel_verified.py scan --pack ./pack.json --signature ./pack.sig.json --trust ./my-trust.json observations ./observations.json",
  "phi-sentinel-review --pack ./pack.json --signature ./pack.sig.json --trust ./my-trust.json --expected-public-key-sha256 <INDEPENDENT-PIN> --i-approve-local-review",
] as const;

/**
 * Browser-only receipt preview. No fetch, no drag-drop upload, no host actions.
 * Imported JSON is untrusted historical data, not live validation or authority.
 */
export function SecurityCenter() {
  const [phiark, setPhiark] = useState<SecurityReceiptView | null>(null);
  const [sentinel, setSentinel] = useState<SecurityReceiptView | null>(null);
  const [review, setReview] = useState<SecurityReceiptView | null>(null);
  const [error, setError] = useState("");

  async function importReceipt(kind: ReceiptKind, event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    setError("");
    if (!file) return;
    if (kind === "phiark") setPhiark(null);
    else if (kind === "sentinel") setSentinel(null);
    else setReview(null);
    if (file.size > MAX_SECURITY_RECEIPT_BYTES) {
      setError("Receipt exceeds 1 MiB. No file was loaded.");
      return;
    }
    try {
      const parsed = parseSecurityReceipt(kind, await file.text());
      if (kind === "phiark") setPhiark(parsed);
      else if (kind === "sentinel") setSentinel(parsed);
      else setReview(parsed);
    } catch {
      setError("Unsupported or malformed receipt. Nothing was verified or uploaded.");
    }
  }

  return (
    <section className="security-center" aria-label="PhiOS Security Center">
      <header className="security-center-heading">
        <span className="security-kicker">Φ FIELD SHIELD / SENTINEL / PHIARK</span>
        <h2>Security Center</h2>
        <p>Inspect locally selected verification receipts. The browser does not
          verify signatures, scan a device, inspect running processes, or contact
          FieldShield and PhiARK runtimes.</p>
        <strong className="security-hold">HOST SECURITY STATUS: NOT OBSERVED</strong>
      </header>
      <div className="security-flow" aria-label="Offline security pipeline">
        <span>01 · FIELD SHIELD</span>
        <span>02 · SIGNED IOC PACKS</span>
        <span>03 · PHIARK LOCAL VAULT</span>
        <span>04 · PHIOS RECEIPT REVIEW</span>
      </div>

      <div className="security-columns">
        <article className="security-section">
          <h3>PhiARK intelligence inventory</h3>
          <p>Use <code>npm run intel -- verify</code> in the actual PhiARK installation,
            save the JSON output yourself, then choose the file here.</p>
          <label className="security-import">
            Select PhiARK verification JSON
            <input type="file" accept=".json,application/json"
              aria-label="Import PhiARK intelligence verification JSON"
              onChange={(event) => void importReceipt("phiark", event)} />
          </label>
          {phiark?.kind === "phiark" ? (
            <div className="security-preview" aria-live="polite">
              <strong>{phiark.label}</strong>
              <dl>
                <div><dt>Objects checked in source output</dt><dd>{phiark.checked}</dd></div>
                <div><dt>Claimed verified</dt><dd>{phiark.claimedVerified}</dd></div>
                <div><dt>Claimed failures</dt><dd>{phiark.failed}</dd></div>
              </dl>
              <p>Publisher labels: {phiark.publisherNames.join(", ") || "None shown"}</p>
              <p className="security-warning">These are assertions in an imported
                historical JSON report. This screen did not re-check any Ed25519
                signatures, actual trust roots, files, or current revocations.</p>
            </div>
          ) : <p className="security-empty">No local PhiARK receipt selected.</p>}
        </article>

        <article className="security-section">
          <h3>Sentinel evidence scan receipt</h3>
          <p>Use a separately authorized, local Sentinel scan. Import its JSON
            output to review coverage without uploading forensic evidence.</p>
          <label className="security-import">
            Select Sentinel scan JSON
            <input type="file" accept=".json,application/json"
              aria-label="Import Sentinel scan report JSON"
              onChange={(event) => void importReceipt("sentinel", event)} />
          </label>
          {sentinel?.kind === "sentinel" ? (
            <div className="security-preview" aria-live="polite">
              <strong>{sentinel.label}</strong>
              <dl>
                <div><dt>Reported decision</dt><dd>{sentinel.decision}</dd></div>
                <div><dt>Evidence observations/files</dt><dd>{sentinel.inspected}</dd></div>
                <div><dt>Indicator matches</dt><dd>{sentinel.findings}</dd></div>
                <div><dt>Uninspected</dt><dd>{sentinel.uninspected}</dd></div>
              </dl>
              <p>{sentinel.packClaim}</p>
              {sentinel.indicatorIds.length > 0 && (
                <p className="security-indicators">Example indicator IDs:
                  {" "}{sentinel.indicatorIds.join(", ")}</p>
              )}
              <p className="security-warning">
                A matching indicator is not proof of infection.
                NO_MATCHES_IN_SCOPE is not a clean-device verdict.
                The UI did not independently authenticate the report.
              </p>
            </div>
          ) : <p className="security-empty">No local Sentinel report selected.</p>}
        </article>
      </div>

      <article className="security-section">
        <h3>Offline signed-pack review · PhiOS v0.2</h3>
        <p>The PhiOS CLI can verify a FieldShield pack using an independently
          checked Ed25519 public-key fingerprint. Choose its generated JSON
          to inspect the historical result here. The browser cannot revalidate
          this file or establish that the source really belongs to the claimed publisher.</p>
        <label className="security-import">
          Select PhiOS offline verification JSON
          <input type="file" accept=".json,application/json"
            aria-label="Import PhiOS offline review JSON"
            onChange={(event) => void importReceipt("phios-review", event)} />
        </label>
        {review?.kind === "phios-review" ? (
          <div className="security-preview" aria-live="polite">
            <strong>{review.label}</strong>
            <dl>
              <div><dt>Publisher claim</dt><dd>{review.publisherClaim}</dd></div>
              <div><dt>IOC entries claimed</dt><dd>{review.indicatorCount}</dd></div>
              <div><dt>Review timestamp</dt><dd>{review.reviewedAt}</dd></div>
              <div><dt>Signature expiration</dt><dd>{review.manifestExpiresAt}</dd></div>
              <div><dt>Pack SHA-256</dt><dd>{review.packSha256}</dd></div>
              <div><dt>External key pin SHA-256</dt><dd>{review.pinnedKeySha256}</dd></div>
            </dl>
            <p className="security-warning">
              This is a user-selected historical JSON claim, not a live verified
              cryptographic result. No host scan, source authenticity confirmation,
              or authority grant has occurred through this viewer.
            </p>
          </div>
        ) : <p className="security-empty">No PhiOS offline review selected.</p>}
      </article>

      {error && <p role="alert" className="security-warning">{error}</p>}
      <section className="security-procedure">
        <h3>Actual offline workflow · run outside this preview</h3>
        <p>These are examples, not executable buttons. Use paths under your control
          and independently provision trusted public keys. Store private evidence
          only on your own system.</p>
        <pre>{LOCAL_COMMANDS.join("\n")}</pre>
        <p className="security-warning">
          No automatic telemetry, host probing, remote downloads, file upload,
          remediation, or authority grants are present in Security Center v0.1.
          Browser selections stay in memory and are discarded on reload.
        </p>
      </section>
    </section>
  );
}
