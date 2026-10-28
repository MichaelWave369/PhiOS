/**
 * PhiOS Security Center v0.4: consented, in-memory observation matching.
 *
 * Never scans the host. No file enumeration, network, process inspection,
 * remediation, storage, telemetry or IPC. Matches the *operator-selected*
 * evidence JSON against a freshly verified signed FieldShield IOC snapshot.
 */
import {
  PACK_LIMIT, MANIFEST_LIMIT, TRUST_LIMIT, parseStrictJson, verifyFieldShieldInBrowser,
} from "./browserPackVerification";

export const OBSERVATION_LIMIT = 8_000_000;
export const MAX_OBSERVATIONS = 100_000;
export const MAX_INDICATORS = 100_000;
export const MAX_MATCHES = 1_000;
const TYPES = new Set(["domain", "url", "sha256", "path", "process", "bundle_id"]);
const CONFIDENCE = new Set(["low", "medium", "high"]);
const SHA = /^[a-fA-F0-9]{64}$/;
const SAFE_ID = /^[A-Za-z0-9_.:-]{1,128}$/;

type Kind = "domain" | "url" | "sha256" | "path" | "process" | "bundle_id";
interface MatchEntry { id: string; kind: Kind; value: string; confidence: string; reference: string }

export interface EvidenceMatchSummary {
  schema: "phios.security_center.observations_match.v0.4";
  scope: "USER_SELECTED_JSON_ONLY";
  decision: "INCOMPLETE" | "INDICATORS_FOUND" | "NO_MATCHES_IN_SCOPE";
  checkedAt: string;
  verifiedPackSha256: string;
  observationFileSha256: string;
  keySha256: string;
  publisherClaim: string;
  indicatorsLoaded: number;
  observationsSupplied: number;
  inspected: number;
  uninspected: number;
  matches: number;
  limitReached: boolean;
  findingIds: Array<{ indicatorId: string; kind: Kind; observationIndex: number; confidence: string }>;
  hostSecurityObserved: false;
  hostScanPerformed: false;
  networkUsed: false;
  sourceIdentityAuthenticated: false;
  evidenceValuesIncluded: false;
}

/** Preserve FieldShield's exact, typed matching semantics, with no fuzzy inference. */
export function normalizeFieldShield(kind: Kind, input: string): string {
  if (typeof input !== "string" || input.length === 0 || input.length > 2048) {
    throw new Error("Invalid indicator value");
  }
  const value = input.trim();
  if (!value) throw new Error("Empty indicator value");
  if (kind === "sha256") {
    if (!SHA.test(value)) throw new Error("Invalid SHA-256 value");
    return value.toLowerCase();
  }
  if (kind === "domain") {
    const lower = value.toLowerCase().replace(/\.+$/, "");
    if (lower.length < 1 || lower.length > 253 || !/^[a-z0-9.-]+$/.test(lower)) {
      throw new Error("Invalid domain");
    }
    if (lower.split(".").some(label => !label || label.length > 63 ||
        label.startsWith("-") || label.endsWith("-"))) throw new Error("Invalid domain labels");
    return lower;
  }
  if (kind === "url") {
    if (!/^https?:\/\//i.test(value) || /\s/.test(value)) {
      throw new Error("Only whitespace-free HTTP(S) URLs are supported");
    }
    let parsed: URL;
    try { parsed = new URL(value); }
    catch { throw new Error("Invalid URL"); }
    if (!["http:", "https:"].includes(parsed.protocol.toLowerCase()) ||
        !parsed.hostname || parsed.username || parsed.password) {
      throw new Error("Invalid URL scheme or credentials");
    }
    return value; // exact URL text, not canonicalized as a different IOC
  }
  if (kind === "path") {
    const path = value.replace(/\\/g, "/");
    if (path.startsWith("/") || /^[a-z]:/i.test(path) ||
        path.split("/").some(part => part === "" || part === "." || part === "..")) {
      throw new Error("Path must be an exact relative path");
    }
    return path;
  }
  if (kind === "process" || kind === "bundle_id") return value;
  throw new Error("Unsupported observation kind");
}

function plain(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected JSON object");
  }
  return value as Record<string, unknown>;
}
function typed(value: unknown): Kind {
  if (typeof value !== "string" || !TYPES.has(value)) throw new Error("Unsupported indicator kind");
  return value as Kind;
}
function compilePack(packRaw: Uint8Array): {
  index: Map<string, MatchEntry[]>; indicatorsLoaded: number;
} {
  const pack = parseStrictJson(packRaw, PACK_LIMIT);
  if (pack.schema !== "fieldshield.ioc-pack.v1" ||
      !Array.isArray(pack.indicators) ||
      pack.indicators.length < 1 || pack.indicators.length > MAX_INDICATORS) {
    throw new Error("Unsupported or oversized signed IOC pack");
  }
  const index = new Map<string, MatchEntry[]>();
  const identifiers = new Set<string>();
  for (const raw of pack.indicators) {
    const obj = plain(raw);
    if (typeof obj.id !== "string" || !SAFE_ID.test(obj.id) ||
        identifiers.has(obj.id)) {
      throw new Error("Duplicate or unsafe signed indicator ID");
    }
    identifiers.add(obj.id);
    const kind = typed(obj.kind);
    if (typeof obj.value !== "string" || typeof obj.confidence !== "string" ||
        !CONFIDENCE.has(obj.confidence) || typeof obj.reference !== "string" ||
        !obj.reference.startsWith("https://")) {
      throw new Error("Invalid signed indicator provenance or confidence");
    }
    const value = normalizeFieldShield(kind, obj.value);
    const match: MatchEntry = {
      id: obj.id, kind, value, confidence: obj.confidence, reference: obj.reference,
    };
    const key = JSON.stringify([kind, value]);
    const matches = index.get(key) ?? [];
    matches.push(match);
    index.set(key, matches);
  }
  return {index, indicatorsLoaded: identifiers.size};
}

function matchObservations(
  raw: Uint8Array, index: Map<string, MatchEntry[]>,
  refs: { packSha256: string; observationSha256: string; keySha256: string;
    publisherClaim: string; indicatorsLoaded: number; checkedAt: string },
): EvidenceMatchSummary {
  const payload = parseStrictJson(raw, OBSERVATION_LIMIT);
  if (payload.schema !== "fieldshield.observations.v1" ||
      !Array.isArray(payload.observations) || payload.observations.length > MAX_OBSERVATIONS) {
    throw new Error("Invalid FieldShield observations.v1 JSON schema or count");
  }
  let inspected = 0, uninspected = 0, matches = 0, limitReached = false;
  const findingIds: EvidenceMatchSummary["findingIds"] = [];

  function record(kind: Kind, normalizedValue: string, observationIndex: number) {
    // Receives a previously validated normalized value, so matching cannot
    // unexpectedly reject an observation after it was counted as inspected.
    const lookupKey = JSON.stringify([kind, normalizedValue]);
    for (const entry of index.get(lookupKey) ?? []) {
      if (matches >= MAX_MATCHES) {
        if (!limitReached) { limitReached = true; uninspected += 1; }
        return;
      }
      matches++;
      // Keep only bounded, non-sensitive safe IDs, not raw observation values.
      if (findingIds.length < 24) {
        findingIds.push({
          indicatorId: entry.id, kind, observationIndex, confidence: entry.confidence,
        });
      }
    }
  }
  for (let i = 0; i < payload.observations.length; i++) {
    const value = payload.observations[i];
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      uninspected++; continue;
    }
    const item = value as Record<string, unknown>;
    if (typeof item.kind !== "string" || !TYPES.has(item.kind) ||
        typeof item.value !== "string") {
      uninspected++; continue;
    }
    const kind = item.kind as Kind;
    let normalized: string;
    try {
      normalized = normalizeFieldShield(kind, item.value);
    } catch {
      uninspected++;
      continue;
    }
    // The observation has passed validation: increment inspected exactly once.
    inspected++;
    record(kind, normalized, i);
    if (kind === "url") {
      // Domain fallback is best effort; rejected fallback normalization cannot
      // reclassify an otherwise valid URL observation as uninspected.
      try {
        const hostname = new URL(normalized).hostname;
        if (hostname) record("domain", normalizeFieldShield("domain", hostname), i);
      } catch { /* Unsupported fallback domain; the URL itself remains inspected. */ }
    }
  }
  return {
    schema: "phios.security_center.observations_match.v0.4",
    scope: "USER_SELECTED_JSON_ONLY",
    decision: uninspected > 0 || inspected === 0 ? "INCOMPLETE" :
      matches > 0 ? "INDICATORS_FOUND" : "NO_MATCHES_IN_SCOPE",
    checkedAt: refs.checkedAt,
    verifiedPackSha256: refs.packSha256,
    observationFileSha256: refs.observationSha256,
    keySha256: refs.keySha256,
    publisherClaim: refs.publisherClaim,
    indicatorsLoaded: refs.indicatorsLoaded,
    observationsSupplied: payload.observations.length,
    inspected, uninspected, matches, limitReached, findingIds,
    hostSecurityObserved: false,
    hostScanPerformed: false,
    networkUsed: false,
    sourceIdentityAuthenticated: false,
    evidenceValuesIncluded: false,
  };
}

/**
 * Single public entrypoint: pack verification ALWAYS happens before matching.
 * The same pack byte snapshot is used for signature verification and matching.
 * A stale prior UI result cannot authorize a new observation match.
 */
export async function verifyAndMatchSelectedObservations(params: {
  packRaw: Uint8Array;
  manifestRaw: Uint8Array;
  trustRaw: Uint8Array;
  observationsRaw: Uint8Array;
  independentPublicKeySha256: string;
  now?: number;
  subtle?: SubtleCrypto;
}): Promise<EvidenceMatchSummary> {
  if (params.observationsRaw.byteLength > OBSERVATION_LIMIT) {
    throw new Error("Observations file exceeds 8,000,000-byte limit");
  }
  const cryptoResult = await verifyFieldShieldInBrowser(
    params.packRaw, params.manifestRaw, params.trustRaw,
    params.independentPublicKeySha256,
    {now: params.now, subtle: params.subtle},
  );
  const compiled = compilePack(params.packRaw); // full indicator validation, after signature
  const subtle = params.subtle ?? globalThis.crypto.subtle;
  const snapshot = new ArrayBuffer(params.observationsRaw.byteLength);
  new Uint8Array(snapshot).set(params.observationsRaw);
  const obsSha256 = Array.from(
    new Uint8Array(await subtle.digest("SHA-256", snapshot)),
    b => b.toString(16).padStart(2, "0"),
  ).join("");
  return matchObservations(params.observationsRaw, compiled.index, {
    packSha256: cryptoResult.packSha256,
    observationSha256: obsSha256,
    keySha256: cryptoResult.publicKeySha256,
    publisherClaim: cryptoResult.publisherClaim,
    indicatorsLoaded: compiled.indicatorsLoaded,
    checkedAt: cryptoResult.checkedAt,
  });
}
