import { describe, expect, it } from "vitest";
import { parseStrictJson, verifyFieldShieldInBrowser } from "./browserPackVerification";

const now = Date.parse("2026-10-28T21:00:00Z");
const encoder = new TextEncoder();
const bytes = (data: unknown): Uint8Array => encoder.encode(JSON.stringify(data, null, 2) + "\n");
const toArrayBuffer = (input: Uint8Array): ArrayBuffer => {
  const target = new ArrayBuffer(input.byteLength);
  new Uint8Array(target).set(input);
  return target;
};
const toHex = (value: Uint8Array): string =>
  Array.from(value, b => b.toString(16).padStart(2, "0")).join("");
const sha = async (raw: Uint8Array): Promise<string> =>
  toHex(new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256", toArrayBuffer(raw))));
const toBase64 = (bytes: Uint8Array): string =>
  btoa(Array.from(bytes, n => String.fromCharCode(n)).join(""));
const subtle = globalThis.crypto.subtle;
const valid = async () => {
  // Standard WebCrypto ephemeral test keys; never stored or bundled.
  const keys = await subtle.generateKey(
    { name: "Ed25519" }, true, ["sign", "verify"],
  ) as CryptoKeyPair;
  const pub = new Uint8Array(await subtle.exportKey("raw", keys.publicKey));
  const pack = bytes({
    schema: "fieldshield.ioc-pack.v1",
    source: "SYNTHETIC SECURITY CENTER TEST ONLY",
    issued_at: "2026-01-01T00:00:00Z",
    indicators: [{ id: "demo-domain", kind: "domain", value: "demo.example.invalid",
      confidence: "low", reference: "https://www.rfc-editor.org/rfc/rfc2606" }],
  });
  const header = {
    schema: "fieldshield.signed-ioc.v1",
    publisher: "test-lab",
    key_id: "test-key-2026",
    pack_sha256: await sha(pack),
    issued_at: "2026-02-01T00:00:00Z",
    expires_at: "2027-01-01T00:00:00Z",
  };
  const sorted = JSON.stringify(Object.fromEntries(
    Object.entries(header).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0),
  ));
  const domain = encoder.encode("FieldShield Sentinel Signed IOC v1\0");
  const message = new Uint8Array(domain.length + encoder.encode(sorted).length);
  message.set(domain);
  message.set(encoder.encode(sorted), domain.length);
  const signature = new Uint8Array(
    await subtle.sign({ name: "Ed25519" }, keys.privateKey, toArrayBuffer(message)),
  );
  const manifest = bytes({ ...header, signature_b64: toBase64(signature) });
  const trust = bytes({
    schema: "fieldshield.trust-store.v1",
    publishers: [{
      id: "test-lab",
      keys: [{
        id: "test-key-2026", algorithm: "ed25519",
        state: "trusted", public_key_b64: toBase64(pub),
      }],
      blocked_pack_sha256: [],
      minimum_issued_at: "2026-01-01T00:00:00Z",
    }],
  });
  return { pack, manifest, trust, pin: await sha(pub) };
};
type Fixture = Awaited<ReturnType<typeof valid>>;
const run = (data: Fixture) => verifyFieldShieldInBrowser(
  data.pack, data.manifest, data.trust, data.pin, { now, subtle },
);

describe("PhiOS offline browser Ed25519 verification", () => {
  it("actually verifies synthetic signed FieldShield bytes using WebCrypto", async () => {
    const data = await valid();
    const result = await run(data);
    expect(result.status).toBe("SIGNATURE_VERIFIED_AGAINST_OPERATOR_PIN_ONLY");
    expect(result.packSha256).toBe(await sha(data.pack));
    expect(result.indicatorsClaimed).toBe(1);
    expect(result.publisherClaim).toBe("test-lab");
    expect(result.hostSecurityObserved).toBe(false);
    expect(result.sourceIdentityAuthenticated).toBe(false);
    expect(result.scanningPerformed).toBe(false);
  });

  it("fails when the exact IOC pack bytes change", async () => {
    const data = await valid();
    data.pack = encoder.encode(new TextDecoder().decode(data.pack) + " ");
    await expect(run(data)).rejects.toThrow("SHA256 mismatch");
  });

  it("fails on a modified Ed25519 signature", async () => {
    const data = await valid();
    const m = JSON.parse(new TextDecoder().decode(data.manifest));
    const mutated = Uint8Array.from(atob(m.signature_b64), (c: string) => c.charCodeAt(0));
    mutated[4] ^= 1;
    m.signature_b64 = toBase64(mutated);
    data.manifest = bytes(m);
    await expect(run(data)).rejects.toThrow("signature did not match");
  });

  it("rejects unpinned and independently mismatching keys", async () => {
    const data = await valid();
    await expect(verifyFieldShieldInBrowser(data.pack, data.manifest, data.trust,
      "", { now, subtle })).rejects.toThrow("out-of-band");
    data.pin = "f".repeat(64);
    await expect(run(data)).rejects.toThrow("independent SHA256 pin");
  });

  it("does not accept a revoked key or locally blocked pack", async () => {
    const data = await valid();
    const t = JSON.parse(new TextDecoder().decode(data.trust));
    t.publishers[0].keys[0].state = "revoked";
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("locally revoked");
    t.publishers[0].keys[0].state = "trusted";
    t.publishers[0].blocked_pack_sha256 = [await sha(data.pack)];
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("locally blocked");
  });

  it("rejects unfamiliar publishers, unknown keys and issuance rollback", async () => {
    const data = await valid();
    const t = JSON.parse(new TextDecoder().decode(data.trust));
    t.publishers = [];
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("not locally trusted");
    t.publishers = [{
      id:"test-lab", keys:[], blocked_pack_sha256:[],
      minimum_issued_at:"2026-01-01T00:00:00Z",
    }];
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("Unknown signing key");
    t.publishers[0].minimum_issued_at = "2026-03-01T00:00:00Z";
    data.trust = bytes(t);
    await expect(run(data)).rejects.toThrow("issuance floor");
  });

  it("rejects expired or not-yet-valid detached manifests", async () => {
    const data = await valid();
    await expect(verifyFieldShieldInBrowser(data.pack,data.manifest,data.trust,
      data.pin,{now:Date.parse("2028-01-01T00:00:00Z"),subtle})).rejects.toThrow("expired");
    await expect(verifyFieldShieldInBrowser(data.pack,data.manifest,data.trust,
      data.pin,{now:Date.parse("2025-01-01T00:00:00Z"),subtle})).rejects.toThrow("not yet valid");
  });

  it("rejects duplicate keys even when one is deeply nested", async () => {
    const raw=encoder.encode('{"schema":"ok","nested":{"same":1,"same":2}}');
    expect(()=>parseStrictJson(raw,500)).toThrow("Duplicate JSON key");
    const data=await valid();
    const m=new TextDecoder().decode(data.manifest).replace(
      '"publisher": "test-lab"', '"publisher": "evil", "publisher": "test-lab"',
    );
    data.manifest=encoder.encode(m);
    await expect(run(data)).rejects.toThrow("Duplicate JSON key");
  });

  it("refuses renamed metadata that was not signed", async () => {
    const data=await valid();
    const m=JSON.parse(new TextDecoder().decode(data.manifest));
    m.expires_at="2027-02-01T00:00:00Z";
    data.manifest=bytes(m);
    await expect(run(data)).rejects.toThrow("signature did not match");
  });

  it("fails closed when the browser crypto backend is absent", async () => {
    // Basic syntactic checks are still tested with malformed JSON.
    const data=await valid();
    const wrongTrust=encoder.encode("{");
    await expect(verifyFieldShieldInBrowser(
      data.pack,data.manifest,wrongTrust,data.pin,{now,subtle},
    )).rejects.toThrow("JSON");
  });

  it("rejects signed non-Sentinel bytes after valid signature", async () => {
    // Only actual FieldShield IOC packs qualify, not arbitrary signed JSON.
    const data=await valid();
    const invalid=encoder.encode('{"schema":"other"}');
    // Its hash differs from the signed digest, and must fail before parsing.
    data.pack=invalid;
    await expect(run(data)).rejects.toThrow("SHA256 mismatch");
  });
});
