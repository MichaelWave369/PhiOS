/**
 * PhiOS Security Center v0.1: strictly bounded, read-only presentation of
 * operator-selected historical JSON receipts. NEVER cryptographic verification.
 * Files are not uploaded, retained, or sent to the PhiOS host.
 */
export const MAX_SECURITY_RECEIPT_BYTES = 1_048_576;

export type ReceiptKind = "sentinel" | "phiark";

export interface SentinelReceiptView {
  kind: "sentinel";
  label: "IMPORTED REPORT · NOT LIVE VERIFIED";
  decision: "NO_MATCHES_IN_SCOPE" | "INDICATORS_FOUND" | "INCOMPLETE";
  mode: "files" | "observations";
  generatedAt: string;
  inspected: number;
  findings: number;
  uninspected: number;
  indicatorIds: string[];
  packClaim: "SIGNED CLAIM IN REPORT · NOT REVERIFIED" | "NO SIGNATURE CLAIM";
}

export interface PhiArkReceiptView {
  kind: "phiark";
  label: "IMPORTED INVENTORY · NOT LIVE VERIFIED";
  checked: number;
  claimedVerified: number;
  failed: number;
  publisherNames: string[];
}

export type SecurityReceiptView = SentinelReceiptView | PhiArkReceiptView;

function record(input: unknown): Record<string, unknown> | null {
  if (input === null || typeof input !== "object" || Array.isArray(input)) return null;
  return input as Record<string, unknown>;
}

function boundedCount(value: unknown, maximum: number): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) &&
    value >= 0 && value <= maximum ? value : null;
}

function boundedText(value: unknown, maximum: number): string | null {
  return typeof value === "string" && value.length > 0 && value.length <= maximum
    && !/[\u0000-\u001f\u007f]/.test(value) ? value : null;
}

export function parseSecurityReceipt(kind: ReceiptKind, raw: string): SecurityReceiptView {
  if (new TextEncoder().encode(raw).length > MAX_SECURITY_RECEIPT_BYTES) {
    throw new Error("Receipt exceeds the 1 MiB local preview limit.");
  }
  let input: unknown;
  try {
    input = JSON.parse(raw) as unknown;
  } catch {
    throw new Error("This file does not contain valid JSON.");
  }
  const data = record(input);
  if (!data) throw new Error("Receipt must be a JSON object.");

  if (kind === "phiark") {
    const checked = boundedCount(data.checked, 1000);
    const claimedVerified = boundedCount(data.passed, 1000);
    if (checked === null || claimedVerified === null || claimedVerified > checked ||
        !Array.isArray(data.results) || data.results.length !== checked) {
      throw new Error("Not a valid PhiARK intelligence verification receipt.");
    }
    const publishers = new Set<string>();
    let verifiedRows = 0;
    for (const item of data.results as unknown[]) {
      const row = record(item);
      if (!row || !/^[0-9a-f]{64}$/.test(String(row.id)) ||
          !["VERIFIED_NOW", "FAIL"].includes(String(row.status))) {
        throw new Error("PhiARK verification row has an unsupported shape.");
      }
      if (row.status === "VERIFIED_NOW") {
        verifiedRows += 1;
        const name = boundedText(row.publisher, 64);
        if (!name) throw new Error("Verified row is missing its publisher.");
        publishers.add(name);
      }
    }
    if (verifiedRows !== claimedVerified) {
      throw new Error("PhiARK verification summary contradicts its rows.");
    }
    return {
      kind: "phiark",
      label: "IMPORTED INVENTORY · NOT LIVE VERIFIED",
      checked,
      claimedVerified,
      failed: checked - claimedVerified,
      publisherNames: [...publishers].sort().slice(0, 12),
    };
  }

  const counts = record(data.counts);
  const scanned = counts && boundedCount(counts.inspected, 100_000);
  const findings = counts && boundedCount(counts.findings, 1_000);
  const uninspected = counts && boundedCount(counts.uninspected, 100_000);
  const decision = data.decision;
  const mode = data.mode;
  const when = boundedText(data.generated_at, 64);
  if (data.schema !== "fieldshield.sentinel.v1" ||
      !["NO_MATCHES_IN_SCOPE", "INDICATORS_FOUND", "INCOMPLETE"].includes(String(decision)) ||
      !["files", "observations"].includes(String(mode)) ||
      scanned === null || scanned === undefined ||
      findings === null || findings === undefined ||
      uninspected === null || uninspected === undefined ||
      !when || !Array.isArray(data.findings) || data.findings.length !== findings) {
    throw new Error("Not a valid FieldShield Sentinel scan receipt.");
  }
  const indicatorIds: string[] = [];
  for (const item of data.findings as unknown[]) {
    const row = record(item);
    const id = row && boundedText(row.indicator_id, 128);
    if (!id || !/^[A-Za-z0-9_.:-]{1,128}$/.test(id)) {
      throw new Error("Scan receipt contains an invalid indicator ID.");
    }
    if (indicatorIds.length < 8 && !indicatorIds.includes(id)) indicatorIds.push(id);
  }
  const claim = record(record(data.indicator_pack)?.verification);
  const signed = claim?.status === "ed25519-verified";
  return {
    kind: "sentinel",
    label: "IMPORTED REPORT · NOT LIVE VERIFIED",
    decision: decision as SentinelReceiptView["decision"],
    mode: mode as SentinelReceiptView["mode"],
    generatedAt: when,
    inspected: scanned,
    findings,
    uninspected,
    indicatorIds,
    packClaim: signed ? "SIGNED CLAIM IN REPORT · NOT REVERIFIED" : "NO SIGNATURE CLAIM",
  };
}
