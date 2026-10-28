/**
 * PhiOS Security Center v0.3: in-memory Ed25519 verification of operator-
 * selected FieldShield v0.3 IOC pack bytes. No server, fetch, process, store.
 *
 * IMPORTANT: the operator independently checks the public-key SHA256.
 * This verifies one signature against one local trust policy; it does NOT
 * establish publisher identity, IOC accuracy, device safety or host authority.
 */
const DOMAIN = new TextEncoder().encode("FieldShield Sentinel Signed IOC v1\0");
export const PACK_LIMIT = 2_000_000;
export const MANIFEST_LIMIT = 16_384;
export const TRUST_LIMIT = 131_072;
const ID = /^[A-Za-z0-9_.:-]{1,64}$/;
const HASH = /^[0-9a-f]{64}$/;
const DATE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
const HEADER_FIELDS = [
  "schema", "publisher", "key_id", "pack_sha256", "issued_at", "expires_at",
] as const;
const MANIFEST_FIELDS = [...HEADER_FIELDS, "signature_b64"];
const TRUST_FIELDS = ["schema", "publishers"];
const PUBLISHER_FIELDS = ["id", "keys", "blocked_pack_sha256", "minimum_issued_at"];
const KEY_FIELDS = ["id", "algorithm", "state", "public_key_b64"];

type JsonObject = Record<string, unknown>;
function object(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected a JSON object");
  }
  return value as JsonObject;
}
function exact(value: JsonObject, fields: readonly string[], name: string): void {
  if (Object.keys(value).length !== fields.length ||
      fields.some(key => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new Error("Unsupported " + name + " fields");
  }
}
function name(value: unknown, field: string): string {
  if (typeof value !== "string" || !ID.test(value)) throw new Error("Invalid " + field);
  return value;
}
function digest(value: unknown, field: string): string {
  if (typeof value !== "string" || !HASH.test(value)) throw new Error("Invalid " + field);
  return value;
}
function date(value: unknown, field: string): number {
  if (typeof value !== "string" || !DATE.test(value)) {
    throw new Error("Invalid " + field + " timezone timestamp");
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw new Error("Invalid " + field + " timestamp");
  return parsed;
}
function decodeBase64(value: unknown, expected: number, field: string): Uint8Array {
  if (typeof value !== "string" || value.length > 120 ||
      !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    throw new Error("Invalid " + field + " base64");
  }
  // atob exists in evergreen browsers and Node 22's browser-compatible runtime.
  let raw: string;
  try { raw = atob(value); }
  catch { throw new Error("Invalid " + field + " base64"); }
  if (raw.length !== expected || btoa(raw) !== value) {
    throw new Error("Invalid " + field + " encoding/length");
  }
  return Uint8Array.from(raw, char => char.charCodeAt(0));
}
/** Copy into an owned ArrayBuffer for WebCrypto's strict BufferSource typing. */
function ownedBuffer(bytes: Uint8Array): ArrayBuffer {
  const out = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(out).set(bytes);
  return out;
}
function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
}
function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length);
  out.set(a); out.set(b, a.length);
  return out;
}

/** Reject duplicate keys at *any nesting depth*, not merely JSON.parse's last-wins result. */
export function parseStrictJson(bytes: Uint8Array, maxBytes: number): JsonObject {
  if (bytes.length > maxBytes) throw new Error("JSON file exceeds local size limit");
  let src: string;
  try { src = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch { throw new Error("JSON file must be valid UTF-8"); }
  let i = 0;
  const ws = () => { while (/\s/.test(src[i] ?? "") && i < src.length) i++; };
  const expect = (token: string) => {
    if (src[i] !== token) throw new Error("Malformed JSON token");
    i++;
  };
  const quoted = (): string => {
    const start = i;
    expect('"');
    while (i < src.length) {
      if (src[i] === '"') {
        i++;
        try { return JSON.parse(src.slice(start, i)) as string; }
        catch { throw new Error("Malformed JSON string"); }
      }
      if (src[i] === "\\") {
        i++;
        if (src[i] === "u") {
          i++;
          if (!/^[a-fA-F0-9]{4}$/.test(src.slice(i, i + 4))) {
            throw new Error("Invalid JSON Unicode escape");
          }
          i += 4;
        } else {
          if (!'"\\/bfnrt'.includes(src[i] ?? "")) throw new Error("Invalid JSON escape");
          i++;
        }
      } else {
        if (src.charCodeAt(i) < 32) throw new Error("JSON control character");
        i++;
      }
    }
    throw new Error("Unterminated JSON string");
  };
  const value = (depth: number): void => {
    if (depth > 48) throw new Error("JSON nesting exceeds safe depth");
    ws();
    if (src[i] === "{") {
      i++; ws();
      const used = new Set<string>();
      if (src[i] === "}") { i++; return; }
      while (i < src.length) {
        ws();
        const key = quoted();
        if (used.has(key)) throw new Error("Duplicate JSON key: " + key);
        used.add(key);
        ws(); expect(":"); value(depth + 1); ws();
        if (src[i] === "}") { i++; return; }
        expect(",");
      }
    } else if (src[i] === "[") {
      i++; ws();
      if (src[i] === "]") { i++; return; }
      while (i < src.length) {
        value(depth + 1); ws();
        if (src[i] === "]") { i++; return; }
        expect(",");
      }
    } else if (src[i] === '"') {
      quoted();
    } else {
      // Bound token lookahead: do not repeatedly copy the entire remaining
      // file for a hostile array with thousands of tiny primitive values.
      const tail = src.slice(i, i + 128);
      const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(tail);
      if (!token) throw new Error("Invalid JSON literal");
      i += token[0].length;
    }
  };
  value(0); ws();
  if (i !== src.length) throw new Error("Trailing or invalid JSON characters");
  try { return object(JSON.parse(src) as unknown); }
  catch { throw new Error("Invalid JSON document"); }
}

export interface BrowserPackReview {
  status: "SIGNATURE_VERIFIED_AGAINST_OPERATOR_PIN_ONLY";
  publisherClaim: string;
  keyId: string;
  packSha256: string;
  manifestSha256: string;
  trustSha256: string;
  publicKeySha256: string;
  signatureExpiresAt: string;
  indicatorsClaimed: number;
  checkedAt: string;
  hostSecurityObserved: false;
  sourceIdentityAuthenticated: false;
  scanningPerformed: false;
}

export async function verifyFieldShieldInBrowser(
  packRaw: Uint8Array,
  manifestRaw: Uint8Array,
  trustRaw: Uint8Array,
  independentPublicKeySha256: string,
  options?: { now?: number; subtle?: SubtleCrypto },
): Promise<BrowserPackReview> {
  const subtle = options?.subtle ?? globalThis.crypto?.subtle;
  if (!subtle) throw new Error("Secure WebCrypto is unavailable. Verification refused.");
  const now = options?.now ?? Date.now();
  if (!Number.isFinite(now)) throw new Error("Invalid review time");
  const pin = digest(independentPublicKeySha256, "out-of-band public-key SHA256");
  const manifest = parseStrictJson(manifestRaw, MANIFEST_LIMIT);
  exact(manifest, MANIFEST_FIELDS, "signed manifest");
  if (manifest.schema !== "fieldshield.signed-ioc.v1") {
    throw new Error("Unknown signed manifest schema");
  }
  const publisher = name(manifest.publisher, "publisher");
  const keyId = name(manifest.key_id, "key ID");
  const signedDigest = digest(manifest.pack_sha256, "signed pack SHA256");
  const issued = date(manifest.issued_at, "manifest issue");
  const expires = date(manifest.expires_at, "manifest expiry");
  if (expires <= issued || issued > now || expires <= now) {
    throw new Error("Signature manifest is expired or not yet valid");
  }
  if (packRaw.byteLength > PACK_LIMIT) throw new Error("IOC pack exceeds size limit");
  const packSha256 = toHex(new Uint8Array(await subtle.digest("SHA-256", ownedBuffer(packRaw))));
  if (packSha256 !== signedDigest) throw new Error("Signed IOC pack SHA256 mismatch");

  const trust = parseStrictJson(trustRaw, TRUST_LIMIT);
  exact(trust, TRUST_FIELDS, "trust-store");
  if (trust.schema !== "fieldshield.trust-store.v1") {
    throw new Error("Unknown local trust-store schema");
  }
  if (!Array.isArray(trust.publishers) || trust.publishers.length > 100) {
    throw new Error("Trust-store publishers must be bounded");
  }
  const seenPublishers = new Set<string>();
  let entry: JsonObject | undefined;
  for (const item of trust.publishers) {
    const row = object(item);
    exact(row, PUBLISHER_FIELDS, "publisher policy");
    const id = name(row.id, "trusted publisher ID");
    if (seenPublishers.has(id)) throw new Error("Duplicate trust publisher");
    seenPublishers.add(id);
    if (id === publisher) entry = row;
  }
  if (!entry) throw new Error("Publisher is not locally trusted");
  if (!Array.isArray(entry.blocked_pack_sha256) ||
      entry.blocked_pack_sha256.some(x => typeof x !== "string" || !HASH.test(x))) {
    throw new Error("Invalid revoked IOC pack list");
  }
  if (entry.blocked_pack_sha256.includes(packSha256)) throw new Error("IOC pack locally blocked");
  if (issued < date(entry.minimum_issued_at, "trust issuance floor")) {
    throw new Error("Pack predates local trust issuance floor");
  }
  if (!Array.isArray(entry.keys) || entry.keys.length > 100) {
    throw new Error("Invalid trust key roster");
  }
  const seenKeys = new Set<string>();
  let publicKey: Uint8Array | undefined;
  for (const item of entry.keys) {
    const row = object(item);
    exact(row, KEY_FIELDS, "trust key");
    const id = name(row.id, "trusted key ID");
    if (seenKeys.has(id)) throw new Error("Duplicate publisher key ID");
    seenKeys.add(id);
    if (row.algorithm !== "ed25519" || !["trusted", "revoked"].includes(String(row.state))) {
      throw new Error("Unsupported key algorithm or state");
    }
    const key = decodeBase64(row.public_key_b64, 32, "Ed25519 public key");
    if (id === keyId) {
      if (row.state === "revoked") throw new Error("Signing key locally revoked");
      publicKey = key;
    }
  }
  if (!publicKey) throw new Error("Unknown signing key; no automatic enrollment");
  const computedPin = toHex(new Uint8Array(await subtle.digest("SHA-256", ownedBuffer(publicKey))));
  if (computedPin !== pin) throw new Error("Public key fails independent SHA256 pin");

  const authHeader = Object.fromEntries(HEADER_FIELDS.map(key => [key, manifest[key]]));
  const ordered = Object.fromEntries(
    Object.entries(authHeader).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
  );
  const message = concat(DOMAIN, new TextEncoder().encode(JSON.stringify(ordered)));
  const signature = decodeBase64(manifest.signature_b64, 64, "Ed25519 signature");
  let valid = false;
  try {
    const imported = await subtle.importKey("raw", ownedBuffer(publicKey), { name: "Ed25519" }, false, ["verify"]);
    valid = await subtle.verify({ name: "Ed25519" }, imported, ownedBuffer(signature), ownedBuffer(message));
  } catch {
    throw new Error("Ed25519 not supported by this secure browser or verification failed");
  }
  if (!valid) throw new Error("Ed25519 signature did not match the pinned key");

  const pack = parseStrictJson(packRaw, PACK_LIMIT);
  if (pack.schema !== "fieldshield.ioc-pack.v1" ||
      typeof pack.source !== "string" || !pack.source.trim() ||
      !Array.isArray(pack.indicators) || pack.indicators.length < 1 ||
      pack.indicators.length > 100_000) {
    throw new Error("Signed bytes are not a supported IOC pack");
  }
  if (date(pack.issued_at, "IOC pack issuance") > issued) {
    throw new Error("IOC pack issue date exceeds signed issue date");
  }
  return {
    status: "SIGNATURE_VERIFIED_AGAINST_OPERATOR_PIN_ONLY",
    publisherClaim: publisher,
    keyId,
    packSha256,
    manifestSha256: toHex(new Uint8Array(await subtle.digest("SHA-256", ownedBuffer(manifestRaw)))),
    trustSha256: toHex(new Uint8Array(await subtle.digest("SHA-256", ownedBuffer(trustRaw)))),
    publicKeySha256: computedPin,
    signatureExpiresAt: manifest.expires_at as string,
    indicatorsClaimed: pack.indicators.length,
    checkedAt: new Date(now).toISOString(),
    hostSecurityObserved: false,
    sourceIdentityAuthenticated: false,
    scanningPerformed: false,
  };
}
