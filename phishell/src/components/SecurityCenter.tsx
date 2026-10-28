import { useState, type ChangeEvent } from "react";
import {
  MAX_SECURITY_RECEIPT_BYTES,
  parseSecurityReceipt,
  type ReceiptKind,
  type SecurityReceiptView,
} from "../security/receiptPreview";
import {
  MANIFEST_LIMIT,
  PACK_LIMIT,
  TRUST_LIMIT,
  verifyFieldShieldInBrowser,
  type BrowserPackReview,
} from "../security/browserPackVerification";
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
  const [packFile, setPackFile] = useState<File | null>(null);
  const [manifestFile, setManifestFile] = useState<File | null>(null);
  const [trustFile, setTrustFile] = useState<File | null>(null);
  const [fingerprint, setFingerprint] = useState("");
  const [keyConfirmed, setKeyConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cryptoResult, setCryptoResult] = useState<BrowserPackReview | null>(null);
  const [cryptoError, setCryptoError] = useState("");

  async function verifySelectedPack() {
    setCryptoResult(null);
    setCryptoError("");
    if (!keyConfirmed || !packFile || !manifestFile || !trustFile) {
      setCryptoError("Select all three files and confirm independent key-fingerprint review.");
      return;
    }
    if (packFile.size > PACK_LIMIT || manifestFile.size > MANIFEST_LIMIT ||
        trustFile.size > TRUST_LIMIT) {
      setCryptoError("Selected files exceed the bounded local verification limits.");
      return;
    }
    setBusy(true);
    try {
      const [pack, manifest, trust] = await Promise.all([
        packFile.arrayBuffer(), manifestFile.arrayBuffer(), trustFile.arrayBuffer(),
      ]);
      const result = await verifyFieldShieldInBrowser(
        new Uint8Array(pack), new Uint8Array(manifest), new Uint8Array(trust),
        fingerprint.trim(),
      );
      setCryptoResult(result);
    } catch (cause) {
      setCryptoError(cause instanceof Error ? cause.message : "Browser verification failed.");
    } finally {
      setBusy(false);
    }
  }

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
        <p>Inspect historical local receipts or independently verify the exact bytes
          of an operator-selected signed intelligence pack using browser WebCrypto.
          No device scan, process inspection, or PhiARK service connection occurs.</p>
        <strong className="security-hold">HOST SECURITY STATUS: NOT OBSERVED</strong>
      </header>
      <div className="security-flow" aria-label="Offline security pipeline">
        <span>01 · FIELD SHIELD</span>
        <span>02 · SIGNED IOC PACKS</span>
        <span>03 · PHIARK LOCAL VAULT</span>
        <span>04 · PHIOS RECEIPT REVIEW</span>
      </div>

      <section className="security-section security-crypto">
        <div className="security-crypto-head">
          <div>
            <span className="security-kicker">SECURITY CENTER v0.3 · LOCAL WEBCRYPTO</span>
            <h3>Verify signed intelligence bytes</h3>
          </div>
          <strong className="security-hold">NO HOST SCAN / NO DEVICE SAFETY CLAIM</strong>
        </div>
        <p>Select the exact FieldShield pack, detached signature manifest and local
          trust policy. Enter the raw Ed25519 public-key SHA-256 fingerprint obtained
          through an independent trusted channel. Nothing is uploaded or saved.</p>
        <div className="security-file-grid">
          <label className="security-import">
            Pack (max 2 MB)
            <input type="file" accept=".json,application/json" disabled={busy}
              aria-label="Select signed IOC pack"
              onChange={e => { setPackFile(e.currentTarget.files?.[0] ?? null); setCryptoResult(null); }} />
          </label>
          <label className="security-import">
            Detached signature manifest (max 16 KiB)
            <input type="file" accept=".json,application/json" disabled={busy}
              aria-label="Select signed IOC manifest"
              onChange={e => { setManifestFile(e.currentTarget.files?.[0] ?? null); setCryptoResult(null); }} />
          </label>
          <label className="security-import">
            Manually reviewed trust policy (max 128 KiB)
            <input type="file" accept=".json,application/json" disabled={busy}
              aria-label="Select local trust policy"
              onChange={e => { setTrustFile(e.currentTarget.files?.[0] ?? null); setCryptoResult(null); }} />
          </label>
        </div>
        <label className="security-pin">
          Independently authenticated public-key SHA-256 (64 lowercase hex digits)
          <input type="text" value={fingerprint} disabled={busy}
            spellCheck={false} autoComplete="off" maxLength={64}
            placeholder="64 lowercase hexadecimal characters"
            aria-label="Independent Ed25519 public-key SHA-256 fingerprint"
            onChange={e => { setFingerprint(e.currentTarget.value); setCryptoResult(null); }} />
        </label>
        <label className="security-acknowledge">
          <input type="checkbox" checked={keyConfirmed} disabled={busy}
            onChange={e => { setKeyConfirmed(e.currentTarget.checked); setCryptoResult(null); }} />
          I independently checked this signing-key fingerprint, outside these three files.
        </label>
        <button className="security-verify-button" type="button"
          disabled={busy || !packFile || !manifestFile || !trustFile ||
            !keyConfirmed || !/^[0-9a-f]{64}$/.test(fingerprint.trim())}
          onClick={() => void verifySelectedPack()}>
          {busy ? "VERIFYING LOCALLY…" : "VERIFY SELECTED PACK · IN THIS BROWSER"}
        </button>
        {cryptoError && <p className="security-warning" role="alert">
          VERIFICATION REFUSED: {cryptoError}
        </p>}
        {cryptoResult && (
          <div className="security-preview" role="status">
            <strong>SIGNATURE VERIFIED AGAINST OPERATOR-PINNED KEY ONLY</strong>
            <dl>
              <div><dt>Claimed publisher</dt><dd>{cryptoResult.publisherClaim}</dd></div>
              <div><dt>Key ID</dt><dd>{cryptoResult.keyId}</dd></div>
              <div><dt>Pack SHA-256</dt><dd>{cryptoResult.packSha256}</dd></div>
              <div><dt>Public-key SHA-256</dt><dd>{cryptoResult.publicKeySha256}</dd></div>
              <div><dt>Claimed indicators</dt><dd>{cryptoResult.indicatorsClaimed}</dd></div>
              <div><dt>Signature expires</dt><dd>{cryptoResult.signatureExpiresAt}</dd></div>
              <div><dt>Reviewed at (browser clock)</dt><dd>{cryptoResult.checkedAt}</dd></div>
            </dl>
            <p className="security-warning">
              The selected pack and manifest match the operator-supplied key pin.
              No independent publisher identity, indicator accuracy, host health,
              secure-clock integrity or device scan is established. Trust is only
              as strong as your independent key verification and this browser.
            </p>
          </div>
        )}
      </section>

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
          remediation, or authority grants are present in Security Center.
          Browser selections and verification results stay in memory until reload.
        </p>
      </section>
    </section>
  );
}
